from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional

from paradex_py.utils import time_now_milli_secs

decimal_zero = Decimal(0)


class OrderAction(Enum):
    NAN = "NAN"
    Send = "SEND"
    SendCancel = "SEND_CANCEL"


class OrderType(Enum):
    Market = "MARKET"
    Limit = "LIMIT"
    StopLimit = "STOP_LIMIT"
    StopMarket = "STOP_MARKET"


class OrderStatus(Enum):
    NEW = "NEW"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


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
        signature_timestamp: Optional[int] = None,
        instruction: str = "GTC",
        reduce_only: bool = False,
        recv_window: Optional[int] = None,
        stp: Optional[
            str
        ] = None,  # Self Trade Prevention, EXPIRE_MAKER, EXPIRE_TAKER or EXPIRE_BOTH, default: EXPIRE_TAKER
        trigger_price: Optional[Decimal] = None,
        order_id: Optional[str] = None,
    ) -> None:
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
        msg += f";last_action:{self.last_action}" if self.last_action != OrderAction.NAN else ""
        msg += f";signed with:{self.signature}@{self.signature_timestamp}"
        return msg

    def __eq__(self, __o) -> bool:
        return self.id == __o.id

    def __hash__(self) -> int:
        return hash(self.id)

    def dump_to_dict(self) -> Dict[Any, Any]:
        order_dict: Dict[Any, Any] = {
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
        if self.reduce_only:
            order_dict["flags"] = ["REDUCE_ONLY"]

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

    def is_limit_type(self) -> bool:
        return self.order_type == OrderType.Limit or self.order_type == OrderType.StopLimit
