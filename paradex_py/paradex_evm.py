import logging
import secrets
from typing import TYPE_CHECKING

from starknet_py.net.signer.stark_curve_signer import KeyPair

from paradex_py._client_base import _ClientBase
from paradex_py.account.evm_account import EvmAccount
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
    ):
        _validate_env(env, "ParadexEvm")

        if not evm_address:
            raise_value_error(f"ParadexEvm: EVM address is required, got {evm_address!r}")
        if not evm_private_key:
            raise_value_error("ParadexEvm: EVM private key is required")

        self.env = env
        self.logger: logging.Logger = logger or logging.getLogger(__name__)

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

        self.account = EvmAccount(
            config=self.config,
            env=env,
            evm_address=evm_address,
            evm_private_key=evm_private_key,
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
