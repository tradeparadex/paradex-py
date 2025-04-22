from decimal import Decimal

from paradex_py.common.order import Order, OrderSide, OrderType


def test_order_type_values():
    """Test that all order types have correct string values."""
    assert OrderType.Market.value == "MARKET"
    assert OrderType.Limit.value == "LIMIT"
    assert OrderType.StopLimit.value == "STOP_LIMIT"
    assert OrderType.StopMarket.value == "STOP_MARKET"
    assert OrderType.TakeProfitLimit.value == "TAKE_PROFIT_LIMIT"
    assert OrderType.TakeProfitMarket.value == "TAKE_PROFIT_MARKET"
    assert OrderType.StopLossMarket.value == "STOP_LOSS_MARKET"
    assert OrderType.StopLossLimit.value == "STOP_LOSS_LIMIT"


def test_is_limit_type():
    """Test that is_limit_type correctly identifies limit-based order types."""
    # Test limit-based order types
    limit_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal(1000),
    )
    assert limit_order.is_limit_type()

    stop_limit_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.StopLimit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal(1000),
    )
    assert stop_limit_order.is_limit_type()

    take_profit_limit_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.TakeProfitLimit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal(1000),
    )
    assert take_profit_limit_order.is_limit_type()

    stop_loss_limit_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.StopLossLimit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal(1000),
    )
    assert stop_loss_limit_order.is_limit_type()

    # Test market-based order types
    market_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.Market,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
    )
    assert not market_order.is_limit_type()

    stop_market_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.StopMarket,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
    )
    assert not stop_market_order.is_limit_type()

    take_profit_market_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.TakeProfitMarket,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
    )
    assert not take_profit_market_order.is_limit_type()

    stop_loss_market_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.StopLossMarket,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
    )
    assert not stop_loss_market_order.is_limit_type()


def test_order_creation_with_trigger_price():
    """Test that orders with trigger prices are created correctly."""
    trigger_price = Decimal(1000)

    stop_limit_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.StopLimit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal(1000),
        trigger_price=trigger_price,
    )
    assert stop_limit_order.trigger_price == trigger_price

    stop_market_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.StopMarket,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        trigger_price=trigger_price,
    )
    assert stop_market_order.trigger_price == trigger_price

    take_profit_limit_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.TakeProfitLimit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal(1000),
        trigger_price=trigger_price,
    )
    assert take_profit_limit_order.trigger_price == trigger_price

    take_profit_market_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.TakeProfitMarket,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        trigger_price=trigger_price,
    )
    assert take_profit_market_order.trigger_price == trigger_price

    stop_loss_limit_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.StopLossLimit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal(1000),
        trigger_price=trigger_price,
    )
    assert stop_loss_limit_order.trigger_price == trigger_price

    stop_loss_market_order = Order(
        market="BTC-USD-PERP",
        order_type=OrderType.StopLossMarket,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        trigger_price=trigger_price,
    )
    assert stop_loss_market_order.trigger_price == trigger_price


def test_order_side_opposite():
    """Test that order side opposite works correctly."""
    assert OrderSide.Buy.opposite_side() == OrderSide.Sell
    assert OrderSide.Sell.opposite_side() == OrderSide.Buy


def test_order_side_sign():
    """Test that order side sign works correctly."""
    assert OrderSide.Buy.sign() == 1
    assert OrderSide.Sell.sign() == -1


def test_order_side_chain_side():
    """Test that order side chain side works correctly."""
    assert OrderSide.Buy.chain_side() == "1"
    assert OrderSide.Sell.chain_side() == "2"
