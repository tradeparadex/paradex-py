"""Paradex Python SDK.

Choose the right client class for your use-case:

+------------------+------------------+---------+-----------+---------+------------------+
| Class            | Credentials      | Trade   | Withdraw  | Auth    | Typical use-case |
+==================+==================+=========+===========+=========+==================+
| Paradex          | L1 private key   | yes     | yes       | FULL    | Full account via |
|                  | (or Ledger)      |         |           |         | L1 key           |
+------------------+------------------+---------+-----------+---------+------------------+
| ParadexL2        | L2 private key   | yes     | yes       | FULL    | Full account via |
|                  | + L2 address     |         |           |         | L2 key directly  |
+------------------+------------------+---------+-----------+---------+------------------+
| ParadexSubkey    | L2 subkey        | yes     | no        | TRADING | Registered       |
|                  | + main L2 addr   |         |           |         | trade-scoped key |
+------------------+------------------+---------+-----------+---------+------------------+
| ParadexEvm       | EVM private key  | no      | no        | AUTH    | EVM wallet;      |
|                  |                  |         |           |         | manage subkeys   |
+------------------+------------------+---------+-----------+---------+------------------+
| ParadexApiKey    | Pre-generated    | no      | no        | AUTH    | Read-only /      |
|                  | API token        |         |           |         | server-side apps |
+------------------+------------------+---------+-----------+---------+------------------+
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
