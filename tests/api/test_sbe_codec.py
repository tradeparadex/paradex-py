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
    FundingRateComparisonEventData,
    MarketSummaryEventData,
    OrderEventData,
    PositionEventData,
    SbeDecodeError,
    TradeEventData,
    _addr,
    _f8,
    _f8n,
    _f12,
    _f12n,
    _ts,
    decode_frame,
)

HEADER = struct.Struct("<HHHH")

MARKET = b"BTC-USD-PERP"
# 32-byte big-endian Starknet address that decodes to "0xdeadbeef"
ACCOUNT_BYTES = b"\x00" * 28 + b"\xde\xad\xbe\xef"


def _hdr(block_len: int, tmpl_id: int, version: int = 0) -> bytes:
    return HEADER.pack(block_len, tmpl_id, 1, version)


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


def test_addr_nonzero():
    b = b"\x00" * 28 + b"\xde\xad\xbe\xef"
    assert _addr(b) == "0xdeadbeef"


def test_addr_zero():
    assert _addr(b"\x00" * 32) == "0x0"


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

_TRADE_STRUCT = struct.Struct("<qqqBqqqB")


def _make_trade_frame(
    ts: int = 1710000000123456,
    seq: int = 42,
    trade_id: int = 999,
    side: int = 1,
    price: int = 4200050000000,
    size: int = 100000,
    created_at: int = 1710000000100000,
    trade_type: int = 1,  # FILL
    market: bytes = MARKET,
) -> bytes:
    block_len = _TRADE_STRUCT.size
    payload = _TRADE_STRUCT.pack(ts, seq, trade_id, side, price, size, created_at, trade_type)
    payload += _var(market)
    return _hdr(block_len, 1) + payload


def test_trade_event_channel_and_type():
    channel, model = decode_frame(_make_trade_frame())
    assert channel == "trades.BTC-USD-PERP"
    assert isinstance(model, TradeEventData)


def test_trade_event_fields():
    _channel, model = decode_frame(_make_trade_frame())
    assert model.timestamp == 1710000000123
    assert model.seq_no == 42
    with pytest.warns(DeprecationWarning):
        assert model.trade_id == 999
    assert model.trade_id_str is None  # a 1:0 frame predates it
    assert model.side == "BUY"
    assert model.price == "42000.50000000"
    assert model.size == "0.00100000"
    assert model.created_at == 1710000000100
    assert model.trade_type == "FILL"
    assert model.market == "BTC-USD-PERP"


def test_trade_event_sell_side():
    _, model = decode_frame(_make_trade_frame(side=2))
    assert model.side == "SELL"


def test_trade_event_non_representable_side():
    _, model = decode_frame(_make_trade_frame(side=254))
    assert model.side is None


def test_trade_event_fill_types():
    _, model = decode_frame(_make_trade_frame(trade_type=2))
    assert model.trade_type == "LIQUIDATION"
    _, model = decode_frame(_make_trade_frame(trade_type=5))
    assert model.trade_type == "RPI"
    _, model = decode_frame(_make_trade_frame(trade_type=6))
    assert model.trade_type == "BLOCK_TRADE"


def test_trade_event_model_dump():
    _, model = decode_frame(_make_trade_frame())
    d = model.model_dump()
    assert d["price"] == "42000.50000000"
    assert d["market"] == "BTC-USD-PERP"
    assert d["trade_type"] == "FILL"


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
    assert model.bid_size == "2.00000000"
    assert model.ask_size == "1.50000000"


def test_bbo_event_null_bid():
    _, model = decode_frame(_make_bbo_frame(bid_price=INT64_MIN, bid_size=INT64_MIN))
    assert model.bid_price is None
    assert model.bid_size is None


def test_bbo_event_null_ask():
    _, model = decode_frame(_make_bbo_frame(ask_price=INT64_MIN, ask_size=INT64_MIN))
    assert model.ask_price is None
    assert model.ask_size is None


# ── BookEvent (id=3) ─────────────────────────────────────────────────────

_BOOK_FIXED = struct.Struct("<qqBqqqqqqqqq")  # 4 new API-feed best price/size fields
_BOOK_ENTRY = struct.Struct("<qq")
_GROUP_HDR = struct.Struct("<HH")


def _make_book_frame(
    ts: int = 1710000000000000,
    seq: int = 10,
    pkg_type: int = 0,  # SNAPSHOT
    best_bid_price: int = INT64_MIN,
    best_bid_size: int = INT64_MIN,
    best_ask_price: int = INT64_MIN,
    best_ask_size: int = INT64_MIN,
    relative_spread: int = INT64_MIN,
    best_bid_api_price: int = INT64_MIN,
    best_bid_api_size: int = INT64_MIN,
    best_ask_api_price: int = INT64_MIN,
    best_ask_api_size: int = INT64_MIN,
    bids: list[tuple[int, int]] | None = None,
    asks: list[tuple[int, int]] | None = None,
    market: bytes = MARKET,
) -> bytes:
    if bids is None:
        bids = [(4200000000000, 200000000), (4199900000000, 300000000)]
    if asks is None:
        asks = [(4200100000000, 150000000)]

    block_len = _BOOK_FIXED.size
    payload = _BOOK_FIXED.pack(
        ts,
        seq,
        pkg_type,
        best_bid_price,
        best_bid_size,
        best_ask_price,
        best_ask_size,
        relative_spread,
        best_bid_api_price,
        best_bid_api_size,
        best_ask_api_price,
        best_ask_api_size,
    )

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


