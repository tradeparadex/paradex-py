"""Unit tests for paradex_py/api/sbe/codec.py

All frames built with struct.pack — no network required.
"""

import struct

import pytest

from paradex_py.api.sbe.codec import (
    INT64_MIN,
    AccountEventData,
    BboEventData,
    BookEventData,
    FillEventData,
    FundingDataEventData,
    MarketSummaryEventData,
    OrderEventData,
    PositionEventData,
    SbeDecodeError,
    TradeEventData,
    _f8,
    _f8n,
    _f12,
    _f12n,
    _ts,
    decode_frame,
)

HEADER = struct.Struct("<HHHH")

MARKET = b"BTC-USD-PERP"
ACCOUNT = b"0xdeadbeef"


def _hdr(block_len: int, tmpl_id: int) -> bytes:
    return HEADER.pack(block_len, tmpl_id, 1, 0)


def _var(s: bytes) -> bytes:
    return bytes([len(s)]) + s


# ── Helper function tests ────────────────────────────────────────────────


def test_ts():
    assert _ts(1710000000123456) == 1710000000123
    assert _ts(0) == 0


def test_f8_positive():
    assert _f8(4200050000000) == "42000.50000000"
    assert _f8(100000) == "0.00100000"
    assert _f8(0) == "0.00000000"
    assert _f8(100_000_000) == "1.00000000"


def test_f8_negative():
    assert _f8(-100000) == "-0.00100000"
    assert _f8(-4200050000000) == "-42000.50000000"


def test_f8n_null():
    assert _f8n(INT64_MIN) is None


def test_f8n_non_null():
    assert _f8n(100000) == "0.00100000"


def test_f12_positive():
    assert _f12(100000000) == "0.000100000000"
    assert _f12(0) == "0.000000000000"
    assert _f12(1_000_000_000_000) == "1.000000000000"


def test_f12_negative():
    assert _f12(-100000000) == "-0.000100000000"


def test_f12n_null():
    assert _f12n(INT64_MIN) is None


def test_f12n_non_null():
    assert _f12n(100000000) == "0.000100000000"


# ── decode_frame error cases ──────────────────────────────────────────────


def test_frame_too_short():
    with pytest.raises(SbeDecodeError, match="too short"):
        decode_frame(b"\x00" * 7)


def test_wrong_schema_id():
    frame = HEADER.pack(0, 1, 99, 0)
    with pytest.raises(SbeDecodeError, match="schemaId"):
        decode_frame(frame)


def test_unknown_template_id():
    frame = HEADER.pack(0, 99, 1, 0)
    with pytest.raises(SbeDecodeError, match="templateId"):
        decode_frame(frame)


# ── TradeEvent (id=1) ────────────────────────────────────────────────────

_TRADE_STRUCT = struct.Struct("<qqqBqqq")


def _make_trade_frame(
    ts: int = 1710000000123456,
    seq: int = 42,
    trade_id: int = 999,
    side: int = 1,
    price: int = 4200050000000,
    size: int = 100000,
    created_at: int = 1710000000100000,
    market: bytes = MARKET,
) -> bytes:
    block_len = _TRADE_STRUCT.size
    payload = _TRADE_STRUCT.pack(ts, seq, trade_id, side, price, size, created_at)
    payload += _var(market)
    return _hdr(block_len, 1) + payload


def test_trade_event_channel_and_type():
    channel, model = decode_frame(_make_trade_frame())
    assert channel == "trades.BTC-USD-PERP"
    assert isinstance(model, TradeEventData)


def test_trade_event_fields():
    channel, model = decode_frame(_make_trade_frame())
    assert model.timestamp == 1710000000123
    assert model.seq_no == 42
    assert model.trade_id == 999
    assert model.side == "BUY"
    assert model.price == "42000.50000000"
    assert model.size == "0.00100000"
    assert model.created_at == 1710000000100
    assert model.market == "BTC-USD-PERP"


def test_trade_event_sell_side():
    _, model = decode_frame(_make_trade_frame(side=2))
    assert model.side == "SELL"


def test_trade_event_non_representable_side():
    _, model = decode_frame(_make_trade_frame(side=254))
    assert model.side is None


def test_trade_event_model_dump():
    _, model = decode_frame(_make_trade_frame())
    d = model.model_dump()
    assert d["price"] == "42000.50000000"
    assert d["market"] == "BTC-USD-PERP"


# ── BboEvent (id=2) ──────────────────────────────────────────────────────

_BBO_STRUCT = struct.Struct("<qqqqqq")


