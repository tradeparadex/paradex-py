"""Paradex Python SDK.

Choose the right client class for your use-case:

+------------------+------------------+---------+-----------+--------+------------------+
| Class            | Credentials      | Trade   | Withdraw  | Auth   | Typical use-case |
+==================+==================+=========+===========+========+==================+
| Paradex          | L1 private key   | yes     | yes       | FULL   | Full account via |
|                  | (or Ledger)      |         |           |        | L1 key           |
+------------------+------------------+---------+-----------+--------+------------------+
| ParadexL2        | L2 private key   | yes     | yes       | FULL   | Full account via |
|                  | + L2 address     |         |           |        | L2 key directly  |
+------------------+------------------+---------+-----------+--------+------------------+
| ParadexSubkey    | L2 subkey        | yes     | no        | TRADING| Registered       |
|                  | + main L2 addr   |         |           |        | trade-scoped key |
+------------------+------------------+---------+-----------+--------+------------------+
| ParadexApiKey    | Pre-generated    | no      | no        | AUTH   | Read-only /      |
|                  | API token        |         |           |        | server-side apps |
+------------------+------------------+---------+-----------+--------+------------------+
"""
