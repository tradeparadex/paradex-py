# Generated from Paradex API spec version 1.106.0

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


class CreateSubkey(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    key_type: Annotated[str | None, Field(description="Key type to be registered as a subkey.")] = None
    name: Annotated[
        str | None, Field(description="User-friendly name for the subkey.", examples=["My Trading Subkey"])
    ] = None
    public_key: Annotated[
        str | None,
        Field(
            description="Public key to be registered as a subkey.",
            examples=["0x3d9f2b2e5f50c1aade60ca540368cd7490160f41270c192c05729fe35b656a9"],
        ),
    ] = None


class CreateToken(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    expiry_duration: Annotated[
        int | None,
        Field(description="Duration in seconds from now until expiration (1 min to 1 year).", examples=[86400]),
    ] = None
    name: Annotated[
        str | None, Field(description="User-friendly name for the JWT token.", examples=["My Long-term Trading Token"])
    ] = None
    token_type: Annotated[str | None, Field(description="Type of token to create.")] = None


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


class CreateXPTransferRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    amount: Annotated[int, Field(description="Amount of XP to transfer (must be >= 1)", examples=[100], ge=1)]
    is_private: Annotated[
        bool | None,
        Field(
            description=(
                "Whether the transfer is private (not shown on public feeds). Defaults to false if not provided."
            ),
            examples=[False],
        ),
    ] = False
    recipient: Annotated[
        str,
        Field(description="Recipient's Starknet address (hex format)", examples=["0x1234567890abcdef0123456789abcdef"]),
    ]
    season: Annotated[
        str | None, Field(description="Season identifier. Defaults to season2 if not provided.", examples=["season2"])
    ] = "season2"


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
    signature: Annotated[
        str, Field(description='Order signature in as a string "[r,s]" signed by account\'s paradex private key')
    ]
    signature_timestamp: Annotated[
        int, Field(description="Unix timestamp in milliseconds of order creation, used for signature verification")
    ]
    size: Annotated[str, Field(description="Existing or modified size of the order", examples=["1.213"])]
    trigger_price: Annotated[
        str | None, Field(description="Existing or modified trigger price of a TPSL order", examples=["29500.12"])
    ] = None
    type: Annotated[str, Field(description="Existing type of the order", examples=["LIMIT"])]


class PriceKind(str, Enum):
    price_kind_last = "last"
    price_kind_mark = "mark"
    price_kind_underlying = "underlying"


class UpdateAccountMaxSlippageRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    max_slippage: str


class UpdateAccountProfileRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    announcements: Annotated[bool | None, Field(examples=[False])] = None
    fill_sound: Annotated[bool | None, Field(examples=[True])] = None
    fills: Annotated[bool | None, Field(examples=[True])] = None
    is_username_private: Annotated[bool | None, Field(examples=[True])] = None
    max_slippage: str | None = None
    orders: Annotated[bool | None, Field(examples=[True])] = None
    referral_code: Annotated[str | None, Field(examples=["referral_code"])] = None
    referred_by: Annotated[str | None, Field(examples=["referral_code"])] = None
    size_currency_display: str | None = None
    tap_share_rate: Annotated[str | None, Field(examples=["0.2"])] = None
    trading_value_display: str | None = None
    transfers: Annotated[bool | None, Field(examples=[True])] = None
    username: Annotated[str | None, Field(examples=["username"])] = None
    xp_share_rate: Annotated[str | None, Field(examples=["0.2"])] = None


class UpdateNotificationPreferencesRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    announcements: Annotated[bool | None, Field(examples=[False])] = None
    fill_sound: Annotated[bool | None, Field(examples=[True])] = None
    fills: Annotated[bool | None, Field(examples=[True])] = None
    orders: Annotated[bool | None, Field(examples=[True])] = None
    transfers: Annotated[bool | None, Field(examples=[True])] = None


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


class Utm(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    campaign: Annotated[str | None, Field(description="UTM campaign parameter", examples=["summer2024"])] = None
    source: Annotated[str | None, Field(description="UTM source parameter", examples=["google"])] = None
    type: Annotated[str | None, Field(description="UTM type parameter", examples=["clickthrough"])] = None


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
    on_behalf_of_account: Annotated[
        str | None,
        Field(
            description="ID corresponding to the configured isolated margin account. Only for isolated margin orders",
            examples=["0x1234567890abcdef"],
        ),
    ] = None
    recv_window: Annotated[
        int | None,
        Field(
            description=(
                "Order will be created if it is received by API within RecvWindow milliseconds from signature"
                " timestamp, minimum is 10 milliseconds"
            )
        ),
    ] = None
    side: Annotated[responses.OrderSide, Field(description="Algo order side", examples=["MARKET"])]
    signature: Annotated[
        str, Field(description='Order signature in as a string "[r,s]" signed by account\'s paradex private key')
    ]
    signature_timestamp: Annotated[
        int, Field(description="Unix timestamp in milliseconds of order creation, used for signature verification")
    ]
    size: Annotated[str, Field(description="Size of the algo order", examples=["1.213"])]
    type: Annotated[responses.OrderType, Field(description="Algo order type, only MARKET is supported")]


class BlockExecuteRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    execution_nonce: Annotated[
        str, Field(description="Unique nonce for this execution request", examples=["execution_001"])
    ]
    selected_offers: Annotated[
        list[str] | None,
        Field(description="Array of offer IDs selected for execution (offers are atomic, not partial)"),
    ] = None
    signatures: Annotated[
        dict[str, responses.BlockTradeSignature],
        Field(
            description=(
                "Map of offer IDs to initiator signatures accepting each offer. Block id if it is a direct block trade."
            )
        ),
    ]


class Onboarding(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    marketing_code: Annotated[
        str | None,
        Field(description="Marketing code of the campaign the user is being onboarded via.", examples=["abcd:code1"]),
    ] = None
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
    utm: Annotated[Utm | None, Field(description="UTM tracking parameters (optional).")] = None


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
            description="ID corresponding to the configured isolated margin account. Only for isolated margin orders",
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
    signature: Annotated[
        str, Field(description='Order signature in as a string "[r,s]" signed by account\'s paradex private key')
    ]
    signature_timestamp: Annotated[
        int, Field(description="Unix timestamp in milliseconds of order creation, used for signature verification")
    ]
    size: Annotated[str, Field(description="Size of the order", examples=["1.213"])]
    stp: Annotated[
        str | None,
        Field(description="Self Trade Prevention, EXPIRE_MAKER, EXPIRE_TAKER or EXPIRE_BOTH, if empty EXPIRE_TAKER"),
    ] = None
    trigger_price: Annotated[str | None, Field(description="Trigger price for stop order")] = None
    type: Annotated[responses.OrderType, Field(description="Order type")]
    vwap_price: Annotated[
        str | None,
        Field(description="Optional VWAP price for market orders used for VWAP instruction, bounded by price band"),
    ] = None


class BlockOfferInfo(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    offerer_order: Annotated[responses.BlockTradeOrder, Field(description="Order details from the offering account")]
    price: Annotated[str, Field(description="Offered price for this market", examples=["30050.00"])]
    size: Annotated[str, Field(description="Offered size for this market", examples=["5.0"])]


class BlockOfferRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    nonce: Annotated[str, Field(description="Unique nonce for this offer request", examples=["98765"])]
    offering_account: Annotated[
        str, Field(description="Starknet address of the account making this offer", examples=["0xabcdef1234567890"])
    ]
    signature: Annotated[
        responses.BlockTradeSignature, Field(description="Cryptographic signature authorizing this offer")
    ]
    trades: Annotated[dict[str, BlockOfferInfo], Field(description="Map of market symbol to offer details")]


class BlockTradeInfo(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    maker_order: Annotated[
        responses.BlockTradeOrder | None, Field(description="Maker order details (empty if requiring offers)")
    ] = None
    price: Annotated[
        str | None, Field(description="Agreed price for this trade (empty if requiring offers)", examples=["30000.00"])
    ] = None
    size: Annotated[
        str | None, Field(description="Agreed size for this trade (empty if requiring offers)", examples=["10.5"])
    ] = None
    taker_order: Annotated[
        responses.BlockTradeOrder | None, Field(description="Taker order details (empty if requiring offers)")
    ] = None
    trade_constraints: Annotated[
        responses.BlockTradeConstraints | None, Field(description="Constraints for this trade when requiring offers")
    ] = None


class BlockTradeRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    block_expiration: Annotated[
        int, Field(description="Unix timestamp in milliseconds when block expires", examples=[1640995800000])
    ]
    nonce: Annotated[str, Field(description="Unique nonce for this block trade request", examples=["67890"])]
    required_signers: Annotated[
        list[str], Field(description="List of accounts that can participate in the block trade")
    ]
    signatures: Annotated[
        dict[str, responses.BlockTradeSignature],
        Field(description="Map of account addresses to their signatures. Can be empty or partial."),
    ]
    trades: Annotated[
        dict[str, BlockTradeInfo], Field(description="Map of market symbol to trade info (one per market)")
    ]
