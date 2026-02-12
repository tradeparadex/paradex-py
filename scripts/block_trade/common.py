"""Shared utilities for block trade scripts (seller and buyer)."""

import json
import logging
import time
from decimal import Decimal
from pathlib import Path

from paradex_py import Paradex
from paradex_py.api.generated.responses import (
    BlockTradeOrder,
    BlockTradeSignature,
    OrderSide,
    OrderType,
    SignatureType,
)
from paradex_py.common.order import Order
from paradex_py.common.order import OrderSide as CommonOrderSide
from paradex_py.common.order import OrderType as CommonOrderType
from paradex_py.message.block_trades import BlockTrade, Trade

DEFAULT_ENVIRONMENT = "nightly"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("block_trades")


def load_test_accounts(accounts_file: str = "test_accounts.json"):
    """Load test accounts from JSON file."""
    path = Path(accounts_file)
    if not path.exists():
        raise FileNotFoundError(
            f"{accounts_file} not found. Run generate_test_keys.py first."
        )
    with open(path) as f:
        return json.load(f)


def create_paradex_client(account_index: int = 0, env: str = DEFAULT_ENVIRONMENT) -> Paradex:
    """Create a Paradex client for the account at the given index."""
    accounts = load_test_accounts()
    if account_index >= len(accounts):
        raise IndexError(f"Account index {account_index} out of range (have {len(accounts)} accounts)")
    account = accounts[account_index]
    client = Paradex(
        env=env,
        l1_address=account["l1_address"],
        l1_private_key=account["l1_private_key"],
    )
    logger.info(f"Created client for account {account_index}: {account['l1_address']}")
    return client


def get_starknet_account(client: Paradex) -> str:
    """Get the Starknet account address for a client."""
    summary = client.api_client.fetch_account_summary()
    return summary.account


def create_and_sign_order(
    client: Paradex,
    market: str,
    side: str,
    price: Decimal,
    size: Decimal,
    client_id: str,
    timestamp: int,
) -> tuple[Order, str]:
    """Create an Order and sign it, returning both the Order object and signature string."""
    order_side = CommonOrderSide.Buy if side.upper() == "BUY" else CommonOrderSide.Sell
    order = Order(
        market=market,
        order_type=CommonOrderType.Limit,
        order_side=order_side,
        size=size,
        limit_price=price,
        client_id=client_id,
        signature_timestamp=timestamp,
        instruction="GTC",
    )
    signature = client.account.sign_order(order)
    return order, signature


def create_block_trade_order(
    market: str,
    side: str,
    price: str,
    size: str,
    signature: str,
    client_id: str,
    timestamp: int,
) -> BlockTradeOrder:
    """Create a BlockTradeOrder (the API model) from order parameters."""
    order_side = OrderSide.order_side_buy if side.upper() == "BUY" else OrderSide.order_side_sell
    return BlockTradeOrder(
        client_id=client_id,
        market=market,
        price=price,
        side=order_side,
        signature=signature,
        signature_timestamp=timestamp,
        size=size,
        type=OrderType.order_type_limit,
    )


def build_trades_for_signing(
    order: Order,
    price: Decimal,
    size: Decimal,
) -> list[Trade]:
    """Build a list of Trade objects suitable for BlockTrade signing.

    Uses the same order for both maker and taker during initial creation/offer signing.
    """
    return [
        Trade(
            price=price,
            size=size,
            maker_order=order,
            taker_order=order,
        )
    ]


def make_block_trade_signature(
    client: Paradex,
    trades: list[Trade],
    signer_account: str,
    sign_fn: str = "sign_block_trade",
) -> BlockTradeSignature:
    """Create and sign a BlockTrade, returning a BlockTradeSignature.

    Args:
        client: Paradex client with account credentials.
        trades: List of Trade objects to sign.
        signer_account: Starknet account address of the signer.
        sign_fn: "sign_block_trade" or "sign_block_offer".
    """
    bt = BlockTrade(version="1.0", trades=trades)

    if sign_fn == "sign_block_offer":
        signature_data = client.account.sign_block_offer(bt)
    else:
        signature_data = client.account.sign_block_trade(bt)

    current_time = int(time.time() * 1000)
    return BlockTradeSignature(
        nonce=f"sig_{current_time}",
        signature_data=signature_data,
        signature_expiration=current_time + 5 * 60 * 1000,
        signature_timestamp=current_time,
        signature_type=SignatureType.starknet,
        signer_account=signer_account,
    )


def opposite_side(side: str) -> str:
    """Return the opposite order side."""
    if side.upper() in ("BUY", "ORDER_SIDE_BUY"):
        return "SELL"
    return "BUY"