def test_book_event_best_prices_null():
    _, model = decode_frame(_make_book_frame())
    assert model.best_bid_price is None
    assert model.best_bid_size is None
    assert model.best_ask_price is None
    assert model.best_ask_size is None
    assert model.relative_spread is None


def test_book_event_best_prices_set():
    _, model = decode_frame(
        _make_book_frame(
            best_bid_price=4200000000000,
            best_bid_size=100000000,
            best_ask_price=4200100000000,
            best_ask_size=150000000,
            relative_spread=238095,  # ~0.00238095 in Rate8
        )
    )
    assert model.best_bid_price == "42000.00000000"
    assert model.best_bid_size == "1.00000000"
    assert model.best_ask_price == "42001.00000000"
    assert model.best_ask_size == "1.50000000"
    assert model.relative_spread is not None


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

_MS_STRUCT = struct.Struct("<" + "q" * 30)  # matches schema 1:1 MarketSummaryEvent block


def _make_ms_frame(market: bytes = MARKET) -> bytes:
    block_len = _MS_STRUCT.size
    payload = _MS_STRUCT.pack(
        1710000000000000,  # ts
        5,  # seq
        4200000000000,  # markPrice
        4199000000000,  # indexPrice
        4201000000000,  # lastPrice
        4200000000_000_000_000,  # volumeUsd24h → very large USD vol
        50_000_000_000,  # openInterest → 500.00000000
        1_000_000,  # fundingRate (Rate8) → 0.01000000
        4200000000000,  # bid (Price8NULL)
        4200100000000,  # ask (Price8NULL)
        100_000_000_000_000_000,  # totalVolume
        -500_000,  # priceChangeRate24h (Rate8) → -0.00500000
        INT64_MIN,  # markIv (null — perp, not option)
        INT64_MIN,  # bidIv (null)
        INT64_MIN,  # askIv (null)
        INT64_MIN,  # lastIv (null)
        INT64_MIN,  # delta (null)
        INT64_MIN,  # gamma (null)
        INT64_MIN,  # vega (null)
        INT64_MIN,  # theta (null — new)
        INT64_MIN,  # rho (null — new)
        INT64_MIN,  # volga (null — new)
        INT64_MIN,  # vanna (null — new)
        INT64_MIN,  # futureFundingRate (null — Rate8NULL)
        INT64_MIN,  # externalFairPrice (null)
        INT64_MIN,  # bidSize (null — new)
        INT64_MIN,  # askSize (null — new)
        INT64_MIN,  # forwardRate (null — 1:1)
        INT64_MIN,  # riskFreeRate (null — 1:1)
        INT64_MIN,  # fundingRatePrecise (null — 1:1)
    )
    payload += _var(market)
    return _hdr(block_len, 4) + payload


def test_ms_event():
    channel, model = decode_frame(_make_ms_frame())
    assert channel == "markets_summary.BTC-USD-PERP"
    assert isinstance(model, MarketSummaryEventData)
    assert model.mark_price == "42000.00000000"
    assert model.index_price == "41990.00000000"
    assert model.funding_rate == "0.01000000"
    assert model.bid == "42000.00000000"
    assert model.ask == "42001.00000000"
    assert model.price_change_rate24h == "-0.00500000"


def test_ms_event_null_options_fields():
    _, model = decode_frame(_make_ms_frame())
    assert model.mark_iv is None
    assert model.bid_iv is None
    assert model.delta is None
    assert model.future_funding_rate is None
    assert model.external_fair_price is None


def test_ms_event_null_bid_ask():
    payload = _MS_STRUCT.pack(
        1710000000000000,
        1,
        4200000000000,
        4199000000000,
        4200000000000,
        100_000_000_000,
        50_000_000_000,
        1_000_000,
        INT64_MIN,  # bid null
        INT64_MIN,  # ask null
        100_000_000_000,
        0,
        INT64_MIN,  # markIv
        INT64_MIN,  # bidIv
        INT64_MIN,  # askIv
        INT64_MIN,  # lastIv
        INT64_MIN,  # delta
        INT64_MIN,  # gamma
        INT64_MIN,  # vega
        INT64_MIN,  # theta (new)
        INT64_MIN,  # rho (new)
        INT64_MIN,  # volga (new)
        INT64_MIN,  # vanna (new)
        INT64_MIN,  # futureFundingRate
        INT64_MIN,  # externalFairPrice
        INT64_MIN,  # bidSize (new)
        INT64_MIN,  # askSize (new)
        INT64_MIN,  # forwardRate (null — 1:1)
        INT64_MIN,  # riskFreeRate (null — 1:1)
        INT64_MIN,  # fundingRatePrecise (null — 1:1)
    )
    frame = _hdr(_MS_STRUCT.size, 4) + payload + _var(MARKET)
    _, model = decode_frame(frame)
    assert model.bid is None
    assert model.ask is None


