#!/usr/bin/env -S uv run
"""Block Trades CLI.

A single entrypoint covering both sides of a block trade. The subcommand
determines the role:

    Seller (initiator) commands:
        whoami        — print your Starknet address
        create        — create a new block trade
        status        — inspect a block trade
        list-offers   — list offers submitted to a block trade
        execute       — execute a block trade with all collected offers

    Buyer (offerer) commands:
        whoami        — print your Starknet address
        offer         — submit an offer to an existing block trade

    Either:
        cancel        — cancel a block trade (initiator) or an offer (offerer)

The `--side BUY|SELL` flag on `create` and `offer` is the buy/sell switch:
the initiator picks the side they take, and the offerer can override the
auto-detected opposite side if needed.

USAGE:
    uv run scripts/block_trade/cli.py whoami
    uv run scripts/block_trade/cli.py create \
        --market ETH-USD-PERP --side SELL --size 1 --price 1956 \
        --required-signer 0x<buyer_address>
    uv run scripts/block_trade/cli.py offer --block-trade-id <id>
    uv run scripts/block_trade/cli.py execute --block-trade-id <id>
    uv run scripts/block_trade/cli.py cancel --block-trade-id <id>
    uv run scripts/block_trade/cli.py cancel --block-trade-id <id> --offer-id <oid>
"""

import argparse
import time
from decimal import Decimal

from common import (
    add_global_args,
    create_paradex_client,
    dto_order,
    logger,
)

from paradex_py.api.generated.requests import (
    BlockExecuteRequest,
    BlockOfferInfo,
    BlockOfferRequest,
    BlockTradeInfo,
    BlockTradeRequest,
)
from paradex_py.api.generated.responses import BlockTradeConstraints
from paradex_py.common.order import OrderSide

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

    request = BlockTradeRequest(
        nonce=nonce,
        block_expiration=expiration,
        required_signers=[seller_address, *args.required_signer],
        signatures={},
        trades={
            market: BlockTradeInfo(
                maker_order=dto_order(seller_address, side, price, size),
                price=str(price),
                size=str(size),
                taker_order=None,
                trade_constraints=constraints,
            ),
        },
    )

    # The SDK reconstructs the signing BlockTrade from the request and inserts
    # the seller's signature into request.signatures[seller_address].
    account.sign_block_trade_request(request)

    response = client.api_client.create_block_trade(request)
    logger.info(f"Block trade created: {response.block_id}")
    print(response.block_id)


def cmd_offer(args):
    client, account, buyer_address = create_paradex_client(args.account_index, args.env)
    logger.info(f"Buyer account: {buyer_address}")

    bt = client.api_client.get_block_trade(args.block_trade_id)
    if not bt.trades:
        logger.error("Block trade has no trades defined.")
        return
    logger.info(f"Block trade {bt.block_id} — status={bt.status}")

    offer_trades: dict[str, BlockOfferInfo] = {}
    for market, detail in bt.trades.items():
        if args.side:
            buyer_side = args.side.upper()
        else:
            maker_side = OrderSide(detail.maker_order.side.value) if detail.maker_order else OrderSide.Buy
            buyer_side = maker_side.opposite_side().value

        price = Decimal(args.price) if args.price else Decimal(detail.price or "0")
        size = Decimal(args.size) if args.size else Decimal(detail.size or "0")
        logger.info(f"  {market}: {buyer_side} {size} @ {price}")

        offer_trades[market] = BlockOfferInfo(
            offerer_order=dto_order(buyer_address, buyer_side, price, size),
            price=str(price),
            size=str(size),
        )

    # `signature` is populated by sign_block_offer_request below — use
    # model_construct to skip validation of the missing required field.
    request = BlockOfferRequest.model_construct(
        nonce=f"offer_{int(time.time() * 1000)}",
        offering_account=buyer_address,
        trades=offer_trades,
    )

    # SDK builds the BlockTradeOffer (distinct primary type, bound to this
    # parent via block_trade_id) and attaches the signature.
    account.sign_block_offer_request(request, args.block_trade_id)

    response = client.api_client.create_block_trade_offer(args.block_trade_id, request)
    logger.info(f"Offer submitted: {response.block_id}")
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

    # Fetch each offer as a typed response; the SDK builds one signature per
    # offer, keyed by offer_id.
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
    """Cancel a block trade (initiator) or an offer (offerer).

    Without --offer-id, cancels the parent block trade.
    With --offer-id, cancels that specific offer.
    """
    client, _, _ = create_paradex_client(args.account_index, args.env)
    if args.offer_id:
        client.api_client.cancel_block_trade_offer(args.block_trade_id, args.offer_id)
        logger.info(f"Cancelled offer {args.offer_id}")
    else:
        client.api_client.cancel_block_trade(args.block_trade_id)
        logger.info(f"Cancelled block trade {args.block_trade_id}")


def main():
    parser = argparse.ArgumentParser(description="Block Trades CLI")
    add_global_args(parser, default_account_index=0)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("whoami", help="Print your Starknet account address")

    p_create = sub.add_parser("create", help="Create a new block trade (seller / initiator)")
    p_create.add_argument("--market", required=True)
    p_create.add_argument("--side", required=True, choices=["BUY", "SELL"])
    p_create.add_argument("--size", required=True)
    p_create.add_argument("--price", required=True)
    p_create.add_argument(
        "--required-signer",
        action="append",
        default=[],
        help="Starknet address of a required signer (repeatable). Use the other party's 'whoami' to get this.",
    )

    p_offer = sub.add_parser("offer", help="Submit an offer to a block trade (buyer / offerer)")
    p_offer.add_argument("--block-trade-id", required=True)
    p_offer.add_argument(
        "--side",
        choices=["BUY", "SELL"],
        default=None,
        help="Override the offerer side (default: opposite of the block trade's maker side)",
    )
    p_offer.add_argument("--price", default=None, help="Override offer price (default: match block trade)")
    p_offer.add_argument("--size", default=None, help="Override offer size (default: match block trade)")

    p_status = sub.add_parser("status", help="Check block trade status")
    p_status.add_argument("--block-trade-id", required=True)

    p_offers = sub.add_parser("list-offers", help="List offers for a block trade")
    p_offers.add_argument("--block-trade-id", required=True)

    p_exec = sub.add_parser("execute", help="Execute block trade with all available offers")
    p_exec.add_argument("--block-trade-id", required=True)

    p_cancel = sub.add_parser("cancel", help="Cancel a block trade (without --offer-id) or an offer (with --offer-id)")
    p_cancel.add_argument("--block-trade-id", required=True)
    p_cancel.add_argument("--offer-id", default=None)

    args = parser.parse_args()
    {
        "whoami": cmd_whoami,
        "create": cmd_create,
        "offer": cmd_offer,
        "status": cmd_status,
        "list-offers": cmd_list_offers,
        "execute": cmd_execute,
        "cancel": cmd_cancel,
    }[args.command](args)


if __name__ == "__main__":
    main()
