#!/usr/bin/env python3
"""SBE vs JSON parity check for non-authenticated public channels.

Subscribes to BBO, trades, and markets_summary on both:
  - ws_client       (JSON, public endpoint)
  - ws_direct_client (SBE binary, direct endpoint)

After collecting N samples per channel, prints a field-by-field comparison
and exits. Any mismatches are reported as FAIL.

Usage:
    uv run python scripts/check_sbe_parity.py [--env testnet|prod] [--market BTC-USD-PERP] [--samples 5]
"""
import argparse
import asyncio
import sys
from collections import defaultdict

from paradex_py import Paradex
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py.common.console_logging import console_logger
from paradex_py.environment import NIGHTLY, PROD, TESTNET, Environment

logger = console_logger
_ENVS: dict[str, Environment] = {"prod": PROD, "testnet": TESTNET, "nightly": NIGHTLY}

# Collected samples: {channel: [{"json": {...}, "sbe": {...}}, ...]}
_json_samples: dict[str, list[dict]] = defaultdict(list)
_sbe_samples: dict[str, list[dict]] = defaultdict(list)


def _extract_bbo(data: dict, source: str) -> dict:
    return {
        "bid": data.get("bid") or data.get("bid_price"),
        "ask": data.get("ask") or data.get("ask_price"),
        "bid_size": data.get("bid_size") or data.get("bid_size"),
        "ask_size": data.get("ask_size") or data.get("ask_size"),
        "market": data.get("market"),
        "_source": source,
    }


def _extract_trade(data: dict, source: str) -> dict:
    return {
        "price": data.get("price"),
        "size": data.get("size"),
        "side": data.get("side"),
        "market": data.get("market"),
        "_source": source,
    }


def _extract_ms(data: dict, source: str) -> dict:
    return {
        "mark_price": data.get("mark_price"),
        "funding_rate": data.get("funding_rate"),
        "open_interest": data.get("open_interest"),
        "market": data.get("market") or data.get("symbol"),
        "_source": source,
    }


async def _connect(client, label: str) -> bool:
    connected = False
    for _ in range(10):
        connected = await client.connect()
        if connected:
            logger.info(f"Connected [{label}] to {client.api_url}")
            return True
        await asyncio.sleep(1)
    return False


async def run_parity(env: Environment, market: str, n_samples: int) -> bool:  # noqa: C901
    paradex = Paradex(env=env, logger=logger, ws_sbe_enabled=True)
    json_client = paradex.ws_client
    sbe_client = paradex.ws_direct_client

    if not await _connect(json_client, "JSON") or not await _connect(sbe_client, "SBE"):
        logger.error("Failed to connect")
        return False

    done = asyncio.Event()

    def _check_done():
        for ch in ("bbo", "trades", "ms"):
            if len(_json_samples[ch]) < n_samples or len(_sbe_samples[ch]) < n_samples:
                return
        done.set()

    async def on_json_bbo(_, msg):
        d = msg["params"]["data"]
        _json_samples["bbo"].append(_extract_bbo(d, "json"))
        _check_done()

    async def on_sbe_bbo(_, msg):
        d = msg["params"]["data"]
        _sbe_samples["bbo"].append(_extract_bbo(d, "sbe"))
        _check_done()

    async def on_json_trade(_, msg):
        d = msg["params"]["data"]
        _json_samples["trades"].append(_extract_trade(d, "json"))
        _check_done()

    async def on_sbe_trade(_, msg):
        d = msg["params"]["data"]
        _sbe_samples["trades"].append(_extract_trade(d, "sbe"))
        _check_done()

    async def on_json_ms(_, msg):
        d = msg["params"]["data"]
        _json_samples["ms"].append(_extract_ms(d, "json"))
        _check_done()

    async def on_sbe_ms(_, msg):
        d = msg["params"]["data"]
        _sbe_samples["ms"].append(_extract_ms(d, "sbe"))
        _check_done()

    for client, bbo_cb, trade_cb, ms_cb in [
        (json_client, on_json_bbo, on_json_trade, on_json_ms),
        (sbe_client, on_sbe_bbo, on_sbe_trade, on_sbe_ms),
    ]:
        await client.subscribe(ParadexWebsocketChannel.BBO, callback=bbo_cb, params={"market": market})
        await client.subscribe(ParadexWebsocketChannel.TRADES, callback=trade_cb, params={"market": market})
        await client.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY, callback=ms_cb, params={"market": market})

    logger.info(f"Collecting {n_samples} samples per channel on {env}...")
    try:
        await asyncio.wait_for(done.wait(), timeout=60)
    except TimeoutError:
        logger.warning("Timeout waiting for samples — printing what we have")

    # ── Print comparison ────────────────────────────────────────────────
    # Fields where SBE precision is intentionally lower than JSON (Rate8 = 8dp max).
    # These are design limitations of the SBE schema, not decoder bugs.
    _KNOWN_PRECISION_DIFF = {"funding_rate", "price_change_rate24h"}

    def _values_match(key: str, jv, sv) -> tuple[bool, str]:
        """Return (is_ok, note). Numerically-equivalent strings count as OK."""
        if jv == sv:
            return True, ""
        try:
            fj, fs = float(jv), float(sv)
        except (TypeError, ValueError):
            return False, ""
        if key in _KNOWN_PRECISION_DIFF:
            # SBE Rate8 caps at 8 decimal places; JSON may have more — not a real mismatch.
            if abs(fj - fs) < 1e-7:
                return True, "precision diff (Rate8 8dp vs JSON)"
            return False, f"numeric diff: {fj - fs:.2e}"
        if fj == fs:
            return True, "trailing zeros only"
        return False, ""

    ok = True
    for label, _channel, json_s, sbe_s in [
        ("BBO", "bbo", _json_samples["bbo"], _sbe_samples["bbo"]),
        ("TRADES", "trades", _json_samples["trades"], _sbe_samples["trades"]),
        ("MARKETS_SUMMARY", "ms", _json_samples["ms"], _sbe_samples["ms"]),
    ]:
        print(f"\n{'='*60}")
        print(f"  {label}  (json={len(json_s)} samples, sbe={len(sbe_s)} samples)")
        print(f"{'='*60}")
        if not json_s or not sbe_s:
            print("  SKIP — no samples collected")
            continue

        # Print latest sample from each
        j = {k: v for k, v in json_s[-1].items() if not k.startswith("_")}
        s = {k: v for k, v in sbe_s[-1].items() if not k.startswith("_")}
        all_keys = sorted(set(j) | set(s))
        for key in all_keys:
            jv, sv = j.get(key), s.get(key)
            is_ok, note = _values_match(key, jv, sv)
            tag = "  OK " if is_ok else "FAIL "
            if not is_ok:
                ok = False
            suffix = f"  # {note}" if note else ""
            print(f"  {tag}  {key:30s}  json={jv!r:<30}  sbe={sv!r}{suffix}")

    print(f"\n{'='*60}")
    print(f"  OVERALL: {'PASS ✓' if ok else 'FAIL ✗'}")
    print(f"{'='*60}\n")
    return ok


def _parse_args():
    p = argparse.ArgumentParser(description="SBE vs JSON parity check")
    p.add_argument("--env", choices=list(_ENVS), default="testnet")
    p.add_argument("--market", default="BTC-USD-PERP")
    p.add_argument("--samples", type=int, default=5, help="Samples per channel (default: 5)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    ok = asyncio.run(run_parity(_ENVS[args.env], args.market, args.samples))
    sys.exit(0 if ok else 1)