# ── FundingDataEvent (id=5) ──────────────────────────────────────────────

_FD_STRUCT = struct.Struct("<qqqqqqqhq")  # +impactPremiumRate in 1:1


def _make_fd_frame(market: bytes = MARKET) -> bytes:
    block_len = _FD_STRUCT.size
    payload = _FD_STRUCT.pack(
        1710000000000000,  # ts
        3,  # seq
        1_000_000,  # fundingRate (Rate8) → 0.01000000
        4200000000000,  # fundingIndex
        1710000000000000,  # createdAt
        500_000,  # fundingPremium (Rate8) → 0.00500000
        800_000,  # fundingRate8h (Rate8) → 0.00800000
        8,  # fundingPeriodHours
        INT64_MIN,  # impactPremiumRate (null — 1:1)
    )
    payload += _var(market)
    return _hdr(block_len, 5) + payload


def test_funding_data_event():
    channel, model = decode_frame(_make_fd_frame())
    assert channel == "funding_data.BTC-USD-PERP"
    assert isinstance(model, FundingDataEventData)
    assert model.funding_rate == "0.01000000"
    assert model.funding_index == "42000.00000000"
    assert model.funding_premium == "0.00500000"
    assert model.funding_rate8h == "0.00800000"
    assert model.funding_period_hours == 8


# ── OrderEvent (id=20) ───────────────────────────────────────────────────

_ORDER_STRUCT = struct.Struct("<qqBBBBqqqqqqq32sqqBB")


def _make_order_frame(
    market: bytes = MARKET,
    price: int = 4200000000000,
    status: int = 3,  # OPEN
) -> bytes:
    block_len = _ORDER_STRUCT.size
    payload = _ORDER_STRUCT.pack(
        1710000000000000,  # ts
        7,  # seq
        status,  # status
        1,  # side BUY
        1,  # orderType LIMIT
        1,  # timeInForce GTC
        price,  # price
        INT64_MIN,  # triggerPrice (null)
        100_000_000,  # size → 1.00000000
        50_000_000,  # sizeOpen
        price,  # avgFillPrice
        1710000000000000,  # createdAt
        1710000001000000,  # updatedAt
        ACCOUNT_BYTES,  # account (32-byte fixed)
        1710000002000000,  # receivedAt
        1710000003000000,  # publishedAt
        0,  # stp NONE
        1,  # flags REDUCE_ONLY bit
    )
    payload += _var(b"order-123")
    payload += _var(b"client-456")
    payload += _var(market)
    payload += _var(b"")  # cancelReason (empty)
    return _hdr(block_len, 20) + payload


def test_order_event():
    channel, model = decode_frame(_make_order_frame())
    assert channel == "orders.BTC-USD-PERP"
    assert isinstance(model, OrderEventData)
    assert model.status == "OPEN"
    assert model.side == "BUY"
    assert model.order_type == "LIMIT"
    assert model.time_in_force == "GTC"
    assert model.price == "42000.00000000"
    assert model.trigger_price is None
    assert model.order_id == "order-123"
    assert model.client_order_id == "client-456"
    assert model.market == "BTC-USD-PERP"
    assert model.account == "0xdeadbeef"
    assert model.stp == "NONE"
    assert model.flags == ["REDUCE_ONLY"]
    assert model.cancel_reason == ""


def test_order_event_null_avg_fill():
    block_len = _ORDER_STRUCT.size
    payload = _ORDER_STRUCT.pack(
        1710000000000000,
        1,
        1,  # NEW
        1,
        1,
        1,
        4200000000000,  # price
        INT64_MIN,  # triggerPrice null
        100_000_000,  # size
        100_000_000,  # sizeOpen
        INT64_MIN,  # avgFillPrice null
        1710000000000000,  # createdAt
        1710000000000000,  # updatedAt
        ACCOUNT_BYTES,
        1710000000000000,  # receivedAt
        1710000000000000,  # publishedAt
        0,  # stp
        0,  # flags
    )
    payload += _var(b"ord") + _var(b"cli") + _var(MARKET) + _var(b"")
    frame = _hdr(block_len, 20) + payload
    _, model = decode_frame(frame)
    assert model.avg_fill_price is None
    assert model.status == "NEW"


# ── FillEvent (id=21) ────────────────────────────────────────────────────

_FILL_STRUCT = struct.Struct("<qqBBBqqqqq32sqq")


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
        ACCOUNT_BYTES,  # account (32-byte fixed)
        4199000000000,  # underlyingPrice → 41990.00000000
        500_000_000,  # realizedFunding → 5.00000000
    )
    payload += _var(b"fill-1")
    payload += _var(b"order-1")
    payload += _var(b"client-1")
    payload += _var(b"trade-1")
    payload += _var(market)
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
    assert model.account == "0xdeadbeef"
    assert model.underlying_price == "41990.00000000"
    assert model.realized_funding == "5.00000000"


