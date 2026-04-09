"""Tests for WebSocket order management methods on ParadexWebsocketClient."""

import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from paradex_py.api.ws_client import ParadexWebsocketClient, WsRpcError
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import TESTNET

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws_client() -> ParadexWebsocketClient:
    """Create a ws_client with auto_start_reader=False to avoid background tasks."""
    return ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)


def _make_open_ws(sent: list[str]) -> MagicMock:
    """Return a mock WebSocket that records sent messages."""
    from websockets import State

    ws = MagicMock()
    ws.state = State.OPEN
    ws.send = AsyncMock(side_effect=lambda msg: sent.append(msg))
    return ws


def _make_order(order_id: str | None = None) -> Order:
    return Order(
        market="BTC-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal("50000"),
        client_id="test-client-id",
        order_id=order_id,
    )


def _inject_response(
    ws_client: ParadexWebsocketClient, msg_id: int, result: dict | None = None, error: dict | None = None
) -> None:
    """Resolve the pending future for *msg_id* as if the server replied."""
    future = ws_client._pending_requests.get(msg_id)
    if future is None or future.done():
        return
    response: dict = {"id": msg_id, "jsonrpc": "2.0"}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = result or {}
    future.set_result(response)


# ---------------------------------------------------------------------------
# WsRpcError
# ---------------------------------------------------------------------------


def test_ws_rpc_error_attributes():
    err = WsRpcError({"code": 403, "message": "permission denied", "data": "extra"})
    assert err.code == 403
    assert err.message == "permission denied"
    assert err.data == "extra"
    assert "403" in str(err)
    assert "permission denied" in str(err)


def test_ws_rpc_error_missing_fields():
    err = WsRpcError({})
    assert err.code is None
    assert err.message == ""
    assert err.data is None


# ---------------------------------------------------------------------------
# _send_request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_request_success():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    result_payload = {"status": "ok"}

    async def inject():
        # Wait until the request is registered then resolve it
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result=result_payload)

    task = asyncio.create_task(inject())
    result = await ws_client._send_request("order.cancel_all", {})
    await task

    assert result == result_payload
    assert len(sent) == 1
    sent_msg = json.loads(sent[0])
    assert sent_msg["method"] == "order.cancel_all"
    assert sent_msg["jsonrpc"] == "2.0"
    assert "id" in sent_msg


@pytest.mark.asyncio
async def test_send_request_raises_ws_rpc_error_on_error_response():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, error={"code": 400, "message": "bad request"})

    task = asyncio.create_task(inject())
    with pytest.raises(WsRpcError) as exc_info:
        await ws_client._send_request("order.create", {})
    await task

    assert exc_info.value.code == 400


@pytest.mark.asyncio
async def test_send_request_timeout_cleans_up():
    ws_client = _make_ws_client()
    ws_client.ws = _make_open_ws([])

    with pytest.raises(asyncio.TimeoutError):
        await ws_client._send_request("order.create", {}, timeout=0.01)

    # Future should be cleaned up after timeout
    assert len(ws_client._pending_requests) == 0


# ---------------------------------------------------------------------------
# _check_subscribed_channel routes pending futures
# ---------------------------------------------------------------------------


def test_check_subscribed_channel_resolves_pending_future():
    ws_client = _make_ws_client()
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        ws_client._pending_requests[42] = future

        message = {"id": 42, "jsonrpc": "2.0", "result": {"order_id": "123", "status": "cancelled"}}
        ws_client._check_subscribed_channel(message)

        assert future.done()
        assert future.result() == message
        assert 42 not in ws_client._pending_requests
    finally:
        loop.close()


def test_check_subscribed_channel_ignores_subscription_acks():
    ws_client = _make_ws_client()
    loop = asyncio.new_event_loop()
    try:
        # Subscription ack with no matching pending request
        message = {"id": 999, "jsonrpc": "2.0", "result": {"channel": "orders.BTC-USD-PERP"}}
        # Should not raise; pending_requests unchanged
        ws_client._check_subscribed_channel(message)
        assert len(ws_client._pending_requests) == 0
        assert ws_client.subscribed_channels.get("orders.BTC-USD-PERP") is True
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# submit_order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_order_with_account():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    mock_account = MagicMock()
    mock_account.sign_order.return_value = '["r","s"]'
    ws_client.account = mock_account

    order = _make_order()
    server_result = {"order": {"id": "srv-id"}, "created_at": 1000, "received_at": 2000}

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result=server_result)

    task = asyncio.create_task(inject())
    result = await ws_client.submit_order(order)
    await task

    assert result == server_result
    sent_msg = json.loads(sent[0])
    assert sent_msg["method"] == "order.create"
    assert sent_msg["params"]["market"] == "BTC-USD-PERP"
    mock_account.sign_order.assert_called_once_with(order)


