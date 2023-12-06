from decimal import Decimal

from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.message.order import build_order_message


def test_build_onboarding_message():
    order = Order(
        market="ETH-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal(1500),
        client_id="",
        signature_timestamp=1634736000000,
    )
    assert build_order_message(1, order) == {
        "domain": {"name": "Paradex", "chainId": "0x1", "version": "1"},
        "primaryType": "Order",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"},
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
            "timestamp": "1634736000000",
            "market": "ETH-USD-PERP",
            "side": "1",
            "orderType": "LIMIT",
            "size": "10000000",
            "price": "150000000000",
        },
    }