def test_fill_event_new_fill_types():
    block_len = _FILL_STRUCT.size
    for raw, expected in [(3, "UNWIND_TRANSFER"), (4, "SETTLE_MARKET"), (5, "RPI"), (6, "BLOCK_TRADE")]:
        payload = _FILL_STRUCT.pack(
            1710000000000000,
            1,
            raw,
            1,
            1,
            4200000000000,
            50_000_000,
            0,
            INT64_MIN,
            1710000000000000,
            ACCOUNT_BYTES,
            4199000000000,
            0,
        )
        payload += _var(b"f") + _var(b"o") + _var(b"c") + _var(b"t") + _var(MARKET)
        _, model = decode_frame(_hdr(block_len, 21) + payload)
        assert model.fill_type == expected


# ── PositionEvent (id=22) ────────────────────────────────────────────────

_POS_STRUCT = struct.Struct("<qqBqqqqqqqq32sqqqqqB")


def _make_position_frame(side: int = 1, liq_price: int = INT64_MIN, mark_price: int = 4190000000000) -> bytes:
    block_len = _POS_STRUCT.size
    payload = _POS_STRUCT.pack(
        1710000000000000,  # ts
        9,  # seq
        side,  # side
        100_000_000,  # size → 1.00000000
        4200000000000,  # avgEntryPrice
        -5000000000,  # unrealizedPnl (negative)
        1000000000,  # realizedPnl
        mark_price,  # markPrice (Price8NULL since 1:2)
        liq_price,  # liquidationPrice (null by default)
        5_00000000,  # leverage → 5.00000000
        1710000001000000,  # updatedAt
        ACCOUNT_BYTES,  # account (32-byte fixed)
        4200000000000,  # avgEntryPriceUsd
        4200000000000,  # cost
        4200000000000,  # costUsd
        1000000000,  # cachedFundingIndex
        -500000000,  # unrealizedFundingPnl
        1,  # status OPEN
    )
    payload += _var(MARKET)
    payload += _var(b"fill-abc")  # lastFillId
    return _hdr(block_len, 22) + payload


def test_position_event_long():
    channel, model = decode_frame(_make_position_frame(side=1))
    assert channel == "positions"
    assert isinstance(model, PositionEventData)
    assert model.side == "LONG"
    assert model.account == "0xdeadbeef"
    assert model.market == "BTC-USD-PERP"


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

_ACC_STRUCT = struct.Struct("<qqqqqqqqq32sqB")


def _make_account_frame(unrealized_pnl: int = 500_00000000) -> bytes:
    block_len = _ACC_STRUCT.size
    payload = _ACC_STRUCT.pack(
        1710000000000000,  # ts
        11,  # seq
        10000_00000000,  # totalCollateral → 10000.00000000
        5000_00000000,  # freeCollateral
        2000_00000000,  # initialMarginReq
        1000_00000000,  # maintenanceMarginReq
        10500_00000000,  # accountValue
        unrealized_pnl,  # unrealizedPnl (Value8NULL since 1:2)
        1710000001000000,  # updatedAt
        ACCOUNT_BYTES,  # account (32-byte fixed)
        9000_00000000,  # marginCushion → 9000.00000000
        1,  # status ACTIVE
    )
    payload += _var(b"USDC")  # settlementAsset
    return _hdr(block_len, 23) + payload


def test_account_event():
    channel, model = decode_frame(_make_account_frame())
    assert channel == "account"
    assert isinstance(model, AccountEventData)
    assert model.total_collateral == "10000.00000000"
    assert model.free_collateral == "5000.00000000"
    assert model.account == "0xdeadbeef"
    assert model.margin_cushion == "9000.00000000"
    assert model.status == "ACTIVE"
    assert model.settlement_asset == "USDC"


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


# ── FundingRateComparisonEvent (id=6) ────────────────────────────────────

# Golden frame captured from the server's encoder. Decoding the exact bytes
# the server emits is what makes this a wire-format contract rather than a
# test of our own packing.
_FRC_GOLDEN_HEX = "1a0006000100010000401e18240a060000401e18240a060000e1f5050000000001010c4254432d5553442d50455250"


def test_frc_event_decodes_go_golden_frame():
    channel, model = decode_frame(bytes.fromhex(_FRC_GOLDEN_HEX))
    assert channel == "funding_rate_comparison"
    assert isinstance(model, FundingRateComparisonEventData)
    assert model.market == "BTC-USD-PERP"
    assert model.hourly_funding_rate == "0.000100000000"
    assert model.last_updated_at == 1700000000000


def test_frc_event_enum_spelling_matches_json_feed():
    """SBE stores enums bare; the JSON feed sends the prefixed protobuf names.

    Callbacks must see identical values on both transports, so the codec
    restores the prefixes.
    """
    _, model = decode_frame(bytes.fromhex(_FRC_GOLDEN_HEX))
    assert model.asset_kind == "ASSET_KIND_PERPETUAL_FUTURE"
    assert model.source == "SOURCE_PARADEX"


_FRC_STRUCT = struct.Struct("<qqqBB")


def _make_frc_frame(asset_kind: int = 1, source: int = 1, rate: int = 10000) -> bytes:
    payload = _FRC_STRUCT.pack(1710000000000000, 1710000000000000, rate, asset_kind, source)
    return _hdr(_FRC_STRUCT.size, 6) + payload + _var(MARKET)


