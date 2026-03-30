"""Public WebSocket market data example: BBO, trades, order book.

Connects to the public WebSocket endpoint (no credentials required) and
subscribes to:
  - bbo.<MARKET>                              (best bid/ask)
  - trades.<MARKET>                           (live trade feed)
  - order_book.<MARKET>.snapshot@15@100ms     (top-15 levels, 100ms refresh)

Pass --latency to compare delivery latency between the public and direct WS
endpoints side-by-side (subscribes BBO on both, prints stats every 10s).

Usage:
    uv run python examples/public_ws_market_data.py
    uv run python examples/public_ws_market_data.py --env prod --market BTC-USD-PERP
    uv run python examples/public_ws_market_data.py --latency
"""

import argparse
import asyncio
import statistics
import time

from paradex_py import Paradex
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py.common.console_logging import console_logger
from paradex_py.environment import NIGHTLY, PROD, TESTNET, Environment

logger = console_logger

_ENVS: dict[str, Environment] = {"prod": PROD, "testnet": TESTNET, "nightly": NIGHTLY}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Public WebSocket market data example")
    parser.add_argument(
        "--env",
        choices=list(_ENVS),
        default="prod",
        help="Paradex environment (default: prod)",
    )
    parser.add_argument(
        "--market",
        default="BTC-USD-PERP",
        help="Market symbol to subscribe to (default: BTC-USD-PERP)",
    )
    parser.add_argument(
        "--latency",
        action="store_true",
        help="Compare delivery latency between public and direct WS endpoints",
    )
    return parser.parse_args()


async def on_bbo(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    data = message["params"]["data"]
    logger.info(
        f"[bbo] {data.get('market')} "
        f"bid={data.get('bid')} ({data.get('bid_size')}) "
        f"ask={data.get('ask')} ({data.get('ask_size')})"
    )


async def on_trades(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    data = message["params"]["data"]
    logger.info(
        f"[trades] {data.get('market')} "
        f"side={data.get('side')} "
        f"price={data.get('price')} "
        f"size={data.get('size')} "
        f"ts={data.get('created_at')}"
    )


async def on_order_book(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    data = message["params"]["data"]
    inserts = data.get("inserts", [])
    bids = [e for e in inserts if e.get("side") == "BUY"]
    asks = [e for e in inserts if e.get("side") == "SELL"]
    best_bid = bids[0] if bids else None
    best_ask = asks[0] if asks else None
    logger.info(
        f"[order_book] {data.get('market')} "
        f"type={data.get('update_type')} "
        f"inserts={len(bids)}b/{len(asks)}a "
        f"best_bid={best_bid} "
        f"best_ask={best_ask}"
    )


def _latency_stats(samples: list[float]) -> str:
    if not samples:
        return "n=0"
    n = len(samples)
    mean = statistics.mean(samples)
    p50 = statistics.median(samples)
    p95 = sorted(samples)[int(n * 0.95)]
    mn = min(samples)
    mx = max(samples)
    return f"n={n} mean={mean:.1f}ms p50={p50:.1f}ms p95={p95:.1f}ms min={mn:.1f}ms max={mx:.1f}ms"


async def run_latency_comparison(env: Environment, market: str) -> None:
    """Subscribe to BBO on both public and direct WS endpoints and compare delivery latency."""
    paradex = Paradex(env=env, logger=logger)

    samples: dict[str, list[float]] = {"public": [], "direct": []}

    def make_bbo_cb(endpoint: str):
        async def cb(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
            recv_ms = time.time() * 1000
            server_ms = message["params"]["data"].get("last_updated_at")
            if server_ms:
                samples[endpoint].append(recv_ms - server_ms)

        return cb

    for client, name in [(paradex.ws_client, "public"), (paradex.ws_direct_client, "direct")]:
        connected = False
        while not connected:
            connected = await client.connect()
            if not connected:
                await asyncio.sleep(1)
        logger.info(f"Connected to {client.api_url} [{name}]")
        await client.subscribe(
            ParadexWebsocketChannel.BBO,
            callback=make_bbo_cb(name),
            params={"market": market},
        )

    logger.info("Subscribed to BBO on both endpoints. Reporting stats every 10s... (Ctrl+C to stop)")

    while True:
        await asyncio.sleep(10)
        for endpoint in ("public", "direct"):
            s = samples[endpoint]
            logger.info(f"[latency/{endpoint}] {_latency_stats(s)}")
            samples[endpoint] = []  # reset window


async def run_subscriptions(env: Environment, market: str) -> None:
    paradex = Paradex(env=env, logger=logger)

    connected = False
    while not connected:
        connected = await paradex.ws_client.connect()
        if not connected:
            logger.info("Connection failed, retrying in 1s...")
            await asyncio.sleep(1)

    logger.info(f"Connected to {paradex.ws_client.api_url}")

    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.BBO,
        callback=on_bbo,
        params={"market": market},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.TRADES,
        callback=on_trades,
        params={"market": market},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.ORDER_BOOK,
        callback=on_order_book,
        params={"market": market, "refresh_rate": "100ms"},
    )

    logger.info(f"Subscribed. Listening for {market} data... (Ctrl+C to stop)")
    await asyncio.get_event_loop().create_future()  # run forever


if __name__ == "__main__":
    args = _parse_args()
    env = _ENVS[args.env]
    if args.latency:
        asyncio.run(run_latency_comparison(env=env, market=args.market))
    else:
        asyncio.run(run_subscriptions(env=env, market=args.market))
