"""SBE WebSocket example: markets summary + order book snapshot.

Connects with SBE binary encoding enabled (?sbeSchemaId=1&sbeSchemaVersion=0),
subscribes to:
  - markets_summary.<MARKET>  (24h rolling stats)
  - order_book.<MARKET>.snapshot@15@100ms  (top-15 levels, 100ms refresh)

Frames arrive as binary and are decoded into Pydantic models before the
callback receives them — the callback sees the same dict shape as JSON mode.

Usage:
    python examples/sbe_ws_market_data.py [--env testnet|nightly|prod] [--market BTC-USD-PERP]

No credentials needed (public channels).
"""

import argparse
import asyncio

from paradex_py import Paradex
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py.common.console_logging import console_logger
from paradex_py.environment import NIGHTLY, PROD, TESTNET, Environment

logger = console_logger

_ENVS: dict[str, Environment] = {"prod": PROD, "testnet": TESTNET, "nightly": NIGHTLY}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SBE WebSocket market data example")
    parser.add_argument(
        "--env",
        choices=list(_ENVS),
        default="testnet",
        help="Paradex environment (default: testnet)",
    )
    parser.add_argument(
        "--market",
        default="BTC-USD-PERP",
        help="Market symbol to subscribe to (default: BTC-USD-PERP)",
    )
    return parser.parse_args()


async def on_markets_summary(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    data = message["params"]["data"]
    logger.info(
        f"[markets_summary] {data.get('market')} "
        f"mark={data.get('mark_price')} "
        f"last={data.get('last_price')} "
        f"funding={data.get('funding_rate')} "
        f"ts={data.get('timestamp')}"
    )


async def on_order_book(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    data = message["params"]["data"]
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    best_bid = bids[0] if bids else None
    best_ask = asks[0] if asks else None
    logger.info(
        f"[order_book] {data.get('market')} "
        f"pkg={data.get('pkg_type')} "
        f"levels={len(bids)}b/{len(asks)}a "
        f"best_bid={best_bid} "
        f"best_ask={best_ask} "
        f"ts={data.get('timestamp')}"
    )


async def main(env: Environment, market: str) -> None:
    logger.info(f"Connecting to {env} (SBE enabled), market={market}")

    paradex = Paradex(
        env=env,
        logger=logger,
        ws_sbe_enabled=True,  # opt-in SBE binary encoding
        auto_start_ws_reader=True,
    )

    connected = False
    while not connected:
        connected = await paradex.ws_client.connect()
        if not connected:
            logger.info("Connection failed, retrying in 1s...")
            await asyncio.sleep(1)

    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.MARKETS_SUMMARY,
        callback=on_markets_summary,
        params={"market": market},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.ORDER_BOOK,
        callback=on_order_book,
        params={"market": market, "refresh_rate": "100ms"},
    )

    logger.info(f"Subscribed (SBE). Listening for {market} data...")
    await asyncio.get_event_loop().create_future()  # run forever


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(env=_ENVS[args.env], market=args.market))
