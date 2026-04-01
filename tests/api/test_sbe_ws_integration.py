"""Integration tests: SBE binary frames through ParadexWebsocketClient."""

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


def test_sbe_disabled_by_default():
    ws_client = ParadexWebsocketClient(env=TESTNET)
    assert ws_client.sbe_enabled is False


def test_sbe_enabled_flag():
    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True)
    assert ws_client.sbe_enabled is True


def test_sbe_via_paradex_constructor():
    paradex = Paradex(env=TESTNET, ws_sbe_enabled=True)
    assert paradex.ws_direct_client.sbe_enabled is True


def test_sbe_off_via_paradex_constructor():
    paradex = Paradex(env=TESTNET)
    assert paradex.ws_client.sbe_enabled is False


# ── URL construction ────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("websockets.connect", new_callable=AsyncMock)
async def test_sbe_url_params_appended(mock_connect: AsyncMock):
    """SBE enabled → ?sbeSchemaId=1&sbeSchemaVersion=0 appended to URL."""
    mock_ws = _make_mock_ws()
    mock_connect.return_value = mock_ws

    ws_client = ParadexWebsocketClient(env=TESTNET, sbe_enabled=True, auto_start_reader=False)
    await ws_client.connect()

    url_called = mock_connect.call_args.args[0]
    assert "sbeSchemaId=1" in url_called
    assert "sbeSchemaVersion=0" in url_called


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
