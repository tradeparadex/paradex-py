#!/usr/bin/env -S uv run
"""
Block Trades — Seller

Creates block trades, lists offers, executes, checks status, and cancels.
Runs independently from the buyer script.

USAGE:
    # 1. Create a block trade (need the buyer's Starknet address)
    uv run scripts/block_trade/seller.py create \
        --market ETH-USD-PERP --side SELL --size 1 --price 1956 \
        --required-signer 0x<buyer_starknet_address>

    # 2. Check status
    uv run scripts/block_trade/seller.py status \
        --block-trade-id <id>

    # 3. List offers submitted by signers
    uv run scripts/block_trade/seller.py list-offers \
        --block-trade-id <id>

    # 4. Execute the block trade with collected offers
    uv run scripts/block_trade/seller.py execute \
        --block-trade-id <id>

    # 5. Cancel a block trade
    uv run scripts/block_trade/seller.py cancel \
        --block-trade-id <id>
"""

import argparse
import sys
import time
from decimal import Decimal
from pathlib import Path

# Allow importing common from the same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from paradex_py.api.generated.requests import (
    BlockExecuteRequest,
    BlockTradeInfo,
    BlockTradeRequest,
)
from paradex_py.api.generated.responses import (
    BlockTradeConstraints,
    BlockTradeSignature,
    SignatureType,
)
from paradex_py.common.order import Order
from paradex_py.common.order import OrderSide as CommonOrderSide
from paradex_py.common.order import OrderType as CommonOrderType
from paradex_py.message.block_trades import BlockTrade, Trade

from common import (
    build_trades_for_signing,
    create_and_sign_order,
    create_block_trade_order,
    create_paradex_client,
    get_starknet_account,
    logger,
    make_block_trade_signature,
)


# ── whoami ───────────────────────────────────────────────────────────────────


def cmd_whoami(args):
    client = create_paradex_client(args.account_index, args.env)
    account_address = get_starknet_account(client)
    logger.info(f"Starknet account: {account_address}")
    print(account_address)


# ── create ───────────────────────────────────────────────────────────────────


def cmd_create(args):
    client = create_paradex_client(args.account_index, args.env)
    account_address = get_starknet_account(client)
    logger.info(f"Seller account: {account_address}")

    current_time = int(time.time() * 1000)
    market = args.market
    side = args.side.upper()
    price = Decimal(args.price)
    size = Decimal(args.size)
    client_id = f"bt_maker_{current_time}"

    # 1. Create and sign the maker order
    order, order_signature = create_and_sign_order(
        client, market, side, price, size, client_id, current_time,
    )
    logger.info(f"Signed maker order: {side} {size} {market} @ {price}")

    # 2. Build the BlockTradeOrder for the API
    bt_order = create_block_trade_order(
        market, side, str(price), str(size), order_signature, client_id, current_time,
    )

    # 3. Build trade info with constraints (±5% of price)
    min_price = str(round(price * Decimal("0.95"), 2))
    max_price = str(round(price * Decimal("1.05"), 2))
    trade_info = BlockTradeInfo(
        maker_order=bt_order,
        price=str(price),
        size=str(size),
        taker_order=None,
        trade_constraints=BlockTradeConstraints(
            min_price=min_price,
            max_price=max_price,
            min_size=str(size),
            max_size=str(size * 5),
        ),
    )

    # 4. Required signers = seller + any extra signers passed on CLI
    required_signers = [account_address] + list(args.required_signer)
    logger.info(f"Required signers: {required_signers}")

    # 5. Build the unsigned request
    request = BlockTradeRequest(
        nonce=f"block_trade_{current_time}",
        required_signers=required_signers,
        signatures={},
        trades={market: trade_info},
        block_expiration=current_time + 5 * 60 * 1000,
    )

    # 6. Sign the block trade (typed data signature over the trades)
    trades_for_signing = build_trades_for_signing(order, price, size)
    bt_sig = make_block_trade_signature(client, trades_for_signing, account_address)
    request.signatures[account_address] = bt_sig

    # 7. Submit
    response = client.api_client.create_block_trade(request)
    block_trade_id = response.block_id
    logger.info(f"Block trade created: {block_trade_id}")
    print(block_trade_id)


# ── status ───────────────────────────────────────────────────────────────────


def cmd_status(args):
    client = create_paradex_client(args.account_index, args.env)
    response = client.api_client.get_block_trade(args.block_trade_id)

    logger.info(f"Block trade: {response.block_id}")
    logger.info(f"  Status:     {response.status}")
    logger.info(f"  Type:       {response.block_type}")
    logger.info(f"  Initiator:  {response.initiator}")
    logger.info(f"  Signers:    {response.required_signers}")
    logger.info(f"  Expires:    {response.block_expiration}")
    if response.trades:
        for market, detail in response.trades.items():
            side = detail.maker_order.side if detail.maker_order else "?"
            logger.info(f"  Trade {market}: {side} {detail.size} @ {detail.price}")


# ── list-offers ──────────────────────────────────────────────────────────────


def cmd_list_offers(args):
    client = create_paradex_client(args.account_index, args.env)
    response = client.api_client.get_block_trade_offers(args.block_trade_id)
    results = response.results or []

    if not results:
        logger.info("No offers found.")
        return

    logger.info(f"Found {len(results)} offer(s):")
    for i, offer in enumerate(results, 1):
        offer_id = offer.get("block_id") or offer.get("id", "?")
        status = offer.get("status", "?")
        trades = offer.get("trades", {})
        markets = ", ".join(trades.keys()) if trades else "?"
        logger.info(f"  [{i}] {offer_id}  status={status}  markets={markets}")
        print(offer_id)


