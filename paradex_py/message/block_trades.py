from decimal import Decimal
from typing import List, cast

from starknet_py.utils.typed_data import TypedData, TypedDataDict

from paradex_py.common.order import Order


class Trade:
    def __init__(
        self,
        price: Decimal,
        size: Decimal,
        maker_order: Order,
        taker_order: Order,
    ) -> None:
        self.price = price
        self.size = size
        self.maker_order = maker_order
        self.taker_order = taker_order

    def chain_price(self) -> str:
        return str(int(self.price.scaleb(8)))

    def chain_size(self) -> str:
        return str(int(self.size.scaleb(8)))


class BlockTrade:
    def __init__(
        self,
        version: str,
        trades: List[Trade],
    ) -> None:
        self.version = version
        self.trades = trades


def build_block_trade_message(chain_id: int, block_trade: BlockTrade) -> TypedData:
    # Build trades array for the message
    trades_message = []
    for trade in block_trade.trades:
        trade_data = {
            "price": trade.chain_price(),
            "size": trade.chain_size(),
            "maker_order": {
                "timestamp": str(trade.maker_order.signature_timestamp),
                "market": trade.maker_order.market,
                "side": trade.maker_order.order_side.chain_side(),
                "orderType": trade.maker_order.order_type.value,
                "size": trade.maker_order.chain_size(),
                "price": trade.maker_order.chain_price(),
            },
            "taker_order": {
                "timestamp": str(trade.taker_order.signature_timestamp),
                "market": trade.taker_order.market,
                "side": trade.taker_order.order_side.chain_side(),
                "orderType": trade.taker_order.order_type.value,
                "size": trade.taker_order.chain_size(),
                "price": trade.taker_order.chain_price(),
            },
        }
        trades_message.append(trade_data)

    message = {
        "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},
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
            "version": block_trade.version,
            "trades": trades_message,
        },
    }
    return TypedData.from_dict(cast(TypedDataDict, message))
