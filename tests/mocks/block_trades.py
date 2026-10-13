from paradex_py.api.generated.responses import BlockTradeOrder as BlockTradeOrderDTO
from paradex_py.api.generated.responses import OrderSide as DTOOrderSide
from paradex_py.api.generated.responses import OrderType as DTOOrderType


def maker_dto(account: str = "0xMAKER") -> BlockTradeOrderDTO:
    return BlockTradeOrderDTO(
        account=account,
        side=DTOOrderSide.order_side_sell,
        type=DTOOrderType.order_type_limit,
        price="1500",
        size="0.1",
    )