def test_frc_event_all_sources():
    for raw, expected in [
        (1, "SOURCE_PARADEX"),
        (2, "SOURCE_BINANCE"),
        (3, "SOURCE_BYBIT"),
        (4, "SOURCE_OKX"),
        (7, "SOURCE_HYPERLIQUID"),
        (12, "SOURCE_STORK"),
    ]:
        _, model = decode_frame(_make_frc_frame(source=raw))
        assert model.source == expected


def test_frc_event_asset_kinds():
    for raw, expected in [
        (1, "ASSET_KIND_PERPETUAL_FUTURE"),
        (2, "ASSET_KIND_OPTION"),
        (3, "ASSET_KIND_SPOT"),
    ]:
        _, model = decode_frame(_make_frc_frame(asset_kind=raw))
        assert model.asset_kind == expected


def test_frc_event_unknown_enum_is_none():
    """An unrecognised venue must not raise: new sources are added upstream."""
    _, model = decode_frame(_make_frc_frame(source=200))
    assert model.source is None


def test_frc_event_negative_rate():
    _, model = decode_frame(_make_frc_frame(rate=-125000000))
    assert model.hourly_funding_rate == "-0.000125000000"


# ── Schema 1:2 additions ─────────────────────────────────────────────────
#
# The SDK still negotiates 1:1, so both shapes have to decode: a 1:1 frame
# (107-byte block, no feeCurrency) and a 1:2 one (116-byte block, feeCurrency
# after market). The server trims the block and cuts the var-data section to
# the negotiated version and stamps the header to match, so block_len gates the
# appended block fields and the header version gates the appended var-data.

_FILL_V2_TAIL = struct.Struct("<BQ")  # flags + orderbookSeqNo, appended in 1:2


def _make_fill_frame_v2(
    flags: int = 0b011,  # INTERACTIVE | RPI
    orderbook_seq_no: int = 987654,
    fee_currency: bytes = b"DIME",
    seq: int = 8,
) -> bytes:
    block = _FILL_STRUCT.pack(
        1710000000000000,  # ts
        seq,  # seq (optional since 1:2)
        1,  # fillType FILL
        1,  # side BUY
        1,  # liquidity MAKER
        4200000000000,  # price
        50_000_000,  # size
        210_000_000,  # fee
        INT64_MIN,  # realizedPnl null
        1710000000000000,  # createdAt
        ACCOUNT_BYTES,  # account
        4199000000000,  # underlyingPrice
        0,  # realizedFunding
    ) + _FILL_V2_TAIL.pack(flags, orderbook_seq_no)
    payload = block + _var(b"fill-1") + _var(b"order-1") + _var(b"client-1") + _var(b"trade-1") + _var(MARKET)
    payload += _var(fee_currency)
    return _hdr(len(block), 21, version=2) + payload


def test_fill_v2_block_grew_to_116():
    """The decoder's own tier boundary is 107 -> 116, not just this file's copy of it."""
    from paradex_py.api.sbe.codec import _FILLEVENT_STRUCT, _FILLEVENT_STRUCT_V2

    assert _FILLEVENT_STRUCT.size == 107
    assert _FILLEVENT_STRUCT.size + _FILLEVENT_STRUCT_V2.size == 116
    # The frames this file builds have to match the layout the decoder expects,
    # or every other assertion here passes against the wrong shape.
    assert _FILL_STRUCT.size == _FILLEVENT_STRUCT.size
    assert _FILL_V2_TAIL.size == _FILLEVENT_STRUCT_V2.size


def test_fill_v2_appended_fields():
    channel, model = decode_frame(_make_fill_frame_v2())
    assert channel == "fills.BTC-USD-PERP"
    assert model.flags == ["INTERACTIVE", "RPI"]
    assert model.orderbook_seq_no == 987654
    assert model.fee_currency == "DIME"
    # The var-data before feeCurrency must still land on the right offsets.
    assert model.market == "BTC-USD-PERP"
    assert model.trade_id == "trade-1"


def test_fill_v2_fee_currency_usdc():
    _, model = decode_frame(_make_fill_frame_v2(fee_currency=b"USDC"))
    assert model.fee_currency == "USDC"


def test_fill_flags_unknown_bit():
    """UNKNOWN is set server-side for a fill flag this schema has no bit for."""
    _, model = decode_frame(_make_fill_frame_v2(flags=1 << 7))
    assert model.flags == ["UNKNOWN"]


def test_fill_flags_fastfill():
    _, model = decode_frame(_make_fill_frame_v2(flags=1 << 2))
    assert model.flags == ["FASTFILL"]


def test_fill_flags_empty_is_not_absent():
    """No bits set decodes to [], which is distinct from the None of a 1:1 frame."""
    _, model = decode_frame(_make_fill_frame_v2(flags=0))
    assert model.flags == []


def test_fill_seq_optional_null():
    """seq is null for position transfers, which carry no orderbook sequence."""
    _, model = decode_frame(_make_fill_frame_v2(seq=INT64_MIN))
    assert model.seq_no is None


def test_fill_seq_optional_present():
    _, model = decode_frame(_make_fill_frame_v2(seq=42))
    assert model.seq_no == 42


