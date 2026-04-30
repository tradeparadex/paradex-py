from decimal import Decimal

from paradex_py.message.block_trades import (
    BLOCK_TRADE_PAYLOAD_VERSION,
    BlockTrade,
    BlockTradeOffer,
    BlockTradeOrder,
    Trade,
    block_trade_from_response,
    build_block_trade_message,
    build_block_trade_offer_message,
)


def _eth_perp_orders():
    """Two BlockTradeOrders on ETH-USD-PERP — matched maker/taker."""
    maker = BlockTradeOrder(
        account="0xMAKER",
        side="BUY",
        order_type="LIMIT",
        size=Decimal("0.1"),
        price=Decimal("1500"),
    )
    taker = BlockTradeOrder(
        account="0xTAKER",
        side="SELL",
        order_type="LIMIT",
        size=Decimal("0.1"),
        price=Decimal("1500"),
    )
    return maker, taker


def test_block_trade_order_class():
    order = BlockTradeOrder(
        account="0xABC",
        side="BUY",
        order_type="LIMIT",
        size=Decimal("0.5"),
        price=Decimal("100"),
    )
    assert order.account == "0xABC"
    assert order.side == "BUY"
    assert order.order_type == "LIMIT"
    assert order.size == Decimal("0.5")
    assert order.price == Decimal("100")


def test_block_trade_order_defaults():
    """Empty BlockTradeOrder — used when one side of a Trade is unfilled (e.g. offer-based parent)."""
    order = BlockTradeOrder()
    assert order.account == ""
    assert order.side == ""
    assert order.order_type == ""
    assert order.size == Decimal(0)
    assert order.price == Decimal(0)


def test_trade_fill_helper():
    maker, taker = _eth_perp_orders()
    trade = Trade.fill(
        market="ETH-USD-PERP",
        price=Decimal("1500.50"),
        size=Decimal("0.1"),
        maker_order=maker,
        taker_order=taker,
    )

    assert trade.market == "ETH-USD-PERP"
    assert trade.price == Decimal("1500.50")
    assert trade.size == Decimal("0.1")
    assert trade.maker_order is maker
    assert trade.taker_order is taker
    assert trade.min_size == Decimal(0)
    assert trade.max_size == Decimal(0)


def test_trade_constraint_helper():
    trade = Trade.constraint(
        market="ETH-USD-PERP",
        min_size=Decimal("0.05"),
        max_size=Decimal("1.0"),
        min_price=Decimal("1400"),
        max_price=Decimal("1600"),
        oracle_tolerance=Decimal("0.02"),
    )

    assert trade.market == "ETH-USD-PERP"
    assert trade.price == Decimal(0)
    assert trade.size == Decimal(0)
    assert trade.maker_order is None
    assert trade.taker_order is None
    assert trade.min_size == Decimal("0.05")
    assert trade.max_size == Decimal("1.0")
    assert trade.max_price == Decimal("1600")
    assert trade.oracle_tolerance == Decimal("0.02")


def test_block_trade_class():
    maker, taker = _eth_perp_orders()
    trades = [
        Trade.fill(
            market="ETH-USD-PERP",
            price=Decimal("1500.50"),
            size=Decimal("0.1"),
            maker_order=maker,
            taker_order=taker,
        ),
    ]

    block_trade = BlockTrade(nonce="n1", expiration=1700000000000, trades=trades)
    assert block_trade.version == BLOCK_TRADE_PAYLOAD_VERSION
    assert block_trade.nonce == "n1"
    assert block_trade.expiration == 1700000000000
    assert len(block_trade.trades) == 1


def test_block_trade_offer_class():
    maker, _ = _eth_perp_orders()
    trades = [Trade.fill("ETH-USD-PERP", Decimal("1500"), Decimal("0.1"), maker, None)]
    offer = BlockTradeOffer(
        nonce="off1",
        expiration=1700000000000,
        block_trade_id="parent_id_123",
        trades=trades,
    )
    assert offer.version == BLOCK_TRADE_PAYLOAD_VERSION
    assert offer.block_trade_id == "parent_id_123"
    assert len(offer.trades) == 1


