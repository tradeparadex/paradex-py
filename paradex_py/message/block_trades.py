import re
from decimal import Decimal
from typing import cast

from starknet_py.net.models.typed_data import TypedDataDict

from paradex_py.api.generated.requests import BlockOfferRequest, BlockTradeRequest
from paradex_py.api.generated.responses import (
    BlockTradeDetailFullResponse,
)
from paradex_py.api.generated.responses import BlockTradeOrder as BlockTradeOrderResponse
from paradex_py.common.order import OrderSide, chain_builder_fee_rate, decimal_zero, validate_builder
from paradex_py.utils import raise_value_error

# BLOCK_TRADE_PAYLOAD_VERSION is the SNIP-12 BlockTrade schema version included in the
# signed payload. Bump when the schema changes; client and server must agree.
BLOCK_TRADE_PAYLOAD_VERSION = "2"
# A payload in which any order names a builder is version 3: its BlockTradeOrder appends
# builder and builder_fee_rate, so every signer commits to each order's builder fee.
BLOCK_TRADE_BUILDER_PAYLOAD_VERSION = "3"
# A builder fee rate spelled as the server accepts it: a plain ASCII decimal below 1000 with at most
# 8 decimal places. Trailing zeros are fine; they scale to the same signed integer.
_FEE_RATE_SPELLING = re.compile(r"(0|[1-9][0-9]{0,2})(\.[0-9]{1,8})?")


class BlockTradeOrder:
    """Order-side component of a Trade. Distinct from the rev0 Order used for standalone
    order signing: drops timestamp (replay protection lives at block level) and market
    (lives at Trade level), but includes account explicitly since a Trade may carry orders
    from different participants.
    """

    def __init__(
        self,
        account: str = "",
        side: str = "",
        order_type: str = "",
        size: Decimal = decimal_zero,
        price: Decimal = decimal_zero,
        builder: str = "",
        builder_fee_rate: Decimal | None = None,
    ) -> None:
        """``builder`` and ``builder_fee_rate`` (a fraction of the leg's notional,
        ``Decimal("0.0005")`` = 5 bps) name a builder this order pays, debited from ``account``.
        Set both or neither; any order naming one makes the payload version 3."""
        builder = validate_builder(builder or None, builder_fee_rate) or ""
        self.account = account
        self.side = side
        self.order_type = order_type
        self.size = size
        self.price = price
        self.builder = builder
        self.builder_fee_rate = builder_fee_rate


class Trade:
    """One trade in a block — becomes a single leaf of the merkle tree at signing time.

    A Trade carries either fill data (for direct/offer trades) or constraint data (for
    offer-based parent blocks where only bounds are agreed at create time). Both variants
    share the same schema: unused fields default to zero so the merkle root commits to
    the absence of the other variant.
    """

    def __init__(
        self,
        market: str = "",
        price: Decimal = decimal_zero,
        size: Decimal = decimal_zero,
        maker_order: BlockTradeOrder | None = None,
        taker_order: BlockTradeOrder | None = None,
        min_size: Decimal = decimal_zero,
        max_size: Decimal = decimal_zero,
        min_price: Decimal = decimal_zero,
        max_price: Decimal = decimal_zero,
        oracle_tolerance: Decimal = decimal_zero,
    ) -> None:
        self.market = market
        self.price = price
        self.size = size
        self.maker_order = maker_order
        self.taker_order = taker_order
        self.min_size = min_size
        self.max_size = max_size
        self.min_price = min_price
        self.max_price = max_price
        self.oracle_tolerance = oracle_tolerance

    @classmethod
    def fill(
        cls,
        market: str,
        price: Decimal,
        size: Decimal,
        maker_order: BlockTradeOrder,
        taker_order: BlockTradeOrder,
    ) -> "Trade":
        """Build a Trade for a direct or offer (filled) trade. Constraints are zero."""
        return cls(
            market=market,
            price=price,
            size=size,
            maker_order=maker_order,
            taker_order=taker_order,
        )

    @classmethod
    def constraint(
        cls,
        market: str,
        min_size: Decimal = decimal_zero,
        max_size: Decimal = decimal_zero,
        min_price: Decimal = decimal_zero,
        max_price: Decimal = decimal_zero,
        oracle_tolerance: Decimal = decimal_zero,
    ) -> "Trade":
        """Build a Trade for an offer-based parent block (constraints only, no fill)."""
        return cls(
            market=market,
            min_size=min_size,
            max_size=max_size,
            min_price=min_price,
            max_price=max_price,
            oracle_tolerance=oracle_tolerance,
        )