# ── execute ──────────────────────────────────────────────────────────────────


def cmd_execute(args):
    client = create_paradex_client(args.account_index, args.env)
    account_address = get_starknet_account(client)

    # Collect offers
    offers_response = client.api_client.get_block_trade_offers(args.block_trade_id)
    offers = offers_response.results or []
    if not offers:
        logger.error("No offers to execute.")
        return

    offer_ids = [o.get("block_id") or o.get("id") for o in offers]
    logger.info(f"Executing with {len(offer_ids)} offer(s): {offer_ids}")

    current_time = int(time.time() * 1000)
    expiration = current_time + 5 * 60 * 1000
    signatures: dict[str, BlockTradeSignature] = {}

    for offer_id, offer in zip(offer_ids, offers, strict=False):
        offer_trades_data = offer.get("trades", {})
        trade_objects: list[Trade] = []

        for market_symbol, info in offer_trades_data.items():
            offerer_order = info.get("offerer_order", {})
            offer_price = Decimal(info.get("price", "0"))
            offer_size = Decimal(info.get("size", "0"))

            maker_order = Order(
                market=market_symbol,
                order_type=CommonOrderType.Limit,
                order_side=(
                    CommonOrderSide.Buy
                    if offerer_order.get("side") == "BUY"
                    else CommonOrderSide.Sell
                ),
                size=offer_size,
                limit_price=offer_price,
                client_id=offerer_order.get("client_id", f"exec_{current_time}"),
                signature_timestamp=current_time,
                instruction="GTC",
            )
            taker_order = Order(
                market=market_symbol,
                order_type=CommonOrderType.Limit,
                order_side=(
                    CommonOrderSide.Sell
                    if offerer_order.get("side") == "BUY"
                    else CommonOrderSide.Buy
                ),
                size=offer_size,
                limit_price=offer_price,
                client_id=f"taker_{current_time}",
                signature_timestamp=current_time,
                instruction="GTC",
            )
            trade_objects.append(Trade(
                price=offer_price,
                size=offer_size,
                maker_order=maker_order,
                taker_order=taker_order,
            ))

        if not trade_objects:
            continue

        bt = BlockTrade(version="1.0", trades=trade_objects)
        sig_data = client.account.sign_block_trade(bt)
        signatures[offer_id] = BlockTradeSignature(
            nonce=f"exec_{offer_id}_{current_time}",
            signature_data=sig_data,
            signature_expiration=expiration,
            signature_timestamp=current_time,
            signature_type=SignatureType.starknet,
            signer_account=account_address,
        )
        logger.info(f"Signed offer {offer_id} for execution")

    execute_request = BlockExecuteRequest(
        execution_nonce=f"execute_{current_time}",
        selected_offers=offer_ids,
        signatures=signatures,
    )
    response = client.api_client.execute_block_trade(args.block_trade_id, execute_request)
    logger.info(f"Execution result: {response.status}")


# ── cancel ───────────────────────────────────────────────────────────────────


def cmd_cancel(args):
    client = create_paradex_client(args.account_index, args.env)
    client.api_client.cancel_block_trade(args.block_trade_id)
    logger.info(f"Cancelled block trade {args.block_trade_id}")


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Block Trades — Seller")
    parser.add_argument("--account-index", type=int, default=0, help="Account index in test_accounts.json (default: 0)")
    parser.add_argument("--env", default="testnet", choices=["prod", "testnet", "nightly"], help="Paradex environment (default: testnet)")
    sub = parser.add_subparsers(dest="command", required=True)

    # whoami
    sub.add_parser("whoami", help="Print your Starknet account address")

    # create
    p_create = sub.add_parser("create", help="Create a new block trade")
    p_create.add_argument("--market", required=True, help="Market symbol, e.g. ETH-USD-PERP")
    p_create.add_argument("--side", required=True, choices=["BUY", "SELL"], help="Maker order side")
    p_create.add_argument("--size", required=True, help="Order size, e.g. 1")
    p_create.add_argument("--price", required=True, help="Order price, e.g. 1956")
    p_create.add_argument(
        "--required-signer", action="append", default=[],
        help="Starknet address of a required signer (repeatable). Use buyer's 'whoami' to get this.",
    )

    # status
    p_status = sub.add_parser("status", help="Check block trade status")
    p_status.add_argument("--block-trade-id", required=True)

    # list-offers
    p_offers = sub.add_parser("list-offers", help="List offers for a block trade")
    p_offers.add_argument("--block-trade-id", required=True)

    # execute
    p_exec = sub.add_parser("execute", help="Execute block trade with all available offers")
    p_exec.add_argument("--block-trade-id", required=True)

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel a block trade")
    p_cancel.add_argument("--block-trade-id", required=True)

    args = parser.parse_args()
    {
        "whoami": cmd_whoami,
        "create": cmd_create,
        "status": cmd_status,
        "list-offers": cmd_list_offers,
        "execute": cmd_execute,
        "cancel": cmd_cancel,
    }[args.command](args)


if __name__ == "__main__":
    main()
