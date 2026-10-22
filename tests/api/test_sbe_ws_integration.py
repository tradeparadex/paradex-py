"""Integration tests: SBE binary frames through ParadexWebsocketClient."""

import asyncio
import logging
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets import State

from paradex_py.api.ws_client import ParadexWebsocketChannel, ParadexWebsocketClient
from paradex_py.environment import TESTNET
from paradex_py.paradex import Paradex

HEADER = struct.Struct("<HHHH")
TRADE_STRUCT = struct.Struct("<qqqBqqqB")
MARKET = b"BTC-USD-PERP"


def _var(s: bytes) -> bytes:
    return bytes([len(s)]) + s


def _make_trade_frame(market: bytes = MARKET) -> bytes:
    block_len = TRADE_STRUCT.size
    payload = TRADE_STRUCT.pack(
        1710000000123456,
        42,
        999,
        1,
        4200050000000,
        100000,
        1710000000100000,
        1,  # tradeType FILL
    )
    payload += _var(market)
    return HEADER.pack(block_len, 1, 1, 0) + payload


def _make_mock_ws(state: State = State.OPEN) -> MagicMock:
    ws = MagicMock()
    ws.state = state
    ws.recv = AsyncMock()
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ── SBE flag default ─────────────────────────────────────────────────────


def test_sbe_enabled_by_default():
    # The Paradex endpoints answer a plain JSON connect with HTTP 400.
    ws_client = ParadexWebsocketClient(env=TESTNET)
    assert ws_client.sbe_enabled is True


def test_sbe_opt_out_flag():
    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=False)
    assert ws_client.sbe_enabled is False


def test_sbe_enabled_flag():
    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True)
    assert ws_client.sbe_enabled is True


def test_sbe_via_paradex_constructor():
    paradex = Paradex(env=TESTNET, ws_sbe_enabled=True)
    assert paradex.ws_direct_client.sbe_enabled is True


def test_sbe_via_paradex_constructor_reaches_default_client():
    """ws_client is the common path; the flag has to reach it too."""
    paradex = Paradex(env=TESTNET, ws_sbe_enabled=True)
    assert paradex.ws_client.sbe_enabled is True


def test_sbe_on_by_default_via_paradex_constructor():
    paradex = Paradex(env=TESTNET)
    assert paradex.ws_client.sbe_enabled is True
    assert paradex.ws_direct_client.sbe_enabled is True


def test_sbe_off_via_paradex_constructor():
    paradex = Paradex(env=TESTNET, ws_sbe_enabled=False)
    assert paradex.ws_client.sbe_enabled is False
    assert paradex.ws_direct_client.sbe_enabled is False


def test_default_client_does_not_log_validate_messages_note(caplog):
    """The SBE/validate_messages note is for callers who asked for validation,
    not for everyone now that SBE is the default."""
    with caplog.at_level(logging.DEBUG):
        ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
    assert "validate_messages" not in caplog.text


def test_validate_messages_with_default_sbe_logs_note(caplog):
    with caplog.at_level(logging.INFO):
        ParadexWebsocketClient(env=TESTNET, validate_messages=True, auto_start_reader=False)
    assert "validate_messages does not apply to SBE frames" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs, expected", [({}, True), ({"sbe_enabled": False}, False)])
async def test_threaded_client_forwards_sbe_flag(kwargs: dict, expected: bool):
    """The threaded wrapper builds its own async client; the flag has to reach it."""
    from paradex_py.api.ws_client_threaded import ThreadedParadexWebsocketClient

    client = ThreadedParadexWebsocketClient(env=TESTNET, **kwargs)
    assert client.sbe_enabled is expected
    client._stop_event.set()  # leave the loop as soon as it has connected
    with patch("paradex_py.api.ws_client_threaded.ParadexWebsocketClient") as mock_cls:
        mock_cls.return_value.connect = AsyncMock()
        mock_cls.return_value.close = AsyncMock()
        await client._async_loop()
    assert mock_cls.call_args.kwargs["sbe_enabled"] is expected


