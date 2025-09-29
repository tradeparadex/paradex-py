#!/usr/bin/env python3
"""
Paradex Simulator Integration Example

Comprehensive example demonstrating all simulator-friendly features:
1. REST API injection with httpx MockTransport
2. WebSocket injection with custom connectors
3. Manual message pumping for deterministic processing
4. High-frequency mode (no artificial delays)
5. subscribe_by_name() for direct channel control
6. JSON-RPC 2.0 compliant WebSocket models

Perfect starting point for backtesting and simulation systems.
"""
import asyncio
import json
import time
from types import SimpleNamespace

import httpx

from paradex_py import Paradex
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.http_client import HttpClient
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import Environment

# Optional: WebSocket RPC models for typed message creation
try:
    from paradex_py.api.ws_models import (
        JSONRPCRequest,
        create_data_message,
        create_subscription_request,
        create_success_response,
    )

    WS_MODELS_AVAILABLE = True
except ImportError:
    WS_MODELS_AVAILABLE = False


class MockConnection:
    """Simple mock WebSocket connection."""

    def __init__(self, messages):
        self.messages = messages
        self.index = 0
        self.state = SimpleNamespace(value="OPEN")
        self.sent = []

    async def send(self, data: str):
        self.sent.append(json.loads(data))

    async def recv(self) -> str:
        if self.index >= len(self.messages):
            await asyncio.sleep(0.01)
            raise asyncio.TimeoutError()
        msg = self.messages[self.index]
        self.index += 1
        return msg

    async def close(self):
        self.state = SimpleNamespace(value="CLOSED")


