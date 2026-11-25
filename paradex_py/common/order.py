import re
from decimal import Decimal
from enum import Enum
from typing import Any

from starknet_py.constants import FIELD_PRIME

from paradex_py.api.generated.responses import OrderFlag
from paradex_py.utils import raise_value_error, time_now_milli_secs

decimal_zero = Decimal(0)

# Builder fee rates are signed at the same 8-decimal scale as sizes and prices.
_CHAIN_DECIMALS = 8
# The address spelling the server accepts for a builder.
_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{1,64}$")


def chain_builder_fee_rate(rate: Decimal) -> str:
    """Scale a builder fee rate to its signed integer ("0.0005" -> "50000").

    The rate is a fraction of the fill's notional, so it must be above 0 with at most 8
    decimal places; a finer rate would be truncated and sign a different fee than requested.
    """
    if not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0:
        raise_value_error(f"builder_fee_rate must be a Decimal above 0, got {rate!r}")
    scaled = rate.scaleb(_CHAIN_DECIMALS)
    if scaled != scaled.to_integral_value():
        raise_value_error(f"builder_fee_rate allows at most {_CHAIN_DECIMALS} decimal places, got {rate}")
    return str(int(scaled))


def builder_address(builder: str, name: str = "builder") -> str:
    """A builder account in canonical ``0x`` form, refusing anything but a non-zero felt address."""
    if not isinstance(builder, str) or not _ADDRESS.match(builder) or not 0 < int(builder, 16) < FIELD_PRIME:
        raise_value_error(f"{name} must be a non-zero 0x hex account address, got {builder!r}")
    return hex(int(builder, 16))


def validate_builder(builder: str | None, builder_fee_rate: Decimal | None) -> str | None:
    """Check a builder and its fee rate are given together, with a valid address and rate.

    Returns the builder in canonical ``0x`` form, or ``None`` for no builder.
    """
    if not builder and builder_fee_rate is None:
        return None
    if not builder or builder_fee_rate is None:
        raise_value_error("builder and builder_fee_rate must be set together")
    address = builder_address(builder)
    chain_builder_fee_rate(builder_fee_rate)
    return address


class OrderAction(Enum):
    NAN = "NAN"
    Send = "SEND"
    SendCancel = "SEND_CANCEL"


class OrderType(Enum):
    Market = "MARKET"
    Limit = "LIMIT"
    StopLimit = "STOP_LIMIT"
    StopMarket = "STOP_MARKET"
    TakeProfitLimit = "TAKE_PROFIT_LIMIT"
    TakeProfitMarket = "TAKE_PROFIT_MARKET"
    StopLossMarket = "STOP_LOSS_MARKET"
    StopLossLimit = "STOP_LOSS_LIMIT"


class OrderStatus(Enum):
    NEW = "NEW"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class MmpCancelReason(Enum):
    """`cancel_reason` values set when Market Maker Protection cancels an order.

    Attributes:
        Triggered: A size, delta or vega limit tripped for the account and base asset.
        Frozen: The order arrived while the account and base asset were frozen.
        Disabled: MMP was disabled for the account and base asset.
        GreeksUnavailable: The market has no usable greeks - missing, stale, or
            not MMP-eligible.
        NotConfigured: The account and base asset have no MMP config, so the
            order cannot be protected.

    Matching on a value it does not know is safe: `cancel_reason` is a plain
    string everywhere in this SDK, never parsed through this enum, so a reason
    added server-side still reaches the caller.
    """

    Triggered = "MMP_TRIGGERED"
    Frozen = "MMP_FROZEN"
    Disabled = "MMP_DISABLED"
    GreeksUnavailable = "MMP_GREEKS_UNAVAILABLE"
    NotConfigured = "MMP_NOT_CONFIGURED"


class OrderSide(Enum):
    Buy = "BUY"
    Sell = "SELL"

    def opposite_side(self) -> "OrderSide":
        return OrderSide.Sell if self == OrderSide.Buy else OrderSide.Buy

    def sign(self) -> int:
        return 1 if self == OrderSide.Buy else -1

    # 1 = buy, 2 = sell (for chain)
    def chain_side(self) -> str:
        return "1" if self == OrderSide.Buy else "2"


