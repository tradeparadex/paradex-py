import asyncio
import os

from starknet_py.common import int_from_hex

from paradex_py import Paradex
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py.environment import TESTNET

# Environment variables
TEST_L1_ADDRESS = os.getenv("L1_ADDRESS", "")
TEST_L1_PRIVATE_KEY = int_from_hex(os.getenv("L1_PRIVATE_KEY", ""))
LOG_FILE = os.getenv("LOG_FILE", "FALSE").lower() == "true"


if LOG_FILE:
    from paradex_py.common.file_logging import file_logger

    logger = file_logger
    logger.info("Using file logger")
else:
    from paradex_py.common.console_logging import console_logger

    logger = console_logger
    logger.info("Using console logger")


async def callback_general(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    message.get("params", {}).get("channel")
    market = message.get("params", {}).get("data", {}).get("market")
    logger.info(f"callback_general(): Channel:{ws_channel} market:{market} message:{message}")


async def paradex_ws_subscribe(paradex: Paradex) -> None:
    """This function subscribes to all Websocket channels
    For market specific channels subscribe to ETH-USD-PERP market"""
    is_connected = False
    while not is_connected:
        is_connected = await paradex.ws_client.connect()
        if not is_connected:
            logger.info("connection failed, retrying in 1 second")
            await asyncio.sleep(1)
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.ACCOUNT,
        callback_general,
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.BALANCE_EVENTS,
        callback_general,
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.BBO,
        callback=callback_general,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.FILLS,
        callback=callback_general,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.FUNDING_DATA,
        callback=callback_general,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.FUNDING_PAYMENTS,
        callback=callback_general,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.FUNDING_RATE_COMPARISON,
        callback=callback_general,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.MARKETS_SUMMARY,
        callback=callback_general,
        params={"market": "BTC-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.ORDERS,
        callback=callback_general,
        params={"market": "ALL"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.ORDER_BOOK,
        callback=callback_general,
        params={"market": "ETH-USD-PERP", "refresh_rate": "100ms", "price_tick": "0_1", "depth": 15},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.POSITIONS,
        callback_general,
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.TRADES,
        callback=callback_general,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.TRADEBUSTS,
        callback_general,
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.TRANSACTIONS,
        callback_general,
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.TRANSFERS,
        callback_general,
    )


paradex = Paradex(
    env=TESTNET,
    l1_address=TEST_L1_ADDRESS,
    l1_private_key=TEST_L1_PRIVATE_KEY,
    logger=logger,
)

asyncio.get_event_loop().run_until_complete(paradex_ws_subscribe(paradex))
asyncio.get_event_loop().run_forever()
