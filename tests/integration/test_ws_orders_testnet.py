#!/usr/bin/env python3
"""
WebSocket order management integration test against Paradex (nightly by default).

Generates a fresh random L2 keypair on first run (saved to keypair.json beside
this file so re-runs reuse the same account).  The faucet automatically
deposits USDC to every newly-onboarded account — the test waits up to
FUNDS_TIMEOUT_S seconds for the deposit before proceeding.

Test cases
----------
1.  Account onboarding & authentication (random L2 keypair, no L1 key needed)
2.  Wait for faucet USDC
3.  WS subscriptions: orders.ALL, fills.ALL, positions
4.  Single order lifecycle per market: submit → modify → cancel-by-id
5.  Cancel by client ID
6.  Batch submit + batch cancel
7.  Cancel-all (market-scoped, then global)
8.  Cancel-on-Disconnect (CoD)
9.  Mixed WS + REST interleaving

Each WS operation is followed by a REST API cross-check to detect any
discrepancy between the WebSocket update and the true server-side state.

Usage
-----
    uv run python tests/integration/test_ws_orders_testnet.py

Optional env vars
-----------------
    ENV              target environment: nightly (default), testnet, prod
    MARKETS          comma-separated, default: BTC-USD-PERP,ETH-USD-PERP
    MIN_USDC_BALANCE minimum USDC balance before running tests, default: 10
    FUNDS_TIMEOUT_S  seconds to wait for faucet, default: 600
    KEYPAIR_FILE     path to persist the generated keypair, default: <script_dir>/keypair.json

Notes
-----
    Testnet now requires the L1 address to hold ≥0.001 ETH or ≥5 USDC on
    Ethereum/Arbitrum/Base as an anti-bot measure.  The nightly environment
    does not enforce this restriction, making it better suited for automated
    testing with a freshly-generated L2 keypair.
"""

import asyncio
import contextlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from starknet_py.constants import EC_ORDER
from starknet_py.net.signer.key_pair import KeyPair

from paradex_py import Paradex
from paradex_py.api.ws_client import ParadexWebsocketChannel, ParadexWebsocketClient, WsRpcError
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import NIGHTLY, PROD, TESTNET, Environment

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ws_testnet")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent

_ENVS: dict[str, Environment] = {"nightly": NIGHTLY, "testnet": TESTNET, "prod": PROD}
ENV: Environment = _ENVS[os.environ.get("ENV", "nightly").lower()]

# nightly only publishes ws.api.nightly.paradex.trade (direct endpoint);
# ws-public.api.nightly.paradex.trade has no DNS record.
_WS_URL_OVERRIDE: str | None = f"wss://ws.api.{ENV}.paradex.trade/v1" if ENV == NIGHTLY else None

_raw_markets = os.environ.get("MARKETS", "BTC-USD-PERP,ETH-USD-PERP")
MARKETS: list[str] = [m.strip() for m in _raw_markets.split(",") if m.strip()]
MIN_USDC_BALANCE = float(os.environ.get("MIN_USDC_BALANCE", "10"))
FUNDS_TIMEOUT_S = int(os.environ.get("FUNDS_TIMEOUT_S", "600"))
FUNDS_POLL_S = 10
KEYPAIR_FILE = Path(os.environ.get("KEYPAIR_FILE", str(_SCRIPT_DIR / "keypair.json")))

WS_UPDATE_TIMEOUT_S = 20.0
COD_CANCEL_TIMEOUT_S = 30

# Limit prices well below current market so orders never fill
_LIMIT_PRICES: dict[str, Decimal] = {
    "BTC-USD-PERP": Decimal("10000"),
    "ETH-USD-PERP": Decimal("500"),
    "SOL-USD-PERP": Decimal("20"),
    "MATIC-USD-PERP": Decimal("0.20"),
    "AVAX-USD-PERP": Decimal("5"),
}
_MODIFY_PRICES: dict[str, Decimal] = {
    "BTC-USD-PERP": Decimal("9000"),
    "ETH-USD-PERP": Decimal("450"),
    "SOL-USD-PERP": Decimal("18"),
    "MATIC-USD-PERP": Decimal("0.18"),
    "AVAX-USD-PERP": Decimal("4.5"),
}
_ORDER_SIZES: dict[str, Decimal] = {
    "BTC-USD-PERP": Decimal("0.001"),
    "ETH-USD-PERP": Decimal("0.01"),
    "SOL-USD-PERP": Decimal("0.1"),
    "MATIC-USD-PERP": Decimal("10"),
    "AVAX-USD-PERP": Decimal("0.1"),
}
_FALLBACK_PRICE = Decimal("1")
_FALLBACK_SIZE = Decimal("0.01")


def _limit_price(market: str) -> Decimal:
    return _LIMIT_PRICES.get(market, _FALLBACK_PRICE)


def _modify_price(market: str) -> Decimal:
    return _MODIFY_PRICES.get(market, _FALLBACK_PRICE * Decimal("0.9"))