def test_build_block_trade_message_fill():
    """Single-leg fill Trade — verify the SNIP-12 rev1 typed-data structure end-to-end."""
    maker, taker = _eth_perp_orders()
    trade = Trade.fill(
        market="ETH-USD-PERP",
        price=Decimal("1500.50"),
        size=Decimal("0.1"),
        maker_order=maker,
        taker_order=taker,
    )
    block_trade = BlockTrade(nonce="42", expiration=1700000000000, trades=[trade])
    message = build_block_trade_message(1, block_trade)

    expected = {
        "domain": {
            "name": "Paradex",
            "chainId": "0x1",
            "version": "1",
            "revision": "1",
        },
        "primaryType": "BlockTrade",
        "types": {
            "StarknetDomain": [
                {"name": "name", "type": "shortstring"},
                {"name": "version", "type": "shortstring"},
                {"name": "chainId", "type": "shortstring"},
                {"name": "revision", "type": "shortstring"},
            ],
            "BlockTrade": [
                {"name": "version", "type": "shortstring"},
                {"name": "nonce", "type": "felt"},
                {"name": "expiration", "type": "felt"},
                {"name": "trades", "type": "merkletree", "contains": "Trade"},
            ],
            "Trade": [
                {"name": "market", "type": "shortstring"},
                {"name": "price", "type": "felt"},
                {"name": "size", "type": "felt"},
                {"name": "maker_order", "type": "BlockTradeOrder"},
                {"name": "taker_order", "type": "BlockTradeOrder"},
                {"name": "min_size", "type": "felt"},
                {"name": "max_size", "type": "felt"},
                {"name": "min_price", "type": "felt"},
                {"name": "max_price", "type": "felt"},
                {"name": "oracle_tolerance", "type": "felt"},
            ],
            "BlockTradeOrder": [
                {"name": "account", "type": "felt"},
                {"name": "side", "type": "shortstring"},
                {"name": "type", "type": "shortstring"},
                {"name": "size", "type": "felt"},
                {"name": "price", "type": "felt"},
            ],
        },
        "message": {
            "version": "2",
            "nonce": "42",
            "expiration": "1700000000000",
            "trades": [
                {
                    "market": "ETH-USD-PERP",
                    "price": "150050000000",
                    "size": "10000000",
                    "maker_order": {
                        "account": "0xMAKER",
                        "side": "1",  # BUY → "1"
                        "type": "LIMIT",
                        "size": "10000000",
                        "price": "150000000000",
                    },
                    "taker_order": {
                        "account": "0xTAKER",
                        "side": "2",  # SELL → "2"
                        "type": "LIMIT",
                        "size": "10000000",
                        "price": "150000000000",
                    },
                    "min_size": "0",
                    "max_size": "0",
                    "min_price": "0",
                    "max_price": "0",
                    "oracle_tolerance": "0",
                }
            ],
        },
    }

    assert message == expected


def test_build_block_trade_message_constraint_only():
    """Offer-based parent block: Trades carry constraints, fill fields zero."""
    trade = Trade.constraint(
        market="BTC-USD-PERP",
        min_size=Decimal("0.05"),
        max_size=Decimal("1.0"),
        min_price=Decimal("29000"),
        max_price=Decimal("31000"),
        oracle_tolerance=Decimal("0.02"),
    )
    block_trade = BlockTrade(nonce="99", expiration=1700000000000, trades=[trade])
    message = build_block_trade_message(1, block_trade)

    trade_msg = message["message"]["trades"][0]
    # Constraint fields populated
    assert trade_msg["market"] == "BTC-USD-PERP"
    assert trade_msg["min_size"] == "5000000"  # 0.05 * 1e8
    assert trade_msg["max_size"] == "100000000"  # 1.0 * 1e8
    assert trade_msg["min_price"] == "2900000000000"
    assert trade_msg["max_price"] == "3100000000000"
    assert trade_msg["oracle_tolerance"] == "2000000"
    # Fill fields zero
    assert trade_msg["price"] == "0"
    assert trade_msg["size"] == "0"
    # Empty BlockTradeOrders on both sides — encoded with all "0"
    for side_key in ("maker_order", "taker_order"):
        assert trade_msg[side_key] == {
            "account": "0",
            "side": "0",
            "type": "0",
            "size": "0",
            "price": "0",
        }