@pytest.mark.asyncio
async def test_submit_order_with_signer():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    mock_signer = MagicMock()
    mock_signer.sign_order.return_value = {"market": "BTC-USD-PERP", "signature": "sig"}

    order = _make_order()

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result={"order": {}})

    task = asyncio.create_task(inject())
    await ws_client.submit_order(order, signer=mock_signer)
    await task

    mock_signer.sign_order.assert_called_once()


@pytest.mark.asyncio
async def test_submit_order_raises_without_account_or_signer():
    ws_client = _make_ws_client()
    ws_client.ws = _make_open_ws([])

    with pytest.raises(ValueError, match="Account not initialized"):
        await ws_client.submit_order(_make_order())


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_order_sends_correct_params():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result={"order_id": "abc", "status": "cancelled"})

    task = asyncio.create_task(inject())
    result = await ws_client.cancel_order("abc")
    await task

    sent_msg = json.loads(sent[0])
    assert sent_msg["method"] == "order.cancel"
    assert sent_msg["params"] == {"id": "abc"}
    assert result["status"] == "cancelled"


# ---------------------------------------------------------------------------
# cancel_order_by_client_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_order_by_client_id_sends_correct_params():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result={"order_id": "abc", "status": "cancelled"})

    task = asyncio.create_task(inject())
    await ws_client.cancel_order_by_client_id("my-id", "BTC-USD-PERP")
    await task

    sent_msg = json.loads(sent[0])
    assert sent_msg["method"] == "order.cancel"
    assert sent_msg["params"] == {"client_id": "my-id", "market": "BTC-USD-PERP"}


# ---------------------------------------------------------------------------
# cancel_all_orders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_all_orders_no_market():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result={"status": "ok"})

    task = asyncio.create_task(inject())
    result = await ws_client.cancel_all_orders()
    await task

    sent_msg = json.loads(sent[0])
    assert sent_msg["method"] == "order.cancel_all"
    assert sent_msg["params"] == {}
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_cancel_all_orders_with_market():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result={"status": "ok"})

    task = asyncio.create_task(inject())
    await ws_client.cancel_all_orders(market="ETH-USD-PERP")
    await task

    sent_msg = json.loads(sent[0])
    assert sent_msg["params"] == {"market": "ETH-USD-PERP"}


# ---------------------------------------------------------------------------
# cancel_orders_batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_orders_batch_sends_correct_params():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    order_ids = ["id1", "id2", "id3"]

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result={"results": []})

    task = asyncio.create_task(inject())
    await ws_client.cancel_orders_batch(order_ids)
    await task

    sent_msg = json.loads(sent[0])
    assert sent_msg["method"] == "order.cancel_batch"
    assert sent_msg["params"] == {"order_ids": order_ids}


# ---------------------------------------------------------------------------
# modify_order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_modify_order_includes_order_id_in_params():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    mock_account = MagicMock()
    mock_account.sign_order.return_value = '["r","s"]'
    ws_client.account = mock_account

    order = _make_order()

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result={"order": {}})

    task = asyncio.create_task(inject())
    await ws_client.modify_order("existing-id", order)
    await task

    sent_msg = json.loads(sent[0])
    assert sent_msg["method"] == "order.modify"
    assert sent_msg["params"]["id"] == "existing-id"


# ---------------------------------------------------------------------------
# cancel_on_disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_on_disconnect_enable():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result={"enabled": True})

    task = asyncio.create_task(inject())
    result = await ws_client.cancel_on_disconnect(True)
    await task

    sent_msg = json.loads(sent[0])
    assert sent_msg["method"] == "order.cancel_on_disconnect"
    assert sent_msg["params"] == {"enabled": True}
    assert result["enabled"] is True


@pytest.mark.asyncio
async def test_cancel_on_disconnect_disable():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result={"enabled": False})

    task = asyncio.create_task(inject())
    result = await ws_client.cancel_on_disconnect(False)
    await task

    assert result["enabled"] is False


# ---------------------------------------------------------------------------
# submit_orders_batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_orders_batch_signs_each_order():
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    mock_account = MagicMock()
    mock_account.sign_order.return_value = '["r","s"]'
    ws_client.account = mock_account

    orders = [_make_order(), _make_order()]

    async def inject():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        msg_id = next(iter(ws_client._pending_requests))
        _inject_response(ws_client, msg_id, result={"results": []})

    task = asyncio.create_task(inject())
    await ws_client.submit_orders_batch(orders)
    await task

    sent_msg = json.loads(sent[0])
    assert sent_msg["method"] == "order.create_batch"
    assert isinstance(sent_msg["params"], list)
    assert len(sent_msg["params"]) == 2
    assert mock_account.sign_order.call_count == 2


# ---------------------------------------------------------------------------
# Reconnect / connection cleanup
# ---------------------------------------------------------------------------