def _order_size(market: str) -> Decimal:
    return _ORDER_SIZES.get(market, _FALLBACK_SIZE)


def _client_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000) % 100_000_000}"


# ---------------------------------------------------------------------------
# Keypair generation / persistence
# ---------------------------------------------------------------------------


def _generate_l2_private_key() -> int:
    """Return a cryptographically random Starknet private key."""
    while True:
        candidate = int.from_bytes(secrets.token_bytes(32), "big")
        if 1 <= candidate < EC_ORDER:
            return candidate


def load_or_create_keypair(path: Path) -> tuple[str, str]:
    """Load an existing keypair from *path* or generate a fresh one.

    Returns (l2_private_key_hex, dummy_l1_address_hex).
    The dummy L1 address is only stored for consistency; the Paradex testnet
    does not validate L1 ownership during onboarding.
    """
    if path.exists():
        data = json.loads(path.read_text())
        logger.info(f"Loaded existing keypair from {path}")
        return data["l2_private_key"], data["l1_address"]

    priv = _generate_l2_private_key()
    kp = KeyPair.from_private_key(priv)
    l2_priv_hex = hex(priv)
    l1_addr = "0x" + secrets.token_hex(20)

    data = {
        "l2_private_key": l2_priv_hex,
        "l2_public_key": hex(kp.public_key),
        "l1_address": l1_addr,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    logger.info(f"Generated new keypair, saved to {path}")
    logger.info(f"  L2 public key : {hex(kp.public_key)}")
    logger.info(f"  Dummy L1 addr : {l1_addr}")
    return l2_priv_hex, l1_addr


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    category: str
    description: str
    details: dict = field(default_factory=dict)


@dataclass
class TestReport:
    issues: list[Issue] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)

    def fail(self, category: str, description: str, **kwargs) -> None:
        self.issues.append(Issue(category=category, description=description, details=kwargs))
        logger.error(f"[FAIL] {category}: {description}" + (f" | {kwargs}" if kwargs else ""))

    def ok(self, description: str) -> None:
        self.passed.append(description)
        logger.info(f"[PASS] {description}")

    def summary(self) -> str:
        sep = "=" * 72
        lines = [
            "",
            sep,
            "  WS ORDER MANAGEMENT — REPORT SUMMARY",
            sep,
            f"  Passed : {len(self.passed)}",
            f"  Issues : {len(self.issues)}",
            "",
        ]
        if self.passed:
            lines.append("PASSED:")
            for p in self.passed:
                lines.append(f"  ✓  {p}")
            lines.append("")
        if self.issues:
            lines.append("ISSUES:")
            for iss in self.issues:
                lines.append(f"  ✗  [{iss.category}] {iss.description}")
                for k, v in iss.details.items():
                    lines.append(f"         {k}: {v}")
            lines.append("")
        lines.append(sep)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Order tracker
# ---------------------------------------------------------------------------


class OrderTracker:
    """Collects all WS order update messages for later inspection."""

    def __init__(self) -> None:
        self._updates: dict[str, list[dict]] = {}
        self._lock = asyncio.Lock()

    async def on_order_update(self, _channel: ParadexWebsocketChannel, message: dict) -> None:
        data = message.get("params", {}).get("data", {})
        oid = data.get("id")
        logger.info(
            f"[WS ORDER] id={oid} cid={data.get('client_id', '')} "
            f"status={data.get('status')} market={data.get('market')}"
        )
        if not oid:
            return
        async with self._lock:
            self._updates.setdefault(oid, []).append(data.copy())

    async def wait_for_status(
        self,
        order_id: str,
        expected_status: str,
        timeout: float = WS_UPDATE_TIMEOUT_S,
    ) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            async with self._lock:
                for upd in reversed(self._updates.get(order_id, [])):
                    if upd.get("status") == expected_status:
                        return upd
            await asyncio.sleep(0.2)
        return None

    async def wait_for_any(self, order_id: str, timeout: float = WS_UPDATE_TIMEOUT_S) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            async with self._lock:
                updates = self._updates.get(order_id, [])
                if updates:
                    return updates[-1]
            await asyncio.sleep(0.2)
        return None


# ---------------------------------------------------------------------------
# Primitive helpers — order construction, submission, cancellation, assertions
# ---------------------------------------------------------------------------


def _make_order(
    market: str,
    prefix: str,
    price: Decimal | None = None,
    order_id: str | None = None,
    client_id: str | None = None,
) -> Order:
    return Order(
        market=market,
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=_order_size(market),
        limit_price=price if price is not None else _limit_price(market),
        client_id=client_id or _client_id(f"{prefix}_{market[:3].lower()}"),
        instruction="GTC",
        order_id=order_id,
    )


def _new_ws_client(paradex: Paradex) -> ParadexWebsocketClient:
    ws = ParadexWebsocketClient(env=ENV, logger=logger, api_client=paradex.api_client, ws_url_override=_WS_URL_OVERRIDE)
    ws.init_account(paradex.account)
    return ws


