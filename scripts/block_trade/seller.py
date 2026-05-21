#!/usr/bin/env -S uv run
"""Block Trades — Seller CLI.

Creates a block trade, lists offers, executes with the collected offers, checks
status, and cancels. Runs independently of buyer.py — the two share only the
block trade ID.

USAGE:
    # Print your Starknet address
    uv run scripts/block_trade/seller.py whoami

    # Create a block trade (needs the buyer's Starknet address)
    uv run scripts/block_trade/seller.py create \
        --market ETH-USD-PERP --side SELL --size 1 --price 1956 \
        --required-signer 0x<buyer_starknet_address>

    # Inspect / list / execute / cancel
    uv run scripts/block_trade/seller.py status --block-trade-id <id>
    uv run scripts/block_trade/seller.py list-offers --block-trade-id <id>
    uv run scripts/block_trade/seller.py execute --block-trade-id <id>
    uv run scripts/block_trade/seller.py cancel --block-trade-id <id>
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

from paradex_py.api.generated.requests import (
    BlockExecuteRequest,
    BlockTradeInfo,
    BlockTradeRequest,
)
from paradex_py.api.generated.responses import BlockTradeConstraints
from paradex_py.message.block_trades import BlockTrade, BlockTradeOrder, Trade

EXPIRATION_MS = 5 * 60 * 1000


def cmd_whoami(args):
    _, _, address = create_paradex_client(args.account_index, args.env)
    print(address)


def cmd_create(args):
    client, account, seller_address = create_paradex_client(args.account_index, args.env)
    logger.info(f"Seller account: {seller_address}")

    market = args.market
    side = args.side.upper()
    price = Decimal(args.price)
    size = Decimal(args.size)

    now = int(time.time() * 1000)
    nonce = f"block_trade_{now}"
    expiration = now + EXPIRATION_MS

    # Constraints widen the acceptable offer range (+/-5% price, up to 5x size).
    constraints = BlockTradeConstraints(
        min_price=str(round(price * Decimal("0.95"), 2)),
        max_price=str(round(price * Decimal("1.05"), 2)),
        min_size=str(size),
        max_size=str(size * 5),
    )

    trade_info = BlockTradeInfo(
        maker_order=dto_order(seller_address, side, price, size),
        price=str(price),
        size=str(size),
        taker_order=None,
        trade_constraints=constraints,
    )

    # Sign the block trade. Each required signer signs the same merkle root.
    # The seller's leaf carries their maker order; taker side is empty (zero
    # fields) until an offer merges in.
    block_trade = BlockTrade(
        nonce=nonce,
        expiration=expiration,
        trades=[
            Trade.fill(
                market=market,
                price=price,
                size=size,
                maker_order=signing_order(seller_address, side, price, size),
                taker_order=BlockTradeOrder(),
            ),
        ],
    )
    bt_sig = account.build_block_trade_signature(block_trade)

    request = BlockTradeRequest(
        nonce=nonce,
        block_expiration=expiration,
        required_signers=[seller_address, *args.required_signer],
        signatures={seller_address: bt_sig},
        trades={market: trade_info},
    )

    response = client.api_client.create_block_trade(request)
    logger.info(f"Block trade created: {response.block_id}")
    print(response.block_id)


def cmd_status(args):
    client, _, _ = create_paradex_client(args.account_index, args.env)
    r = client.api_client.get_block_trade(args.block_trade_id)
    logger.info(f"Block trade: {r.block_id}")
    logger.info(f"  Status:     {r.status}")
    logger.info(f"  Type:       {r.block_type}")
    logger.info(f"  Initiator:  {r.initiator}")
    logger.info(f"  Signers:    {r.required_signers}")
    logger.info(f"  Expires:    {r.block_expiration}")
    for market, detail in (r.trades or {}).items():
        side = detail.maker_order.side if detail.maker_order else "?"
        logger.info(f"  Trade {market}: {side} {detail.size} @ {detail.price}")


def cmd_list_offers(args):
    client, _, _ = create_paradex_client(args.account_index, args.env)
    response = client.api_client.get_block_trade_offers(args.block_trade_id)
    offers = response.results or []
    if not offers:
        logger.info("No offers found.")
        return
    logger.info(f"Found {len(offers)} offer(s):")
    for i, offer in enumerate(offers, 1):
        offer_id = offer.get("block_id") or offer.get("id", "?")
        status = offer.get("status", "?")
        markets = ", ".join((offer.get("trades") or {}).keys()) or "?"
        logger.info(f"  [{i}] {offer_id}  status={status}  markets={markets}")
        print(offer_id)


def cmd_execute(args):
    client, account, _ = create_paradex_client(args.account_index, args.env)
    offers = client.api_client.get_block_trade_offers(args.block_trade_id).results or []
    if not offers:
        logger.error("No offers to execute.")
        return

    offer_ids: list[str] = [oid for o in offers if (oid := o.get("block_id") or o.get("id"))]
    logger.info(f"Executing with {len(offer_ids)} offer(s): {offer_ids}")

    # Fetch each offer as a typed response, then let the SDK build the executor
    # signatures (one per offer, keyed by offer_id) in a single call.
    offer_responses = [client.api_client.get_block_trade_offer(args.block_trade_id, oid) for oid in offer_ids]
    signatures = account.build_executor_signatures_for_offers(offer_responses)

    request = BlockExecuteRequest(
        execution_nonce=f"execute_{int(time.time() * 1000)}",
        selected_offers=offer_ids,
        signatures=signatures,
    )
    response = client.api_client.execute_block_trade(args.block_trade_id, request)
    logger.info(f"Execution result: {response.status}")


def cmd_cancel(args):
    client, _, _ = create_paradex_client(args.account_index, args.env)
    client.api_client.cancel_block_trade(args.block_trade_id)
    logger.info(f"Cancelled block trade {args.block_trade_id}")


def main():
    parser = argparse.ArgumentParser(description="Block Trades — Seller")
    add_global_args(parser, default_account_index=0)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("whoami", help="Print your Starknet account address")

    p_create = sub.add_parser("create", help="Create a new block trade")
    p_create.add_argument("--market", required=True)
    p_create.add_argument("--side", required=True, choices=["BUY", "SELL"])
    p_create.add_argument("--size", required=True)
    p_create.add_argument("--price", required=True)
    p_create.add_argument(
        "--required-signer",
        action="append",
        default=[],
        help="Starknet address of a required signer (repeatable). Use buyer's 'whoami' to get this.",
    )

    p_status = sub.add_parser("status", help="Check block trade status")
    p_status.add_argument("--block-trade-id", required=True)

    p_offers = sub.add_parser("list-offers", help="List offers for a block trade")
    p_offers.add_argument("--block-trade-id", required=True)

    p_exec = sub.add_parser("execute", help="Execute block trade with all available offers")
    p_exec.add_argument("--block-trade-id", required=True)

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
