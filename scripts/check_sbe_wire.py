#!/usr/bin/env python3
"""Check live SBE frames against the vendored schema, with no credentials.

check_sbe_schema.py compares the vendored XML with the upstream schema, which
needs access to where that lives. This compares it with what a server actually
sends, which does not: it connects to an environment's public feed at a given schema
version, subscribes to every public channel, and checks each raw frame's
layout against paradex_1_0.xml before decoding it.

Per frame it fails on:
  - a blockLength longer than the schema's block at that version (the server
    sends fixed fields this schema does not have)
  - bytes left over after the last var-data field the schema knows (the server
    sends appended var-data this schema does not have)
  - a frame decode_frame rejects

A blockLength shorter than the schema's, or appended var-data missing at the
end of the frame, is reported but is not a failure: it is what a server that
predates an in-place 1:2 addition sends, and the decoder tolerates it.

For trades it also checks that trade_id_str carries a full id: the int64
trade_id must equal its low 64 bits, and the two must differ once the id is
past int64.

Only public templates (1-6) can be checked this way; orders, fills, positions
and account need an authenticated session. A version above the decoder's is
also probed, and a server that accepts it is reported, since that means a
newer schema is being served.

Usage:
    uv run python scripts/check_sbe_wire.py [--env nightly|testnet|prod] [--version 2]
        [--market BTC-USD-PERP] [--seconds 20] [--min-trades 1]

Exit status: 0 when every frame matched, 1 on any mismatch, 2 if no frames
arrived or the connection failed.
"""

import argparse
import asyncio
import json
import logging
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_sbe_decoder import _field_struct_char, parse_schema

from paradex_py.api.sbe import decode_frame
from paradex_py.api.sbe.codec import _SCHEMA_ID, _SCHEMA_VERSION

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "paradex_py" / "api" / "sbe" / "paradex_1_0.xml"
_HEADER = struct.Struct("<HHHH")
_GROUP_HDR = struct.Struct("<HH")
_PUBLIC_TEMPLATES = {1, 2, 3, 4, 5, 6}


def _layouts(schema: dict) -> dict:
    """templateId → (name, fields [(since, size)], groups, data sinceVersions)."""
    out = {}
    for msg in schema["messages"]:
        fields = [
            (f["since"], struct.calcsize("<" + _field_struct_char(f["type"], schema["enums"], schema["enum_encoding"])))
            for f in msg["fields"]
        ]
        out[msg["id"]] = (msg["name"], fields, len(msg["groups"]), [d["since"] for d in msg["data"]])
    return out


def _int64_wrap(n: int) -> int:
    low = n & 0xFFFF_FFFF_FFFF_FFFF
    return low - (1 << 64) if low >= 1 << 63 else low


def check_frame(data: bytes, layouts: dict, stats: dict) -> list[str]:  # noqa: C901
    """Return the problems with one frame; record tolerated shortfalls in stats."""
    block_len, tmpl_id, schema_id, version = _HEADER.unpack_from(data, 0)
    if schema_id != _SCHEMA_ID:
        return [f"schemaId {schema_id}, expected {_SCHEMA_ID}"]
    if tmpl_id not in layouts:
        return [f"templateId {tmpl_id} is not in the schema"]
    name, fields, n_groups, data_since = layouts[tmpl_id]
    label = f"{name}({tmpl_id})@v{version}"

    expected_block = sum(size for since, size in fields if since <= version)
    problems = []
    if block_len > expected_block:
        problems.append(f"{label}: blockLength {block_len} > schema's {expected_block} (unknown fixed fields)")
    elif block_len < expected_block:
        stats["short_block"][f"{label}: blockLength {block_len} < {expected_block}"] += 1

    payload = data[8:]
    offset = block_len
    try:
        for _ in range(n_groups):
            entry_len, count = _GROUP_HDR.unpack_from(payload, offset)
            offset += 4 + entry_len * count
        for i, since in enumerate(data_since):
            if since > version:
                break
            if offset >= len(payload) and since > 0:
                stats["absent_var"][f"{label}: var-data #{i} absent"] += 1
                break
            offset += 1 + payload[offset]
    except (IndexError, struct.error) as exc:
        return [*problems, f"{label}: walk failed: {exc}"]
    if offset < len(payload):
        problems.append(f"{label}: {len(payload) - offset} unknown trailing bytes (unknown var-data)")
    elif offset > len(payload):
        problems.append(f"{label}: var-data runs {offset - len(payload)} bytes past the frame")

    try:
        _channel, model = decode_frame(data)
    except Exception as exc:
        return [*problems, f"{label}: decode_frame failed: {exc}"]

    if tmpl_id == 1 and model is not None:
        stats["trades"] += 1
        tid_str = getattr(model, "trade_id_str", None)
        if version >= 2 and tid_str is not None:
            dumped = model.model_dump()
            stats["trade_ids"].append((tid_str, dumped["trade_id"]))
            if not tid_str.isdigit():
                problems.append(f"{label}: trade_id_str {tid_str!r} is not a decimal id")
            elif _int64_wrap(int(tid_str)) != dumped["trade_id"]:
                problems.append(f"{label}: int64 trade_id {dumped['trade_id']} is not the low 64 bits of {tid_str}")
    return problems