async def _ws_submit(ws: ParadexWebsocketClient, order: Order, report: TestReport, label: str) -> str | None:
    try:
        result = await ws.submit_order(order)
        oid = result["order"]["id"]
        report.ok(f"{label} WS submit id={oid}")
        return oid
    except (WsRpcError, KeyError) as exc:
        report.fail("WS_SUBMIT", f"{label} WS submit failed", error=str(exc))
        return None


def _rest_submit(paradex: Paradex, order: Order, report: TestReport, label: str) -> str | None:
    try:
        result = paradex.api_client.submit_order(order)
        oid = result["order"]["id"]
        report.ok(f"{label} REST submit id={oid}")
        return oid
    except Exception as exc:
        report.fail("REST_SUBMIT", f"{label} REST submit failed", error=str(exc))
        return None


async def _expect_ws(
    tracker: OrderTracker,
    oid: str,
    status: str,
    report: TestReport,
    label: str,
    timeout: float = WS_UPDATE_TIMEOUT_S,
) -> bool:
    upd = await tracker.wait_for_status(oid, status, timeout=timeout)
    if upd:
        report.ok(f"{label} WS {status} id={oid}")
        return True
    report.fail("WS_NO_UPDATE", f"{label} no WS {status}", order_id=oid)
    return False


async def _expect_ws_all(
    tracker: OrderTracker, ids: list[str], status: str, report: TestReport, label: str, timeout: float = 12
) -> None:
    for oid in ids:
        await _expect_ws(tracker, oid, status, report, label, timeout)


def _rest_check_all(paradex: Paradex, ids: list[str], status: str, report: TestReport, label: str) -> None:
    for oid in ids:
        _validate_rest_status(paradex, oid, status, report, label)


async def _ws_cancel(ws: ParadexWebsocketClient, oid: str, report: TestReport, label: str) -> bool:
    try:
        await ws.cancel_order(oid)
        report.ok(f"{label} WS cancel id={oid}")
        return True
    except WsRpcError as exc:
        report.fail("WS_CANCEL", f"{label} WS cancel failed", error=str(exc))
        return False


def _rest_cancel(paradex: Paradex, oid: str, report: TestReport, label: str) -> bool:
    try:
        paradex.api_client.cancel_order(oid)
        report.ok(f"{label} REST cancel id={oid}")
        return True
    except Exception as exc:
        report.fail("REST_CANCEL", f"{label} REST cancel failed", error=str(exc))
        return False


async def _ws_modify(
    ws: ParadexWebsocketClient,
    tracker: OrderTracker,
    oid: str,
    mod_order: Order,
    report: TestReport,
    label: str,
) -> str | None:
    """WS modify; returns active order ID (same for in-place, new for cancel+replace)."""
    try:
        result = await ws.modify_order(oid, mod_order)
        mid = result["order"]["id"]
        mode = "in-place" if mid == oid else "cancel+replace"
        report.ok(f"{label} WS modify mode={mode} id={mid}")
    except (WsRpcError, KeyError) as exc:
        report.fail("WS_MODIFY", f"{label} WS modify failed", error=str(exc))
        with contextlib.suppress(Exception):
            await ws.cancel_order(oid)
        return None
    if mid == oid:
        await tracker.wait_for_any(mid)
    else:
        await tracker.wait_for_status(mid, "OPEN")
        await tracker.wait_for_status(oid, "CLOSED")
    return mid


# ---------------------------------------------------------------------------
# REST helpers
# ---------------------------------------------------------------------------


def _rest_fetch_order(paradex: Paradex, order_id: str) -> dict | None:
    try:
        return paradex.api_client.fetch_order(order_id=order_id)
    except Exception as exc:
        logger.warning(f"REST fetch_order({order_id[:12]}...): {exc}")
        return None


def _rest_open_orders(paradex: Paradex, market: str | None = None) -> list[dict] | None:
    """Return open orders, or None if the REST call itself failed."""
    try:
        params = {"market": market} if market else None
        resp = paradex.api_client.fetch_orders(params=params)
        return resp.get("results", [])
    except Exception as exc:
        logger.warning(f"REST fetch_orders: {exc}")
        return None


def _validate_rest_status(paradex: Paradex, order_id: str, expected: str, report: TestReport, ctx: str) -> dict | None:
    order = _rest_fetch_order(paradex, order_id)
    if order is None:
        report.fail("REST_FETCH", f"{ctx}: could not fetch order", order_id=order_id)
        return None
    actual = order.get("status", "?")
    if actual == expected:
        report.ok(f"REST {ctx}: order {order_id[:12]}... status={actual}")
    else:
        report.fail("REST_MISMATCH", f"{ctx}: expected={expected} actual={actual}", order_id=order_id)
    return order