def test_fill_v1_frame_leaves_v2_fields_absent():
    """A 1:1 frame has none of the appended fields and must not read past its block."""
    _, model = decode_frame(_make_fill_frame(market=MARKET))
    assert model.flags is None
    assert model.orderbook_seq_no is None
    assert model.fee_currency is None
    # A short block must not desync the var-data that follows it.
    assert model.market == "BTC-USD-PERP"
    assert model.fill_id == "fill-1"


def test_order_flags_mmp_bit():
    """OrderFlags.MMP is bit 5, added in 1:2."""
    _, model = decode_frame(_make_order_frame_with_flags(1 << 5))
    assert model.flags == ["MMP"]


def _make_order_frame_with_flags(flags: int) -> bytes:
    payload = _ORDER_STRUCT.pack(
        1710000000000000,
        7,
        3,  # status OPEN
        1,  # side BUY
        1,  # orderType LIMIT
        1,  # timeInForce GTC
        4200000000000,
        INT64_MIN,
        100_000_000,
        50_000_000,
        4200000000000,
        1710000000000000,
        1710000001000000,
        ACCOUNT_BYTES,
        1710000002000000,
        1710000003000000,
        0,  # stp NONE
        flags,
    )
    payload += _var(b"order-123") + _var(b"client-456") + _var(MARKET) + _var(b"")
    return _hdr(_ORDER_STRUCT.size, 20, version=2) + payload


def test_position_mark_price_null():
    """markPrice became Price8NULL in 1:2 — nothing upstream feeds it."""
    _, model = decode_frame(_make_position_frame(mark_price=INT64_MIN))
    assert model.mark_price is None


def test_position_mark_price_present():
    _, model = decode_frame(_make_position_frame(mark_price=4190000000000))
    assert model.mark_price == "41900.00000000"


def test_account_unrealized_pnl_null():
    """unrealizedPnl became Value8NULL in 1:2 — nothing upstream feeds it."""
    _, model = decode_frame(_make_account_frame(unrealized_pnl=INT64_MIN))
    assert model.unrealized_pnl is None


def test_account_unrealized_pnl_present():
    _, model = decode_frame(_make_account_frame(unrealized_pnl=500_00000000))
    assert model.unrealized_pnl == "500.00000000"


def test_truncated_var_data_raises_decode_error():
    """A frame whose var-data stops short must raise the error the ws client handles.

    Reachable if a server ever stamps its own schema version on a frame trimmed
    to an older one: the decoder would look for feeCurrency that is not there.
    An IndexError here would escape _process_binary_message and surface as a
    connection failure instead of a dropped frame.
    """
    frame = _make_fill_frame_v2()
    with pytest.raises(SbeDecodeError, match="Truncated frame"):
        decode_frame(frame[:-3])


def test_var_data_length_past_end_raises_decode_error():
    """A length prefix longer than the bytes that follow it must not slice silently."""
    frame = bytearray(_make_fill_frame_v2())
    frame[-5] = 200  # feeCurrency length prefix, far past the end
    with pytest.raises(SbeDecodeError, match="Truncated frame"):
        decode_frame(bytes(frame))


# ── Blocks trimmed to an earlier version ─────────────────────────────────
#
# MarketSummary and FundingData already carried sinceVersion=1 fields before
# this change, and both went from an unconditional unpack to a block_len gate.
# A server capped below 1:1 sends the trimmed block, which no other frame in
# this file exercises.

_MS_V0_STRUCT = struct.Struct("<" + "q" * 27)  # schema 1:0 MarketSummaryEvent block
_FD_V0_STRUCT = struct.Struct("<qqqqqqqh")  # schema 1:0 FundingDataEvent block


def _make_ms_v0_frame() -> bytes:
    payload = _MS_V0_STRUCT.pack(*([1710000000000000, 5] + [4200000000000] * 25))
    payload += _var(MARKET)
    return _hdr(_MS_V0_STRUCT.size, 4, version=0) + payload


def _make_fd_v0_frame() -> bytes:
    payload = _FD_V0_STRUCT.pack(1710000000000000, 3, 1_000_000, 4200000000000, 1710000000000000, 500_000, 800_000, 8)
    payload += _var(MARKET)
    return _hdr(_FD_V0_STRUCT.size, 5, version=0) + payload


def test_ms_v0_block_sizes():
    from paradex_py.api.sbe.codec import _MARKETSUMMARYEVENT_STRUCT, _MARKETSUMMARYEVENT_STRUCT_V1

    assert _MARKETSUMMARYEVENT_STRUCT.size == 216
    assert _MARKETSUMMARYEVENT_STRUCT.size + _MARKETSUMMARYEVENT_STRUCT_V1.size == 240
    assert _MS_V0_STRUCT.size == _MARKETSUMMARYEVENT_STRUCT.size


def test_ms_v0_frame_leaves_v1_fields_absent():
    channel, model = decode_frame(_make_ms_v0_frame())
    assert channel == "markets_summary.BTC-USD-PERP"
    assert model.forward_rate is None
    assert model.risk_free_rate is None
    assert model.funding_rate_precise is None
    # A trimmed block must not shift the var-data that follows it.
    assert model.market == "BTC-USD-PERP"
    assert model.mark_price == "42000.00000000"


