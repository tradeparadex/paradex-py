from decimal import Decimal
from enum import Enum

from paradex_py.utils import time_now_milli_secs

decimal_zero = Decimal(0)


class OrderAction(Enum):
    NAN = "NAN"
    Send = "SEND"
    SendCancel = "SEND_CANCEL"


class OrderType(Enum):
    Market = "MARKET"
    Limit = "LIMIT"


class OrderStatus(Enum):
    NEW = "NEW"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class OrderSide(Enum):
    Buy = "BUY"
    Sell = "SELL"

    def opposite_side(self) -> "OrderSide":
        if self == OrderSide.Buy:
            return OrderSide.Sell
        else:
            return OrderSide.Buy

    def sign(self) -> int:
        if self == OrderSide.Buy:
            return 1
        else:
            return -1

    def chain_side(self) -> str:
        if self == OrderSide.Buy:
            return "1"
        else:
            return "2"


class Order:
    def __init__(
        self,
        market,
        order_type: OrderType,
        order_side: OrderSide,
        size: Decimal,
        limit_price: Decimal = decimal_zero,
        client_id: str = "",
        signature_timestamp=None,
    ) -> None:
        ts = int(time_now_milli_secs())
        self.id: str = ""
        self.account: str = ""
        self.status = OrderStatus.NEW
        self.limit_price = limit_price
        self.size = size
        self.market = market
        self.remaining = size
        self.order_type = order_type
        self.order_side = order_side
        self.client_id = client_id
        # created_at is in milliseconds
        self.created_at = ts
        self.cancel_reason = ""
        self.last_action = OrderAction.NAN
        self.last_action_time = 0
        self.cancel_attempts = 0
        self.signature = ""
        self.signature_timestamp = ts if signature_timestamp is None else signature_timestamp

    def __repr__(self) -> str:
        ord_status = self.status.value
        if self.status == OrderStatus.CLOSED:
            ord_status += f"({self.cancel_reason})"
        msg = f"{self.market} {ord_status} {self.order_type.name} "
        msg += f"{self.order_side} {self.remaining}/{self.size}"
        msg += f"@{self.limit_price}" if self.order_type == OrderType.Limit else ""
        msg += f";id={self.id}" if self.id else ""
        msg += f";client_id={self.client_id}" if self.client_id else ""
        msg += f";last_action:{self.last_action}" if self.last_action != OrderAction.NAN else ""
        msg += f";signed with:{self.signature}@{self.signature_timestamp}"
        return msg

    def __eq__(self, __o) -> bool:
        return self.id == __o.id

    def __hash__(self) -> int:
        return hash(self.id)

    def dump_to_dict(self) -> dict:
        order_dict = {
            "market": self.market,
            "side": self.order_side.value,
            "size": str(self.size),
            "type": self.order_type.value,
            "client_id": self.client_id,
            "signature": self.signature,
            "signature_timestamp": self.signature_timestamp,
        }
        if self.order_type == OrderType.Limit:
            order_dict["price"] = str(self.limit_price)

        return order_dict

    def chain_price(self) -> str:
        if self.order_type == OrderType.Market:
            return "0"
        return str(int(self.limit_price.scaleb(8)))

    def chain_size(self) -> str:
        return str(int(self.size.scaleb(8)))