class Order:
    def __init__(
        self,
        market: str,
        order_type: OrderType,
        order_side: OrderSide,
        size: Decimal,
        limit_price: Decimal = decimal_zero,
        client_id: str = "",
        signature_timestamp: int | None = None,
        instruction: str = "GTC",
        reduce_only: bool = False,
        recv_window: int | None = None,
        stp: (
            str | None
        ) = None,  # Self Trade Prevention, EXPIRE_MAKER, EXPIRE_TAKER or EXPIRE_BOTH, default: EXPIRE_TAKER
        trigger_price: Decimal | None = None,
        order_id: str | None = None,
        mmp: bool = False,  # Opt into Market Maker Protection; LIMIT orders on dated options and perps only
        builder: str | None = None,
        builder_fee_rate: Decimal | None = None,
    ) -> None:
        """An order to sign and send.

        ``builder`` (the builder's account address) and ``builder_fee_rate`` (a fraction of
        each fill's notional, ``Decimal("0.0005")`` = 5 bps, at most 8 decimal places) attribute
        the order to a builder, which charges that fee in USDC on every fill. Set both or
        neither. An order naming a builder is signed as ``BuilderOrder`` instead of ``Order``.
        The account must have approved the builder at a rate at least this high, for example
        through a session grant carrying a :class:`~paradex_py.message.session.Builder`.
        A builder is set when the order is created, so a modify (``order_id``) takes none.
        """
        builder = validate_builder(builder, builder_fee_rate)
        if builder and order_id:
            raise_value_error("builder is set when an order is created; a modify (order_id) takes none")
        ts = time_now_milli_secs()
        self.id = order_id
        self.account: str = ""
        self.status = OrderStatus.NEW
        self.limit_price = limit_price
        self.size = size
        self.market = market
        self.remaining = size
        self.order_type = order_type
        self.order_side = order_side
        self.client_id = client_id
        self.instruction = instruction
        self.reduce_only = reduce_only
        self.mmp = mmp
        self.created_at = ts  # milliseconds
        self.cancel_reason = ""
        self.last_action = OrderAction.NAN
        self.last_action_time = 0
        self.cancel_attempts = 0
        self.signature = ""
        self.signature_timestamp = ts if signature_timestamp is None else signature_timestamp
        self.recv_window = recv_window
        self.stp = stp
        self.trigger_price = trigger_price
        self.builder = builder
        self.builder_fee_rate = builder_fee_rate

    def __repr__(self) -> str:
        ord_status = self.status.value
        if self.status == OrderStatus.CLOSED:
            ord_status += f"({self.cancel_reason})"
        msg = f"{self.market} {ord_status} {self.order_type.name} "
        msg += f"{self.order_side} {self.remaining}/{self.size}"
        msg += f"@{self.limit_price}" if self.is_limit_type() else ""
        msg += f"trigger@{self.trigger_price}" if self.trigger_price else ""
        msg += f"recv_window={self.recv_window}" if self.recv_window else ""
        msg += f";id={self.id}" if self.id else ""
        msg += f";client_id={self.client_id}" if self.client_id else ""
        msg += f";builder={self.builder}@{self.builder_fee_rate}" if self.builder else ""
        msg += f";last_action:{self.last_action}" if self.last_action != OrderAction.NAN else ""
        msg += f";signed with:{self.signature}@{self.signature_timestamp}"
        return msg

    def __eq__(self, __o) -> bool:
        return self.id == __o.id

    def __hash__(self) -> int:
        return hash(self.id)

    def dump_to_dict(self) -> dict[Any, Any]:
        order_dict: dict[Any, Any] = {
            "market": self.market,
            "side": self.order_side.value,
            "size": str(self.size),
            "type": self.order_type.value,
            "client_id": self.client_id,
            "instruction": self.instruction,
            "signature": self.signature,
            "signature_timestamp": self.signature_timestamp,
            "recv_window": self.recv_window,
            "stp": self.stp,
        }
        if self.is_limit_type():
            order_dict["price"] = str(self.limit_price)
        if self.trigger_price:
            order_dict["trigger_price"] = str(self.trigger_price)
        # The generated OrderFlag is the one the API responses are parsed
        # through, so there is a single spelling of these values in the SDK.
        flags = []
        if self.reduce_only:
            flags.append(OrderFlag.flags_reduce_only.value)
        if self.mmp:
            flags.append(OrderFlag.flags_mmp.value)
        if flags:
            order_dict["flags"] = flags
        if self.builder and self.builder_fee_rate is not None:
            order_dict["builder"] = self.builder
            order_dict["builder_fee_rate"] = format(self.builder_fee_rate.normalize(), "f")

        # For modify order
        if self.id:
            order_dict["id"] = self.id
        return order_dict

    def chain_price(self) -> str:
        if self.order_type == OrderType.Market:
            return "0"
        return str(int(self.limit_price.scaleb(8)))

    def chain_size(self) -> str:
        return str(int(self.size.scaleb(8)))

    def chain_builder_fee_rate(self) -> str:
        """The builder fee rate as signed in ``BuilderOrder`` ("0.0005" -> "50000")."""
        if self.builder_fee_rate is None:
            raise_value_error("order names no builder")
        return chain_builder_fee_rate(self.builder_fee_rate)

    def is_limit_type(self) -> bool:
        return self.order_type in [
            OrderType.Limit,
            OrderType.StopLimit,
            OrderType.TakeProfitLimit,
            OrderType.StopLossLimit,
        ]