def create_rest_simulator():
    """Create REST API simulator with httpx MockTransport."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/system/config"):
            return httpx.Response(200, json={"paraclear_decimals": 8})
        elif request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"results": [{"symbol": "BTC-USD-PERP"}]})
        return httpx.Response(404, json={"error": "not found"})

    mock_transport = httpx.MockTransport(handler)
    return HttpClient(http_client=httpx.Client(transport=mock_transport))


async def demo_rest_injection():
    """Demonstrate REST API injection."""
    print("=== REST API Injection ===")

    api_client = ParadexApiClient(
        env=Environment.TESTNET, http_client=create_rest_simulator(), api_base_url="https://simulator.example.com/v1"
    )

    try:
        api_client.fetch_system_config()
        markets = api_client.fetch_markets()
        print(f"✅ REST simulation: {len(markets.get('results', []))} markets")
    except Exception as e:
        print(f"❌ REST error: {e}")


async def demo_websocket_injection():
    """Demonstrate WebSocket injection with high-frequency processing."""
    print("\n=== WebSocket Injection + High-Frequency Mode ===")

    # Create market data messages
    messages = []
    for i in range(50):
        if WS_MODELS_AVAILABLE:
            # Use typed models if available
            msg = create_data_message(
                "bbo.BTC-USD-PERP",
                {"bid": str(50000 + i), "ask": str(50001 + i), "timestamp": str(int(time.time() * 1000) + i)},
            )
        else:
            # Fallback to manual JSON
            msg = json.dumps(
                {"params": {"channel": "bbo.BTC-USD-PERP"}, "data": {"bid": str(50000 + i), "ask": str(50001 + i)}}
            )
        messages.append(msg)

    async def mock_connector(url: str, headers: dict):
        return MockConnection(messages)

    # High-frequency WebSocket client (NO SLEEPS!)
    ws_client = ParadexWebsocketClient(
        env=Environment.TESTNET,
        auto_start_reader=False,  # Manual pumping
        connector=mock_connector,
        ws_url_override="wss://simulator.example.com/v1",
        reader_sleep_on_error=0,  # 🔥 No delays!
        reader_sleep_on_no_connection=0,  # 🔥 High frequency!
    )

    await ws_client.connect()

    # Track performance
    received = []

    async def handler(channel, message):
        received.append(message["data"])

    # Use subscribe_by_name for direct channel control
    await ws_client.subscribe_by_name("bbo.BTC-USD-PERP", handler)

    # High-speed message processing
    start_time = time.time()
    while len(received) < 50:
        result = await ws_client.pump_once()
        if not result:
            break
    end_time = time.time()

    processing_time = end_time - start_time
    rate = len(received) / processing_time if processing_time > 0 else float("inf")

    print(f"✅ Processed {len(received)} messages in {processing_time:.4f}s")
    print(f"✅ Rate: {rate:.0f} messages/second")
    print(f"✅ Average latency: {(processing_time/len(received))*1000:.2f}ms per message")

    await ws_client._close_connection()


async def demo_message_injection():
    """Demonstrate direct message injection."""
    print("\n=== Direct Message Injection ===")

    ws_client = ParadexWebsocketClient(env=Environment.TESTNET, auto_start_reader=False)

    injected = []

    async def handler(channel, message):
        injected.append(message)
        print(f"📥 Injected: {message['data']}")

    await ws_client.subscribe_by_name("trades.BTC-USD-PERP", handler)

    # Direct message injection (perfect for unit tests)
    test_messages = [
        json.dumps(
            {"params": {"channel": "trades.BTC-USD-PERP"}, "data": {"price": "50000", "size": "0.1", "side": "buy"}}
        ),
        json.dumps(
            {"params": {"channel": "trades.BTC-USD-PERP"}, "data": {"price": "50001", "size": "0.2", "side": "sell"}}
        ),
    ]

    for msg in test_messages:
        await ws_client.inject(msg)

    print(f"✅ Injected {len(injected)} messages directly")


async def demo_json_rpc_models():
    """Demonstrate JSON-RPC 2.0 compliant models."""
    if not WS_MODELS_AVAILABLE:
        print("\n=== JSON-RPC Models (SKIPPED - not available) ===")
        return

    print("\n=== JSON-RPC 2.0 Models ===")

    # Create subscription request with string ID (per JSON-RPC spec)
    sub_request = create_subscription_request("bbo.BTC-USD-PERP", "req_123")
    print(f"📤 Subscription: {sub_request}")

    # Create success response
    success = create_success_response("req_123", {"channel": "bbo.BTC-USD-PERP"})
    print(f"📥 Success: {success}")

    # Create data message
    data_msg = create_data_message("bbo.BTC-USD-PERP", {"bid": "50000", "ask": "50001"})
    print(f"📊 Data: {data_msg}")

    # Demonstrate correct ID types per JSON-RPC 2.0 spec
    request_models = [
        JSONRPCRequest(method="subscribe", id="string_id"),  # String
        JSONRPCRequest(method="subscribe", id=42),  # Integer
        JSONRPCRequest(method="subscribe", id=None),  # Null (notification)
    ]

    print("✅ JSON-RPC 2.0 ID types:")
    for i, req in enumerate(request_models, 1):
        print(f"  {i}. ID type: {type(req.id).__name__} = {req.id}")


async def demo_full_integration():
    """Complete integration example."""
    print("\n=== Full Integration Example ===")

    # Create market data
    market_data = [
        json.dumps({"params": {"channel": "bbo.BTC-USD-PERP"}, "data": {"bid": str(50000 + i), "ask": str(50001 + i)}})
        for i in range(5)
    ]

    async def full_connector(url: str, headers: dict):
        return MockConnection(market_data)

    # Full Paradex instance with all injections
    paradex = Paradex(
        env=Environment.TESTNET,
        # REST injection
        http_client=create_rest_simulator(),
        api_base_url="https://simulator.example.com/v1",
        # WebSocket injection (high-frequency mode)
        auto_start_ws_reader=False,
        ws_connector=full_connector,
        ws_url_override="wss://simulator.example.com/v1",
        ws_reader_sleep_on_error=0,  # No artificial delays
        ws_reader_sleep_on_no_connection=0,
    )

    # Test REST
    try:
        paradex.api_client.fetch_system_config()
        print("✅ REST: System config loaded")
    except Exception as e:
        print(f"❌ REST error: {e}")

    # Test WebSocket
    await paradex.ws_client.connect()

    updates = []

    async def update_handler(channel, message):
        updates.append(message["data"])

    await paradex.ws_client.subscribe_by_name("bbo.BTC-USD-PERP", update_handler)

    # Process all messages
    while len(updates) < 5:
        result = await paradex.ws_client.pump_once()
        if not result:
            break

    print(f"✅ WebSocket: {len(updates)} BBO updates received")
    await paradex.ws_client._close_connection()


async def main():
    """Run all simulator integration examples."""
    print("🚀 Paradex Simulator Integration")
    print("=" * 50)

    await demo_rest_injection()
    await demo_websocket_injection()
    await demo_message_injection()
    await demo_json_rpc_models()
    await demo_full_integration()

    print("\n" + "=" * 50)
    print("🎯 Key Features for Simulators:")
    print("1. 🔌 REST injection: httpx MockTransport + custom base URL")
    print("2. 🔌 WebSocket injection: custom connectors + URL override")
    print("3. ⚡ High-frequency mode: sleep_on_error=0, sleep_on_no_connection=0")
    print("4. 🎮 Manual control: auto_start_reader=False + pump_once()")
    print("5. 💉 Direct injection: inject() for unit testing")
    print("6. 🏷️  subscribe_by_name(): direct channel subscription")
    print("7. 📜 JSON-RPC 2.0: compliant WebSocket models")
    print("\n✨ Perfect for backtesting, simulation, and high-frequency trading!")


if __name__ == "__main__":
    asyncio.run(main())