# ── URL construction ────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("websockets.connect", new_callable=AsyncMock)
async def test_sbe_url_params_appended(mock_connect: AsyncMock):
    """SBE enabled → ?sbeSchemaId=1&sbeSchemaVersion=3 appended to URL."""
    mock_ws = _make_mock_ws()
    mock_connect.return_value = mock_ws

    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    await ws_client.connect()

    url_called = mock_connect.call_args.args[0]
    assert "sbeSchemaId=1" in url_called
    assert "sbeSchemaVersion=3" in url_called


@pytest.mark.asyncio
@patch("websockets.connect", new_callable=AsyncMock)
async def test_default_client_connects_with_sbe_url(mock_connect: AsyncMock):
    """With no flags at all, connect asks for SBE (a bare URL is a 400)."""
    mock_connect.return_value = _make_mock_ws()

    ws_client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
    await ws_client.connect()

    assert mock_connect.call_args.args[0] == (
        "wss://ws-public.api.testnet.paradex.trade/v1?sbeSchemaId=1&sbeSchemaVersion=3"
    )


def test_negotiated_version_matches_decoder_version():
    """The SDK asks for exactly the version its decoder was generated for.

    v0.7.1 shipped the 1:2 decoder while still negotiating 1:1, because every
    environment capped negotiation at 1 and a request above the cap is a 400 at
    connect. nightly, testnet and prod serve 1:3 (and refuse 1:4), so the split
    is closed.

    Both directions stay forbidden. Negotiating above the decoder would decode
    frames with a layout it does not know. Negotiating below it is allowed
    only as a deliberate hold-back while the server cap catches up with a
    newer schema, so if this fails because the schema moved ahead, lower the
    expectation here on purpose rather than bumping NEGOTIATED_SCHEMA_VERSION
    to match: the server must be serving the new version first.
    """
    from paradex_py.api.sbe import NEGOTIATED_SCHEMA_VERSION
    from paradex_py.api.sbe.codec import _SCHEMA_VERSION

    assert NEGOTIATED_SCHEMA_VERSION == 3
    assert _SCHEMA_VERSION == 3
    assert NEGOTIATED_SCHEMA_VERSION == _SCHEMA_VERSION


@pytest.mark.asyncio
@patch("websockets.connect", new_callable=AsyncMock)
async def test_sbe_url_requests_negotiated_not_decoder_version(mock_connect: AsyncMock):
    """The connect URL carries the negotiated version, not the decoder's."""
    from paradex_py.api.sbe import NEGOTIATED_SCHEMA_VERSION

    mock_ws = _make_mock_ws()
    mock_connect.return_value = mock_ws

    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    await ws_client.connect()

    url_called = mock_connect.call_args.args[0]
    assert f"sbeSchemaVersion={NEGOTIATED_SCHEMA_VERSION}" in url_called


@pytest.mark.asyncio
@patch("websockets.connect", new_callable=AsyncMock)
async def test_no_sbe_url_params_when_disabled(mock_connect: AsyncMock):
    """SBE disabled → no SBE params in URL."""
    mock_ws = _make_mock_ws()
    mock_connect.return_value = mock_ws

    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=False, auto_start_reader=False)
    await ws_client.connect()

    url_called = mock_connect.call_args.args[0]
    assert "sbeSchemaId" not in url_called


@pytest.mark.asyncio
@patch("websockets.connect", new_callable=AsyncMock)
async def test_sbe_url_with_existing_query_param(mock_connect: AsyncMock):
    """Existing '?' in URL → use '&' separator."""
    mock_ws = _make_mock_ws()
    mock_connect.return_value = mock_ws

    ws_client = ParadexWebsocketClient(
        env=TESTNET,
        sbe_enabled=True,
        auto_start_reader=False,
        ws_url_override="wss://ws.example.com/v1?foo=bar",
    )
    await ws_client.connect()

    url_called = mock_connect.call_args.args[0]
    assert "foo=bar&sbeSchemaId=1" in url_called


