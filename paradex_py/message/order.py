from starknet_py.net.models.typed_data import TypedData

from paradex_py.common.order import Order


def build_order_message(chain_id: int, o: Order) -> TypedData:
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
    return message