class BlockTrade:
    """Domain model for a block trade payload to be signed.

    nonce and expiration are block-level fields included in the signed merkle struct hash;
    every required signer of the same block produces a signature over the same messageHash.
    """

    def __init__(
        self,
        nonce: str,
        expiration: int,
        trades: list[Trade],
        version: str | None = None,
    ) -> None:
        """``version`` is optional: when set, signing refuses trades that call for another one."""
        self.expected_version = version
        self.nonce = nonce
        self.expiration = expiration
        self.trades = trades

    @property
    def version(self) -> str:
        """The payload version the trades sign under, derived from them (:func:`block_trade_version`)."""
        return block_trade_version(self.trades)


class BlockTradeOffer:
    """Domain model for a block trade offer payload to be signed by an offerer.

    Distinct from BlockTrade: the offerer commits only to their own fills + the parent
    block reference, NOT to the parent's constraints or expiration. The block_trade_id
    field binds the offer cryptographically to a specific parent — an offer signed for
    parent A cannot be replayed against parent B.

    Each Trade should be built with the offerer's data on one side (maker by convention,
    matching the server's merge logic) and the other side empty/zero. Constraints are
    zero — the offerer doesn't sign parent constraints.
    """

    def __init__(
        self,
        nonce: str,
        expiration: int,
        block_trade_id: str,
        trades: list[Trade],
        version: str | None = None,
    ) -> None:
        """``version`` is optional: when set, signing refuses trades that call for another one."""
        self.expected_version = version
        self.nonce = nonce
        self.expiration = expiration
        self.block_trade_id = block_trade_id
        self.trades = trades

    @property
    def version(self) -> str:
        """The payload version the trades sign under, derived from them (:func:`block_trade_version`)."""
        return block_trade_version(self.trades)


def block_trade_version(trades: list[Trade]) -> str:
    """The payload version trades are signed under: 3 when any order names a builder, else 2.

    The server derives the version from the orders it verifies, so a signer must too.
    """
    for trade in trades:
        for order in (trade.maker_order, trade.taker_order):
            if order is not None and order.builder:
                return BLOCK_TRADE_BUILDER_PAYLOAD_VERSION
    return BLOCK_TRADE_PAYLOAD_VERSION


def _chain_decimal(d: Decimal) -> str:
    """Scale a decimal to its on-chain integer representation (ParaclearDecimals = 8)."""
    return str(int(Decimal(d).scaleb(8)))


def _empty_block_trade_order_message(with_builder: bool) -> dict:
    """Zero-valued BlockTradeOrder used when one side of a Trade is empty (e.g. an offer
    where the offerer occupies maker side and taker side is empty until merge). All fields
    encoded as "0" so starknet-py can parse as felts."""
    message = {
        "account": "0",
        "side": "0",
        "type": "0",
        "size": "0",
        "price": "0",
    }
    if with_builder:
        message["builder"] = "0"
        message["builder_fee_rate"] = "0"
    return message


def _felt_or_zero(s: str) -> str:
    """Encode an empty string as "0" (felt zero) for starknet-py compatibility.
    Empty strings fail felt parsing in the lib."""
    return s if s else "0"


def _block_trade_order_message(order: BlockTradeOrder | None, with_builder: bool) -> dict:
    """The BlockTradeOrder leaf; version 3 (``with_builder``) appends builder (a felt) and
    builder_fee_rate (at 8 decimals), both "0" for an order naming none."""
    if order is None:
        return _empty_block_trade_order_message(with_builder)
    message = {
        "account": _felt_or_zero(order.account),
        "side": OrderSide(order.side).chain_side() if order.side else "0",
        "type": _felt_or_zero(order.order_type),
        "size": _chain_decimal(order.size),
        "price": _chain_decimal(order.price),
    }
    if with_builder:
        message["builder"] = _felt_or_zero(order.builder)
        message["builder_fee_rate"] = (
            chain_builder_fee_rate(order.builder_fee_rate) if order.builder_fee_rate is not None else "0"
        )
    return message


def _trade_message(trade: Trade, with_builder: bool) -> dict:
    return {
        "market": _felt_or_zero(trade.market),
        "price": _chain_decimal(trade.price),
        "size": _chain_decimal(trade.size),
        "maker_order": _block_trade_order_message(trade.maker_order, with_builder),
        "taker_order": _block_trade_order_message(trade.taker_order, with_builder),
        "min_size": _chain_decimal(trade.min_size),
        "max_size": _chain_decimal(trade.max_size),
        "min_price": _chain_decimal(trade.min_price),
        "max_price": _chain_decimal(trade.max_price),
        "oracle_tolerance": _chain_decimal(trade.oracle_tolerance),
    }


