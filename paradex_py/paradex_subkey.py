from paradex_py.auth_level import AuthLevel
from paradex_py.paradex_l2 import ParadexL2

__all__ = ["ParadexSubkey"]


class ParadexSubkey(ParadexL2):
    """Registered subkey authentication — trade-scoped subclass of ParadexL2
    with trade-scoped capabilities (no withdrawals).

    Subkeys are registered signing keys scoped to order management only.
    Use ``ParadexL2`` directly when authenticating with a main account key.

    Args:
        env (Environment): Environment
        l2_private_key (str): The subkey's L2 private key (required)
        l2_address (str): The *main account* address this subkey is registered under.
            This is **not** the subkey's own derived address — it must be the address
            of the parent account that registered this subkey.
        logger (logging.Logger, optional): Logger. Defaults to None.
        ws_timeout (int, optional): WebSocket read timeout in seconds. Defaults to None.
        ws_enabled (bool, optional): Whether to create a WebSocket client. Defaults to True.

    Examples:
        >>> from paradex_py import ParadexSubkey
        >>> from paradex_py.environment import TESTNET
        >>> paradex = ParadexSubkey(
        ...     env=TESTNET,
        ...     l2_private_key="0x<subkey-private-key>",
        ...     l2_address="0x<main-account-address>",  # parent account, not subkey address
        ... )
        >>> paradex.can_trade
        True
        >>> paradex.can_withdraw
        False
    """

    @property
    def auth_level(self) -> AuthLevel:
        """``AuthLevel.TRADING`` — subkey can sign orders but not withdrawals."""
        return AuthLevel.TRADING

    @property
    def can_withdraw(self) -> bool:
        """Always ``False`` — subkeys can only sign orders; direct on-chain operations
        (deposit, withdraw, transfer) require the full account key."""
        return False
