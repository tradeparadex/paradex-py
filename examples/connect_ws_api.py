import asyncio
import os
import time
from decimal import Decimal

from starknet_py.common import int_from_hex

from examples.shared import logger
from paradex_py import Paradex
from paradex_py.api.ws_client import (
    ParadexWebsocketChannel,
    get_ws_channel_from_name,
    paradex_channel_market,
    paradex_channel_suffix,
)
from paradex_py.common.order import Order, OrderSide, OrderStatus, OrderType
from paradex_py.environment import TESTNET

# Environment variables
TEST_L1_ADDRESS = os.getenv("L1_ADDRESS", "")
TEST_L1_PRIVATE_KEY = int_from_hex(os.getenv("L1_PRIVATE_KEY", ""))


def order_from_ws_message(msg: dict) -> Order:
    """
    Creates an Order object from a Paradex websocket message.
    """
    client_id = msg["client_id"] if msg["client_id"] else msg["id"]
    order = Order(
        market=msg["market"],
        order_type=OrderType(msg["type"]),
        order_side=OrderSide(msg["side"]),
        size=Decimal(msg["size"]),
        limit_price=Decimal(msg["price"]),
        client_id=client_id,
        instruction=msg.get("instruction", "GTC"),
        reduce_only=bool("REDUCE_ONLY" in msg.get("flags", [])),
    )
    order.id = msg["id"]
    order.status = OrderStatus(msg["status"])
    order.account = msg["account"]
    order.remaining = Decimal(msg["remaining_size"])
    order.created_at = int(msg["created_at"])
    order.cancel_reason = msg["cancel_reason"]
    return order


async def paradex_ws_subscribe(paradex: Paradex) -> None:
    await paradex.ws_client.connect()
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.ACCOUNT)
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.BALANCE_EVENTS)
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.BBO, "ETH-USD-PERP")
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.FILLS, "ETH-USD-PERP")
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.FUNDING_DATA, "ETH-USD-PERP")
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.FUNDING_PAYMENTS, "ETH-USD-PERP")
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY)
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.ORDERS, "ALL")
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.ORDER_BOOK, "ETH-USD-PERP")
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.ORDER_BOOK_DELTAS, "ETH-USD-PERP")
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.POINTS_DATA, "ETH-USD-PERP", "LiquidityProvider")
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.POINTS_DATA, "ETH-USD-PERP", "Trader")
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.POSITIONS)
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.TRADES, "ETH-USD-PERP")
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.TRADEBUSTS)
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.TRANSACTIONS)
    await paradex.ws_client.subscribe(ParadexWebsocketChannel.TRANSFERS)


# Assumes paradex has L1 address and private key
async def paradex_ws_test(paradex: Paradex):
    try:
        await paradex_ws_subscribe(paradex)
        async for message in paradex.ws_client.read_messages():
            if "params" not in message:
                logger.info(f"Non-actionable {message}")
            else:
                message_channel = message["params"].get("channel")
                logger.info(f"Channel: {message_channel} message:{message}")
                ws_channel = get_ws_channel_from_name(message_channel)
                if ws_channel is None:
                    logger.info(f"Non-actionable channel:{message_channel} {message}")
                else:
                    if ws_channel == ParadexWebsocketChannel.ORDERS:
                        data = order_from_ws_message(message["params"]["data"])
                    else:
                        data = message["params"]["data"]
                    market = paradex_channel_market(message_channel)
                    if ws_channel == ParadexWebsocketChannel.ORDER_BOOK:
                        update_type = paradex_channel_suffix(message_channel)
                        logger.info(f"Order Book update_type:{update_type}")
                    program = (
                        paradex_channel_suffix(message_channel)
                        if ws_channel == ParadexWebsocketChannel.POINTS_DATA
                        else ""
                    )
                    logger.info(f"Channel:{ws_channel}  Market:{market} Program:{program} data:{data}")
    except Exception:
        logger.exception("Connection closed unexpectedly:")
        time.sleep(1)
        await paradex_ws_test()


paradex = Paradex(
    env=TESTNET,
    l1_address=TEST_L1_ADDRESS,
    l1_private_key=TEST_L1_PRIVATE_KEY,
    logger=logger,
)

asyncio.get_event_loop().run_until_complete(paradex_ws_test(paradex))