def test_build_block_trade_message_offer_based_one_side():
    """Offer-based create with one side filled (initiator) and the other empty (offer fills later)."""
    maker, _ = _eth_perp_orders()
    trade = Trade.fill(
        market="ETH-USD-PERP",
        price=Decimal("1500"),
        size=Decimal("0.1"),
        maker_order=maker,
        taker_order=None,
    )
    block_trade = BlockTrade(nonce="n", expiration=1700000000000, trades=[trade])
    message = build_block_trade_message(1, block_trade)

    trade_msg = message["message"]["trades"][0]
    assert trade_msg["maker_order"]["account"] == "0xMAKER"
    assert trade_msg["taker_order"] == {
        "account": "0",
        "side": "0",
        "type": "0",
        "size": "0",
        "price": "0",
    }


def test_build_block_trade_message_sorts_by_market():
    """Trades are canonically sorted by market (alphabetical) regardless of input order.
    Without this the merkle root diverges from the server, which sorts independently."""
    maker, taker = _eth_perp_orders()
    eth = Trade.fill("ETH-USD-PERP", Decimal("1500"), Decimal("0.1"), maker, taker)
    btc = Trade.fill("BTC-USD-PERP", Decimal("45000"), Decimal("0.01"), maker, taker)

    bt_eth_first = BlockTrade(nonce="n", expiration=1700000000000, trades=[eth, btc])
    bt_btc_first = BlockTrade(nonce="n", expiration=1700000000000, trades=[btc, eth])

    msg_eth_first = build_block_trade_message(1, bt_eth_first)
    msg_btc_first = build_block_trade_message(1, bt_btc_first)

    # Same trades, different input order — canonical sort produces the SAME message.
    assert msg_eth_first == msg_btc_first
    # And the canonical order is alphabetical: BTC before ETH.
    assert msg_eth_first["message"]["trades"][0]["market"] == "BTC-USD-PERP"
    assert msg_eth_first["message"]["trades"][1]["market"] == "ETH-USD-PERP"


def test_build_block_trade_offer_message_sorts_by_market():
    maker, _ = _eth_perp_orders()
    eth = Trade.fill("ETH-USD-PERP", Decimal("1500"), Decimal("0.1"), maker, None)
    btc = Trade.fill("BTC-USD-PERP", Decimal("45000"), Decimal("0.01"), maker, None)

    offer_eth_first = BlockTradeOffer(nonce="o", expiration=1700000000000, block_trade_id="P", trades=[eth, btc])
    offer_btc_first = BlockTradeOffer(nonce="o", expiration=1700000000000, block_trade_id="P", trades=[btc, eth])

    msg_a = build_block_trade_offer_message(1, offer_eth_first)
    msg_b = build_block_trade_offer_message(1, offer_btc_first)

    assert msg_a == msg_b
    assert msg_a["message"]["trades"][0]["market"] == "BTC-USD-PERP"