# ---------------------------------------------------------------------------
# Test: single order lifecycle (submit → modify → cancel by ID)
# ---------------------------------------------------------------------------


async def test_single_order_lifecycle(
    paradex: Paradex, ws: ParadexWebsocketClient, tracker: OrderTracker, market: str, report: TestReport
) -> None:
    logger.info(f"\n{'─' * 60}\n[TEST] Single order lifecycle  market={market}\n{'─' * 60}")
    lbl = f"[{market}]"

    oid = await _ws_submit(ws, _make_order(market, "slc"), report, lbl)
    if oid is None:
        return
    await _expect_ws(tracker, oid, "OPEN", report, lbl)
    await asyncio.sleep(0.5)
    _validate_rest_status(paradex, oid, "OPEN", report, f"post-submit {lbl}")

    mid = await _ws_modify(
        ws, tracker, oid, _make_order(market, "slc", price=_modify_price(market), order_id=oid), report, lbl
    )
    if mid is None:
        return
    await asyncio.sleep(0.5)
    _validate_rest_status(paradex, mid, "OPEN", report, f"post-modify {lbl}")
    if mid != oid:
        _validate_rest_status(paradex, oid, "CLOSED", report, f"original CLOSED {lbl}")

    if not await _ws_cancel(ws, mid, report, lbl):
        return
    await _expect_ws(tracker, mid, "CLOSED", report, lbl)
    await asyncio.sleep(0.5)
    _validate_rest_status(paradex, mid, "CLOSED", report, f"post-cancel {lbl}")


# ---------------------------------------------------------------------------
# Test: cancel by client ID
# ---------------------------------------------------------------------------


async def test_cancel_by_client_id(
    paradex: Paradex, ws: ParadexWebsocketClient, tracker: OrderTracker, market: str, report: TestReport
) -> None:
    logger.info(f"\n{'─' * 60}\n[TEST] Cancel by client_id  market={market}\n{'─' * 60}")
    lbl = f"[{market}]"

    cid = _client_id(f"cid_{market[:3].lower()}")
    oid = await _ws_submit(ws, _make_order(market, "cid", client_id=cid), report, lbl)
    if oid is None:
        return
    await tracker.wait_for_status(oid, "OPEN")
    await asyncio.sleep(0.5)

    try:
        await ws.cancel_order_by_client_id(client_id=cid, market=market)
        report.ok(f"{lbl} cancel_by_client_id cid={cid}")
    except WsRpcError as exc:
        report.fail("WS_CANCEL_CID", f"{lbl} cancel_by_client_id failed", error=str(exc))
        return

    await _expect_ws(tracker, oid, "CLOSED", report, lbl)
    await asyncio.sleep(0.5)
    _validate_rest_status(paradex, oid, "CLOSED", report, f"post-cid-cancel {lbl}")


# ---------------------------------------------------------------------------
# Test: batch submit + batch cancel
# ---------------------------------------------------------------------------


def _extract_batch_order_ids(batch_result: list | dict) -> list[str]:
    raw = batch_result if isinstance(batch_result, list) else batch_result.get("results", [])
    return [item["order"]["id"] for item in raw if isinstance(item, dict) and item.get("order", {}).get("id")]


async def test_batch_submit_and_cancel(
    paradex: Paradex, ws: ParadexWebsocketClient, tracker: OrderTracker, market: str, report: TestReport
) -> None:
    logger.info(f"\n{'─' * 60}\n[TEST] Batch submit + batch cancel  market={market}\n{'─' * 60}")
    lbl = f"[{market}]"
    batch_size = 5
    orders = [
        _make_order(market, f"bt{i}", price=_limit_price(market) - Decimal(str(i * 10))) for i in range(batch_size)
    ]

    try:
        batch_result = await ws.submit_orders_batch(orders)
    except WsRpcError as exc:
        report.fail("WS_BATCH_SUBMIT", f"submit_orders_batch failed {lbl}", error=str(exc))
        return

    ids = _extract_batch_order_ids(batch_result)
    if not ids:
        report.fail("WS_BATCH_SUBMIT", f"No IDs in batch result {lbl}", result=str(batch_result)[:300])
        return
    report.ok(f"submit_orders_batch {lbl}: {len(ids)}/{batch_size} orders")

    await _expect_ws_all(tracker, ids, "OPEN", report, lbl, timeout=12)
    await asyncio.sleep(0.5)
    _rest_check_all(paradex, ids, "OPEN", report, f"post-batch-submit {lbl}")

    try:
        await ws.cancel_orders_batch(ids)
        report.ok(f"cancel_orders_batch {lbl}: {len(ids)} orders")
    except WsRpcError as exc:
        report.fail("WS_BATCH_CANCEL", f"cancel_orders_batch failed {lbl}", error=str(exc))
        return

    await _expect_ws_all(tracker, ids, "CLOSED", report, lbl, timeout=12)
    await asyncio.sleep(0.5)
    _rest_check_all(paradex, ids, "CLOSED", report, f"post-batch-cancel {lbl}")


