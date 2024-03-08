import asyncio
import os

from starknet_py.common import int_from_hex

from paradex_py import Paradex
from paradex_py.api.ws_client import (
    ParadexWebsocketChannel,
    order_from_ws_message,
    paradex_channel_market,
    paradex_channel_suffix,
)
from paradex_py.environment import TESTNET

# Environment variables
TEST_L1_ADDRESS = os.getenv("L1_ADDRESS", "")
TEST_L1_PRIVATE_KEY = int_from_hex(os.getenv("L1_PRIVATE_KEY", ""))

if os.getenv("LOG_FILE", "FALSE").lower() == "true":
    from examples.file_logging import file_logger

    my_logger = file_logger
    my_logger.info("Using file logger")
else:
    from examples.shared import logger

    my_logger = logger
    my_logger.info("Using console logger")


async def handle_order(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    order = order_from_ws_message(message["params"]["data"])
    my_logger.info(f"handle_order(): Channel:{ws_channel} order:{order}")


async def handle_order_book(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    data = message["params"]["data"]
    message_channel = message["params"].get("channel")
    market = paradex_channel_market(message_channel)
    update_type = paradex_channel_suffix(message_channel)
    my_logger.info(f"handle_order_book(): Channel:{ws_channel} market:{market} update_type:{update_type} data:{data}")


async def handle_points_data(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    data = message["params"]["data"]
    message_channel = message["params"].get("channel")
    market = paradex_channel_market(message_channel)
    program = paradex_channel_suffix(message_channel)
    my_logger.info(f"handle_points_data(): Channel:{ws_channel} market:{market} program:{program} data:{data}")


async def handle_general_message(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    message_channel = message["params"].get("channel")
    market = paradex_channel_market(message_channel)
    my_logger.info(f"handle_general_message(): Channel:{ws_channel} market:{market} message:{message}")


async def paradex_ws_subscribe(paradex: Paradex) -> None:
    """This function subscribes to all Websocket channels
    For market specific channels subscribe to ETH-USD-PERP market"""
    await paradex.ws_client.connect()
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.ACCOUNT,
        handle_general_message,
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.BALANCE_EVENTS,
        handle_general_message,
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.BBO,
        callback=handle_general_message,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.FILLS,
        callback=handle_general_message,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.FUNDING_DATA,
        callback=handle_general_message,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.FUNDING_PAYMENTS,
        callback=handle_general_message,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.MARKETS_SUMMARY,
        callback=handle_general_message,
    )
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.ORDERS, callback=handle_order, params={"market": "ALL"})
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.ORDER_BOOK,
        callback=handle_order_book,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.ORDER_BOOK_DELTAS,
        callback=handle_order_book,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.POINTS_DATA,
        callback=handle_points_data,
        params={"market": "ETH-USD-PERP", "program": "LiquidityProvider"},
    )
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.POINTS_DATA,
        callback=handle_points_data,
        params={"market": "ETH-USD-PERP", "program": "Trader"},
    )
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.POSITIONS, handle_general_message)
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.TRADES,
        callback=handle_general_message,
        params={"market": "ETH-USD-PERP"},
    )
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.TRADEBUSTS, handle_general_message)
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.TRANSACTIONS, handle_general_message)
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.TRANSFERS, handle_general_message)


paradex = Paradex(
    env=TESTNET,
    l1_address=TEST_L1_ADDRESS,
    l1_private_key=TEST_L1_PRIVATE_KEY,
    logger=my_logger,
)

asyncio.get_event_loop().run_until_complete(paradex_ws_subscribe(paradex))
asyncio.get_event_loop().run_forever()
