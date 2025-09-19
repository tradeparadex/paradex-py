from typing import cast

from starknet_py.utils.typed_data import TypedDataDict

from paradex_py.common.order import Order


def build_order_message(chain_id: int, o: Order) -> TypedDataDict:
    message = {
        "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},
        "primaryType": "Order",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
            "Order": [
                {
                    "name": "timestamp",
                    "type": "felt",
                },  # Time of signature request in ms since epoch; Acts as a nonce;
                {"name": "market", "type": "felt"},  # E.g.: "ETH-USD-PERP"
                {"name": "side", "type": "felt"},  # Buy or Sell
                {"name": "orderType", "type": "felt"},  # Limit or Market
                {"name": "size", "type": "felt"},  # Quantum value with 8 decimals;
                {
                    "name": "price",
                    "type": "felt",
                },  # Quantum value with 8 decimals; Limit price or 0 at the moment of signature
            ],
        },
        "message": {
            "timestamp": str(o.signature_timestamp),
            "market": o.market,  # As encoded short string
            "side": o.order_side.chain_side(),  # 1: BUY, 2: SELL
            "orderType": o.order_type.value,  # As encoded short string
            "size": o.chain_size(),
            "price": o.chain_price(),
        },
    }
    return cast(TypedDataDict, message)


def build_modify_order_message(chain_id: int, o: Order) -> TypedDataDict:
    message = {
        "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},
        "primaryType": "ModifyOrder",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
            "ModifyOrder": [
                {
                    "name": "timestamp",
                    "type": "felt",
                },  # Time of signature request in ms since epoch; Acts as a nonce;
                {"name": "market", "type": "felt"},  # E.g.: "ETH-USD-PERP"
                {"name": "side", "type": "felt"},  # Buy or Sell
                {"name": "orderType", "type": "felt"},  # Limit
                {"name": "size", "type": "felt"},  # Quantum value with 8 decimals;
                {
                    "name": "price",
                    "type": "felt",
                },  # Quantum value with 8 decimals; Limit price or 0 at the moment of signature
                {
                    "name": "id",
                    "type": "felt",
                },
            ],
        },
        "message": {
            "timestamp": str(o.signature_timestamp),
            "market": o.market,  # As encoded short string
            "side": o.order_side.chain_side(),  # 1: BUY, 2: SELL
            "orderType": o.order_type.value,  # As encoded short string
            "size": o.chain_size(),
            "price": o.chain_price(),
            "id": o.id,
        },
    }
    return cast(TypedDataDict, message)