def test_build_block_trade_offer_message_schema():
    """Offer typed-data has primaryType BlockTradeOffer and binds block_trade_id."""
    maker, _ = _eth_perp_orders()
    trade = Trade.fill("ETH-USD-PERP", Decimal("1500"), Decimal("0.1"), maker, None)
    offer = BlockTradeOffer(
        nonce="o1",
        expiration=1700000000000,
        block_trade_id="parent_block_xyz",
        trades=[trade],
    )
    message = build_block_trade_offer_message(7, offer)

    assert message["primaryType"] == "BlockTradeOffer"
    assert message["domain"]["chainId"] == "0x7"
    assert message["domain"]["revision"] == "1"
    assert message["message"]["block_trade_id"] == "parent_block_xyz"
    assert message["types"]["BlockTradeOffer"] == [
        {"name": "version", "type": "shortstring"},
        {"name": "nonce", "type": "felt"},
        {"name": "expiration", "type": "felt"},
        {"name": "block_trade_id", "type": "felt"},
        {"name": "trades", "type": "merkletree", "contains": "Trade"},
    ]


def test_block_trade_offer_distinct_primary_type():
    """BlockTrade and BlockTradeOffer are cryptographically domain-separated by primaryType.
    Even with identical Trades, the typed-data messages differ — so signatures cannot be
    replayed across the two flows."""
    maker, taker = _eth_perp_orders()
    trade = Trade.fill("ETH-USD-PERP", Decimal("1500"), Decimal("0.1"), maker, taker)

    bt = BlockTrade(nonce="x", expiration=1700000000000, trades=[trade])
    offer = BlockTradeOffer(nonce="x", expiration=1700000000000, block_trade_id="P", trades=[trade])

    bt_msg = build_block_trade_message(1, bt)
    offer_msg = build_block_trade_offer_message(1, offer)

    assert bt_msg["primaryType"] != offer_msg["primaryType"]
    # The trades arrays would match if we strip primary-type-specific fields, but the
    # TYPE_HASH derived from primaryType differs, so messageHash is domain-separated.


class _FakeOrder:
    """Minimal stand-in for a server-returned BlockTradeOrder"""

    def __init__(self, account, side_value, type_value, size, price):
        self.account = account

        class _Enum:
            def __init__(self, value):
                self.value = value

        self.side = _Enum(side_value)
        self.type = _Enum(type_value)
        self.size = size
        self.price = price


class _FakeTradeDetail:
    def __init__(self, *, maker_order=None, taker_order=None, price="0", size="0", trade_constraints=None):
        self.maker_order = maker_order
        self.taker_order = taker_order
        self.price = price
        self.size = size
        self.trade_constraints = trade_constraints


class _FakeBlockResponse:
    def __init__(self, trades_dict):
        self.trades = trades_dict


def test_block_trade_from_response_fill():
    """Reconstruct a signing-shape BlockTrade from a server response containing fill trades."""
    maker_dto = _FakeOrder("0xMAKER", "SELL", "LIMIT", "0.1", "1500")
    taker_dto = _FakeOrder("0xTAKER", "BUY", "LIMIT", "0.1", "1500")
    response = _FakeBlockResponse(
        {"ETH-USD-PERP": _FakeTradeDetail(maker_order=maker_dto, taker_order=taker_dto, price="1500", size="0.1")}
    )

    bt = block_trade_from_response(response, nonce="executor_nonce", expiration=1700000000000)
    assert bt.nonce == "executor_nonce"
    assert bt.expiration == 1700000000000
    assert len(bt.trades) == 1
    trade = bt.trades[0]
    assert trade.market == "ETH-USD-PERP"
    assert trade.price == Decimal("1500")
    assert trade.size == Decimal("0.1")
    assert trade.maker_order.account == "0xMAKER"
    assert trade.maker_order.side == "SELL"
    assert trade.taker_order.account == "0xTAKER"
    assert trade.taker_order.side == "BUY"
    # Constraints zero (fill Trade)
    assert trade.min_size == Decimal(0)
    assert trade.max_size == Decimal(0)