# ---------------------------------------------------------------------------
# Test: cancel all (market-scoped then global)
# ---------------------------------------------------------------------------


async def _cancel_all_and_verify(
    ws: ParadexWebsocketClient,
    paradex: Paradex,
    tracker: OrderTracker,
    submitted: dict[str, list[str]],
    report: TestReport,
) -> None:
    try:
        await ws.cancel_all_orders()
        report.ok("cancel_all_orders() global")
    except WsRpcError as exc:
        report.fail("WS_CANCEL_ALL", "global cancel_all_orders() failed", error=str(exc))
        return
    for ids in submitted.values():
        for oid in ids:
            await tracker.wait_for_status(oid, "CLOSED", timeout=12)
    await asyncio.sleep(1)
    remaining = _rest_open_orders(paradex)
    if remaining is None:
        report.fail("REST_FETCH", "REST error after global cancel_all")
    elif not remaining:
        report.ok("No open orders after global cancel_all_orders()")
    else:
        for o in remaining:
            report.fail(
                "REST_MISMATCH",
                "Order still open after global cancel_all",
                order_id=o.get("id", "?"),
                market=o.get("market", "?"),
            )


async def test_cancel_all(
    paradex: Paradex, ws: ParadexWebsocketClient, tracker: OrderTracker, markets: list[str], report: TestReport
) -> None:
    logger.info(f"\n{'─' * 60}\n[TEST] Cancel all  markets={markets}\n{'─' * 60}")

    submitted: dict[str, list[str]] = {}
    for market in markets:
        ids = []
        for i in range(2):
            oid = await _ws_submit(
                ws,
                _make_order(market, f"ca{i}", price=_limit_price(market) - Decimal(str(i * 5))),
                report,
                f"[{market}]",
            )
            if oid:
                ids.append(oid)
        submitted[market] = ids

    if not any(submitted.values()):
        report.fail("WS_SUBMIT", "No orders submitted for cancel_all test")
        return
    for _market, ids in submitted.items():
        for oid in ids:
            await tracker.wait_for_status(oid, "OPEN", timeout=10)
    await asyncio.sleep(0.5)

    # cancel_all on first market only
    first = markets[0]
    try:
        await ws.cancel_all_orders(market=first)
        report.ok(f"cancel_all_orders(market={first})")
    except WsRpcError as exc:
        report.fail("WS_CANCEL_ALL", f"cancel_all_orders(market={first}) failed", error=str(exc))
        return
    await _expect_ws_all(tracker, submitted[first], "CLOSED", report, f"[{first}]", timeout=12)
    await asyncio.sleep(0.5)
    _rest_check_all(paradex, submitted[first], "CLOSED", report, f"post-cancel_all({first})")

    # second market's orders must still be open
    if len(markets) > 1 and submitted.get(markets[1]):
        second = markets[1]
        open_ids = {o["id"] for o in (_rest_open_orders(paradex, market=second) or [])}
        if any(oid in open_ids for oid in submitted[second]):
            report.ok(f"{second} orders survived cancel_all({first})")
        else:
            report.fail("REST_MISMATCH", f"{second} orders should survive cancel_all({first})")

    await _cancel_all_and_verify(ws, paradex, tracker, submitted, report)


# ---------------------------------------------------------------------------
# Test: concurrent multi-market stress
# ---------------------------------------------------------------------------


async def _stress_submit_market(ws: ParadexWebsocketClient, market: str, count: int, report: TestReport) -> list[str]:
    ids = []
    for i in range(count):
        oid = await _ws_submit(
            ws,
            _make_order(market, f"cs{i}", price=_limit_price(market) - Decimal(str(i * 7))),
            report,
            f"[cs/{market}]",
        )
        if oid:
            ids.append(oid)
    return ids


async def test_concurrent_stress(
    paradex: Paradex, ws: ParadexWebsocketClient, tracker: OrderTracker, markets: list[str], report: TestReport
) -> None:
    """Submit orders across all markets simultaneously, then cancel all at once."""
    logger.info(f"\n{'─' * 60}\n[TEST] Concurrent stress  markets={markets}\n{'─' * 60}")
    results = await asyncio.gather(*[_stress_submit_market(ws, m, 4, report) for m in markets])
    all_ids = [oid for ids in results for oid in ids]
    report.ok(f"concurrent stress: submitted {len(all_ids)} orders across {len(markets)} markets")

    open_count = 0
    for oid in all_ids:
        if await tracker.wait_for_status(oid, "OPEN", timeout=15):
            open_count += 1
    report.ok(f"concurrent stress: {open_count}/{len(all_ids)} OPEN via WS")
    await asyncio.sleep(0.5)

    try:
        await ws.cancel_all_orders()
        report.ok("concurrent stress: cancel_all issued")
    except WsRpcError as exc:
        report.fail("WS_CANCEL_ALL", "concurrent stress cancel_all failed", error=str(exc))
        return

    closed_count = 0
    for oid in all_ids:
        if await tracker.wait_for_status(oid, "CLOSED", timeout=15):
            closed_count += 1
    report.ok(f"concurrent stress: {closed_count}/{len(all_ids)} CLOSED via WS")
    await asyncio.sleep(1)

    remaining = _rest_open_orders(paradex)
    if remaining is None:
        report.fail("REST_FETCH", "concurrent stress: REST error after cancel_all")
    elif not remaining:
        report.ok("concurrent stress: no open orders after cancel_all")
    else:
        report.fail("REST_MISMATCH", f"concurrent stress: {len(remaining)} orders still open")