# ── Binary frame dispatch ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_binary_frame_dispatched_to_callback():
    """Binary SBE frame decoded and callback invoked with correct shape."""
    received = []

    async def on_trade(ws_channel, message):
        received.append((ws_channel, message))

    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    ws_client.callbacks["trades.BTC-USD-PERP"] = on_trade

    frame = _make_trade_frame()
    await ws_client._process_binary_message(frame)

    assert len(received) == 1
    ws_channel, message = received[0]
    assert ws_channel == ParadexWebsocketChannel.TRADES
    assert message["params"]["channel"] == "trades.BTC-USD-PERP"
    data = message["params"]["data"]
    assert data["market"] == "BTC-USD-PERP"
    assert data["price"] == "42000.50000000"
    assert data["side"] == "BUY"


@pytest.mark.asyncio
async def test_short_position_reaches_callback_with_negative_size():
    """A short PositionEvent reaches a positions callback signed, as JSON sends it."""
    from tests.api.test_sbe_codec import _POSITION_GOLDEN

    received = []

    async def on_position(ws_channel, message):
        received.append((ws_channel, message))

    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    ws_client.callbacks["positions"] = on_position

    json_pos, frame_hex = _POSITION_GOLDEN["short"]
    await ws_client._process_binary_message(bytes.fromhex(frame_hex))

    assert len(received) == 1
    ws_channel, message = received[0]
    assert ws_channel == ParadexWebsocketChannel.POSITIONS
    data = message["params"]["data"]
    assert data["side"] == json_pos["side"] == "SHORT"
    assert data["size"] == "-0.50000000"


@pytest.mark.asyncio
async def test_binary_frame_model_dump_type():
    """model_dump() returns plain dict (backward-compat shape for callbacks)."""
    received_data = {}

    async def on_trade(ws_channel, message):
        received_data.update(message["params"]["data"])

    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    ws_client.callbacks["trades.BTC-USD-PERP"] = on_trade

    await ws_client._process_binary_message(_make_trade_frame())
    assert isinstance(received_data, dict)
    assert "timestamp" in received_data


@pytest.mark.asyncio
async def test_json_path_unaffected_with_sbe_enabled():
    """Text (JSON) frames still processed through _process_message when SBE enabled."""
    received = []

    async def on_bbo(ws_channel, message):
        received.append(message)

    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    ws_client.callbacks["bbo.BTC-USD-PERP"] = on_bbo

    import json

    text_msg = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "subscription",
            "params": {"channel": "bbo.BTC-USD-PERP"},
            "data": {"bid": "42000", "ask": "42001"},
        }
    )
    await ws_client._process_message(text_msg)
    assert len(received) == 1


@pytest.mark.asyncio
async def test_malformed_binary_logged_not_raised(caplog):
    """Malformed binary frame logs a warning but does not raise."""
    import logging

    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    with caplog.at_level(logging.WARNING):
        # Too short — SbeDecodeError expected to be caught
        await ws_client._process_binary_message(b"\x00\x00\x00")
    assert any("SBE decode error" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_binary_no_callback_no_error():
    """Binary frame with no matching callback is silently dropped."""
    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    # No callbacks registered — should not raise
    await ws_client._process_binary_message(_make_trade_frame())


# ── pump_once with binary ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pump_once_binary_sbe():
    """pump_once with a binary SBE frame routes through _process_binary_message."""
    received = []

    async def on_trade(ws_channel, message):
        received.append(message)

    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    ws_client.callbacks["trades.BTC-USD-PERP"] = on_trade

    mock_ws = _make_mock_ws()
    mock_ws.recv.return_value = _make_trade_frame()
    ws_client.ws = mock_ws

    result = await ws_client.pump_once()
    assert result is True
    assert len(received) == 1


@pytest.mark.asyncio
async def test_pump_once_binary_without_sbe_decodes_utf8():
    """pump_once with bytes and sbe_enabled=False falls through to UTF-8 decode."""
    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=False, auto_start_reader=False)

    import json

    received = []

    async def on_bbo(ws_channel, message):
        received.append(message)

    ws_client.callbacks["bbo.BTC-USD-PERP"] = on_bbo

    text = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "subscription",
            "params": {"channel": "bbo.BTC-USD-PERP"},
            "data": {},
        }
    )
    mock_ws = _make_mock_ws()
    mock_ws.recv.return_value = text.encode("utf-8")
    ws_client.ws = mock_ws

    result = await ws_client.pump_once()
    assert result is True
    assert len(received) == 1


# ── _resolve_sbe_channel ──────────────────────────────────────────────────