def _make_bbo_frame(
    ts: int = 1710000000000000,
    seq: int = 1,
    bid_price: int = 4200000000000,
    bid_size: int = 200000000,
    ask_price: int = 4200100000000,
    ask_size: int = 150000000,
    market: bytes = MARKET,
) -> bytes:
    block_len = _BBO_STRUCT.size
    payload = _BBO_STRUCT.pack(ts, seq, bid_price, bid_size, ask_price, ask_size)
    payload += _var(market)
    return _hdr(block_len, 2) + payload


def test_bbo_event():
    channel, model = decode_frame(_make_bbo_frame())
    assert channel == "bbo.BTC-USD-PERP"
    assert isinstance(model, BboEventData)
    assert model.bid_price == "42000.00000000"
    assert model.ask_price == "42001.00000000"


def test_bbo_event_null_bid():
    _, model = decode_frame(_make_bbo_frame(bid_price=INT64_MIN))
    assert model.bid_price is None


def test_bbo_event_null_ask():
    _, model = decode_frame(_make_bbo_frame(ask_price=INT64_MIN))
    assert model.ask_price is None


# ── BookEvent (id=3) ─────────────────────────────────────────────────────

_BOOK_FIXED = struct.Struct("<qqB")
_BOOK_ENTRY = struct.Struct("<qq")
_GROUP_HDR = struct.Struct("<HH")


def _make_book_frame(
    ts: int = 1710000000000000,
    seq: int = 10,
    pkg_type: int = 0,  # SNAPSHOT
    bids: list[tuple[int, int]] | None = None,
    asks: list[tuple[int, int]] | None = None,
    market: bytes = MARKET,
) -> bytes:
    if bids is None:
        bids = [(4200000000000, 200000000), (4199900000000, 300000000)]
    if asks is None:
        asks = [(4200100000000, 150000000)]

    block_len = _BOOK_FIXED.size
    payload = _BOOK_FIXED.pack(ts, seq, pkg_type)

    # bids group
    entry_blk = _BOOK_ENTRY.size
    payload += _GROUP_HDR.pack(entry_blk, len(bids))
    for p, s in bids:
        payload += _BOOK_ENTRY.pack(p, s)

    # asks group
    payload += _GROUP_HDR.pack(entry_blk, len(asks))
    for p, s in asks:
        payload += _BOOK_ENTRY.pack(p, s)

    payload += _var(market)
    return _hdr(block_len, 3) + payload


def test_book_event_channel_and_type():
    channel, model = decode_frame(_make_book_frame())
    assert channel == "order_book.BTC-USD-PERP"
    assert isinstance(model, BookEventData)


def test_book_event_fields():
    _, model = decode_frame(_make_book_frame())
    assert model.pkg_type == "SNAPSHOT"
    assert len(model.bids) == 2
    assert model.bids[0] == ["42000.00000000", "2.00000000"]
    assert len(model.asks) == 1
    assert model.asks[0] == ["42001.00000000", "1.50000000"]


def test_book_event_delta():
    _, model = decode_frame(_make_book_frame(pkg_type=1))
    assert model.pkg_type == "DELTA"


def test_book_event_empty_groups():
    _, model = decode_frame(_make_book_frame(bids=[], asks=[]))
    assert model.bids == []
    assert model.asks == []


def test_book_event_zero_size_removal():
    # qty=0 means remove the price level — codec just passes through the value
    _, model = decode_frame(_make_book_frame(bids=[(4200000000000, 0)], asks=[]))
    assert model.bids[0][1] == "0.00000000"


# ── MarketSummaryEvent (id=4) ─────────────────────────────────────────────

_MS_STRUCT = struct.Struct("<qqqqqqqqqqqqqq")


def _make_ms_frame(market: bytes = MARKET) -> bytes:
    block_len = _MS_STRUCT.size
    payload = _MS_STRUCT.pack(
        1710000000000000,  # ts
        5,  # seq
        4200000000000,  # markPrice
        4199000000000,  # indexPrice
        4201000000000,  # lastPrice
        4100000000000,  # openPrice24h
        4300000000000,  # highPrice24h
        4000000000000,  # lowPrice24h
        100_000_000_000,  # volume24h  → 1000.00000000
        4200000000_000_000_000,  # volumeUsd24h → very large, just test type
        50_000_000_000,  # openInterest
        210000000_000_000_000,  # openInterestUsd
        100_000_000,  # fundingRate (Rate12) → 0.000100000000
        1710003600000000,  # nextFundingAt
    )
    payload += _var(market)
    return _hdr(block_len, 4) + payload