def block_trade_from_response(response: BlockTradeDetailFullResponse, nonce: str, expiration: int) -> BlockTrade:
    """Reconstruct the signing BlockTrade from a `BlockTradeDetailFullResponse`.

    The reconstruction must produce the exact same trade leaves the server will recompute
    when verifying — order, fill/constraint variant, and field values must all match.
    The trades dict iteration order in the response is the canonical signing order
    (the API serializes proto `repeated Trade` in insertion order, which Python dicts
    preserve since 3.7).

    Used by executors at execute time to sign the merkle root of an offer or direct
    block they're accepting. The supplied `nonce` and `expiration` are the executor's
    own — they do not have to match the create-time block-level nonce.
    """
    trades: list[Trade] = []
    for market, detail in (response.trades or {}).items():
        if detail.maker_order is not None and detail.taker_order is not None:
            trades.append(
                Trade.fill(
                    market=market,
                    price=Decimal(detail.price or "0"),
                    size=Decimal(detail.size or "0"),
                    maker_order=_block_trade_order_from_response(detail.maker_order),
                    taker_order=_block_trade_order_from_response(detail.taker_order),
                )
            )
            continue

        constraints = detail.trade_constraints
        if constraints is not None:
            trades.append(
                Trade.constraint(
                    market=market,
                    min_size=Decimal(constraints.min_size or "0"),
                    max_size=Decimal(constraints.max_size or "0"),
                    min_price=Decimal(constraints.min_price or "0"),
                    max_price=Decimal(constraints.max_price or "0"),
                    # oracle_tolerance is in the proto Trade but not yet exposed on
                    # BlockTradeConstraints; default to 0 until the DTO adds it.
                    oracle_tolerance=Decimal(0),
                )
            )

    return BlockTrade(nonce=nonce, expiration=expiration, trades=trades)


def _block_trade_order_from_response(response_order: BlockTradeOrderResponse) -> BlockTradeOrder:
    """Convert a response-side BlockTradeOrder DTO into the signing-side BlockTradeOrder."""
    # The builder fields are not in the published API models yet; they arrive as extra
    # fields, which the generated models keep.
    builder = getattr(response_order, "builder", None) or ""
    builder_fee_rate = getattr(response_order, "builder_fee_rate", None)
    rate: Decimal | None = None
    if builder:
        # The request sends this extra as written, so only the spelling the server accepts
        # may be signed: anything else would sign one value and send another.
        if not isinstance(builder_fee_rate, str) or not _FEE_RATE_SPELLING.fullmatch(builder_fee_rate):
            raise_value_error(
                f'builder_fee_rate must be a plain decimal string such as "0.0005", got {builder_fee_rate!r}'
            )
        rate = Decimal(builder_fee_rate)
    return BlockTradeOrder(
        account=response_order.account or "",
        side=response_order.side.value,
        order_type=response_order.type.value,
        size=Decimal(response_order.size or "0"),
        price=Decimal(response_order.price or "0"),
        builder=builder,
        builder_fee_rate=rate,
    )


def block_trade_from_request(request: BlockTradeRequest) -> BlockTrade:
    """Reconstruct the signing BlockTrade from a `BlockTradeRequest`.

    Used by required signers at create time: build the request (with
    `maker_order` per market), then derive the signing payload here. The
    block-level nonce/expiration come from the request itself — every required
    signer of the same block produces a signature over the same merkle root.

    Missing maker/taker sides become empty (zero-valued) `BlockTradeOrder`
    leaves, so the merkle commits to their absence.
    """
    trades: list[Trade] = []
    for market, info in (request.trades or {}).items():
        maker_order = _block_trade_order_from_response(info.maker_order) if info.maker_order else BlockTradeOrder()
        taker_order = _block_trade_order_from_response(info.taker_order) if info.taker_order else BlockTradeOrder()
        trades.append(
            Trade.fill(
                market=market,
                price=Decimal(info.price or "0"),
                size=Decimal(info.size or "0"),
                maker_order=maker_order,
                taker_order=taker_order,
            )
        )
    return BlockTrade(nonce=request.nonce, expiration=request.block_expiration, trades=trades)


def block_trade_offer_from_request(request: BlockOfferRequest, block_trade_id: str, expiration: int) -> BlockTradeOffer:
    """Reconstruct the signing BlockTradeOffer from a `BlockOfferRequest`.

    `block_trade_id` binds the offer signature to its parent (path parameter
    of the API call, not present on the request body). The offerer signs only
    their own fills — the counter-side stays empty in every leaf.
    """
    trades: list[Trade] = []
    for market, info in (request.trades or {}).items():
        offerer_order = _block_trade_order_from_response(info.offerer_order)
        trades.append(
            Trade.fill(
                market=market,
                price=Decimal(info.price),
                size=Decimal(info.size),
                maker_order=offerer_order,
                taker_order=BlockTradeOrder(),
            )
        )
    return BlockTradeOffer(
        nonce=request.nonce,
        expiration=expiration,
        block_trade_id=block_trade_id,
        trades=trades,
    )