def test_resolve_exact_match():
    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    ws_client.callbacks["trades.BTC-USD-PERP"] = lambda *a: None
    assert ws_client._resolve_sbe_channel("trades.BTC-USD-PERP") == "trades.BTC-USD-PERP"


def test_resolve_prefix_scan():
    """order_book.BTC-USD-PERP → order_book.BTC-USD-PERP.snapshot@15@100ms"""
    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    ws_client.callbacks["order_book.BTC-USD-PERP.snapshot@15@100ms"] = lambda *a: None
    result = ws_client._resolve_sbe_channel("order_book.BTC-USD-PERP")
    assert result == "order_book.BTC-USD-PERP.snapshot@15@100ms"


def test_resolve_markets_summary_all_fallback():
    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    ws_client.callbacks["markets_summary.ALL"] = lambda *a: None
    result = ws_client._resolve_sbe_channel("markets_summary.ETH-USD-PERP")
    assert result == "markets_summary.ALL"


def test_resolve_no_match_returns_none():
    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    assert ws_client._resolve_sbe_channel("unknown.MARKET") is None


def test_frc_frame_resolves_to_the_all_subscription():
    """The decoded frame's channel must route to the live ALL subscription.

    The server publishes this channel only as ALL (its regex is anchored to
    `funding_rate_comparison.ALL@{500ms|1000ms}`), so one subscription carries
    every symbol and the market is a payload field. A market-qualified channel
    name would not route at all: the `*.ALL` fallback matches a literal `.ALL`
    key, not the `ALL@1000ms` the subscription registers.
    """
    from paradex_py.api.sbe.codec import decode_frame

    golden = "1a0006000100010000401e18240a060000401e18240a060000e1f5050000000001010c4254432d5553442d50455250"
    channel, model = decode_frame(bytes.fromhex(golden))

    ws_client = ParadexWebsocketClient(env=TESTNET)
    ws_client.callbacks["funding_rate_comparison.ALL@1000ms"] = lambda *_: None

    assert ws_client._resolve_sbe_channel(channel) == "funding_rate_comparison.ALL@1000ms"
    assert ws_client._resolve_sbe_channel(f"funding_rate_comparison.{model.market}") is None


@pytest.mark.asyncio
async def test_frc_subscribe_defaults_refresh_rate():
    """subscribe() without params must register the ALL@1000ms channel.

    Driven through subscribe() rather than reimplementing the defaulting: the
    point is to guard the default in ws_client, so asserting on a locally
    computed value would pass even with that code deleted.
    """
    client = ParadexWebsocketClient(env=TESTNET)
    client._subscribe_to_channel_by_name = AsyncMock()

    async def _cb(_channel, _message):
        pass

    await client.subscribe(ParadexWebsocketChannel.FUNDING_RATE_COMPARISON, callback=_cb)

    assert "funding_rate_comparison.ALL@1000ms" in client.callbacks
    client._subscribe_to_channel_by_name.assert_awaited_once_with("funding_rate_comparison.ALL@1000ms")


@pytest.mark.asyncio
async def test_frc_subscribe_honours_an_explicit_refresh_rate():
    """The default must not override a caller-supplied rate."""
    client = ParadexWebsocketClient(env=TESTNET)
    client._subscribe_to_channel_by_name = AsyncMock()

    async def _cb(_channel, _message):
        pass

    await client.subscribe(
        ParadexWebsocketChannel.FUNDING_RATE_COMPARISON,
        callback=_cb,
        params={"refresh_rate": "500ms"},
    )

    assert "funding_rate_comparison.ALL@500ms" in client.callbacks


# ── Routing must not cross market names ─────────────────────────────────


def test_resolve_prefix_stops_at_market_boundary():
    """Market names nest (spot ETH-USD is a prefix of its options), so an
    order_book frame for ETH-USD must not reach an option's callback."""
    ws_client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
    ws_client.callbacks["order_book.ETH-USD-22OCT26-2000-C.snapshot@15@100ms"] = lambda *_: None
    assert ws_client._resolve_sbe_channel("order_book.ETH-USD") is None

    # With both subscribed, each frame reaches its own market, whatever the order.
    ws_client.callbacks["order_book.ETH-USD.snapshot@15@100ms"] = lambda *_: None
    assert ws_client._resolve_sbe_channel("order_book.ETH-USD") == "order_book.ETH-USD.snapshot@15@100ms"
    assert (
        ws_client._resolve_sbe_channel("order_book.ETH-USD-22OCT26-2000-C")
        == "order_book.ETH-USD-22OCT26-2000-C.snapshot@15@100ms"
    )