def test_fd_v0_block_sizes():
    from paradex_py.api.sbe.codec import _FUNDINGDATAEVENT_STRUCT, _FUNDINGDATAEVENT_STRUCT_V1

    assert _FUNDINGDATAEVENT_STRUCT.size == 58
    assert _FUNDINGDATAEVENT_STRUCT.size + _FUNDINGDATAEVENT_STRUCT_V1.size == 66
    assert _FD_V0_STRUCT.size == _FUNDINGDATAEVENT_STRUCT.size


def test_fd_v0_frame_leaves_v1_field_absent():
    channel, model = decode_frame(_make_fd_v0_frame())
    assert channel == "funding_data.BTC-USD-PERP"
    assert model.impact_premium_rate is None
    assert model.market == "BTC-USD-PERP"
    assert model.funding_rate == "0.01000000"
    assert model.funding_period_hours == 8


# ── Malformed frames must not escape as struct.error ─────────────────────


def test_block_len_past_payload_raises_decode_error():
    """blockLength drives every unpack offset, so it has to be bounded.

    struct.error is not what _process_binary_message catches, and from
    pump_once it escapes the try and takes the connection down.
    """
    frame = _make_fill_frame_v2()
    truncated = frame[: 8 + 110]  # header + 110 bytes, but blockLength says 116
    with pytest.raises(SbeDecodeError, match="Truncated frame"):
        decode_frame(truncated)


def test_block_shorter_than_base_raises_decode_error():
    """A block_len inside the payload but a payload shorter than the base block."""
    payload = _FILL_STRUCT.pack(
        1710000000000000, 1, 1, 1, 1, 4200000000000, 50_000_000, 0, INT64_MIN, 1710000000000000, ACCOUNT_BYTES, 0, 0
    )
    frame = _hdr(20, 21, version=1) + payload[:20]
    with pytest.raises(SbeDecodeError):
        decode_frame(frame)


# ── Schema 1:2 fields added in place (tradeIdStr, request_info, lastSeenNotification) ──
#
# These landed in 1:2 after it was first served, so version 2 describes two
# layouts of each message and the header version byte cannot tell them apart.
# The decoder has to go by blockLength for fixed fields and by what is left in
# the frame for appended var-data.

# A real Paradex trade id: 28 digits, far past int64. The short ids in the
# fixtures above are why the int64 truncation went unnoticed.
_REAL_TRADE_ID = "1790243311180201709220570002"


def _int64_wrap(n: int) -> int:
    """What the server puts in the legacy int64 tradeId: the low 64 bits, signed."""
    low = n & 0xFFFF_FFFF_FFFF_FFFF
    return low - (1 << 64) if low >= 1 << 63 else low


def _make_trade_frame_v2(trade_id_str: bytes | None = _REAL_TRADE_ID.encode(), version: int = 2) -> bytes:
    trade_id = _int64_wrap(int(_REAL_TRADE_ID))
    payload = _TRADE_STRUCT.pack(1710000000123456, 42, trade_id, 1, 4200050000000, 100000, 1710000000100000, 1)
    payload += _var(MARKET)
    if trade_id_str is not None:
        payload += _var(trade_id_str)
    return _hdr(_TRADE_STRUCT.size, 1, version=version) + payload


def test_trade_v2_round_trips_28_digit_trade_id():
    _channel, model = decode_frame(_make_trade_frame_v2())
    assert model.trade_id_str == _REAL_TRADE_ID
    assert model.model_dump()["trade_id_str"] == _REAL_TRADE_ID
    # The legacy int64 cannot hold it: it is the wrapped low 64 bits, not the id.
    with pytest.warns(DeprecationWarning):
        assert model.trade_id == _int64_wrap(int(_REAL_TRADE_ID))
        assert str(model.trade_id) != _REAL_TRADE_ID


def test_trade_int64_trade_id_can_be_negative():
    """Some real ids wrap to a negative int64; trade_id_str is still exact."""
    real = str((1 << 90) + (1 << 63) + 7)  # low 64 bits have the sign bit set
    trade_id = _int64_wrap(int(real))
    assert trade_id < 0
    payload = _TRADE_STRUCT.pack(0, 0, trade_id, 1, 0, 0, 0, 1) + _var(MARKET) + _var(real.encode())
    _channel, model = decode_frame(_hdr(_TRADE_STRUCT.size, 1, version=2) + payload)
    assert model.trade_id_str == real


def test_trade_v2_without_trade_id_str_is_absent_not_malformed():
    """A 1:2 frame from a server that predates tradeIdStr ends after market."""
    _channel, model = decode_frame(_make_trade_frame_v2(trade_id_str=None))
    assert model.market == "BTC-USD-PERP"
    assert model.trade_id_str is None


def test_trade_v1_frame_ignores_trade_id_str():
    """Below 1:2 the server cuts the var-data before tradeIdStr; the header gates it."""
    _channel, model = decode_frame(_make_trade_frame_v2(trade_id_str=None, version=1))
    assert model.trade_id_str is None
    assert model.market == "BTC-USD-PERP"


def test_trade_v2_trade_id_str_cut_short_raises():
    """Absent at the end of the frame is tolerated; started and cut short is not."""
    with pytest.raises(SbeDecodeError, match="Truncated frame"):
        decode_frame(_make_trade_frame_v2()[:-5])


