import logging
import secrets
from typing import TYPE_CHECKING

from eth_account import Account as EthAccount
from starknet_py.net.signer.key_pair import KeyPair

from paradex_py._client_base import _ClientBase
from paradex_py.account.evm_account import EvmAccount
from paradex_py.account.utils import (
    derive_l2_address_eip191,
    derive_vault_operator_l2_address_eip191,
)
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.auth_level import AuthLevel
from paradex_py.environment import Environment, _validate_env
from paradex_py.utils import raise_value_error

if TYPE_CHECKING:
    from paradex_py.paradex_subkey import ParadexSubkey

__all__ = ["ParadexEvm"]


class ParadexEvm(_ClientBase):
    """Paradex client authenticated via EVM (Ethereum) key using SIWE (ERC-4361).

    The Starknet address is derived deterministically from the EVM address.
    This client provides ``AuthLevel.AUTHENTICATED`` — it can call all
    authenticated REST endpoints but cannot sign orders directly (no Starknet
    signing key). For trading, register a subkey with :meth:`api_client.create_subkey`
    and use :class:`~paradex_py.ParadexSubkey`.

    Args:
        env (Environment): Environment
        evm_address (str): Ethereum address (checksummed or lowercase hex).
        evm_private_key (str): Ethereum private key (hex string with 0x prefix).
        logger (logging.Logger, optional): Logger. Defaults to None.
        ws_timeout (int, optional): WebSocket read timeout in seconds. Defaults to None.
        ws_enabled (bool, optional): Whether to create a WebSocket client. Defaults to True.
            Set to False for REST-only use cases.
        ws_sbe_enabled (bool, optional): Enable SBE encoding on WebSocket. Defaults to False.
        server_derive_address (bool, optional): When True, fetch the L2 address from
            ``GET /onboarding`` (signer type ``eip191``) instead of deriving it locally from
            ``paraclear_evm_account_hash``. Also caches the ``exists`` flag so
            ``POST /v2/onboarding`` is skipped when the account is already onboarded. Defaults
            to False (local derivation path unchanged).
        vault_operator_address (str, optional): Authenticate *as* this EVM vault
            operator sub-account instead of the key's own main account. The SIWE
            message is still signed by ``evm_private_key`` (operators have no key of
            their own), but the session targets the operator: the JWT's ``sub`` is the
            operator address, so subkeys registered in this session belong to the
            operator and :meth:`create_trading_subkey` returns a client that trades
            the vault. The operator must already exist (it is created by vault
            creation with ``operator_signer_type=eip191``). Mutually exclusive with
            ``vault_operator_index``.
        vault_operator_index (int, optional): Like ``vault_operator_address``, but
            resolves the operator's address from its index: server-side via
            ``GET /onboarding?vault_operator_index=N`` when
            ``server_derive_address=True``, locally otherwise. Index N is the N-th
            eip191 vault operator of this EVM key's main account (0-based, allocated
            at vault creation). Mutually exclusive with ``vault_operator_address``.

    Examples:
        >>> from paradex_py import ParadexEvm
        >>> from paradex_py.environment import Environment
        >>> paradex = ParadexEvm(
        ...     env=Environment.TESTNET,
        ...     evm_address="0x...",
        ...     evm_private_key="0x...",
        ... )
        >>> paradex.api_client.fetch_balances()
        >>> # List and create subkeys
        >>> paradex.api_client.fetch_subkeys()
        >>> paradex.api_client.create_subkey({
        ...     "name": "trading-bot",
        ...     "public_key": "0x...",
        ...     "state": "active",
        ... })
        >>> # Trade a vault as its EVM operator (owner key, operator target)
        >>> operator = ParadexEvm(
        ...     env=Environment.TESTNET,
        ...     evm_address="0x...",
        ...     evm_private_key="0x...",
        ...     vault_operator_index=0,
        ... )
        >>> subkey = operator.create_trading_subkey()
        >>> subkey.api_client.submit_order(order=buy_order)
    """

    def __init__(
        self,
        env: Environment,
        evm_address: str,
        evm_private_key: str,
        logger: logging.Logger | None = None,
        ws_timeout: int | None = None,
        ws_enabled: bool = True,
        ws_sbe_enabled: bool = False,
        server_derive_address: bool = False,
        vault_operator_address: str | None = None,
        vault_operator_index: int | None = None,
    ):
        _validate_env(env, "ParadexEvm")

        if not evm_address:
            raise_value_error(f"ParadexEvm: EVM address is required, got {evm_address!r}")
        if not evm_private_key:
            raise_value_error("ParadexEvm: EVM private key is required")
        if vault_operator_address is not None and vault_operator_index is not None:
            raise_value_error(
                "ParadexEvm: vault_operator_address and vault_operator_index are mutually exclusive — pass at most one"
            )

        self.env = env
        self.logger: logging.Logger = logger or logging.getLogger(__name__)
        self.server_derive_address = server_derive_address

        self.api_client = ParadexApiClient(env=env, logger=logger)
        self.ws_client: ParadexWebsocketClient | None = (
            ParadexWebsocketClient(
                env=env,
                logger=logger,
                ws_timeout=ws_timeout,
                api_client=self.api_client,
                sbe_enabled=ws_sbe_enabled,
            )
            if ws_enabled
            else None
        )
        self.config = self.api_client.fetch_system_config()

        # Derive the L2 address outside the EvmAccount constructor — either from the
        # server (GET /onboarding) or from the shared local helper. Both paths converge
        # to a single downstream EvmAccount(...) call with a pre-resolved address.
        # `EthAccount.from_key(...)` normalises the address to checksum format, which is
        # what both the ``/onboarding`` endpoint and the local derivation helper expect.
        checksum_address = EthAccount.from_key(evm_private_key).address
        is_vault_operator = vault_operator_address is not None or vault_operator_index is not None
        is_onboarded: bool | None = None
        if is_vault_operator:
            # Operator sessions authenticate as the operator's L2 address while
            # signing SIWE with the owner's key. Operators are onboarded by vault
            # creation, never by POST /v2/onboarding, so is_onboarded=True skips
            # the auto-onboarding path and goes straight to POST /v2/auth.
            if vault_operator_address is not None:
                l2_address_hex = vault_operator_address
            elif server_derive_address:
                info = self.api_client.fetch_onboarding(
                    {
                        "account_signer_type": "eip191",
                        "eth_address": checksum_address,
                        "vault_operator_index": vault_operator_index,
                    }
                )
                l2_address_hex = info["address"]
                if info.get("exists") is False:
                    raise_value_error(
                        f"ParadexEvm: vault operator index {vault_operator_index} "
                        f"({l2_address_hex}) does not exist yet — operators are created "
                        "by vault creation with operator_signer_type=eip191"
                    )
                # A server that predates EVM vault operators ignores the unknown
                # vault_operator_index query param and answers for the OWNER's
                # main account. Never let an "operator" session silently target
                # the main account.
                if int(l2_address_hex, 16) == derive_l2_address_eip191(self.config, checksum_address):
                    raise_value_error(
                        "ParadexEvm: GET /onboarding returned the owner's main account "
                        f"for vault_operator_index={vault_operator_index} — this server "
                        "does not support EVM vault operators (feature flag off or "
                        "pre-feature deployment)"
                    )
            else:
                if vault_operator_index is None:
                    # Unreachable: is_vault_operator with no address implies an
                    # index. The explicit check narrows the type for ty.
                    raise_value_error("ParadexEvm: vault operator session requires an index")
                l2_address_hex = hex(
                    derive_vault_operator_l2_address_eip191(self.config, checksum_address, vault_operator_index)
                )
            is_onboarded = True
        elif server_derive_address:
            info = self.api_client.fetch_onboarding(
                {
                    "account_signer_type": "eip191",
                    "eth_address": checksum_address,
                }
            )
            l2_address_hex = info["address"]
            exists = info.get("exists")
            is_onboarded = bool(exists) if exists is not None else None
        else:
            l2_address_hex = hex(derive_l2_address_eip191(self.config, checksum_address))

        self.account = EvmAccount(
            config=self.config,
            env=env,
            evm_address=evm_address,
            evm_private_key=evm_private_key,
            l2_address=l2_address_hex,
            is_onboarded=is_onboarded,
            is_vault_operator=is_vault_operator,
        )

        self.api_client.init_account_evm(self.account)

    @property
    def auth_level(self) -> AuthLevel:
        """``AuthLevel.FULL`` — full L2 account; deposits and withdrawals supported."""
        return AuthLevel.FULL

    @property
    def is_authenticated(self) -> bool:
        """Always ``True`` — credentials were provided at construction."""
        return True

    @property
    def can_trade(self) -> bool:
        """Always ``False`` — order signing requires a registered Starknet subkey.
        Use :meth:`create_trading_subkey` to generate one."""
        return False

    @property
    def can_withdraw(self) -> bool:
        """Always ``True`` — the L2 account is owned by the EVM key; on-chain
        operations (deposit, withdraw, transfer) are supported."""
        return True

    @property
    def is_onboarded(self) -> bool | None:
        """Cached onboarding state from ``GET /onboarding``.

        Returns ``True`` / ``False`` when ``server_derive_address=True`` populated the cache at
        construction, ``None`` otherwise (local derivation path). Vault operator
        sessions always report ``True`` — it means "skip auto-onboarding"
        (operators are onboarded by vault creation), not "existence verified";
        a nonexistent operator fails at auth."""
        return self.account.is_onboarded if self.account is not None else None

    def create_trading_subkey(self, name: str = "trading") -> "ParadexSubkey":
        """Generate a fresh Starknet subkey, register it, and return a ready-to-trade client.

        This is the recommended way to enable trading from an EVM-authenticated account.
        The generated private key is ephemeral — save it if you need to reuse the subkey
        across sessions.

        Args:
            name (str): Human-readable label for the subkey. Defaults to ``"trading"``.

        Returns:
            ParadexSubkey: Authenticated client signed with the new subkey.

        Examples:
            >>> evm = ParadexEvm(env=TESTNET, evm_address="0x...", evm_private_key="0x...")
            >>> subkey = evm.create_trading_subkey()
            >>> subkey.api_client.submit_order(order=buy_order)
        """
        from paradex_py.paradex_subkey import ParadexSubkey

        l2_private_key_int = secrets.randbelow(2**251)
        key_pair = KeyPair.from_private_key(l2_private_key_int)
        self.api_client.create_subkey(
            {
                "name": name,
                "public_key": hex(key_pair.public_key),
                "state": "active",
            }
        )
        return ParadexSubkey(
            env=self.env,
            l2_private_key=hex(l2_private_key_int),
            l2_address=hex(self.account.l2_address),
        )
