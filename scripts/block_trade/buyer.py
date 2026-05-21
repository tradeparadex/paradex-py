#!/usr/bin/env -S uv run
"""Block Trades — Buyer CLI.

Submits an offer to an existing block trade and cancels offers. Runs
independently of seller.py — only the block trade ID is shared.

USAGE:
    # Print your Starknet address (give this to the seller)
    uv run scripts/block_trade/buyer.py whoami

    # Submit an offer (matches the block trade's price/size by default)
    uv run scripts/block_trade/buyer.py offer --block-trade-id <id>

    # Override price and/or size
    uv run scripts/block_trade/buyer.py offer --block-trade-id <id> --price 1956 --size 1

    # Cancel an offer
    uv run scripts/block_trade/buyer.py cancel --block-trade-id <id> --offer-id <oid>
"""

import argparse
import time
from decimal import Decimal

from common import (
    add_global_args,
    create_paradex_client,
    dto_order,
    logger,
    signing_order,
)

from paradex_py.api.generated.requests import BlockOfferInfo, BlockOfferRequest
from paradex_py.common.order import OrderSide
from paradex_py.message.block_trades import BlockTradeOffer, BlockTradeOrder, Trade

EXPIRATION_MS = 5 * 60 * 1000


def cmd_whoami(args):
    _, _, address = create_paradex_client(args.account_index, args.env)
    print(address)


def cmd_offer(args):
    client, account, buyer_address = create_paradex_client(args.account_index, args.env)
    logger.info(f"Buyer account: {buyer_address}")

    bt = client.api_client.get_block_trade(args.block_trade_id)
    if not bt.trades:
        logger.error("Block trade has no trades defined.")
        return
    logger.info(f"Block trade {bt.block_id} — status={bt.status}")

    now = int(time.time() * 1000)
    nonce = f"offer_{now}"
    expiration = now + EXPIRATION_MS

    offer_trades: dict[str, BlockOfferInfo] = {}
    signing_trades: list[Trade] = []

    for market, detail in bt.trades.items():
        maker_side = OrderSide(detail.maker_order.side.value) if detail.maker_order else OrderSide.Buy
        buyer_side = maker_side.opposite_side().value  # "BUY" / "SELL"

        price = Decimal(args.price) if args.price else Decimal(detail.price or "0")
        size = Decimal(args.size) if args.size else Decimal(detail.size or "0")
        logger.info(f"  {market}: {buyer_side} {size} @ {price}")

        offer_trades[market] = BlockOfferInfo(
            offerer_order=dto_order(buyer_address, buyer_side, price, size),
            price=str(price),
            size=str(size),
        )
        signing_trades.append(
            Trade.fill(
                market=market,
                price=price,
                size=size,
                maker_order=signing_order(buyer_address, buyer_side, price, size),
                taker_order=BlockTradeOrder(),  # offerer signs only their side; counter-side is empty
            )
        )

    # Sign the BlockTradeOffer — distinct primary type from BlockTrade, binds the
    # signature to this parent via block_trade_id.
    offer = BlockTradeOffer(
        nonce=nonce,
        expiration=expiration,
        block_trade_id=args.block_trade_id,
        trades=signing_trades,
    )
    signature = account.build_block_trade_offer_signature(offer)

    request = BlockOfferRequest(
        nonce=nonce,
        offering_account=buyer_address,
        signature=signature,
        trades=offer_trades,
    )
    response = client.api_client.create_block_trade_offer(args.block_trade_id, request)
    logger.info(f"Offer submitted: {response.block_id}")
    print(response.block_id)


def cmd_cancel(args):
    client, _, _ = create_paradex_client(args.account_index, args.env)
    client.api_client.cancel_block_trade_offer(args.block_trade_id, args.offer_id)
    logger.info(f"Cancelled offer {args.offer_id}")


def main():
    parser = argparse.ArgumentParser(description="Block Trades — Buyer")
    add_global_args(parser, default_account_index=1)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("whoami", help="Print your Starknet account address")

    p_offer = sub.add_parser("offer", help="Submit an offer to a block trade")
    p_offer.add_argument("--block-trade-id", required=True)
    p_offer.add_argument("--price", default=None, help="Override offer price (default: match block trade)")
    p_offer.add_argument("--size", default=None, help="Override offer size (default: match block trade)")

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
