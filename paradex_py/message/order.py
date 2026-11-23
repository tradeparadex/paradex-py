from typing import cast

from starknet_py.net.models.typed_data import TypedDataDict

from paradex_py.common.order import Order


def build_order_message(chain_id: int, o: Order) -> TypedDataDict:
    """The SNIP-12 rev0 typed data an order is signed under.

    An order naming a builder signs as ``BuilderOrder``: the ``Order`` fields, in order, then
    ``builder`` (a felt) and ``builderFeeRate`` (the rate at 8 decimals). Its distinct type hash
    keeps either signature from being replayed as the other. Without a builder an order keeps
    the ``Order`` hash.
    """
    if o.builder:
        return _build_builder_order_message(chain_id, o)
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


_BUILDER_ORDER_TYPE = [
    {"name": "timestamp", "type": "felt"},
    {"name": "market", "type": "felt"},
    {"name": "side", "type": "felt"},
    {"name": "orderType", "type": "felt"},
    {"name": "size", "type": "felt"},
    {"name": "price", "type": "felt"},
    {"name": "builder", "type": "felt"},  # The builder's account address
    {"name": "builderFeeRate", "type": "felt"},  # Fraction of notional with 8 decimals; "0.0005" -> 50000
]


def _build_builder_order_message(chain_id: int, o: Order) -> TypedDataDict:
    """The ``BuilderOrder`` typed data for an order naming a builder (see :func:`build_order_message`)."""
    message = {
        "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},
        "primaryType": "BuilderOrder",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
            "BuilderOrder": _BUILDER_ORDER_TYPE,
        },
        "message": {
            "timestamp": str(o.signature_timestamp),
            "market": o.market,
            "side": o.order_side.chain_side(),
            "orderType": o.order_type.value,
            "size": o.chain_size(),
            "price": o.chain_price(),
            "builder": o.builder,
            "builderFeeRate": o.chain_builder_fee_rate(),
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
