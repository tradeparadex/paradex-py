import logging
import secrets
from typing import TYPE_CHECKING

from eth_account import Account as EthAccount
from starknet_py.net.signer.key_pair import KeyPair

from paradex_py._client_base import _ClientBase
from paradex_py.account.evm_account import EvmAccount
from paradex_py.account.utils import derive_l2_address_eip191
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
    ):
        _validate_env(env, "ParadexEvm")

        if not evm_address:
            raise_value_error(f"ParadexEvm: EVM address is required, got {evm_address!r}")
        if not evm_private_key:
            raise_value_error("ParadexEvm: EVM private key is required")

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
        is_onboarded: bool | None = None
        if server_derive_address:
            info = self.api_client.fetch_onboarding(
                {
                    "account_signer_type": "eip191",
                    "eth_address": checksum_address,
                }
            )
            l2_address_hex: str = info["address"]
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
        construction, ``None`` otherwise (local derivation path)."""
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