def test_ms_event():
    channel, model = decode_frame(_make_ms_frame())
    assert channel == "markets_summary.BTC-USD-PERP"
    assert isinstance(model, MarketSummaryEventData)
    assert model.mark_price == "42000.00000000"
    assert model.funding_rate == "0.000100000000"
    assert model.next_funding_at == 1710003600000


# ── FundingDataEvent (id=5) ──────────────────────────────────────────────

_FD_STRUCT = struct.Struct("<qqqqq")


def _make_fd_frame(market: bytes = MARKET) -> bytes:
    block_len = _FD_STRUCT.size
    payload = _FD_STRUCT.pack(
        1710000000000000,  # ts
        3,  # seq
        100_000_000,  # fundingRate (Rate12) → 0.000100000000
        4200000000000,  # fundingIndex
        1710000000000000,  # createdAt
    )
    payload += _var(market)
    return _hdr(block_len, 5) + payload


def test_funding_data_event():
    channel, model = decode_frame(_make_fd_frame())
    assert channel == "funding_data.BTC-USD-PERP"
    assert isinstance(model, FundingDataEventData)
    assert model.funding_rate == "0.000100000000"
    assert model.funding_index == "42000.00000000"


# ── OrderEvent (id=20) ───────────────────────────────────────────────────

_ORDER_STRUCT = struct.Struct("<qqBBBBBqqqqqqqq")


def _make_order_frame(
    market: bytes = MARKET,
    price: int = 4200000000000,
    status: int = 2,  # OPEN
) -> bytes:
    block_len = _ORDER_STRUCT.size
    payload = _ORDER_STRUCT.pack(
        1710000000000000,  # ts
        7,  # seq
        status,  # status
        1,  # side BUY
        1,  # orderType LIMIT
        1,  # timeInForce GTC
        0,  # reduceOnly FALSE
        price,  # price
        INT64_MIN,  # triggerPrice (null)
        100_000_000,  # size → 1.00000000
        50_000_000,  # sizeFilledTotal → 0.50000000
        50_000_000,  # sizeOpen
        price,  # avgFillPrice
        1710000000000000,  # createdAt
        1710000001000000,  # updatedAt
    )
    payload += _var(b"order-123")
    payload += _var(b"client-456")
    payload += _var(market)
    payload += _var(ACCOUNT)
    return _hdr(block_len, 20) + payload


def test_order_event():
    channel, model = decode_frame(_make_order_frame())
    assert channel == "orders.BTC-USD-PERP"
    assert isinstance(model, OrderEventData)
    assert model.status == "OPEN"
    assert model.side == "BUY"
    assert model.order_type == "LIMIT"
    assert model.time_in_force == "GTC"
    assert model.reduce_only == "FALSE"
    assert model.price == "42000.00000000"
    assert model.trigger_price is None
    assert model.order_id == "order-123"
    assert model.client_order_id == "client-456"
    assert model.market == "BTC-USD-PERP"


def test_order_event_null_avg_fill():
    payload_struct = _ORDER_STRUCT
    block_len = payload_struct.size
    payload = payload_struct.pack(
        1710000000000000,
        1,
        1,
        1,
        1,
        1,
        0,  # status NEW, side BUY, LIMIT, GTC, not reduce_only
        4200000000000,  # price
        INT64_MIN,  # triggerPrice null
        100_000_000,  # size
        0,  # sizeFilledTotal
        100_000_000,  # sizeOpen
        INT64_MIN,  # avgFillPrice null
        1710000000000000,  # createdAt
        1710000000000000,  # updatedAt
    )
    payload += _var(b"ord") + _var(b"cli") + _var(MARKET) + _var(ACCOUNT)
    frame = _hdr(block_len, 20) + payload
    _, model = decode_frame(frame)
    assert model.avg_fill_price is None
    assert model.status == "NEW"


# ── FillEvent (id=21) ────────────────────────────────────────────────────

_FILL_STRUCT = struct.Struct("<qqBBBqqqqq")


def _make_fill_frame(market: bytes = MARKET) -> bytes:
    block_len = _FILL_STRUCT.size
    payload = _FILL_STRUCT.pack(
        1710000000000000,  # ts
        8,  # seq
        1,  # fillType FILL
        2,  # side SELL
        2,  # liquidity TAKER
        4200000000000,  # price
        50_000_000,  # size → 0.50000000
        -210_000_000,  # fee (negative = rebate)
        INT64_MIN,  # realizedPnl null
        1710000000000000,  # createdAt
    )
    payload += _var(b"fill-1")
    payload += _var(b"order-1")
    payload += _var(b"client-1")
    payload += _var(b"trade-1")
    payload += _var(market)
    payload += _var(ACCOUNT)
    return _hdr(block_len, 21) + payload


