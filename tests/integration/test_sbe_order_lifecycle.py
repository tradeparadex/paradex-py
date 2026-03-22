#!/usr/bin/env -S uv run
"""
SBE Order Lifecycle Integration Test

Verifies that SBE binary WebSocket frames are received and correctly decoded
for the full order lifecycle: place LIMIT → cancel, then place MARKET → fill.

USAGE:
    uv run tests/integration/test_sbe_order_lifecycle.py [--env nightly|testnet]

PREREQUISITES:
    - .env.local in project root with PARADEX_ACCOUNT and PARADEX_PRIVATE_KEY
    - Funded account on the target environment
    - Liquid BTC-USD-PERP orderbook for the MARKET order fill step

WHAT IS TESTED:
    1. LIMIT order placed far below market → SBE OrderEvent OPEN received
    2. LIMIT order cancelled → SBE OrderEvent CLOSED received
    3. MARKET BUY order placed → SBE OrderEvent CLOSED + FillEvent received
    4. All decoded field values match the submitted order parameters
    5. All timestamps are valid milliseconds (not seconds)
    6. Events arrive via SBE binary frames (not JSON text fallback)
"""

import argparse
import asyncio
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from paradex_py import ParadexL2
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import NIGHTLY, TESTNET

# ── load .env.local ───────────────────────────────────────────────────────────
for _p in [Path(".env.local"), Path(__file__).parents[2] / ".env.local"]:
    if _p.exists():
        for _l in _p.read_text().splitlines():
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                _k, _v = _l.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip("\"'"))
        break

MARKET = "BTC-USD-PERP"
# Size small enough to be safely fillable; adjust if min_order_size changes
MARKET_ORDER_SIZE = Decimal("0.001")
LIMIT_ORDER_SIZE = Decimal("0.001")
EVENT_TIMEOUT = 10.0  # seconds to wait for each expected WS event


# ── helpers ───────────────────────────────────────────────────────────────────


def _ts_ok(v: int) -> bool:
    """Valid millisecond timestamp: between 2020 and 2040."""
    return 1_577_836_800_000 < v < 2_208_988_800_000


def _check(condition: bool, msg: str) -> None:
    if not condition:
        print(f"  FAIL: {msg}")
        sys.exit(1)
    print(f"  ok   {msg}")


# Per-channel event queues; filled by WS callbacks
_order_events: asyncio.Queue = asyncio.Queue()
_fill_events: asyncio.Queue = asyncio.Queue()
_binary_frame_count = 0


async def _on_orders(ws, msg):
    global _binary_frame_count
    data = msg["params"]["data"]
    # SBE binary frames produce OrderEventData model fields (order_type, order_id, …)
    # JSON text frames produce JSON API field names (type, id, …)
    is_sbe = isinstance(data, dict) and "order_type" in data
    if is_sbe:
        _binary_frame_count += 1
    await _order_events.put({"data": data, "sbe": is_sbe})


async def _on_fills(ws, msg):
    global _binary_frame_count
    data = msg["params"]["data"]
    is_sbe = isinstance(data, dict) and "fill_type" in data
    if is_sbe:
        _binary_frame_count += 1
    await _fill_events.put({"data": data, "sbe": is_sbe})


async def _wait_order(status: str, order_id: str, timeout: float = EVENT_TIMEOUT) -> dict:
    """Wait for an order event with matching order_id and status."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for order {order_id} status={status}")
        try:
            evt = await asyncio.wait_for(_order_events.get(), timeout=remaining)
        except asyncio.TimeoutError as e:
            raise TimeoutError(f"Timed out waiting for order {order_id} status={status}") from e
        d = evt["data"]
        # handle both SBE field names (order_id, status) and JSON (id, status)
        eid = d.get("order_id") or d.get("id", "")
        est = d.get("status", "")
        if eid == order_id and est == status:
            return evt
        # put back unrelated events
        await _order_events.put(evt)
        await asyncio.sleep(0.05)


async def _wait_fill(order_id: str, timeout: float = EVENT_TIMEOUT) -> dict:
    """Wait for a fill event with matching order_id."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for fill on order {order_id}")
        try:
            evt = await asyncio.wait_for(_fill_events.get(), timeout=remaining)
        except asyncio.TimeoutError as e:
            raise TimeoutError(f"Timed out waiting for fill on order {order_id}") from e
        d = evt["data"]
        eid = d.get("order_id", "")
        if eid == order_id:
            return evt
        await _fill_events.put(evt)
        await asyncio.sleep(0.05)


def _place(
    client: ParadexL2, order_type: OrderType, side: OrderSide, size: Decimal, price: Decimal | None = None
) -> str:
    order = Order(
        market=MARKET,
        order_type=order_type,
        order_side=side,
        size=size,
        limit_price=price or Decimal("0"),
        client_id=f"sbe-test-{int(time.time() * 1000)}",
        signature_timestamp=int(time.time() * 1000),
        instruction="GTC" if order_type == OrderType.Limit else "IOC",
        reduce_only=False,
    )
    order.signature = client.account.sign_order(order)
    resp = client.api_client.submit_order(order)
    return resp["id"]


# ── main test ─────────────────────────────────────────────────────────────────