# ── message["encoding"] tells a callback which field names it got ───────


@pytest.mark.asyncio
async def test_sbe_message_is_marked_sbe():
    received = []

    async def on_trade(ws_channel, message):
        received.append(message)

    ws_client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
    ws_client.callbacks["trades.BTC-USD-PERP"] = on_trade
    await ws_client._process_binary_message(_make_trade_frame())
    assert received[0]["encoding"] == "sbe"


@pytest.mark.asyncio
async def test_json_frame_on_sbe_connection_is_marked_json():
    """Private channels can still arrive as JSON on an SBE connection."""
    received = []

    async def on_order(ws_channel, message):
        received.append(message)

    ws_client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
    assert ws_client.sbe_enabled is True
    ws_client.callbacks["orders.ALL"] = on_order
    frame = '{"jsonrpc":"2.0","method":"subscription","params":{"channel":"orders.ALL","data":{"id":"o-1"}}}'
    await ws_client._process_message(frame)
    assert received[0]["encoding"] == "json"
    assert received[0]["params"]["data"]["id"] == "o-1"


@pytest.mark.asyncio
async def test_validated_json_message_keeps_encoding():
    """Validation rebuilds the message dict; the marker must survive it."""
    received = []

    async def on_bbo(ws_channel, message):
        received.append(message)

    ws_client = ParadexWebsocketClient(env=TESTNET, validate_messages=True, auto_start_reader=False)
    ws_client.callbacks["bbo.BTC-USD-PERP"] = on_bbo
    frame = '{"jsonrpc":"2.0","method":"subscription","params":{"channel":"bbo.BTC-USD-PERP","data":{}}}'
    with patch("paradex_py.api.ws_client.validate_ws_message") as validate:
        validate.return_value.model_dump.return_value = {
            "jsonrpc": "2.0",
            "params": {"channel": "bbo.BTC-USD-PERP", "data": {}},
        }
        await ws_client._process_message(frame)
    validate.assert_called_once()  # JSON frames are validated on an SBE connection
    assert received[0]["encoding"] == "json"


# ── A rejected subscription says why ───────────────────────────────────


def test_subscription_error_logs_server_reason(caplog):
    """The server rejects a second order_book feed for a market on an SBE
    session; the reason is in error.data, which used to be dropped."""
    ws_client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
    reason = "channel 'order_book.BTC-USD-PERP.deltas' cannot share an SBE session"
    with caplog.at_level(logging.ERROR):
        ws_client._check_subscribed_channel(
            {"id": 7, "error": {"code": -32600, "message": "invalid subscribe request", "data": reason}}
        )
    assert reason in caplog.text


# ── close() cannot hang on a busy feed ─────────────────────────────────


@pytest.mark.asyncio
async def test_reader_stops_once_closing_even_without_cancel():
    """On Python 3.11 wait_for() can drop a cancel that lands as recv() completes,
    so the reader must also stop on _is_closing or close() waits on it forever."""
    ws_client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
    ws_client.ws = _make_mock_ws()
    ws_client.ws.recv.return_value = _make_trade_frame()  # a feed that never goes quiet
    reader = asyncio.create_task(ws_client._read_messages())
    await asyncio.sleep(0.01)
    assert not reader.done()

    ws_client._is_closing = True  # what close() sets, here without the cancel
    try:
        # asyncio.wait, not wait_for: wait_for would cancel a stuck reader and
        # then hang on the very race this test is about.
        await asyncio.wait({reader}, timeout=2)
        assert reader.done(), "reader kept running after _is_closing was set"
    finally:
        # Starve the reader so a cancel cannot race a ready recv() and lands.
        ws_client.ws = None
        reader.cancel()
        await asyncio.wait({reader}, timeout=5)
