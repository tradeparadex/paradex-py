"""WebSocket order management example with Cancel-on-Disconnect.

This example shows how to submit, modify, and cancel orders over a persistent
WebSocket connection instead of the REST API, and how to arm Cancel-on-Disconnect
so open orders are automatically cancelled if the connection drops.

Key differences from REST:
  - All order methods are async and use the same connection as subscriptions.
  - Cancel-on-Disconnect (CoD) is session-scoped and OFF by default; call
    ``cancel_on_disconnect(True)`` after each (re)connect to arm it.
  - WsRpcError is raised when the server rejects a request (instead of httpx errors).

Usage:
    L1_ADDRESS=0x... L1_PRIVATE_KEY=0x... python examples/ws_order_management.py
"""

import asyncio
import logging
import os
from decimal import Decimal

from paradex_py import Paradex
from paradex_py.api.ws_client import ParadexWebsocketChannel, WsRpcError
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import TESTNET

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

L1_ADDRESS = os.environ["L1_ADDRESS"]
L1_PRIVATE_KEY = os.environ["L1_PRIVATE_KEY"]

MARKET = "ETH-USD-PERP"


async def on_order_update(ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    data = message.get("params", {}).get("data", {})
    logger.info(f"Order update: id={data.get('id')} status={data.get('status')} market={data.get('market')}")


async def main() -> None:
    paradex = Paradex(env=TESTNET, l1_address=L1_ADDRESS, l1_private_key=L1_PRIVATE_KEY)
    ws = paradex.ws_client

    # Connect and authenticate
    connected = await ws.connect()
    if not connected:
        raise RuntimeError("WebSocket connection failed")
    logger.info("Connected")

    # Subscribe to order updates so we see fills and status changes
    await ws.subscribe(ParadexWebsocketChannel.ORDERS, on_order_update, params={"market": "ALL"})

    # Arm Cancel-on-Disconnect for this session.
    # CoD is OFF by default and resets on every reconnect — re-enable after reconnects
    # if your application requires it.
    cod_result = await ws.cancel_on_disconnect(True)
    logger.info(f"Cancel-on-Disconnect enabled: {cod_result['enabled']}")

    # --- Submit a limit order ---
    order = Order(
        market=MARKET,
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.01"),
        limit_price=Decimal("1000"),  # well below market — won't fill
        instruction="GTC",
    )
    try:
        result = await ws.submit_order(order)
        order_id = result["order"]["id"]
        logger.info(f"Order created: id={order_id}")
    except WsRpcError as e:
        logger.error(f"submit_order failed: {e}")
        return

    # --- Modify the order (lower the price) ---
    modify_order = Order(
        market=MARKET,
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.01"),
        limit_price=Decimal("999"),
        instruction="GTC",
        order_id=order_id,
    )
    try:
        mod_result = await ws.modify_order(order_id, modify_order)
        logger.info(f"Order modified: id={mod_result['order']['id']}")
    except WsRpcError as e:
        logger.error(f"modify_order failed: {e}")

    # --- Cancel the order by ID ---
    try:
        cancel_result = await ws.cancel_order(order_id)
        logger.info(f"Order cancelled: {cancel_result}")
    except WsRpcError as e:
        logger.error(f"cancel_order failed: {e}")

    # --- Demonstrate cancel_all_orders (no-op if no open orders remain) ---
    try:
        all_result = await ws.cancel_all_orders(market=MARKET)
        logger.info(f"cancel_all_orders: {all_result}")
    except WsRpcError as e:
        logger.error(f"cancel_all_orders failed: {e}")

    # --- Disarm CoD before clean shutdown so the close doesn't trigger cancellations ---
    await ws.cancel_on_disconnect(False)
    logger.info("Cancel-on-Disconnect disabled")

    await ws.close()
    logger.info("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