async def run(env):
    l2_addr = os.getenv("PARADEX_ACCOUNT", "")
    l2_key = os.getenv("PARADEX_PRIVATE_KEY", "")
    if not l2_addr or not l2_key:
        print("ERROR: PARADEX_ACCOUNT and PARADEX_PRIVATE_KEY must be set in .env.local")
        sys.exit(1)

    print(f"\nEnvironment : {env}")
    print(f"Account     : {l2_addr[:18]}…")
    print(f"Market      : {MARKET}\n")

    client = ParadexL2(env=env, l2_address=l2_addr, l2_private_key=l2_key, ws_sbe_enabled=True)

    while not await client.ws_client.connect():
        await asyncio.sleep(1)
    print("WS connected (SBE enabled)\n")

    await client.ws_client.subscribe(ParadexWebsocketChannel.ORDERS, callback=_on_orders, params={"market": "ALL"})
    await client.ws_client.subscribe(ParadexWebsocketChannel.FILLS, callback=_on_fills, params={"market": "ALL"})
    # give subscriptions a moment to activate
    await asyncio.sleep(1)

    # ── fetch current BBO to compute a far-from-market limit price ────────────
    bbo = client.api_client.fetch_bbo(MARKET)
    ask = Decimal(str(bbo.get("ask_price") or bbo.get("ask") or "100000"))
    limit_price = (ask * Decimal("0.5")).quantize(Decimal("1"))
    print(f"BBO ask: {ask}  →  limit price: {limit_price}\n")

    # ─────────────────────────────────────────────────────────────────────────
    print("=" * 55)
    print("STEP 1: LIMIT order place + cancel")
    print("=" * 55)

    oid = _place(client, OrderType.Limit, OrderSide.Buy, LIMIT_ORDER_SIZE, limit_price)
    print(f"  placed order_id={oid}")

    evt = await _wait_order("OPEN", oid)
    d = evt["data"]
    _check(evt["sbe"], "order OPEN arrived as SBE binary frame")
    _check(d["order_id"] == oid, f"order_id matches ({d['order_id'][:20]}…)")
    _check(d["status"] == "OPEN", "status == OPEN")
    _check(d["side"] == "BUY", "side == BUY")
    _check(d["order_type"] == "LIMIT", "order_type == LIMIT")
    _check(d["market"] == MARKET, f"market == {MARKET}")
    _check(_ts_ok(d["timestamp"]), f"timestamp is valid ms ({d['timestamp']})")
    _check(_ts_ok(d["created_at"]), f"created_at is valid ms ({d['created_at']})")
    _check(d["avg_fill_price"] is None, "avg_fill_price is None (unfilled)")
    _check(d["account"].lower() == l2_addr.lower(), "account address matches")
    print()

    client.api_client.cancel_order(oid)
    print(f"  cancelled {oid}")

    evt = await _wait_order("CLOSED", oid)
    d = evt["data"]
    _check(evt["sbe"], "order CLOSED arrived as SBE binary frame")
    _check(d["status"] == "CLOSED", "status == CLOSED")
    _check(_ts_ok(d["updated_at"]), f"updated_at is valid ms ({d['updated_at']})")
    print()

    # ─────────────────────────────────────────────────────────────────────────
    print("=" * 55)
    print("STEP 2: MARKET order → fill")
    print("=" * 55)

    oid2 = _place(client, OrderType.Market, OrderSide.Buy, MARKET_ORDER_SIZE)
    print(f"  placed market order_id={oid2}")

    # wait for both CLOSED order event and a fill event concurrently
    order_task = asyncio.create_task(_wait_order("CLOSED", oid2))
    fill_task = asyncio.create_task(_wait_fill(oid2))
    try:
        order_evt, fill_evt = await asyncio.gather(order_task, fill_task)
    except TimeoutError as e:
        print(f"  FAIL: {e}")
        print("  (market may be illiquid — no matching orders on the book)")
        sys.exit(1)

    od = order_evt["data"]
    fd = fill_evt["data"]

    _check(order_evt["sbe"], "order CLOSED arrived as SBE binary frame")
    _check(od["status"] == "CLOSED", "order status == CLOSED")
    _check(od["order_type"] == "MARKET", "order_type == MARKET")
    _check(_ts_ok(od["timestamp"]), f"order timestamp valid ms ({od['timestamp']})")

    _check(fill_evt["sbe"], "fill arrived as SBE binary frame")
    _check(fd["order_id"] == oid2, "fill order_id matches")
    _check(fd["side"] == "BUY", "fill side == BUY")
    _check(fd["market"] == MARKET, f"fill market == {MARKET}")
    _check(fd["fill_type"] == "FILL", "fill_type == FILL")
    _check(Decimal(fd["size"]) > 0, f"fill size > 0 ({fd['size']})")
    _check(Decimal(fd["price"]) > 0, f"fill price > 0 ({fd['price']})")
    _check(_ts_ok(fd["timestamp"]), f"fill timestamp valid ms ({fd['timestamp']})")
    _check(_ts_ok(fd["created_at"]), f"fill created_at valid ms ({fd['created_at']})")
    _check(fd["account"].lower() == l2_addr.lower(), "fill account address matches")
    print()

    # ─────────────────────────────────────────────────────────────────────────
    print("=" * 55)
    print(f"PASSED  —  {_binary_frame_count} SBE binary frames decoded")
    print("=" * 55)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["nightly", "testnet"], default="nightly")
    args = parser.parse_args()
    env = NIGHTLY if args.env == "nightly" else TESTNET
    asyncio.run(run(env))
