from decimal import Decimal

from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.message.block_trades import BlockTrade, Trade, build_block_trade_message


def test_trade_class():
    # Create test orders
    maker_order = Order(
        market="ETH-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal("1500"),
        signature_timestamp=1634736000000,
    )

    taker_order = Order(
        market="ETH-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Sell,
        size=Decimal("0.1"),
        limit_price=Decimal("1500"),
        signature_timestamp=1634736000001,
    )

    # Create trade
    trade = Trade(
        price=Decimal("1500.50"),
        size=Decimal("0.1"),
        maker_order=maker_order,
        taker_order=taker_order,
    )

    # Test properties
    assert trade.price == Decimal("1500.50")
    assert trade.size == Decimal("0.1")
    assert trade.maker_order == maker_order
    assert trade.taker_order == taker_order

    # Test chain formatting
    assert trade.chain_price() == "150050000000"  # 1500.50 * 10^8
    assert trade.chain_size() == "10000000"  # 0.1 * 10^8


def test_block_trade_class():
    # Create test orders
    maker_order = Order(
        market="ETH-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal("1500"),
        signature_timestamp=1634736000000,
    )

    taker_order = Order(
        market="ETH-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Sell,
        size=Decimal("0.1"),
        limit_price=Decimal("1500"),
        signature_timestamp=1634736000001,
    )

    # Create trades
    trades = [
        Trade(
            price=Decimal("1500.50"),
            size=Decimal("0.1"),
            maker_order=maker_order,
            taker_order=taker_order,
        ),
        Trade(
            price=Decimal("1501.00"),
            size=Decimal("0.05"),
            maker_order=maker_order,
            taker_order=taker_order,
        ),
    ]

    # Create block trade
    block_trade = BlockTrade(version="1.0", trades=trades)

    # Test properties
    assert block_trade.version == "1.0"
    assert len(block_trade.trades) == 2
    assert block_trade.trades[0].price == Decimal("1500.50")
    assert block_trade.trades[1].price == Decimal("1501.00")


def test_build_block_trade_message():
    # Create test orders
    maker_order = Order(
        market="ETH-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal("1500"),
        signature_timestamp=1634736000000,
    )

    taker_order = Order(
        market="ETH-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Sell,
        size=Decimal("0.1"),
        limit_price=Decimal("1500"),
        signature_timestamp=1634736000001,
    )

    # Create trade
    trade = Trade(
        price=Decimal("1500.50"),
        size=Decimal("0.1"),
        maker_order=maker_order,
        taker_order=taker_order,
    )

    # Create block trade
    block_trade = BlockTrade(version="1.0", trades=[trade])

    # Test message building
    message = build_block_trade_message(1, block_trade)

    expected = {
        "domain": {"name": "Paradex", "chainId": "0x1", "version": "1"},
        "primaryType": "BlockTrade",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
            "BlockTrade": [
                {"name": "version", "type": "shortstring"},
                {"name": "trades", "type": "Trade*"},
            ],
            "Trade": [
                {"name": "price", "type": "felt"},
                {"name": "size", "type": "felt"},
                {"name": "maker_order", "type": "Order"},
                {"name": "taker_order", "type": "Order"},
            ],
            "Order": [
                {"name": "timestamp", "type": "felt"},
                {"name": "market", "type": "felt"},
                {"name": "side", "type": "felt"},
                {"name": "orderType", "type": "felt"},
                {"name": "size", "type": "felt"},
                {"name": "price", "type": "felt"},
            ],
        },
        "message": {
            "version": "1.0",
            "trades": [
                {
                    "price": "150050000000",  # 1500.50 * 10^8
                    "size": "10000000",  # 0.1 * 10^8
                    "maker_order": {
                        "timestamp": "1634736000000",
                        "market": "ETH-USD-PERP",
                        "side": "1",  # Buy
                        "orderType": "LIMIT",
                        "size": "10000000",  # 0.1 * 10^8
                        "price": "150000000000",  # 1500 * 10^8
                    },
                    "taker_order": {
                        "timestamp": "1634736000001",
                        "market": "ETH-USD-PERP",
                        "side": "2",  # Sell
                        "orderType": "LIMIT",
                        "size": "10000000",  # 0.1 * 10^8
                        "price": "150000000000",  # 1500 * 10^8
                    },
                }
            ],
        },
    }

    assert message == expected


def test_build_block_trade_message_multiple_trades():
    # Create test orders
    maker_order1 = Order(
        market="ETH-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal("1500"),
        signature_timestamp=1634736000000,
    )

    taker_order1 = Order(
        market="ETH-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Sell,
        size=Decimal("0.1"),
        limit_price=Decimal("1500"),
        signature_timestamp=1634736000001,
    )

    maker_order2 = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.Market,
        order_side=OrderSide.Sell,
        size=Decimal("0.01"),
        limit_price=Decimal("0"),  # Market order
        signature_timestamp=1634736000002,
    )

    taker_order2 = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.Market,
        order_side=OrderSide.Buy,
        size=Decimal("0.01"),
        limit_price=Decimal("0"),  # Market order
        signature_timestamp=1634736000003,
    )

    # Create trades
    trades = [
        Trade(
            price=Decimal("1500.50"),
            size=Decimal("0.1"),
            maker_order=maker_order1,
            taker_order=taker_order1,
        ),
        Trade(
            price=Decimal("45000.75"),
            size=Decimal("0.01"),
            maker_order=maker_order2,
            taker_order=taker_order2,
        ),
    ]

    # Create block trade
    block_trade = BlockTrade(version="2.0", trades=trades)

    # Test message building
    message = build_block_trade_message(5, block_trade)

    # Verify structure
    assert message["domain"]["chainId"] == "0x5"
    assert message["primaryType"] == "BlockTrade"
    assert message["message"]["version"] == "2.0"
    assert len(message["message"]["trades"]) == 2

    # Verify first trade
    trade1 = message["message"]["trades"][0]
    assert trade1["price"] == "150050000000"  # 1500.50 * 10^8
    assert trade1["size"] == "10000000"  # 0.1 * 10^8
    assert trade1["maker_order"]["market"] == "ETH-USD-PERP"
    assert trade1["maker_order"]["side"] == "1"  # Buy
    assert trade1["taker_order"]["side"] == "2"  # Sell

    # Verify second trade
    trade2 = message["message"]["trades"][1]
    assert trade2["price"] == "4500075000000"  # 45000.75 * 10^8
    assert trade2["size"] == "1000000"  # 0.01 * 10^8
    assert trade2["maker_order"]["market"] == "BTC-USD-PERP"
    assert trade2["maker_order"]["side"] == "2"  # Sell
    assert trade2["maker_order"]["orderType"] == "MARKET"
    assert trade2["maker_order"]["price"] == "0"  # Market order
    assert trade2["taker_order"]["side"] == "1"  # Buy