# ---------------------------------------------------------------------------
# Test: mixed WS + REST interleaving
# ---------------------------------------------------------------------------


async def _rest_modify_track_via_ws(
    paradex: Paradex, tracker: OrderTracker, market: str, oid: str, mod_order: Order, report: TestReport
) -> str | None:
    """Issue REST modify; derive active order ID from WS event (in-place vs cancel+replace)."""
    try:
        paradex.api_client.modify_order(oid, mod_order)
        report.ok(f"[{market}] REST modify accepted id={oid}")
    except Exception as exc:
        report.fail("REST_MODIFY", f"[{market}] REST modify failed", error=str(exc))
        with contextlib.suppress(Exception):
            paradex.api_client.cancel_order(oid)
        return None

    ws_upd = await tracker.wait_for_any(oid)
    if ws_upd and ws_upd.get("status") == "CLOSED":
        report.ok(f"[{market}] REST modify cancel+replace: original CLOSED")
        open_orders = _rest_open_orders(paradex) or []
        active: str | None = next((o["id"] for o in open_orders if o.get("market") == market), None)
        if active:
            report.ok(f"[{market}] replacement order id={active}")
        else:
            report.fail("REST_FETCH", f"[{market}] no replacement after cancel+replace")
        return active
    if ws_upd:
        report.ok(f"[{market}] REST modify in-place: WS update id={oid}")
        return oid
    report.fail("WS_NO_UPDATE", f"[{market}] no WS update after REST modify", order_id=oid)
    return oid  # best-effort fallback


async def test_mixed_ws_rest(
    paradex: Paradex, ws: ParadexWebsocketClient, tracker: OrderTracker, market: str, report: TestReport
) -> None:
    """Interleave WS and REST order operations and cross-verify each step."""
    logger.info(f"\n{'─' * 60}\n[TEST] Mixed WS+REST  market={market}\n{'─' * 60}")
    lbl = f"[{market}]"

    # WS submit → REST modify → REST cancel → WS CLOSED
    oid_a = await _ws_submit(ws, _make_order(market, "mwa"), report, lbl)
    if oid_a is None:
        return
    await tracker.wait_for_status(oid_a, "OPEN", timeout=12)
    await asyncio.sleep(0.3)

    active_a = await _rest_modify_track_via_ws(
        paradex, tracker, market, oid_a, _make_order(market, "mwa", price=_modify_price(market), order_id=oid_a), report
    )
    if active_a is None:
        return
    if not _rest_cancel(paradex, active_a, report, lbl):
        return
    await _expect_ws(tracker, active_a, "CLOSED", report, lbl, timeout=12)
    await asyncio.sleep(0.3)

    # REST submit → WS OPEN → WS cancel → REST CLOSED
    oid_b = _rest_submit(paradex, _make_order(market, "mr"), report, lbl)
    if oid_b is None:
        return
    await _expect_ws(tracker, oid_b, "OPEN", report, lbl, timeout=12)
    await asyncio.sleep(0.3)
    if not await _ws_cancel(ws, oid_b, report, lbl):
        return
    await _expect_ws(tracker, oid_b, "CLOSED", report, lbl, timeout=12)
    await asyncio.sleep(0.5)
    _validate_rest_status(paradex, oid_b, "CLOSED", report, f"mixed {lbl}")


# ---------------------------------------------------------------------------
# Cancel-on-Disconnect helpers
# ---------------------------------------------------------------------------


async def _wait_cod_cancelled(paradex: Paradex, cod_ids: list[str]) -> bool:
    """Poll REST until all CoD order IDs are gone from open orders or timeout."""
    deadline = time.monotonic() + COD_CANCEL_TIMEOUT_S
    while time.monotonic() < deadline:
        await asyncio.sleep(3)
        open_orders = _rest_open_orders(paradex)
        if open_orders is None:
            continue
        if not any(oid in {o["id"] for o in open_orders} for oid in cod_ids):
            return True
    return False


def _check_cod_results(paradex: Paradex, cod_ids: list[str], report: TestReport) -> None:
    for oid in cod_ids:
        rest_order = _rest_fetch_order(paradex, oid)
        status = rest_order.get("status", "?") if rest_order else "unknown"
        if status == "CLOSED":
            report.ok(f"CoD: order {oid} is CLOSED")
        else:
            report.fail("WS_COD", f"CoD order still {status} after {COD_CANCEL_TIMEOUT_S}s", order_id=oid)