def test_fill_event():
    channel, model = decode_frame(_make_fill_frame())
    assert channel == "fills.BTC-USD-PERP"
    assert isinstance(model, FillEventData)
    assert model.fill_type == "FILL"
    assert model.side == "SELL"
    assert model.liquidity == "TAKER"
    assert model.price == "42000.00000000"
    assert model.fee == "-2.10000000"
    assert model.realized_pnl is None
    assert model.fill_id == "fill-1"
    assert model.trade_id == "trade-1"


# ── PositionEvent (id=22) ────────────────────────────────────────────────

_POS_STRUCT = struct.Struct("<qqBqqqqqqqq")


def _make_position_frame(side: int = 1, liq_price: int = INT64_MIN) -> bytes:
    block_len = _POS_STRUCT.size
    payload = _POS_STRUCT.pack(
        1710000000000000,  # ts
        9,  # seq
        side,  # side
        100_000_000,  # size → 1.00000000
        4200000000000,  # avgEntryPrice
        -5000000000,  # unrealizedPnl (negative)
        1000000000,  # realizedPnl
        4190000000000,  # markPrice
        liq_price,  # liquidationPrice (null by default)
        5_00000000,  # leverage → 5.00000000
        1710000001000000,  # updatedAt
    )
    payload += _var(MARKET) + _var(ACCOUNT)
    return _hdr(block_len, 22) + payload


def test_position_event_long():
    channel, model = decode_frame(_make_position_frame(side=1))
    assert channel == "positions"
    assert isinstance(model, PositionEventData)
    assert model.side == "LONG"


def test_position_event_short():
    _, model = decode_frame(_make_position_frame(side=2))
    assert model.side == "SHORT"


def test_position_event_null_liquidation():
    _, model = decode_frame(_make_position_frame(liq_price=INT64_MIN))
    assert model.liquidation_price is None


def test_position_event_liquidation_price():
    _, model = decode_frame(_make_position_frame(liq_price=3500000000000))
    assert model.liquidation_price == "35000.00000000"


def test_position_event_negative_unrealized_pnl():
    _, model = decode_frame(_make_position_frame())
    assert model.unrealized_pnl == "-50.00000000"


# ── AccountEvent (id=23) ──────────────────────────────────────────────────

_ACC_STRUCT = struct.Struct("<qqqqqqqqq")


def _make_account_frame() -> bytes:
    block_len = _ACC_STRUCT.size
    payload = _ACC_STRUCT.pack(
        1710000000000000,  # ts
        11,  # seq
        10000_00000000,  # totalCollateral → 10000.00000000
        5000_00000000,  # freeCollateral
        2000_00000000,  # initialMarginReq
        1000_00000000,  # maintenanceMarginReq
        10500_00000000,  # accountValue
        500_00000000,  # unrealizedPnl
        1710000001000000,  # updatedAt
    )
    payload += _var(ACCOUNT)
    return _hdr(block_len, 23) + payload


def test_account_event():
    channel, model = decode_frame(_make_account_frame())
    assert channel == "account"
    assert isinstance(model, AccountEventData)
    assert model.total_collateral == "10000.00000000"
    assert model.free_collateral == "5000.00000000"
    assert model.account == "0xdeadbeef"


# ── HeartbeatEvent (id=40) ──────────────────────────────────────────────

_HB_STRUCT = struct.Struct("<qq")


def _make_heartbeat_frame() -> bytes:
    block_len = _HB_STRUCT.size
    payload = _HB_STRUCT.pack(1710000000000000, 100)
    return _hdr(block_len, 40) + payload


def test_heartbeat_returns_none():
    channel, model = decode_frame(_make_heartbeat_frame())
    assert channel is None
    assert model is None


# ── SubscribedEvent (id=41) ──────────────────────────────────────────────

_SUB_STRUCT = struct.Struct("<qqB")


def _make_subscribed_frame() -> bytes:
    block_len = _SUB_STRUCT.size
    payload = _SUB_STRUCT.pack(1710000000000000, 1, 0)
    payload += _var(b"bbo.BTC-USD-PERP")
    return _hdr(block_len, 41) + payload


def test_subscribed_returns_none():
    channel, model = decode_frame(_make_subscribed_frame())
    assert channel is None
    assert model is None


# ── Timestamp precision ──────────────────────────────────────────────────


def test_timestamp_microseconds_to_millis():
    """1710000000123456 μs → 1710000000123 ms (drops sub-millisecond)."""
    _, model = decode_frame(_make_trade_frame(ts=1710000000123456))
    assert model.timestamp == 1710000000123
