from decimal import Decimal

from paradex_py.common.order import MmpCancelReason, Order, OrderFlag, OrderSide, OrderType


def _order(**kwargs) -> Order:
    return Order(
        market="BTC-USD-26DEC26-105000-C",
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal(1000),
        **kwargs,
    )


def test_order_flag_values():
    """Flag values are the strings the API expects in the flags array."""
    assert OrderFlag.ReduceOnly.value == "REDUCE_ONLY"
    assert OrderFlag.Mmp.value == "MMP"


def test_mmp_cancel_reason_values():
    """Cancel reasons match the ones the API sets on a cancelled MMP order."""
    assert MmpCancelReason.Triggered.value == "MMP_TRIGGERED"
    assert MmpCancelReason.Frozen.value == "MMP_FROZEN"
    assert MmpCancelReason.Disabled.value == "MMP_DISABLED"
    assert MmpCancelReason.GreeksUnavailable.value == "MMP_GREEKS_UNAVAILABLE"
    assert MmpCancelReason.NotConfigured.value == "MMP_NOT_CONFIGURED"


def test_order_without_flags_omits_flags():
    """An order with neither flag sends no flags key, as before MMP existed."""
    assert "flags" not in _order().dump_to_dict()


def test_order_with_mmp_flag():
    assert _order(mmp=True).dump_to_dict()["flags"] == ["MMP"]


def test_order_with_reduce_only_flag():
    assert _order(reduce_only=True).dump_to_dict()["flags"] == ["REDUCE_ONLY"]


def test_order_with_both_flags():
    """MMP combines with REDUCE_ONLY; the API accepts at most these two."""
    assert _order(reduce_only=True, mmp=True).dump_to_dict()["flags"] == ["REDUCE_ONLY", "MMP"]


def test_mmp_defaults_to_false():
    assert _order().mmp is False