def test_trade_reads_block_length_from_header():
    """A longer block from a newer schema must be skipped, not read as var-data."""
    payload = _TRADE_STRUCT.pack(1710000000123456, 42, 1, 1, 4200050000000, 100000, 1710000000100000, 1)
    payload += b"\xaa" * 8  # a fixed field this decoder does not know
    payload += _var(MARKET) + _var(_REAL_TRADE_ID.encode())
    _channel, model = decode_frame(_hdr(_TRADE_STRUCT.size + 8, 1, version=2) + payload)
    assert model.market == "BTC-USD-PERP"
    assert model.trade_id_str == _REAL_TRADE_ID


def test_trade_id_access_is_deprecated():
    _channel, model = decode_frame(_make_trade_frame())
    with pytest.warns(DeprecationWarning, match="use trade_id_str"):
        _ = model.trade_id


_ORDER_V2_TAIL = struct.Struct("<BB")  # requestStatus, requestType


def _make_order_frame_v2(
    request_status: int | None = 1,  # PENDING
    request_type: int = 1,  # MODIFY_ORDER
    request_id: bytes | None = b"req-789",
    request_message: bytes | None = b"",
    version: int = 2,
) -> bytes:
    """An order frame at 1:2. request_status=None leaves the block at its 1:1 length."""
    base = _make_order_frame()[8:]
    block, var_data = base[: _ORDER_STRUCT.size], base[_ORDER_STRUCT.size :]
    if request_status is not None:
        block += _ORDER_V2_TAIL.pack(request_status, request_type)
    if request_id is not None:
        var_data += _var(request_id)
    if request_message is not None:
        var_data += _var(request_message)
    return _hdr(len(block), 20, version=version) + block + var_data


def test_order_v2_block_grew_to_128():
    frame = _make_order_frame_v2()
    assert HEADER.unpack_from(frame, 0)[0] == 128


def test_order_v2_request_info_present():
    _channel, model = decode_frame(_make_order_frame_v2(request_message=b"price out of band"))
    assert model.request_status == "PENDING"
    assert model.request_type == "MODIFY_ORDER"
    assert model.request_id == "req-789"
    assert model.request_message == "price out of band"
    assert model.request_info == {
        "id": "req-789",
        "message": "price out of band",
        "request_type": "MODIFY_ORDER",
        "status": "PENDING",
    }
    # Everything before the appended fields still decodes where it did.
    assert model.cancel_reason == ""
    assert model.market == "BTC-USD-PERP"


def test_order_v2_both_unspecified_means_no_request_info():
    """UNSPECIFIED on both enums is how SBE says the JSON omitted request_info."""
    _channel, model = decode_frame(_make_order_frame_v2(request_status=0, request_type=0, request_id=b""))
    assert model.request_status == "UNSPECIFIED"
    assert model.request_type == "UNSPECIFIED"
    assert model.request_info is None


def test_order_v1_frame_leaves_request_fields_absent():
    frame = _make_order_frame_v2(request_status=None, request_id=None, request_message=None, version=1)
    assert HEADER.unpack_from(frame, 0)[0] == 126
    _channel, model = decode_frame(frame)
    assert model.request_status is None
    assert model.request_type is None
    assert model.request_id is None
    assert model.request_message is None
    assert model.request_info is None
    assert model.cancel_reason == ""


def test_order_v2_from_server_predating_request_info():
    """1:2 header, 1:1 block and var-data: what a server before request_info sends."""
    frame = _make_order_frame_v2(request_status=None, request_id=None, request_message=None)
    _channel, model = decode_frame(frame)
    assert model.request_status is None
    assert model.request_id is None
    assert model.request_info is None
    assert model.market == "BTC-USD-PERP"


_ACC_V2_TAIL = struct.Struct("<q")  # lastSeenNotification


def _make_account_frame_v2(last_seen_us: int | None = 1713400000000000, version: int = 2) -> bytes:
    base = _make_account_frame()[8:]
    block, var_data = base[: _ACC_STRUCT.size], base[_ACC_STRUCT.size :]
    if last_seen_us is not None:
        block += _ACC_V2_TAIL.pack(last_seen_us)
    return _hdr(len(block), 23, version=version) + block + var_data


def test_account_v2_last_seen_notification():
    frame = _make_account_frame_v2()
    assert HEADER.unpack_from(frame, 0)[0] == 121
    _channel, model = decode_frame(frame)
    # Microseconds on the wire, milliseconds out — the same as JSON carries it.
    assert model.last_seen_notification == 1713400000000
    assert model.settlement_asset == "USDC"
    assert model.status == "ACTIVE"


def test_account_v2_never_acknowledged_is_zero_not_absent():
    _channel, model = decode_frame(_make_account_frame_v2(last_seen_us=0))
    assert model.last_seen_notification == 0


def test_account_v1_frame_leaves_last_seen_notification_absent():
    frame = _make_account_frame_v2(last_seen_us=None, version=1)
    assert HEADER.unpack_from(frame, 0)[0] == 113
    _channel, model = decode_frame(frame)
    assert model.last_seen_notification is None
    assert model.settlement_asset == "USDC"
