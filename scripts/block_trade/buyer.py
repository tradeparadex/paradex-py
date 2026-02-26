#!/usr/bin/env -S uv run
"""
Block Trades — Buyer

Submits offers to existing block trades and cancels them.
Runs independently from the seller script.

USAGE:
    # 0. Print your Starknet address (give this to the seller)
    uv run scripts/block_trade/buyer.py whoami

    # 1. Submit an offer to an existing block trade
    #    (auto-detects opposite side, matches price/size from the block trade)
    uv run scripts/block_trade/buyer.py offer \
        --block-trade-id <id>

    # 1b. Override price and/or size
    uv run scripts/block_trade/buyer.py offer \
        --block-trade-id <id> --price 1956 --size 1

    # 2. Cancel an offer
    uv run scripts/block_trade/buyer.py cancel \
        --block-trade-id <id> --offer-id <offer_id>
"""

import argparse
import sys
import time
from decimal import Decimal
from pathlib import Path

# Allow importing common from the same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from paradex_py.api.generated.requests import (
    BlockOfferInfo,
    BlockOfferRequest,
)

from common import (
    build_trades_for_signing,
    create_and_sign_order,
    create_block_trade_order,
    create_paradex_client,
    get_starknet_account,
    logger,
    make_block_trade_signature,
    opposite_side,
)


# ── whoami ───────────────────────────────────────────────────────────────────


def cmd_whoami(args):
    client = create_paradex_client(args.account_index, args.env)
    account_address = get_starknet_account(client)
    logger.info(f"Starknet account: {account_address}")
    print(account_address)


# ── offer ────────────────────────────────────────────────────────────────────


def cmd_offer(args):
    client = create_paradex_client(args.account_index, args.env)
    account_address = get_starknet_account(client)
    logger.info(f"Buyer account: {account_address}")

    # Fetch block trade details to understand what we're responding to
    bt = client.api_client.get_block_trade(args.block_trade_id)
    if not bt.trades:
        logger.error("Block trade has no trades defined.")
        return

    logger.info(f"Block trade {bt.block_id} — status={bt.status}")

    current_time = int(time.time() * 1000)
    offer_trades: dict[str, BlockOfferInfo] = {}
    all_trades_for_signing = []

    for market_symbol, detail in bt.trades.items():
        # Determine the side the buyer should take (opposite of maker)
        maker_side_str = "BUY"
        if detail.maker_order and detail.maker_order.side:
            maker_side_str = detail.maker_order.side.value
        buyer_side = opposite_side(maker_side_str)

        # Use CLI overrides if provided, otherwise match the block trade
        price = Decimal(args.price) if args.price else Decimal(detail.price or "0")
        size = Decimal(args.size) if args.size else Decimal(detail.size or "0")

        logger.info(f"  {market_symbol}: {buyer_side} {size} @ {price}")

        client_id = f"offer_{current_time}_{market_symbol}"

        # Sign the individual order
        order, order_signature = create_and_sign_order(
            client, market_symbol, buyer_side, price, size, client_id, current_time,
        )

        # Build the BlockTradeOrder for the API payload
        bt_order = create_block_trade_order(
            market_symbol, buyer_side, str(price), str(size),
            order_signature, client_id, current_time,
        )

        offer_trades[market_symbol] = BlockOfferInfo(
            offerer_order=bt_order,
            price=str(price),
            size=str(size),
        )

        # Accumulate trades for the block-level signature
        all_trades_for_signing.extend(build_trades_for_signing(order, price, size))

    if not offer_trades:
        logger.error("No valid trades to offer.")
        return

    # Sign the block offer (typed data over all trades)
    offer_sig = make_block_trade_signature(
        client, all_trades_for_signing, account_address, sign_fn="sign_block_offer",
    )

    # Build and submit the offer request
    request = BlockOfferRequest(
        nonce=f"offer_{current_time}",
        offering_account=account_address,
        signature=offer_sig,
        trades=offer_trades,
    )

    response = client.api_client.create_block_trade_offer(args.block_trade_id, request)
    offer_id = response.block_id
    logger.info(f"Offer submitted: {offer_id}")
    print(offer_id)


# ── cancel ───────────────────────────────────────────────────────────────────


def cmd_cancel(args):
    client = create_paradex_client(args.account_index, args.env)
    client.api_client.cancel_block_trade_offer(args.block_trade_id, args.offer_id)
    logger.info(f"Cancelled offer {args.offer_id}")


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Block Trades — Buyer")
    parser.add_argument("--account-index", type=int, default=1, help="Account index in test_accounts.json (default: 1)")
    parser.add_argument("--env", default="testnet", choices=["prod", "testnet", "nightly"], help="Paradex environment (default: testnet)")
    sub = parser.add_subparsers(dest="command", required=True)

    # whoami
    sub.add_parser("whoami", help="Print your Starknet account address")

    # offer
    p_offer = sub.add_parser("offer", help="Submit an offer to a block trade")
    p_offer.add_argument("--block-trade-id", required=True)
    p_offer.add_argument("--price", default=None, help="Override offer price (default: match block trade)")
    p_offer.add_argument("--size", default=None, help="Override offer size (default: match block trade)")

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel an offer")
    p_cancel.add_argument("--block-trade-id", required=True)
    p_cancel.add_argument("--offer-id", required=True)

    args = parser.parse_args()
    {
        "whoami": cmd_whoami,
        "offer": cmd_offer,
        "cancel": cmd_cancel,
    }[args.command](args)


if __name__ == "__main__":
    main()
