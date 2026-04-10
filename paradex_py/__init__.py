"""Paradex Python SDK.

Choose the right client class for your use-case:

+------------------+------------------+---------+-----------+---------+--------------------------------+
| Class            | Credentials      | Trade   | Withdraw  | Auth    | Typical use-case               |
+==================+==================+=========+===========+=========+================================+
| Paradex          | L1 private key   | yes     | yes       | FULL    | Full account via L1 key        |
|                  | (or Ledger)      |         |           |         |                                |
+------------------+------------------+---------+-----------+---------+--------------------------------+
| ParadexL2        | L2 private key   | yes     | yes       | FULL    | Full account via L2 key        |
|                  | + L2 address     |         |           |         |                                |
+------------------+------------------+---------+-----------+---------+--------------------------------+
| ParadexEvm       | EVM private key  | no [1]  | yes       | FULL    | EVM wallet; full L2 account    |
|                  |                  |         |           |         | (contract keyed to EVM pubkey) |
+------------------+------------------+---------+-----------+---------+--------------------------------+
| ParadexSubkey    | L2 subkey        | yes     | no        | TRADING | Registered trade-scoped key    |
|                  | + main L2 addr   |         |           |         |                                |
+------------------+------------------+---------+-----------+---------+--------------------------------+
| ParadexApiKey    | Pre-generated    | no      | no        | AUTH    | Read-only / server-side apps   |
|                  | API token        |         |           |         |                                |
+------------------+------------------+---------+-----------+---------+--------------------------------+

[1] Order signing requires a registered Starknet subkey.
    Call ``evm.create_trading_subkey()`` to generate one and get a ready-to-trade client.
"""

from .auth_level import AuthLevel
from .environment import NIGHTLY, PROD, TESTNET, Environment
from .paradex import Paradex
from .paradex_api_key import ParadexApiKey
from .paradex_evm import ParadexEvm
from .paradex_l2 import ParadexL2
from .paradex_subkey import ParadexSubkey

__all__ = [
    "AuthLevel",
    "Environment",
    "NIGHTLY",
    "PROD",
    "TESTNET",
    "Paradex",
    "ParadexApiKey",
    "ParadexEvm",
    "ParadexL2",
    "ParadexSubkey",
]