class _FakeConstraints:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_block_trade_message_hash_pinned():
    """Pin the messageHash for a fixed BlockTrade input. Tied to the schema, encoding,
    trade sort, and domain definitions — any change to any of those flips this hash, so
    an equivalent verifier (e.g. a server) producing the same hash for the same inputs
    confirms the two implementations stay aligned."""
    from starknet_py.utils.typed_data import TypedData

    maker_address = "0x1111"
    taker_address = "0x2222"
    maker_btc = BlockTradeOrder(maker_address, "SELL", "LIMIT", Decimal("0.1"), Decimal("73000"))
    taker_btc = BlockTradeOrder(taker_address, "BUY", "LIMIT", Decimal("0.1"), Decimal("73000"))
    maker_eth = BlockTradeOrder(maker_address, "SELL", "LIMIT", Decimal("1"), Decimal("3000"))
    taker_eth = BlockTradeOrder(taker_address, "BUY", "LIMIT", Decimal("1"), Decimal("3000"))
    # Trades intentionally in non-canonical (ETH before BTC) input order — the sort happens
    # at the cryptographic boundary, so the hash is invariant to input order.
    block_trade = BlockTrade(
        nonce="1234567890",
        expiration=1700000000000,
        trades=[
            Trade.fill("ETH-USD-PERP", Decimal("3000"), Decimal("1"), maker_eth, taker_eth),
            Trade.fill("BTC-USD-PERP", Decimal("73000"), Decimal("0.1"), maker_btc, taker_btc),
        ],
    )

    typed_data = TypedData.from_dict(build_block_trade_message(1, block_trade))
    actual = f"0x{typed_data.message_hash(int(maker_address, 16)):x}"
    assert actual == "0x426f5dd572deed472db9aa9ac2469f4a456a3a72854b723065daf3ccc350812"


def test_block_trade_offer_message_hash_pinned():
    """Pin the messageHash for a fixed BlockTradeOffer input. Distinct from the BlockTrade
    hash — domain-separated by primaryType + the block_trade_id binding. Same pinning
    rationale as above."""
    from starknet_py.utils.typed_data import TypedData

    maker_address = "0x1111"
    maker_btc = BlockTradeOrder(maker_address, "SELL", "LIMIT", Decimal("0.1"), Decimal("73000"))
    maker_eth = BlockTradeOrder(maker_address, "SELL", "LIMIT", Decimal("1"), Decimal("3000"))
    # Offerer occupies maker side only; taker side is None (encoded as zero BlockTradeOrder).
    offer = BlockTradeOffer(
        nonce="offer_nonce_1",
        expiration=1700000300000,
        block_trade_id="parent_block_xyz",
        trades=[
            Trade.fill("ETH-USD-PERP", Decimal("3000"), Decimal("1"), maker_eth, None),
            Trade.fill("BTC-USD-PERP", Decimal("73000"), Decimal("0.1"), maker_btc, None),
        ],
    )

    typed_data = TypedData.from_dict(build_block_trade_offer_message(1, offer))
    actual = f"0x{typed_data.message_hash(int(maker_address, 16)):x}"
    assert actual == "0x3d43168f6def95bf9371aae3b20a2e9713e91a773b1a192f5e0729e96b7b139"


def test_block_trade_from_response_constraint_only():
    """Offer-based parent: server returns trade_constraints, no maker/taker orders."""
    constraints = _FakeConstraints(
        min_size="0.05", max_size="1.0", min_price="29000", max_price="31000", oracle_tolerance="0.02"
    )
    response = _FakeBlockResponse({"BTC-USD-PERP": _FakeTradeDetail(trade_constraints=constraints)})

    bt = block_trade_from_response(response, nonce="n", expiration=1700000000000)
    assert len(bt.trades) == 1
    trade = bt.trades[0]
    assert trade.market == "BTC-USD-PERP"
    assert trade.min_size == Decimal("0.05")
    assert trade.max_price == Decimal("31000")
    assert trade.maker_order is None
    assert trade.taker_order is None