_STARKNET_DOMAIN_TYPE = [
    {"name": "name", "type": "shortstring"},
    {"name": "version", "type": "shortstring"},
    {"name": "chainId", "type": "shortstring"},
    {"name": "revision", "type": "shortstring"},
]

_TRADE_TYPE = [
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
]

_BLOCK_TRADE_ORDER_TYPE = [
    {"name": "account", "type": "felt"},
    {"name": "side", "type": "shortstring"},
    {"name": "type", "type": "shortstring"},
    {"name": "size", "type": "felt"},
    {"name": "price", "type": "felt"},
]

# Version 3 BlockTradeOrder: version 2's fields, then the builder this order pays.
_BUILDER_BLOCK_TRADE_ORDER_TYPE = [
    *_BLOCK_TRADE_ORDER_TYPE,
    {"name": "builder", "type": "felt"},
    {"name": "builder_fee_rate", "type": "felt"},
]


def _build_block_typed_data(
    chain_id: int,
    primary_type: str,
    primary_fields: list[dict],
    primary_values: dict,
    trades: list[Trade],
    expected_version: str | None,
) -> TypedDataDict:
    """Build SNIP-12 revision 1 (Poseidon) typed data for a block-trade-shaped payload.

    Trades are sorted alphabetically by market — the canonical ordering both client and
    server agree on. Without this merkle root would not be deterministic.

    Version 3 signs each BlockTradeOrder with its builder fields; version 2 keeps the
    original schema and hash.
    """
    # The server derives the version from the orders, so any other version signs a hash
    # it can never verify.
    version = block_trade_version(trades)
    if expected_version is not None and expected_version != version:
        raise_value_error(f"these trades sign as payload version {version}, not {expected_version!r}")
    with_builder = version == BLOCK_TRADE_BUILDER_PAYLOAD_VERSION
    sorted_trades = sorted(trades, key=lambda t: t.market)
    message = {
        "domain": {
            "name": "Paradex",
            "chainId": hex(chain_id),
            "version": "1",
            "revision": "1",
        },
        "primaryType": primary_type,
        "types": {
            "StarknetDomain": _STARKNET_DOMAIN_TYPE,
            primary_type: primary_fields,
            "Trade": _TRADE_TYPE,
            "BlockTradeOrder": _BUILDER_BLOCK_TRADE_ORDER_TYPE if with_builder else _BLOCK_TRADE_ORDER_TYPE,
        },
        "message": {
            **primary_values,
            "trades": [_trade_message(t, with_builder) for t in sorted_trades],
        },
    }
    return cast(TypedDataDict, message)


def build_block_trade_offer_message(chain_id: int, offer: BlockTradeOffer) -> TypedDataDict:
    """Build the SNIP-12 typed data for a BlockTradeOffer.

    Distinct primary type from BlockTrade — the resulting messageHash is cryptographically
    domain-separated, so an offer signature cannot be replayed as a block-trade signature
    even if the trade leaves match. The block_trade_id binds the offer to a specific parent.
    """
    return _build_block_typed_data(
        chain_id,
        primary_type="BlockTradeOffer",
        primary_fields=[
            {"name": "version", "type": "shortstring"},
            {"name": "nonce", "type": "felt"},
            {"name": "expiration", "type": "felt"},
            {"name": "block_trade_id", "type": "felt"},
            {"name": "trades", "type": "merkletree", "contains": "Trade"},
        ],
        primary_values={
            "version": offer.version,
            "nonce": offer.nonce,
            "expiration": str(offer.expiration),
            "block_trade_id": offer.block_trade_id,
        },
        trades=offer.trades,
        expected_version=offer.expected_version,
    )


def build_block_trade_message(chain_id: int, block_trade: BlockTrade) -> TypedDataDict:
    """Build the SNIP-12 typed data for a BlockTrade.

    The trades slice is declared as `merkletree` in the schema, so the lib reduces the
    leaves to a single felt (the merkle root) when computing the struct hash. A single
    signature over this root commits to every trade leaf atomically.
    """
    return _build_block_typed_data(
        chain_id,
        primary_type="BlockTrade",
        primary_fields=[
            {"name": "version", "type": "shortstring"},
            {"name": "nonce", "type": "felt"},
            {"name": "expiration", "type": "felt"},
            {"name": "trades", "type": "merkletree", "contains": "Trade"},
        ],
        primary_values={
            "version": block_trade.version,
            "nonce": block_trade.nonce,
            "expiration": str(block_trade.expiration),
        },
        trades=block_trade.trades,
        expected_version=block_trade.expected_version,
    )