async def _verify_cod_via_reconnect(paradex: Paradex, cod_ids: list[str], report: TestReport) -> None:
    """Reconnect a fresh WS session and confirm CoD orders appear CLOSED."""
    ws_verify = _new_ws_client(paradex)
    if not await ws_verify.connect():
        report.fail("WS_CONNECT", "CoD reconnect-verify: failed to connect")
        return
    verify_tracker = OrderTracker()
    await ws_verify.subscribe(ParadexWebsocketChannel.ORDERS, verify_tracker.on_order_update, params={"market": "ALL"})
    await asyncio.sleep(1)

    confirmed = 0
    for oid in cod_ids:
        if await verify_tracker.wait_for_status(oid, "CLOSED", timeout=10):
            confirmed += 1
        else:
            rest = _rest_fetch_order(paradex, oid)
            if rest and rest.get("status") == "CLOSED":
                confirmed += 1
            else:
                report.fail("WS_COD", f"CoD reconnect-verify: order {oid} not confirmed CLOSED")
    if confirmed == len(cod_ids):
        report.ok(f"CoD reconnect-verify: all {len(cod_ids)} orders CLOSED after reconnect")
    ws_verify.disable_reconnect = True
    with contextlib.suppress(Exception):
        await ws_verify.close()


# ---------------------------------------------------------------------------
# Test: Cancel-on-Disconnect
# ---------------------------------------------------------------------------


async def test_cancel_on_disconnect(paradex: Paradex, tracker: OrderTracker, market: str, report: TestReport) -> None:
    logger.info(f"\n{'─' * 60}\n[TEST] Cancel-on-Disconnect  market={market}\n{'─' * 60}")

    ws_cod = _new_ws_client(paradex)
    if not await ws_cod.connect():
        report.fail("WS_CONNECT", "CoD: failed to connect second WS session")
        return
    await ws_cod.subscribe(ParadexWebsocketChannel.ORDERS, tracker.on_order_update, params={"market": "ALL"})

    try:
        cod_result = await ws_cod.cancel_on_disconnect(True)
        if cod_result.get("enabled"):
            report.ok("cancel_on_disconnect(True) acknowledged")
        else:
            report.fail("WS_COD", "Server did not confirm CoD enabled", result=str(cod_result))
            await ws_cod.close()
            return
    except WsRpcError as exc:
        report.fail("WS_COD", "cancel_on_disconnect(True) rejected", error=str(exc))
        await ws_cod.close()
        return

    oid = await _ws_submit(ws_cod, _make_order(market, "cod"), report, "[CoD]")
    if oid is None:
        await ws_cod.close()
        return
    cod_ids = [oid]

    await tracker.wait_for_status(oid, "OPEN", timeout=10)
    await asyncio.sleep(0.5)
    _validate_rest_status(paradex, oid, "OPEN", report, "CoD pre-disconnect")

    ws_cod.disable_reconnect = True
    await ws_cod.close()
    logger.info("CoD: connection dropped — waiting for server-side cancellation...")

    if await _wait_cod_cancelled(paradex, cod_ids):
        report.ok(f"CoD: all orders cancelled by server  ids={cod_ids}")
    else:
        _check_cod_results(paradex, cod_ids, report)

    await _verify_cod_via_reconnect(paradex, cod_ids, report)


# ---------------------------------------------------------------------------
# Fund wait
# ---------------------------------------------------------------------------


async def wait_for_funds(paradex: Paradex, report: TestReport) -> bool:
    logger.info(f"Waiting for USDC balance >= {MIN_USDC_BALANCE} (timeout={FUNDS_TIMEOUT_S}s)...")
    deadline = time.monotonic() + FUNDS_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            resp = paradex.api_client.fetch_balances()
            for bal in resp.get("results", []):
                if bal.get("token") == "USDC":
                    size = float(bal.get("size", 0))
                    if size >= MIN_USDC_BALANCE:
                        report.ok(f"USDC balance sufficient: {size} USDC")
                        return True
                    logger.info(f"USDC balance: {size} — need >= {MIN_USDC_BALANCE}, retrying...")
        except Exception as exc:
            logger.warning(f"fetch_balances: {exc}")
        await asyncio.sleep(FUNDS_POLL_S)
    report.fail("FUNDS", f"USDC balance below {MIN_USDC_BALANCE} after {FUNDS_TIMEOUT_S}s")
    return False


# ---------------------------------------------------------------------------
# Test suite runner / teardown
# ---------------------------------------------------------------------------


