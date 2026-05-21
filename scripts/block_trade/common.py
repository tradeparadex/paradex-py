"""Shared bits for the block-trade CLI scripts.

Most signing/typed-data plumbing lives in `paradex_py.account.account` and
`paradex_py.message.block_trades` — these helpers just load test accounts,
construct the Paradex client, and provide the two small adapters needed to
convert between the request-side `BlockTradeOrder` DTO and the signing-side
`BlockTradeOrder` struct.
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import cast

# examples/utils.py provides the standard get_logger() — make it importable
# regardless of cwd by adding the repo root to sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from examples.utils import get_logger  # noqa: E402
from paradex_py import Paradex  # noqa: E402
from paradex_py.account.account import ParadexAccount  # noqa: E402
from paradex_py.api.generated.responses import BlockTradeOrder as BlockTradeOrderDTO  # noqa: E402
from paradex_py.api.generated.responses import OrderSide as DTOOrderSide  # noqa: E402
from paradex_py.api.generated.responses import OrderType as DTOOrderType  # noqa: E402
from paradex_py.environment import Environment  # noqa: E402

logger = get_logger("block_trade")


def load_test_accounts(path: str = "test_accounts.json") -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{path} not found. Run generate_test_keys.py first.")
    with open(p) as f:
        return json.load(f)


def create_paradex_client(account_index: int, env: str) -> tuple[Paradex, ParadexAccount, str]:
    """Return (client, account, account_address_hex). The account is guaranteed non-None."""
    accounts = load_test_accounts()
    if account_index >= len(accounts):
        raise IndexError(f"account_index {account_index} out of range (have {len(accounts)} accounts)")
    a = accounts[account_index]
    client = Paradex(env=cast(Environment, env), l1_address=a["l1_address"], l1_private_key=a["l1_private_key"])
    if client.account is None:
        raise RuntimeError("Paradex client was constructed without an account.")
    address = hex(client.account.l2_address)
    logger.info(f"Created client for account {account_index}: {a['l1_address']} (L2 {address})")
    return client, client.account, address


def add_global_args(parser: argparse.ArgumentParser, default_account_index: int) -> None:
    parser.add_argument("--account-index", type=int, default=default_account_index)
    parser.add_argument("--env", default="testnet", choices=["prod", "testnet", "nightly"])


def dto_order(account: str, side: str, price: Decimal, size: Decimal) -> BlockTradeOrderDTO:
    """Build the request-side BlockTradeOrder DTO."""
    return BlockTradeOrderDTO(
        account=account,
        side=DTOOrderSide.order_side_buy if side == "BUY" else DTOOrderSide.order_side_sell,
        type=DTOOrderType.order_type_limit,
        price=str(price),
        size=str(size),
    )
