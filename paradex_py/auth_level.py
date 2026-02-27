from enum import IntEnum

__all__ = ["AuthLevel"]


class AuthLevel(IntEnum):
    """Capability tier of a Paradex client instance.

    Designed for integer comparison so MCP tool guards can use ``>=``:

    Examples:
        >>> if client.auth_level >= AuthLevel.AUTHENTICATED:
        ...     # allow account-read tools (positions, fills, balances)
        >>> if client.auth_level >= AuthLevel.TRADING:
        ...     # allow order-write tools (create, cancel)
        >>> if client.auth_level >= AuthLevel.FULL:
        ...     # allow withdrawal / transfer tools
    """

    UNAUTHENTICATED = 0
    """No credentials — public market/system data only."""

    AUTHENTICATED = 1
    """Token present, but no signing key.
    Can read private account data (positions, fills, balances).
    Cannot sign or submit orders.
    Typical for ``ParadexApiKey``."""

    TRADING = 2
    """Registered subkey — can sign and submit orders only.
    Cannot perform direct on-chain operations (deposit, withdraw, transfer).
    Typical for ``ParadexSubkey``."""

    FULL = 3
    """Full L2 account key — unrestricted access: order signing + all direct on-chain
    operations (deposit, withdraw, transfer).
    Typical for ``ParadexL2`` (main account key) and ``Paradex`` (L1-derived key)."""