async def _run_test_suite(
    paradex: Paradex, ws: ParadexWebsocketClient, tracker: OrderTracker, report: TestReport
) -> None:
    try:
        await asyncio.gather(*[test_single_order_lifecycle(paradex, ws, tracker, m, report) for m in MARKETS])
        await asyncio.sleep(1)
        await asyncio.gather(*[test_cancel_by_client_id(paradex, ws, tracker, m, report) for m in MARKETS])
        await asyncio.sleep(1)
        await asyncio.gather(*[test_batch_submit_and_cancel(paradex, ws, tracker, m, report) for m in MARKETS])
        await asyncio.sleep(1)
        await test_cancel_all(paradex, ws, tracker, MARKETS, report)
        await asyncio.sleep(1)
        await test_concurrent_stress(paradex, ws, tracker, MARKETS, report)
        await asyncio.sleep(1)
        await asyncio.gather(*[test_mixed_ws_rest(paradex, ws, tracker, m, report) for m in MARKETS])
        await asyncio.sleep(1)
        await test_cancel_on_disconnect(paradex, tracker, MARKETS[0], report)
    except Exception as exc:
        logger.exception("Unexpected error during test run")
        report.fail("UNEXPECTED", str(exc))


async def _teardown(paradex: Paradex, ws: ParadexWebsocketClient) -> None:
    try:
        remaining = _rest_open_orders(paradex)
        if remaining is None or remaining:
            if remaining:
                logger.info(f"Final cleanup: {len(remaining)} open orders remaining")
            else:
                logger.warning("Final cleanup: REST error — attempting cancel_all anyway")
            await ws.cancel_all_orders()
            await asyncio.sleep(2)
    except Exception as exc:
        logger.warning(f"Final cleanup: {exc}")
    await ws.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    report = TestReport()

    l2_priv_hex, l1_addr = load_or_create_keypair(KEYPAIR_FILE)

    logger.info(f"Initializing Paradex client (env={ENV}, L2-only keypair)...")
    try:
        paradex = Paradex(
            env=ENV,
            l1_address=l1_addr,
            l2_private_key=l2_priv_hex,
            server_derive_address=True,
            ws_url_override=_WS_URL_OVERRIDE,
        )
    except Exception as exc:
        report.fail("ONBOARDING", f"Client init / onboarding failed: {exc}")
        print(report.summary())
        return 1

    l2_addr = hex(paradex.account.l2_address) if paradex.account else "unknown"
    report.ok(f"Onboarding / auth  L2={l2_addr}")

    if not await wait_for_funds(paradex, report):
        print(report.summary())
        return 1

    ws = paradex.ws_client
    if not await ws.connect():
        report.fail("WS_CONNECT", "Failed to connect to WebSocket")
        print(report.summary())
        return 1
    report.ok("WebSocket connected")

    tracker = OrderTracker()
    await ws.subscribe(ParadexWebsocketChannel.ORDERS, tracker.on_order_update, params={"market": "ALL"})
    report.ok("Subscribed to orders.ALL")

    fills_log: list[dict] = []

    async def _on_fill(_ch: ParadexWebsocketChannel, msg: dict) -> None:
        data = msg.get("params", {}).get("data", {})
        fills_log.append(data)
        logger.info(f"[WS FILL] market={data.get('market')} size={data.get('fill_size')} price={data.get('price')}")

    await ws.subscribe(ParadexWebsocketChannel.FILLS, _on_fill, params={"market": "ALL"})
    report.ok("Subscribed to fills.ALL")

    positions_log: list[dict] = []

    async def _on_position(_ch: ParadexWebsocketChannel, msg: dict) -> None:
        data = msg.get("params", {}).get("data", {})
        positions_log.append(data)
        logger.info(f"[WS POSITION] market={data.get('market')} size={data.get('size')}")

    await ws.subscribe(ParadexWebsocketChannel.POSITIONS, _on_position)
    report.ok("Subscribed to positions")

    await asyncio.sleep(1)

    # Verify clean slate before tests
    pre_open = _rest_open_orders(paradex)
    if pre_open is None:
        report.fail("PRE_EXISTING_ORDERS", "Startup check: REST error fetching open orders")
    elif pre_open:
        logger.warning(f"Startup: {len(pre_open)} pre-existing open orders — cancelling before tests")
        try:
            await ws.cancel_all_orders()
            await asyncio.sleep(2)
            post = _rest_open_orders(paradex) or []
            if post:
                report.fail("PRE_EXISTING_ORDERS", f"Startup cleanup incomplete: {len(post)} orders remain")
            else:
                report.ok(f"Startup: cleaned up {len(pre_open)} pre-existing orders")
        except Exception as exc:
            report.fail("PRE_EXISTING_ORDERS", f"Startup cleanup failed: {exc}")
    else:
        report.ok("Startup: no pre-existing open orders")

    try:
        await _run_test_suite(paradex, ws, tracker, report)
    finally:
        await _teardown(paradex, ws)

    logger.info(f"WS fills received: {len(fills_log)}  position updates: {len(positions_log)}")
    print(report.summary())
    return 0 if not report.issues else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
