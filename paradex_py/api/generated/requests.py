# Generated from Paradex API spec version 1.96.03

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import responses


class AccountMarginRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    leverage: Annotated[int, Field(description="Leverage value (1 up to market's maximum leverage)", examples=[10])]
    margin_type: Annotated[str, Field(description="Margin type (CROSS or ISOLATED)", examples=["CROSS"])]
    on_behalf_of_account: Annotated[
        str | None,
        Field(
            description="Specify sub-account ID to set margin for, if not provided, it will be the main account itself",
            examples=["0x1234567890abcdef"],
        ),
    ] = None


class CancelOrderBatchRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    client_order_ids: Annotated[
        list[str] | None,
        Field(description="List of client order IDs to cancel", examples=[['["client-id-1"', '"client-id-2"]']]),
    ] = None
    order_ids: Annotated[
        list[str] | None,
        Field(description="List of order IDs to cancel", examples=[['["order-id-1"', '"order-id-2"]']]),
    ] = None


class CreateVault(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    deposit_tx_signature: Annotated[
        str | None, Field(description="Initial deposit transfer by vault owner", examples=["["])
    ] = None
    description: Annotated[
        str | None, Field(description="Description for the vault", examples=["My vault description"])
    ] = None
    lockup_period: Annotated[
        int | None, Field(description="User's deposits lockup period in days", examples=[1])
    ] = None
    max_tvl: Annotated[
        int | None, Field(description="Max TVL locked by the Vault, if any. 0 for unlimited", examples=[1000000])
    ] = None
    name: Annotated[str | None, Field(description="Unique name for the vault", examples=["MyVault"])] = None
    profit_share: Annotated[
        int | None, Field(description="Vault owner profit share (percentage)", examples=[10])
    ] = None
    public_key: Annotated[
        str | None, Field(description="Public key of vault operator", examples=["0x1234567890abcdef"])
    ] = None


class ModifyOrderRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    id: Annotated[str, Field(description="Order ID to be modified")]
    market: Annotated[str, Field(description="Market for which order is modified", examples=["BTC-USD-PERP"])]
    on_behalf_of_account: Annotated[
        str | None,
        Field(
            description="ID corresponding to the configured isolated margin account.  Only for isolated margin orders",
            examples=["0x1234567890abcdef"],
        ),
    ] = None
    price: Annotated[str, Field(description="Existing or modified price of the order", examples=["29500.12"])]
    side: Annotated[str, Field(description="Existing side of the order", examples=["BUY"])]
    signature: Annotated[str, Field(description="Order Payload signed with STARK Private Key")]
    signature_timestamp: Annotated[
        int, Field(description="Timestamp of order creation, used for signature verification")
    ]
    size: Annotated[str, Field(description="Existing or modified size of the order", examples=["1.213"])]
    type: Annotated[str, Field(description="Existing type of the order", examples=["LIMIT"])]


class Onboarding(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    public_key: Annotated[
        str | None,
        Field(
            description="Public key of the user being onboarded.",
            examples=["0x3d9f2b2e5f50c1aade60ca540368cd7490160f41270c192c05729fe35b656a9"],
        ),
    ] = None
    referral_code: Annotated[
        str | None,
        Field(description="Referral code of the user who referred the user being onboarded.", examples=["cryptofox8"]),
    ] = None


class PriceKind(Enum):
    price_kind_last = "last"
    price_kind_mark = "mark"
    price_kind_underlying = "underlying"


class UpdateAccountMaxSlippageRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    max_slippage: str


class UpdateSizeCurrencyDisplayRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    size_currency_display: str


class UpdateTradingValueDisplayRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    trading_value_display: str


class AlgoOrderRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    algo_type: Annotated[str, Field(description="Algo type, required for algo orders creation", examples=["TWAP"])]
    duration_seconds: Annotated[
        int,
        Field(
            description=(
                "Duration in seconds for which the algo order will be running, required for algo orders creation"
            ),
            examples=[3600],
        ),
    ]
    market: Annotated[str, Field(description="Market for which order is created", examples=["BTC-USD-PERP"])]
    side: Annotated[responses.OrderSide, Field(description="Algo order side", examples=["MARKET"])]
    signature: Annotated[str, Field(description="Order Payload signed with STARK Private Key")]
    signature_timestamp: Annotated[
        int, Field(description="Timestamp of order creation, used for signature verification")
    ]
    size: Annotated[str, Field(description="Size of the algo order", examples=["1.213"])]
    type: Annotated[responses.OrderType, Field(description="Algo order type, only MARKET is supported")]


class OrderRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    client_id: Annotated[
        str | None, Field(description="Unique client assigned ID for the order", examples=["123454321"], max_length=64)
    ] = None
    flags: Annotated[list[responses.OrderFlag] | None, Field(description="Order flags, allow flag: REDUCE_ONLY")] = None
    instruction: Annotated[
        responses.OrderInstruction, Field(description="Order Instruction, GTC, IOC, RPI or POST_ONLY if empty GTC")
    ]
    market: Annotated[str, Field(description="Market for which order is created", examples=["BTC-USD-PERP"])]
    on_behalf_of_account: Annotated[
        str | None,
        Field(
            description="ID corresponding to the configured isolated margin account.  Only for isolated margin orders",
            examples=["0x1234567890abcdef"],
        ),
    ] = None
    price: Annotated[str, Field(description="Order price", examples=["29500.12"])]
    recv_window: Annotated[
        int | None,
        Field(
            description=(
                "Order will be created if it is received by API within RecvWindow milliseconds from signature"
                " timestamp, minimum is 10 milliseconds"
            )
        ),
    ] = None
    side: Annotated[responses.OrderSide, Field(description="Order side")]
    signature: Annotated[str, Field(description="Order Payload signed with STARK Private Key")]
    signature_timestamp: Annotated[
        int, Field(description="Timestamp of order creation, used for signature verification")
    ]
    size: Annotated[str, Field(description="Size of the order", examples=["1.213"])]
    stp: Annotated[
        str | None,
        Field(description="Self Trade Prevention, EXPIRE_MAKER, EXPIRE_TAKER or EXPIRE_BOTH, if empty EXPIRE_TAKER"),
    ] = None
    trigger_price: Annotated[str | None, Field(description="Trigger price for stop order")] = None
    type: Annotated[responses.OrderType, Field(description="Order type")]