def _channels(market: str) -> list[str]:
    return [
        f"trades.{market}",
        f"bbo.{market}",
        f"order_book.{market}.snapshot@15@100ms",
        f"markets_summary.{market}",
        f"funding_data.{market}",
        "funding_rate_comparison.ALL@1000ms",
    ]


def _url(env: str, version: int) -> str:
    return f"wss://ws.api.{env}.paradex.trade/v1?sbeSchemaId={_SCHEMA_ID}&sbeSchemaVersion={version}"


async def probe_newer(env: str) -> bool:
    """True if the server accepts a version above the decoder's."""
    try:
        async with websockets.connect(_url(env, _SCHEMA_VERSION + 1), open_timeout=10):
            return True
    except Exception:
        return False


async def run(env: str, version: int, market: str, seconds: float, min_trades: int) -> int:  # noqa: C901
    layouts = _layouts(parse_schema(str(SCHEMA_PATH)))
    stats: dict = {"short_block": Counter(), "absent_var": Counter(), "trades": 0, "trade_ids": []}
    per_template: Counter = Counter()
    problems: dict[str, int] = defaultdict(int)
    url = _url(env, version)
    print(f"Connecting to {url}")
    try:
        async with websockets.connect(url, open_timeout=15, max_size=None) as ws:
            for i, channel in enumerate(_channels(market)):
                await ws.send(
                    json.dumps({"jsonrpc": "2.0", "id": i, "method": "subscribe", "params": {"channel": channel}})
                )
            loop = asyncio.get_running_loop()
            deadline = loop.time() + seconds
            while (remaining := deadline - loop.time()) > 0:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                if isinstance(msg, str):
                    if '"error"' in msg:
                        print(f"  server error: {msg[:200]}")
                    continue
                tmpl_id = _HEADER.unpack_from(msg, 0)[1] if len(msg) >= 8 else -1
                per_template[tmpl_id] += 1
                hdr_version = _HEADER.unpack_from(msg, 0)[3] if len(msg) >= 8 else -1
                if hdr_version != version:
                    problems[f"header version {hdr_version}, negotiated {version}"] += 1
                for p in check_frame(msg, layouts, stats):
                    problems[p] += 1
    except Exception as exc:
        print(f"Connection failed: {exc!r}")
        return 2

    print(f"Frames per templateId: {dict(sorted(per_template.items()))}")
    for label, n in {**stats["short_block"], **stats["absent_var"]}.items():
        print(f"  tolerated ({n}x): {label}")
    for tid_str, tid_int in stats["trade_ids"][:3]:
        print(f"  trade_id_str={tid_str} ({len(tid_str)} digits)  int64 trade_id={tid_int}")
    if version >= 2 and stats["trades"] and not stats["trade_ids"]:
        print("  note: no trade at v2 carried trade_id_str (server predates it?)")

    if await probe_newer(env):
        print(f"  NOTE: {env} accepts sbeSchemaVersion={_SCHEMA_VERSION + 1}; a newer schema is being served")

    if not per_template:
        print("FAIL: no SBE frames arrived")
        return 2
    missing = _PUBLIC_TEMPLATES - set(per_template)
    if missing:
        print(f"  not seen in {seconds:.0f}s: templateIds {sorted(missing)}")
    if stats["trades"] < min_trades:
        print(f"FAIL: {stats['trades']} trades seen, wanted at least {min_trades}; rerun with more --seconds")
        return 2
    if problems:
        for p, n in problems.items():
            print(f"FAIL ({n}x): {p}")
        return 1
    print(f"OK: {sum(per_template.values())} frames at v{version} match the schema")
    return 0


def main() -> None:
    # websockets logs a keepalive traceback when a busy feed is closed mid-burst.
    logging.getLogger("websockets").setLevel(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--env", default="prod", choices=["prod", "testnet", "nightly"])
    parser.add_argument("--version", type=int, default=_SCHEMA_VERSION, help="schema version to negotiate")
    parser.add_argument("--market", default="BTC-USD-PERP")
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--min-trades", type=int, default=1, help="fail if fewer trades arrive (0 to skip)")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.env, args.version, args.market, args.seconds, args.min_trades)))


if __name__ == "__main__":
    main()