def test_cancel_pending_requests_sets_exception_on_all_futures():
    """_cancel_pending_requests fails every in-flight future immediately."""
    ws_client = _make_ws_client()
    loop = asyncio.new_event_loop()
    try:
        f1 = loop.create_future()
        f2 = loop.create_future()
        ws_client._pending_requests[1] = f1
        ws_client._pending_requests[2] = f2

        exc = ConnectionError("WebSocket connection closed")
        ws_client._cancel_pending_requests(exc)

        assert f1.done() and f1.exception() is exc
        assert f2.done() and f2.exception() is exc
        assert ws_client._pending_requests == {}
    finally:
        loop.close()


def test_cancel_pending_requests_skips_already_done_futures():
    """_cancel_pending_requests does not raise on futures that are already resolved."""
    ws_client = _make_ws_client()
    loop = asyncio.new_event_loop()
    try:
        f = loop.create_future()
        f.set_result({"result": {}})
        ws_client._pending_requests[1] = f

        ws_client._cancel_pending_requests(ConnectionError("closed"))
        # Should not raise; future remains resolved (not overwritten)
        assert f.result() == {"result": {}}
        assert ws_client._pending_requests == {}
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_close_connection_cancels_pending_requests():
    """Closing the connection immediately fails in-flight requests."""
    ws_client = _make_ws_client()
    ws_client.ws = _make_open_ws([])

    loop = asyncio.get_event_loop()
    future = loop.create_future()
    ws_client._pending_requests[99] = future

    await ws_client._close_connection()

    assert future.done()
    assert isinstance(future.exception(), ConnectionError)
    assert ws_client._pending_requests == {}


@pytest.mark.asyncio
async def test_send_request_raises_connection_error_on_disconnect():
    """A pending _send_request raises ConnectionError when the connection closes."""
    ws_client = _make_ws_client()
    ws_client.ws = _make_open_ws([])

    async def close_during_request():
        while not ws_client._pending_requests:
            await asyncio.sleep(0)
        await ws_client._close_connection()

    task = asyncio.create_task(close_during_request())
    with pytest.raises(ConnectionError):
        await ws_client._send_request("order.cancel_all", {}, timeout=5.0)
    await task


# ---------------------------------------------------------------------------
# Concurrent requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_requests_resolved_independently():
    """Multiple in-flight requests are each resolved with their own response."""
    ws_client = _make_ws_client()
    sent: list[str] = []
    ws_client.ws = _make_open_ws(sent)

    results: list[dict] = []

    async def do_cancel(order_id: str) -> None:
        result = await ws_client.cancel_order(order_id)
        results.append(result)

    # Start two concurrent cancels
    t1 = asyncio.create_task(do_cancel("order-A"))
    t2 = asyncio.create_task(do_cancel("order-B"))

    # Wait until both requests are registered
    while len(ws_client._pending_requests) < 2:
        await asyncio.sleep(0)

    ids = list(ws_client._pending_requests.keys())
    # Deliver responses via _process_message so the full pop() path is exercised
    await ws_client._process_message(
        json.dumps({"id": ids[0], "jsonrpc": "2.0", "result": {"order_id": "order-A", "status": "cancelled"}})
    )
    await ws_client._process_message(
        json.dumps({"id": ids[1], "jsonrpc": "2.0", "result": {"order_id": "order-B", "status": "cancelled"}})
    )

    await asyncio.gather(t1, t2)

    assert len(results) == 2
    statuses = {r["status"] for r in results}
    assert statuses == {"cancelled"}
    # Both futures consumed — no leaks
    assert ws_client._pending_requests == {}


# ---------------------------------------------------------------------------
# _process_message end-to-end routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_message_resolves_pending_future():
    """When a WS message arrives via the reader, the pending future is resolved."""
    ws_client = _make_ws_client()
    loop = asyncio.get_event_loop()

    future = loop.create_future()
    ws_client._pending_requests[1234] = future

    raw_response = json.dumps({"id": 1234, "jsonrpc": "2.0", "result": {"order_id": "x", "status": "cancelled"}})
    await ws_client._process_message(raw_response)

    assert future.done()
    assert future.result()["result"]["order_id"] == "x"
    assert 1234 not in ws_client._pending_requests


@pytest.mark.asyncio
async def test_process_message_does_not_route_subscription_ack_to_pending():
    """Subscription acks are not consumed by the pending-requests map."""
    ws_client = _make_ws_client()
    loop = asyncio.get_event_loop()

    # Register a pending request with id=5
    future = loop.create_future()
    ws_client._pending_requests[5] = future

    # Arrive a subscription ack with a *different* id
    raw_ack = json.dumps({"id": 99, "jsonrpc": "2.0", "result": {"channel": "orders.BTC-USD-PERP"}})
    await ws_client._process_message(raw_ack)

    # Subscription was recorded
    assert ws_client.subscribed_channels.get("orders.BTC-USD-PERP") is True
    # Pending request for id=5 is untouched
    assert not future.done()
    assert 5 in ws_client._pending_requests

    # Clean up
    future.cancel()
