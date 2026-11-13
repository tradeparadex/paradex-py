"""BuilderOrder signing: an order naming a builder signs the Order fields plus the builder and
its fee rate, under its own type. The pinned hash is the server's reference vector."""

from decimal import Decimal

import pytest
from starknet_py.cairo.felt import encode_shortstring
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.hash.utils import compute_hash_on_elements
from starknet_py.utils.typed_data import TypedData

from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.message.order import build_order_message

ACCOUNT = 0x4A09444A934577EBF338AA6473C7B0DF084158ED03408C07057CC2ECBBB5938
CHAIN_ID = encode_shortstring("PRIVATE_SN_POTC_GOERLI")
REFERENCE_HASH = "0x4c5d000ffcedffd12468ad34f2c296e4daf028db5c4c7001ab93ee392664807"


def _order(**overrides) -> Order:
    fields = {
        "market": "BTC-USD-PERP",
        "order_type": OrderType.Limit,
        "order_side": OrderSide.Sell,
        "size": Decimal("0.4543"),
        "limit_price": Decimal("28981"),
        "signature_timestamp": 1684815490129,
        "builder": "0x5b0b",
        "builder_fee_rate": Decimal("0.0005"),
    }
    fields.update(overrides)
    return Order(**fields)


def _hash(order: Order) -> int:
    return TypedData.from_dict(build_order_message(CHAIN_ID, order)).message_hash(ACCOUNT)


def test_builder_order_hash_pinned():
    assert hex(_hash(_order())) == REFERENCE_HASH


def test_builder_order_hash_field_by_field():
    """Recompute the SNIP-12 rev0 hash by hand, so the layout is checked independently of the lib."""
    type_hash = get_selector_from_name(
        "BuilderOrder(timestamp:felt,market:felt,side:felt,orderType:felt,size:felt,price:felt,"
        "builder:felt,builderFeeRate:felt)"
    )
    struct_hash = compute_hash_on_elements(
        [
            type_hash,
            1684815490129,
            encode_shortstring("BTC-USD-PERP"),
            2,  # SELL
            encode_shortstring("LIMIT"),
            45430000,  # 0.4543 at 8 decimals
            2898100000000,  # 28981 at 8 decimals
            0x5B0B,
            50000,  # 0.0005 at 8 decimals
        ]
    )
    domain_hash = compute_hash_on_elements(
        [
            get_selector_from_name("StarkNetDomain(name:felt,chainId:felt,version:felt)"),
            encode_shortstring("Paradex"),
            CHAIN_ID,
            1,
        ]
    )
    expected = compute_hash_on_elements([encode_shortstring("StarkNet Message"), domain_hash, ACCOUNT, struct_hash])
    assert _hash(_order()) == expected


def test_builder_order_signs_what_matters():
    base = _hash(_order())
    # The builder is a felt and the rate a number: spelling changes nothing.
    assert _hash(_order(builder="0x0000005B0B", builder_fee_rate=Decimal("0.00050"))) == base
    assert _hash(_order(builder="0x5b0c")) != base
    assert _hash(_order(builder_fee_rate=Decimal("0.0006"))) != base


def test_order_without_builder_keeps_order_hash():
    plain = _order(builder=None, builder_fee_rate=None)
    message = build_order_message(CHAIN_ID, plain)
    assert message["primaryType"] == "Order"
    assert "builder" not in message["message"]
    assert _hash(plain) != _hash(_order())


def test_builder_order_message_shape():
    message = build_order_message(1, _order())
    assert message["primaryType"] == "BuilderOrder"
    assert [f["name"] for f in message["types"]["BuilderOrder"]] == [
        "timestamp",
        "market",
        "side",
        "orderType",
        "size",
        "price",
        "builder",
        "builderFeeRate",
    ]
    assert message["message"]["builder"] == "0x5b0b"
    assert message["message"]["builderFeeRate"] == "50000"


def test_builder_fields_in_request_body():
    body = _order(builder_fee_rate=Decimal("0.00050")).dump_to_dict()
    assert body["builder"] == "0x5b0b"
    assert body["builder_fee_rate"] == "0.0005"
    plain = _order(builder=None, builder_fee_rate=None).dump_to_dict()
    assert "builder" not in plain
    assert "builder_fee_rate" not in plain


@pytest.mark.parametrize(
    ("builder", "rate", "match"),
    [
        ("0x5b0b", None, "together"),
        (None, Decimal("0.0005"), "together"),
        ("0x5b0b", Decimal(0), "above 0"),
        ("0x5b0b", Decimal("-0.0001"), "above 0"),
        ("0x5b0b", Decimal("0.000000001"), "8 decimal places"),
        ("0x5b0b", 0.0005, "Decimal"),
        ("0x0", Decimal("0.0005"), "non-zero 0x hex"),
        ("BUILDER", Decimal("0.0005"), "non-zero 0x hex"),
        # Spellings the server refuses, or that would sign a different felt.
        ("171", Decimal("0.0005"), "non-zero 0x hex"),
        ("ab", Decimal("0.0005"), "non-zero 0x hex"),
        ("0XAB", Decimal("0.0005"), "non-zero 0x hex"),
        (" 0xab", Decimal("0.0005"), "non-zero 0x hex"),
        ("-0xab", Decimal("0.0005"), "non-zero 0x hex"),
        ("0x_ab", Decimal("0.0005"), "non-zero 0x hex"),
        ("0x" + "f" * 64, Decimal("0.0005"), "non-zero 0x hex"),
        ("0x" + "1" * 65, Decimal("0.0005"), "non-zero 0x hex"),
    ],
)
def test_builder_validation(builder, rate, match):
    with pytest.raises(ValueError, match=match):
        _order(builder=builder, builder_fee_rate=rate)


def test_builder_is_stored_canonical():
    order = _order(builder="0x0000005B0B")
    assert order.builder == "0x5b0b"
    assert order.dump_to_dict()["builder"] == "0x5b0b"


def test_modify_order_takes_no_builder():
    with pytest.raises(ValueError, match="modify"):
        _order(order_id="123")


def test_builder_in_repr():
    assert "builder=0x5b0b@0.0005" in repr(_order())
