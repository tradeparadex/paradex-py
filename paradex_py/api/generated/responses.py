# Generated from Paradex API spec version 1.97.0

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class SignatureType(Enum):
    """
    Type of cryptographic signature used
    """

    starknet = "STARKNET"


class BlockTradeSignature(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    nonce: Annotated[str, Field(description="Unique nonce to prevent replay attacks", examples=["12345"])]
    signature_data: Annotated[
        str, Field(description="The actual signature bytes in hex format", examples=["0xabc123..."])
    ]
    signature_expiration: Annotated[
        int, Field(description="Unix timestamp in milliseconds when signature expires", examples=[1640995800000])
    ]
    signature_timestamp: Annotated[
        int, Field(description="Unix timestamp in milliseconds when signature was created", examples=[1640995200000])
    ]
    signature_type: Annotated[
        SignatureType, Field(description="Type of cryptographic signature used", examples=["STARKNET"])
    ]
    signer_account: Annotated[
        str, Field(description="Starknet account address of the signer", examples=["0x1234567890abcdef"])
    ]


class APIResults(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    results: Annotated[list[dict[str, Any]] | None, Field(description="Array of results")] = None


class AccountHistoricalDataResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    data: Annotated[list[float] | None, Field(description="Ordered list of datapoints")] = None
    timestamps: Annotated[list[int] | None, Field(description="Ordered list of timestamps")] = None


class AccountKind(Enum):
    account_kind_unspecified = ""
    account_kind_main = "main"
    account_kind_subaccount = "subaccount"
    account_kind_vault_operator = "vault_operator"
    account_kind_vault_sub_operator = "vault_sub_operator"


class AccountMarginEntry(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    isolated_margin_leverage: Annotated[int | None, Field(description="Isolated margin leverage")] = None
    leverage: Annotated[int | None, Field(description="Leverage value")] = None
    margin_type: Annotated[str | None, Field(description="Margin type (CROSS/ISOLATED)")] = None
    market: Annotated[str | None, Field(description="Market symbol")] = None


class AccountSettingsResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    trading_value_display: Annotated[str | None, Field(examples=["SPOT_NOTIONAL"])] = None


class AccountSummaryResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[
        str | None,
        Field(
            description="User's starknet account",
            examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d9454fa"],
        ),
    ] = None
    account_value: Annotated[
        str | None, Field(description="Current account value [with unrealized P&Ls]", examples=["136285.06918911"])
    ] = None
    free_collateral: Annotated[
        str | None,
        Field(
            description="Free collateral available (Account value in excess of Initial Margin required)",
            examples=["73276.47229774"],
        ),
    ] = None
    initial_margin_requirement: Annotated[
        str | None,
        Field(description="Amount required to open trade for the existing positions", examples=["63008.59689218"]),
    ] = None
    maintenance_margin_requirement: Annotated[
        str | None, Field(description="Amount required to maintain exisiting positions", examples=["31597.25239676"])
    ] = None
    margin_cushion: Annotated[
        str | None, Field(description="Acc value in excess of maintenance margin required", examples=["104687.8167956"])
    ] = None
    seq_no: Annotated[
        int | None,
        Field(
            description=(
                "Unique increasing number (non-sequential) that is assigned to this account update. Can be used to"
                " deduplicate multiple feeds"
            ),
            examples=[1681471234972000000],
        ),
    ] = None
    settlement_asset: Annotated[
        str | None, Field(description="Settlement asset for the account", examples=["USDC"])
    ] = None
    status: Annotated[
        str | None, Field(description="Status of the acc - like ACTIVE, LIQUIDATION", examples=["ACTIVE"])
    ] = None
    total_collateral: Annotated[
        str | None, Field(description="User's total collateral", examples=["123003.62047353"])
    ] = None
    updated_at: Annotated[int | None, Field(description="Account last updated time", examples=[1681471234972])] = None


class AlgoType(Enum):
    algo_type_unspecified = ""
    algo_type_twap = "TWAP"


class AnnouncementKind(Enum):
    announcement_kind_update = "UPDATE"
    announcement_kind_listing = "LISTING"
    announcement_kind_delisting = "DELISTING"


class AskBidArray(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    asks: Annotated[list[list[str]] | None, Field(description="List of Ask sizes and prices")] = None
    best_ask_interactive: Annotated[
        list[str] | None, Field(description="Size on the best ask from UI", examples=[["10.5"]])
    ] = None
    best_bid_interactive: Annotated[
        list[str] | None, Field(description="Size on the best bid from UI", examples=[["10.5"]])
    ] = None
    bids: Annotated[list[list[str]] | None, Field(description="List of Bid sizes and prices")] = None
    last_updated_at: Annotated[
        int | None, Field(description="Last update to the orderbook in milliseconds", examples=[1681462770114])
    ] = None
    market: Annotated[str | None, Field(description="Market name", examples=["ETH-USD-PERP"])] = None
    seq_no: Annotated[int | None, Field(description="Sequence number of the orderbook", examples=[20784])] = None


class AuthResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    jwt_token: Annotated[
        str | None,
        Field(
            description="Authentication token",
            examples=[
                "eyJhbGciOiJFUzM4NCIsInR5cCI6IkpXVCJ9.eyJ0eXAiOiJhdCtKV1QiLCJleHAiOjE2ODE0NTI5MDcsImlhdCI6MTY4MTQ1MjYwNywiaXNzIjoiUGFyYWRleCBzdGFnaW5nIiwic3ViIjoiMHg0OTVkMmViNTIzNmExMmI4YjRhZDdkMzg0OWNlNmEyMDNjZTIxYzQzZjQ3M2MyNDhkZmQ1Y2U3MGQ5NDU0ZmEifQ.BPihIbGhnnsuPlReqC9x12JFXldpswg5EdA6tTiDQm-_UHaRz_8RfVBqWc2fPN6CzFsXTq7GowZu-2qMxPvZK_fGcxEhTp2k1r8MUxowlUIT4vPu2scCwrsyIujlCAwS"
            ],
        ),
    ] = None


class BBOResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    ask: Annotated[str | None, Field(description="Best ask price", examples=["30130.15"])] = None
    ask_size: Annotated[str | None, Field(description="Best ask size", examples=["0.05"])] = None
    bid: Annotated[str | None, Field(description="Best bid price", examples=["30112.22"])] = None
    bid_size: Annotated[str | None, Field(description="Best bid size", examples=["0.04"])] = None
    last_updated_at: Annotated[
        int | None, Field(description="Last update to the orderbook in milliseconds", examples=[1681493939981])
    ] = None
    market: Annotated[str | None, Field(description="Symbol of the market", examples=["BTC-USD-PERP"])] = None
    seq_no: Annotated[int | None, Field(description="Sequence number of the orderbook", examples=[20784])] = None


class BalanceResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    last_updated_at: Annotated[
        int | None, Field(description="Balance last updated time", examples=[1681462770114])
    ] = None
    size: Annotated[
        str | None,
        Field(
            description=(
                "Balance amount of settlement token (includes deposits, withdrawals, realized PnL, realized funding,"
                " and fees)"
            ),
            examples=["123003.620"],
        ),
    ] = None
    token: Annotated[str | None, Field(description="Name of the token", examples=["USDC"])] = None


class BlockExecutionResultResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    executed_at: Annotated[int | None, Field(description="When execution completed", examples=[1640995500000])] = None
    failed_trades: Annotated[int | None, Field(description="Number of trades that failed", examples=[1])] = None
    successful_trades: Annotated[
        int | None, Field(description="Number of trades that executed successfully", examples=[3])
    ] = None
    total_notional: Annotated[
        str | None, Field(description="Total notional value executed", examples=["315000.00"])
    ] = None


class BlockOffersSummaryResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    accepted_offers: Annotated[
        int | None, Field(description="Number of offers that were accepted", examples=[2])
    ] = None
    pending_offers: Annotated[int | None, Field(description="Number of offers still pending", examples=[6])] = None
    total_offered_size: Annotated[str | None, Field(description="Sum of all offered sizes", examples=["85.5"])] = None
    total_offers: Annotated[int | None, Field(description="Total number of offers received", examples=[8])] = None


class BlockTradeConstraintsResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    max_price: Annotated[str | None, Field(description="Maximum price allowed", examples=["31000.00"])] = None
    max_size: Annotated[str | None, Field(description="Maximum trade size allowed", examples=["100.0"])] = None
    min_price: Annotated[str | None, Field(description="Minimum price allowed", examples=["29000.00"])] = None
    min_size: Annotated[str | None, Field(description="Minimum trade size allowed", examples=["0.1"])] = None


class BlockTradeFillResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    fee: Annotated[str | None, Field(description="Fee charged for this fill", examples=["5.25"])] = None
    fill_id: Annotated[str | None, Field(description="Unique identifier for the fill", examples=["fill_789"])] = None
    price: Annotated[str | None, Field(description="Actual execution price", examples=["30000.00"])] = None
    size: Annotated[str | None, Field(description="Actual size that was filled", examples=["10.5"])] = None


class BlockTradeStatus(Enum):
    block_trade_status_created = "CREATED"
    block_trade_status_offer_collection = "OFFER_COLLECTION"
    block_trade_status_ready_to_execute = "READY_TO_EXECUTE"
    block_trade_status_executing = "EXECUTING"
    block_trade_status_completed = "COMPLETED"
    block_trade_status_cancelled = "CANCELLED"


class BlockTradeOrder(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    client_id: Annotated[
        str | None, Field(description="Unique client assigned ID for the order", examples=["123454321"], max_length=64)
    ] = None
    flags: Annotated[list[OrderFlag] | None, Field(description="Order flags, allow flag: REDUCE_ONLY")] = None
    instruction: Annotated[
        OrderInstruction, Field(description="Order Instruction, GTC, IOC, RPI or POST_ONLY if empty GTC")
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
    side: Annotated[OrderSide, Field(description="Order side")]
    signature: Annotated[str, Field(description="Order Payload signed with STARK Private Key")]
    signature_timestamp: Annotated[
        int, Field(description="Timestamp of order creation, used for signature verification")
    ]
    signed_impact_price: Annotated[
        str | None, Field(description="Optional signed impact price for market orders (base64 encoded)")
    ] = None
    size: Annotated[str, Field(description="Size of the order", examples=["1.213"])]
    stp: Annotated[
        str | None,
        Field(description="Self Trade Prevention, EXPIRE_MAKER, EXPIRE_TAKER or EXPIRE_BOTH, if empty EXPIRE_TAKER"),
    ] = None
    trigger_price: Annotated[str | None, Field(description="Trigger price for stop order")] = None
    type: Annotated[OrderType, Field(description="Order type")]


class BridgedToken(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    decimals: int | None = None
    l1_bridge_address: str | None = None
    l1_token_address: str | None = None
    l2_bridge_address: str | None = None
    l2_token_address: str | None = None
    name: str | None = None
    symbol: str | None = None


class CancelOrderResult(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[str | None, Field(description="Account that owns the order")] = None
    client_id: Annotated[str | None, Field(description="Client order ID")] = None
    id: Annotated[str | None, Field(description="Order ID")] = None
    market: Annotated[str | None, Field(description="Market of the order")] = None
    status: Annotated[
        str | None, Field(description="Status of the cancellation: QUEUED_FOR_CANCELLATION, ALREADY_CLOSED, NOT_FOUND")
    ] = None


class Delta1CrossMarginParams(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    imf_base: Annotated[str | None, Field(description="Initial Margin Base", examples=["0.11"])] = None
    imf_factor: Annotated[str | None, Field(description="Initial Margin Factor, always 0.", examples=["0"])] = None
    imf_shift: Annotated[
        str | None, Field(description="Initial Margin Shift, unused, always 0.", examples=["0"])
    ] = None
    mmf_factor: Annotated[str | None, Field(description="Maintenance Margin Factor", examples=["0.51"])] = None


class DiscordProfile(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    id: str | None = None
    image_url: str | None = None
    username: str | None = None


class ErrorCode(Enum):
    error_code_validation = "VALIDATION_ERROR"
    error_code_binding = "BINDING_ERROR"
    error_code_internal_error = "INTERNAL_ERROR"
    error_code_not_found = "NOT_FOUND"
    error_code_service_unavailable = "SERVICE_UNAVAILABLE"
    error_code_string_invalid_parameter = "INVALID_REQUEST_PARAMETER"
    error_code_string_order_id_not_found = "ORDER_ID_NOT_FOUND"
    error_code_string_order_is_closed = "ORDER_IS_CLOSED"
    error_code_string_order_is_not_open = "ORDER_IS_NOT_OPEN"
    error_code_string_invalid_size_for_modify_order = "INVALID_ORDER_SIZE"
    error_code_string_client_order_id_not_found = "CLIENT_ORDER_ID_NOT_FOUND"
    error_code_string_duplicated_client_order_id = "DUPLICATED_CLIENT_ID"
    error_code_string_invalid_price_precision = "INVALID_PRICE_PRECISION"
    error_code_string_invalid_symbol = "INVALID_SYMBOL"
    error_code_string_invalid_token = "INVALID_TOKEN"
    error_code_string_bad_eth_address = "INVALID_ETHEREUM_ADDRESS"
    error_code_string_bad_eth_signature = "INVALID_ETHEREUM_SIGNATURE"
    error_code_string_bad_stark_net_address = "INVALID_STARKNET_ADDRESS"
    error_code_string_bad_stark_net_signature = "INVALID_STARKNET_SIGNATURE"
    error_code_string_starknet_sig_verification_failed = "STARKNET_SIGNATURE_VERIFICATION_FAILED"
    error_code_string_bad_format_starknet_call = "BAD_STARKNET_REQUEST"
    error_code_string_signer_mismatch = "ETHEREUM_SIGNER_MISMATCH"
    error_code_string_hash_mismatch = "ETHEREUM_HASH_MISMATCH"
    error_code_string_not_onboarded = "NOT_ONBOARDED"
    error_code_string_bad_timestamp = "INVALID_TIMESTAMP"
    error_code_string_bad_expiration = "INVALID_SIGNATURE_EXPIRATION"
    error_code_string_account_id_not_found = "ACCOUNT_NOT_FOUND"
    error_code_string_invalid_order_signature = "INVALID_ORDER_SIGNATURE"
    error_code_string_bad_public_key = "PUBLIC_KEY_INVALID"
    error_code_string_unauthorized_eth_address = "UNAUTHORIZED_ETHEREUM_ADDRESS"
    error_code_string_unauthorized_error = "UNAUTHORIZED_ERROR"
    error_code_string_eth_address_already_onboarded = "ETHEREUM_ADDRESS_ALREADY_ONBOARDED"
    error_code_string_market_not_found = "MARKET_NOT_FOUND"
    error_code_string_allowlist_not_found = "ALLOWLIST_ENTRY_NOT_FOUND"
    error_code_string_username_in_use = "USERNAME_IN_USE"
    error_code_string_geo_ip_block = "GEO_IP_BLOCK"
    error_code_string_eth_address_blocked = "ETHEREUM_ADDRESS_BLOCKED"
    error_code_string_program_not_found = "PROGRAM_NOT_FOUND"
    error_code_string_program_not_supported = "PROGRAM_NOT_SUPPORTED"
    error_code_string_invalid_dashboard = "INVALID_DASHBOARD"
    error_code_string_market_not_open = "MARKET_NOT_OPEN"
    error_code_string_invalid_referral_code = "INVALID_REFERRAL_CODE"
    error_code_string_request_not_allowed = "REQUEST_NOT_ALLOWED"
    error_code_string_parent_address_already_onboarded = "PARENT_ADDRESS_ALREADY_ONBOARDED"
    error_code_string_invalid_parent_account = "INVALID_PARENT_ACCOUNT"
    error_code_string_invalid_vault_operator_chain = "INVALID_VAULT_OPERATOR_CHAIN"
    error_code_string_vault_operator_already_onboarded = "VAULT_OPERATOR_ALREADY_ONBOARDED"
    error_code_string_vault_name_in_use = "VAULT_NAME_IN_USE"
    error_code_string_vault_not_found = "VAULT_NOT_FOUND"
    error_code_string_vault_strategy_not_found = "VAULT_STRATEGY_NOT_FOUND"
    error_code_string_vault_limit_reached = "VAULT_LIMIT_REACHED"
    error_code_string_batch_size_out_of_range = "BATCH_SIZE_OUT_OF_RANGE"
    error_code_string_isolated_market_account_mismatch = "ISOLATED_MARKET_ACCOUNT_MISMATCH"
    error_code_string_no_access_to_market = "NO_ACCESS_TO_MARKET"
    error_code_string_points_summary_not_found = "POINTS_SUMMARY_NOT_FOUND"
    error_code_string_algo_id_not_found = "ALGO_ID_NOT_FOUND"
    error_code_string_invalid_derivation_path = "INVALID_DERIVATION_PATH"
    error_code_string_profile_stats_not_found = "PROFILE_STATS_NOT_FOUND"
    error_code_string_invalid_chain = "INVALID_CHAIN"
    error_code_string_invalid_layerswap_swap = "INVALID_LAYERSWAP_SWAP"
    error_code_string_invalid_rhinofi_request = "INVALID_RHINOFI_REQUEST"
    error_code_string_invalid_rhinofi_quote = "INVALID_RHINOFI_QUOTE"
    error_code_string_invalid_rhinofi_quote_commit = "INVALID_RHINOFI_QUOTE_COMMIT"
    error_code_string_social_username_in_use = "SOCIAL_USERNAME_IN_USE"
    error_code_string_invalid_o_auth_request = "INVALID_OAUTH_REQUEST"
    error_code_string_rpi_account_not_whitelisted = "RPI_ACCOUNT_NOT_WHITELISTED"


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    error: ErrorCode | None = None
    message: str | None = None


class Fees(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    commission_rate: Annotated[
        str | None,
        Field(description="multiplier used to calculate the commission amount from fee", examples=["0.0001"]),
    ] = None
    discount_rate: Annotated[
        str | None,
        Field(
            description=(
                "multiplier used to calculate the fee rate after discount, if discount is 10%, then discount_rate"
                " is 0.9"
            ),
            examples=["0.9"],
        ),
    ] = None
    maker_rate: Annotated[str | None, Field(examples=["0.0001"])] = None
    option_maker_rate: Annotated[str | None, Field(examples=["0.0001"])] = None
    option_taker_rate: Annotated[str | None, Field(examples=["0.0001"])] = None
    taker_rate: Annotated[str | None, Field(examples=["0.0001"])] = None


class FillFlag(Enum):
    fill_flag_interactive = "interactive"
    fill_flag_rpi = "rpi"


class FillType(Enum):
    fill_type_liquidation = "LIQUIDATION"
    fill_type_transfer = "TRANSFER"
    fill_type_fill = "FILL"
    fill_type_settle_market = "SETTLE_MARKET"
    fill_type_rpi = "RPI"
    fill_type_block_trade = "BLOCK_TRADE"


class FundingDataResult(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    created_at: Annotated[
        int | None, Field(description="Timestamp in milliseconds when the funding data was created")
    ] = None
    funding_index: Annotated[str | None, Field(description="Current funding index value as a decimal string")] = None
    funding_premium: Annotated[str | None, Field(description="Current funding premium as a decimal string")] = None
    funding_rate: Annotated[str | None, Field(description="Current funding rate as a decimal string")] = None
    market: Annotated[str | None, Field(description="Market represents the market identifier")] = None


class FundingPayment(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[str | None, Field(description="Account that made the payment")] = None
    created_at: Annotated[int | None, Field(description="Funding payment time", examples=[1681375481000])] = None
    fill_id: Annotated[
        str | None, Field(description="Fill id that triggered the payment (if any)", examples=["8615262148007718462"])
    ] = None
    id: Annotated[
        str | None,
        Field(description="Unique string ID to identify the payment", examples=["1681375578221101699352320000"]),
    ] = None
    index: Annotated[
        str | None, Field(description="Value of the funding index at the time of payment", examples=["-2819.53434361"])
    ] = None
    market: Annotated[
        str | None, Field(description="Market against which payment is made", examples=["BTC-USD-PERP"])
    ] = None
    payment: Annotated[
        str | None, Field(description="Payment amount in settlement asset", examples=["34.4490622"])
    ] = None


class GetAccountMarginConfigsResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[str | None, Field(description="Account ID")] = None
    configs: Annotated[
        list[AccountMarginEntry] | None, Field(description="List of margin configurations per market")
    ] = None


class Greeks(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    delta: Annotated[str | None, Field(description="Market Delta", examples=["1"])] = None
    gamma: Annotated[str | None, Field(description="Market Gamma", examples=["0.2"])] = None
    rho: Annotated[str | None, Field(description="Market Rho", examples=["0.2"])] = None
    vanna: Annotated[str | None, Field(description="Market Vanna", examples=["0.2"])] = None
    vega: Annotated[str | None, Field(description="Market Vega", examples=["0.2"])] = None
    volga: Annotated[str | None, Field(description="Market Volga", examples=["0.2"])] = None


class ImpactPriceResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    encoded: Annotated[
        str | None, Field(description="Opaque signed impact price for attaching to a market order")
    ] = None
    impact_price: Annotated[str | None, Field(description="The calculated impact price", examples=["30130.15"])] = None
    market: Annotated[str | None, Field(description="Symbol of the market", examples=["BTC-USD-PERP"])] = None
    side: Annotated[str | None, Field(description="Trade side (BUY or SELL)", examples=["BUY"])] = None
    size: Annotated[str | None, Field(description="Size of the order", examples=["0.05"])] = None


class InsuranceAccountResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[
        str | None,
        Field(
            description="Starknet address of the Insurance fund",
            examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d9454fa"],
        ),
    ] = None
    account_value: Annotated[
        str | None, Field(description="Total account value of insurance fund", examples=["136285.069"])
    ] = None
    settlement_asset: Annotated[
        str | None, Field(description="Settlement Asset for the account", examples=["USDC"])
    ] = None
    updated_at: Annotated[int | None, Field(description="Account last updated time", examples=[1681471234972])] = None


class LiquidationResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    created_at: Annotated[
        int | None, Field(description="Liquidation created at timestamp", examples=[1697213130097])
    ] = None
    id: Annotated[str | None, Field(description="Liquidation transaction hash", examples=["0x123456789"])] = None


class MarketChainDetails(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    collateral_address: Annotated[str | None, Field(description="Collateral address", examples=["0x1234567890"])] = None
    contract_address: Annotated[str | None, Field(description="Contract address", examples=["0x1234567890"])] = None
    fee_account_address: Annotated[
        str | None, Field(description="Fee account address", examples=["0x1234567890"])
    ] = None
    fee_maker: Annotated[str | None, Field(description="Maker fee", examples=["0.01"])] = None
    fee_taker: Annotated[str | None, Field(description="Taker fee", examples=["0.01"])] = None
    insurance_fund_address: Annotated[
        str | None, Field(description="Insurance fund address", examples=["0x1234567890"])
    ] = None
    liquidation_fee: Annotated[str | None, Field(description="Liquidation fee", examples=["0.01"])] = None
    oracle_address: Annotated[str | None, Field(description="Oracle address", examples=["0x1234567890"])] = None
    symbol: Annotated[str | None, Field(description="Market symbol", examples=["ETH-USD-PERP"])] = None


class MarketKind(Enum):
    market_kind_unknown = ""
    market_kind_cross = "cross"
    market_kind_isolated = "isolated"


class AssetKind(Enum):
    """
    Type of asset
    """

    perp = "PERP"
    perp_option = "PERP_OPTION"


class OptionType(Enum):
    """
    Type of option
    """

    put = "PUT"
    call = "CALL"


class MarketSummaryResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    ask: Annotated[str | None, Field(description="Best ask price", examples=["30130.15"])] = None
    ask_iv: Annotated[str | None, Field(description="Ask implied volatility, for options", examples=["0.2"])] = None
    bid: Annotated[str | None, Field(description="Best bid price", examples=["30112.22"])] = None
    bid_iv: Annotated[str | None, Field(description="Bid implied volatility, for options", examples=["0.2"])] = None
    created_at: Annotated[int | None, Field(description="Market summary creation time")] = None
    delta: Annotated[str | None, Field(description="Deprecated: Use greeks.delta instead", examples=["1"])] = None
    funding_rate: Annotated[
        str | None,
        Field(
            description=(
                "This raw funding rate corresponds to the actual funding period of the instrument itself. It is not a"
                " normalized 8h funding rate."
            ),
            examples=["0.3"],
        ),
    ] = None
    future_funding_rate: Annotated[
        str | None, Field(description="For options it's a smoothed version of future's funding rate", examples=["0.3"])
    ] = None
    greeks: Annotated[
        Greeks | None, Field(description="Greeks (delta, gamma, vega). Partial for perpetual futures.")
    ] = None
    last_iv: Annotated[
        str | None, Field(description="Last traded price implied volatility, for options", examples=["0.2"])
    ] = None
    last_traded_price: Annotated[str | None, Field(description="Last traded price", examples=["30109.53"])] = None
    mark_iv: Annotated[str | None, Field(description="Mark implied volatility, for options", examples=["0.2"])] = None
    mark_price: Annotated[
        str | None,
        Field(
            description="[Mark price](https://docs.paradex.trade/risk-system/mark-price-calculation)",
            examples=["29799.70877478"],
        ),
    ] = None
    open_interest: Annotated[
        str | None, Field(description="Open interest in base currency", examples=["6100048.3"])
    ] = None
    price_change_rate_24h: Annotated[
        str | None, Field(description="Price change rate in the last 24 hours", examples=["0.05"])
    ] = None
    symbol: Annotated[str | None, Field(description="Market symbol", examples=["BTC-USD-PERP"])] = None
    total_volume: Annotated[
        str | None, Field(description="Lifetime total traded volume in USD", examples=["141341.0424"])
    ] = None
    underlying_price: Annotated[
        str | None, Field(description="Underlying asset price (spot price)", examples=["29876.3"])
    ] = None
    volume_24h: Annotated[str | None, Field(description="24 hour volume in USD", examples=["47041.0424"])] = None


class Nft(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    collection_address: str | None = None
    collection_name: str | None = None
    description: str | None = None
    id: str | None = None
    image_url: str | None = None
    name: str | None = None


class OrderFlag(Enum):
    flags_reduce_only = "REDUCE_ONLY"
    flags_stop_condition_below_trigger = "STOP_CONDITION_BELOW_TRIGGER"
    flags_stop_condition_above_trigger = "STOP_CONDITION_ABOVE_TRIGGER"
    flags_interactive = "INTERACTIVE"


class OrderInstruction(Enum):
    order_instruction_gtc = "GTC"
    order_instruction_post_only = "POST_ONLY"
    order_instruction_ioc = "IOC"
    order_instruction_rpi = "RPI"


class OrderSide(Enum):
    order_side_buy = "BUY"
    order_side_sell = "SELL"


class OrderStatus(Enum):
    order_status_new = "NEW"
    order_status_untriggered = "UNTRIGGERED"
    order_status_open = "OPEN"
    order_status_closed = "CLOSED"


class OrderType(Enum):
    order_type_market = "MARKET"
    order_type_limit = "LIMIT"
    order_type_stop_limit = "STOP_LIMIT"
    order_type_stop_market = "STOP_MARKET"
    order_type_take_profit_limit = "TAKE_PROFIT_LIMIT"
    order_type_take_profit_market = "TAKE_PROFIT_MARKET"
    order_type_stop_loss_market = "STOP_LOSS_MARKET"
    order_type_stop_loss_limit = "STOP_LOSS_LIMIT"


class PaginatedAPIResults(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    next: Annotated[
        str | None,
        Field(
            description="The pointer to fetch next set of records (null if there are no records left)",
            examples=["eyJmaWx0ZXIiMsIm1hcmtlciI6eyJtYXJrZXIiOiIxNjc1NjUwMDE3NDMxMTAxNjk5N="],
        ),
    ] = None
    prev: Annotated[
        str | None,
        Field(
            description="The pointer to fetch previous set of records (null if there are no records left)",
            examples=["eyJmaWx0ZXIiOnsiTGltaXQiOjkwfSwidGltZSI6MTY4MTY3OTgzNzk3MTMwOTk1MywibWFya2VyIjp7Im1zMjExMD=="],
        ),
    ] = None
    results: Annotated[list[dict[str, Any]] | None, Field(description="Array of paginated results")] = None


class PerpetualOptionMarginParams(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    long_itm: Annotated[str | None, Field(description="Margin fraction for long ITM options", examples=["0.2"])] = None
    premium_multiplier: Annotated[
        str | None, Field(description="Multiplier for margin fraction for premium", examples=["1.2"])
    ] = None
    short_itm: Annotated[
        str | None, Field(description="Margin fraction for short ITM options", examples=["0.4"])
    ] = None
    short_otm: Annotated[
        str | None, Field(description="Margin fraction for short OTM options", examples=["0.25"])
    ] = None
    short_put_cap: Annotated[
        str | None, Field(description="Cap for margin fraction for short put options", examples=["0.5"])
    ] = None


class Side(Enum):
    """
    Position Side : Long or Short
    """

    short = "SHORT"
    long = "LONG"


class Status(Enum):
    """
    Status of Position : Open or Closed
    """

    open = "OPEN"
    closed = "CLOSED"


class PositionResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[str | None, Field(description="Account ID of the position")] = None
    average_entry_price: Annotated[str | None, Field(description="Average entry price", examples=["29001.34"])] = None
    average_entry_price_usd: Annotated[
        str | None, Field(description="Average entry price in USD", examples=["29001.34"])
    ] = None
    average_exit_price: Annotated[str | None, Field(description="Average exit price", examples=["29001.34"])] = None
    cached_funding_index: Annotated[
        str | None, Field(description="Position cached funding index", examples=["1234.3"])
    ] = None
    closed_at: Annotated[int | None, Field(description="Position closed time", examples=[1681493939981])] = None
    cost: Annotated[str | None, Field(description="Position cost", examples=["-10005.4623"])] = None
    cost_usd: Annotated[str | None, Field(description="Position cost in USD", examples=["-10005.4623"])] = None
    created_at: Annotated[int | None, Field(description="Position creation time", examples=[1681493939981])] = None
    id: Annotated[str | None, Field(description="Unique string ID for the position", examples=["1234234"])] = None
    last_fill_id: Annotated[
        str | None, Field(description="Last fill ID to which the position is referring", examples=["1234234"])
    ] = None
    last_updated_at: Annotated[
        int | None, Field(description="Position last update time", examples=[1681493939981])
    ] = None
    leverage: Annotated[str | None, Field(description="Leverage of the position")] = None
    liquidation_price: Annotated[str | None, Field(description="Liquidation price of the position")] = None
    market: Annotated[str | None, Field(description="Market for position", examples=["BTC-USD-PERP"])] = None
    realized_positional_funding_pnl: Annotated[
        str | None,
        Field(
            description="Realized Funding PnL for the position. Reset to 0 when position is closed or flipped.",
            examples=["12.234"],
        ),
    ] = None
    realized_positional_pnl: Annotated[
        str | None,
        Field(
            description=(
                "Realized PnL including both positional PnL and funding payments. Reset to 0 when position is closed or"
                " flipped."
            ),
            examples=["-123.23"],
        ),
    ] = None
    seq_no: Annotated[
        int | None,
        Field(
            description=(
                "Unique increasing number (non-sequential) that is assigned to this position update. Can be used to"
                " deduplicate multiple feeds"
            ),
            examples=[1681471234972000000],
        ),
    ] = None
    side: Annotated[Side | None, Field(description="Position Side : Long or Short")] = None
    size: Annotated[
        str | None,
        Field(
            description="Size of the position with sign (positive if long or negative if short)", examples=["-0.345"]
        ),
    ] = None
    status: Annotated[Status | None, Field(description="Status of Position : Open or Closed")] = None
    unrealized_funding_pnl: Annotated[
        str | None, Field(description="Unrealized running funding P&L for the position", examples=["12.234"])
    ] = None
    unrealized_pnl: Annotated[
        str | None,
        Field(
            description=(
                "Unrealized P&L of the position in the quote asset. Includes the unrealized running funding P&L."
            ),
            examples=["-123.23"],
        ),
    ] = None


class ReferralConfigResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    commission_rate: Annotated[
        str | None, Field(description="Commission rate for the referer", examples=["0.1"])
    ] = None
    commission_volume_cap: Annotated[
        str | None, Field(description="Volume cap for commission", examples=["1000000000"])
    ] = None
    discount_rate: Annotated[str | None, Field(description="Discount rate for the referee", examples=["0.1"])] = None
    discount_volume_cap: Annotated[
        str | None, Field(description="Volume cap for discount", examples=["30000000"])
    ] = None
    minimum_volume: Annotated[
        str | None, Field(description="Minimum volume required to be eligible for Program", examples=["0.123"])
    ] = None
    name: Annotated[str | None, Field(description="Referral name", examples=["Referral"])] = None
    points_bonus_rate: Annotated[
        str | None, Field(description="Points bonus rate for the referee", examples=["0.1"])
    ] = None
    points_bonus_volume_cap: Annotated[
        str | None, Field(description="Volume cap for points bonus", examples=["1000000000"])
    ] = None
    referral_type: Annotated[str | None, Field(description="Referral type", examples=["Referral"])] = None


class ReferralsResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    address: Annotated[str | None, Field(description="referee address")] = None
    created_at: Annotated[
        int | None, Field(description="Joined at timestamp in milliseconds", examples=[1715592690488])
    ] = None
    referral_code: Annotated[
        str | None, Field(description="Referral code used to onboard the referee", examples=["maxdegen01"])
    ] = None
    referral_rewards: Annotated[
        str | None, Field(description="Total referral commission earned from the fee of referee", examples=["0.123"])
    ] = None
    volume_traded: Annotated[str | None, Field(description="Total volume traded by referee", examples=["0.123"])] = None


class RequestInfo(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    id: Annotated[str | None, Field(description="Request id")] = None
    message: Annotated[str | None, Field(description="Error message for failed requests")] = None
    request_type: Annotated[str | None, Field(description="Type of request (MODIFY_ORDER)")] = None
    status: Annotated[str | None, Field(description="Status of modify order request")] = None


class STPMode(Enum):
    stp_mode_expire_maker = "EXPIRE_MAKER"
    stp_mode_expire_taker = "EXPIRE_TAKER"
    stp_mode_expire_both = "EXPIRE_BOTH"


class Strategy(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    address: Annotated[
        str | None,
        Field(
            description="Contract address of the sub-operator",
            examples=["0x29464b79b02543ed8746bba6e71c8a15401dd27b7279a5fa2f2fe8e8cdfabb"],
        ),
    ] = None
    name: Annotated[str | None, Field(description="Strategy name", examples=["Alpha Strategy"])] = None


class SystemConfigResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    block_explorer_url: Annotated[
        str | None,
        Field(
            description="Block explorer URL for the current SN Instance",
            examples=["https://voyager.testnet.paradex.trade/"],
        ),
    ] = None
    bridged_tokens: Annotated[
        list[BridgedToken] | None,
        Field(
            description=(
                "bridged tokens"
                " config\nhttps://github.com/starknet-io/starknet-addresses/blob/master/bridged_tokens/goerli.json"
            )
        ),
    ] = None
    environment: Annotated[
        str | None, Field(description="Environment of the Paradex Instance", examples=["local"])
    ] = None
    l1_chain_id: Annotated[str | None, Field(description="L1 chain ID value", examples=["5"])] = None
    l1_core_contract_address: Annotated[
        str | None,
        Field(
            description="Address of Starknet L1 core contract", examples=["0x182FE62c57461d4c5Ab1aE6F04f1D51aA1607daf"]
        ),
    ] = None
    l1_operator_address: Annotated[
        str | None,
        Field(description="Address of Starknet L1 operator", examples=["0x63e762538C70442758Fd622116d817761c94FD6A"]),
    ] = None
    l1_relayer_address: Annotated[
        str | None, Field(description="Address of L1 Relayer", examples=["0x63e762538C70442758Fd622116d817761c94FD6A"])
    ] = None
    l2_relayer_address: Annotated[
        str | None, Field(description="Address of L2 Relayer", examples=["0x63e762538C70442758Fd622116d817761c94FD6A"])
    ] = None
    liquidation_fee: Annotated[str | None, Field(description="Liquidation fee", examples=["0.20"])] = None
    oracle_address: Annotated[
        str | None,
        Field(
            description="Oracle contract address",
            examples=["0x47c622ce5f7ff7fa17725df596f4f506364e49be0621eb142a75b44ee3689c6"],
        ),
    ] = None
    paraclear_account_hash: Annotated[
        str | None,
        Field(
            description="Class hash of the account contract",
            examples=["0x033434ad846cdd5f23eb73ff09fe6fddd568284a0fb7d1be20ee482f044dabe2"],
        ),
    ] = None
    paraclear_account_proxy_hash: Annotated[
        str | None,
        Field(
            description="Proxy hash of the account contract",
            examples=["0x3530cc4759d78042f1b543bf797f5f3d647cde0388c33734cf91b7f7b9314a9"],
        ),
    ] = None
    paraclear_address: Annotated[
        str | None,
        Field(
            description="Paraclear contract address",
            examples=["0x4638e3041366aa71720be63e32e53e1223316c7f0d56f7aa617542ed1e7554d"],
        ),
    ] = None
    paraclear_decimals: int | None = None
    partial_liquidation_buffer: Annotated[
        str | None,
        Field(
            description=(
                "Partial liquidation buffer. Account value is supposed to be at least this much above the MMR after"
                " partial liquidation"
            ),
            examples=["0.2"],
        ),
    ] = None
    partial_liquidation_share_increment: Annotated[
        str | None,
        Field(
            description=(
                "Minimum granularity of partial liquidation share. The share is rounded up to the nearest multiple of"
                " this value"
            ),
            examples=["0.05"],
        ),
    ] = None
    starknet_chain_id: Annotated[
        str | None, Field(description="Chain ID for the Starknet Instance", examples=["SN_CHAIN_ID"])
    ] = None
    starknet_fullnode_rpc_url: Annotated[
        str | None,
        Field(
            description="Full node RPC URL from Starknet",
            examples=["https://pathfinder.api.testnet.paradex.trade/rpc/v0_7"],
        ),
    ] = None
    starknet_gateway_url: Annotated[
        str | None,
        Field(description="Feeder Gateway URL from Starknet", examples=["https://potc-testnet-02.starknet.io"]),
    ] = None
    universal_deployer_address: Annotated[
        str | None,
        Field(description="Universal deployer address", examples=["0x1f3f9d3f1f0b7f3f9f3f9f3f9f3f9f3f9f3f9f3f"]),
    ] = None


class SystemStatus(Enum):
    system_status_ok = "ok"
    system_status_maintenance = "maintenance"
    system_status_cancel_only = "cancel_only"


class SystemTimeResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    server_time: Annotated[str | None, Field(description="Paradex Server time", examples=["1681493415023"])] = None


class TradeResult(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    created_at: Annotated[
        int | None, Field(description="Unix Millisecond timestamp at which trade was done", examples=[1681497002041])
    ] = None
    id: Annotated[str | None, Field(description="Unique Trade ID per TradeType", examples=["12345643"])] = None
    market: Annotated[
        str | None, Field(description="Market for which trade was done", examples=["BTC-USD-PERP"])
    ] = None
    price: Annotated[str | None, Field(description="Trade price", examples=["30001.2"])] = None
    side: Annotated[OrderSide | None, Field(description="Taker side")] = None
    size: Annotated[str | None, Field(description="Trade size", examples=["0.01"])] = None
    trade_type: Annotated[
        FillType | None, Field(description="Trade type, can be FILL, LIQUIDATION, or RPI", examples=["FILL"])
    ] = None


class TradebustResult(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[
        str | None,
        Field(
            description="Paradex Account",
            examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d9454fa"],
        ),
    ] = None
    busted_fill_id: Annotated[
        str | None, Field(description="Unique ID of the busted fill", examples=["12342345"])
    ] = None
    created_at: Annotated[
        int | None, Field(description="Unix timestamp in milliseconds when bust was created", examples=[1681497002041])
    ] = None


class TraderRole(Enum):
    trader_role_taker = "TAKER"
    trader_role_maker = "MAKER"


class State(Enum):
    """
    Status of the transaction on Starknet
    """

    accepted_on_l1 = "ACCEPTED_ON_L1"
    accepted_on_l2 = "ACCEPTED_ON_L2"
    not_received = "NOT_RECEIVED"
    received = "RECEIVED"
    rejected = "REJECTED"
    reverted = "REVERTED"


class Type(Enum):
    """
    Event that triggered the transaction
    """

    transaction_fill = "TRANSACTION_FILL"
    transaction_liquidate = "TRANSACTION_LIQUIDATE"
    transaction_settle_market = "TRANSACTION_SETTLE_MARKET"


class TransactionResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    completed_at: Annotated[int | None, Field(description="Timestamp from when the transaction was completed")] = None
    created_at: Annotated[
        int | None, Field(description="Timestamp from when the transaction was sent to blockchain gateway")
    ] = None
    hash: Annotated[
        str | None,
        Field(
            description=(
                "Tx Hash of the settled trade                                                // Hash of the transaction"
            ),
            examples=["0x445c05d6bfb899e39338440d199971c4d7f4cde7878ed3888df3f716efb8df2"],
        ),
    ] = None
    id: Annotated[
        str | None,
        Field(
            description=(
                "Unique string ID of the event that triggered the transaction. For example, fill ID or liquidation ID"
            ),
            examples=["12342423"],
        ),
    ] = None
    state: Annotated[State | None, Field(description="Status of the transaction on Starknet")] = None
    type: Annotated[Type | None, Field(description="Event that triggered the transaction")] = None


class TransferBridge(Enum):
    transfer_bridge_unspecified = ""
    transfer_bridge_starkgate = "STARKGATE"
    transfer_bridge_layerswap = "LAYERSWAP"
    transfer_bridge_rhinofi = "RHINOFI"
    transfer_bridge_hyperlane = "HYPERLANE"


class TransferDirection(Enum):
    transfer_direction_in = "IN"
    transfer_direction_out = "OUT"


class TransferKind(Enum):
    transfer_kind_deposit = "DEPOSIT"
    transfer_kind_withdrawal = "WITHDRAWAL"
    transfer_kind_unwinding = "UNWINDING"
    transfer_kind_vault_deposit = "VAULT_DEPOSIT"
    transfer_kind_vault_withdrawal = "VAULT_WITHDRAWAL"
    transfer_kind_auto_withdrawal = "AUTO_WITHDRAWAL"


class TransferStatus(Enum):
    transfer_status_pending = "PENDING"
    transfer_status_available = "AVAILABLE"
    transfer_status_completed = "COMPLETED"
    transfer_status_failed = "FAILED"


class TwitterProfile(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    id: str | None = None
    image_url: str | None = None
    username: str | None = None


class UpdateAccountMarginConfigResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[str | None, Field(description="Account ID")] = None
    leverage: Annotated[int | None, Field(description="Leverage value")] = None
    margin_type: Annotated[str | None, Field(description="Margin type (CROSS/ISOLATED)")] = None
    market: Annotated[str | None, Field(description="Market symbol")] = None


class VaultAccountSummaryResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    address: Annotated[
        str | None, Field(description="Contract address of the vault", examples=["0x1234567890abcdef"])
    ] = None
    created_at: Annotated[
        int | None,
        Field(description="Unix timestamp in milliseconds of when the user joined the vault.", examples=[1717171717]),
    ] = None
    deposited_amount: Annotated[
        str | None, Field(description="Amount deposited on the vault by the user in USDC", examples=["123.45"])
    ] = None
    total_pnl: Annotated[
        str | None, Field(description="Total P&L realized by the user in USD.", examples=["149.12"])
    ] = None
    total_roi: Annotated[
        str | None,
        Field(description="Total ROI realized by the user in percentage, i.e. 0.1 means 10%.", examples=["0.724"]),
    ] = None
    vtoken_amount: Annotated[
        str | None, Field(description="Amount of vault tokens owned by the user", examples=["123.45"])
    ] = None


class VaultHistoricalDataResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    address: Annotated[
        str | None, Field(description="Contract address of the vault", examples=["0x1234567890abcdef"])
    ] = None
    data: Annotated[list[float] | None, Field(description="Ordered list of datapoints")] = None
    timestamps: Annotated[list[int] | None, Field(description="Ordered list of timestamps")] = None


class VaultKind(Enum):
    vault_kind_user = "user"
    vault_kind_protocol = "protocol"


class VaultStatus(Enum):
    vault_status_initializing = "INITIALIZING"
    vault_status_active = "ACTIVE"
    vault_status_closed = "CLOSED"
    vault_status_failed = "FAILED"


class VaultSummaryResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    address: Annotated[
        str | None, Field(description="Contract address of the vault", examples=["0x1234567890abcdef"])
    ] = None
    last_month_return: Annotated[
        str | None,
        Field(
            description="APR return of the vault in the last trailing month in percentage, i.e. 0.1 means 10%",
            examples=["0.023"],
        ),
    ] = None
    max_drawdown: Annotated[
        str | None,
        Field(
            description="Max all time drawdown realized by the vault in percentage, i.e. 0.1 means 10%",
            examples=["0.1916"],
        ),
    ] = None
    max_drawdown_24h: Annotated[
        str | None,
        Field(
            description="Max drawdown realized by the vault in the last 24 hours in percentage, i.e. 0.1 means 10%",
            examples=["0.0138"],
        ),
    ] = None
    max_drawdown_30d: Annotated[
        str | None,
        Field(
            description="Max drawdown realized by the vault in the last 30 days in percentage, i.e. 0.1 means 10%",
            examples=["0.1821"],
        ),
    ] = None
    max_drawdown_7d: Annotated[
        str | None,
        Field(
            description="Max drawdown realized by the vault in the last 7 days in percentage, i.e. 0.1 means 10%",
            examples=["0.1124"],
        ),
    ] = None
    net_deposits: Annotated[
        str | None, Field(description="Net deposits of the vault in USDC", examples=["1000000"])
    ] = None
    num_depositors: Annotated[int | None, Field(description="Number of depositors on the vault", examples=[100])] = None
    owner_equity: Annotated[
        str | None,
        Field(
            description="Vault equity of the owner (% of ownership) in percentage, i.e. 0.1 means 10%",
            examples=["0.145"],
        ),
    ] = None
    pnl_24h: Annotated[
        str | None, Field(description="P&L of the vault in the last 24 hours in USD", examples=["13.41"])
    ] = None
    pnl_30d: Annotated[
        str | None, Field(description="P&L of the vault in the last 30 days in USD", examples=["114.19"])
    ] = None
    pnl_7d: Annotated[
        str | None, Field(description="P&L of the vault in the last 7 days in USD", examples=["91.31"])
    ] = None
    roi_24h: Annotated[
        str | None,
        Field(
            description="Return of the vault in the last 24 hours in percentage, i.e. 0.1 means 10%", examples=["0.034"]
        ),
    ] = None
    roi_30d: Annotated[
        str | None,
        Field(
            description="Return of the vault in the last 30 days in percentage, i.e. 0.1 means 10%", examples=["0.003"]
        ),
    ] = None
    roi_7d: Annotated[
        str | None,
        Field(
            description="Return of the vault in the last 7 days in percentage, i.e. 0.1 means 10%", examples=["0.123"]
        ),
    ] = None
    total_pnl: Annotated[str | None, Field(description="Total P&L of the vault in USD", examples=["149.12"])] = None
    total_roi: Annotated[
        str | None, Field(description="Total ROI of the vault in percentage, i.e. 0.1 means 10%", examples=["0.724"])
    ] = None
    tvl: Annotated[
        str | None,
        Field(
            description="Net deposits of the vault in USDC (deprecated; use net_deposits instead)", examples=["1000000"]
        ),
    ] = None
    volume: Annotated[
        str | None, Field(description="All time volume traded by the vault in USD", examples=["12345678.16"])
    ] = None
    volume_24h: Annotated[
        str | None, Field(description="Volume traded by the vault in the last 24 hours in USD", examples=["45678.16"])
    ] = None
    volume_30d: Annotated[
        str | None, Field(description="Volume traded by the vault in the last 30 days in USD", examples=["2345678.16"])
    ] = None
    volume_7d: Annotated[
        str | None, Field(description="Volume traded by the vault in the last 7 days in USD", examples=["345678.16"])
    ] = None
    vtoken_price: Annotated[
        str | None, Field(description="Current value of vault token price in USD", examples=["1.23"])
    ] = None
    vtoken_supply: Annotated[
        str | None, Field(description="Total amount of available vault tokens", examples=["1000000"])
    ] = None


class VaultsConfigResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    max_lockup_period_days: Annotated[
        str | None,
        Field(description="Maximum lockup period in days an owner can configure for a vault", examples=["4"]),
    ] = None
    max_profit_share_percentage: Annotated[
        str | None,
        Field(
            description="Maximum profit share percentage (0-100) an owner can configure for a vault", examples=["50"]
        ),
    ] = None
    min_initial_deposit: Annotated[
        str | None,
        Field(
            description=(
                "Minimum initial collateral deposit (in currency units) at vault creation. Only applies to the owner"
            ),
            examples=["1000"],
        ),
    ] = None
    min_lockup_period_days: Annotated[
        str | None,
        Field(description="Minimum lockup period in days an owner can configure for a vault", examples=["1"]),
    ] = None
    min_owner_share_percentage: Annotated[
        str | None,
        Field(
            description="Minimum share percentage (0-100) the vault owner must maintain on the vault", examples=["5"]
        ),
    ] = None
    vault_factory_address: Annotated[
        str | None, Field(description="Address of the vault factory contract", examples=["0x1234567890abcdef"])
    ] = None


class AccountInfoResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[
        str | None,
        Field(
            description="Starknet address of the account",
            examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d9454fa"],
        ),
    ] = None
    created_at: Annotated[int | None, Field(description="Account creation time", examples=[1681471234972])] = None
    derivation_path: Annotated[
        str | None,
        Field(
            description="Account derivation path used to derive the account, if a sub-account",
            examples=["m/44'/9004'/0'/0/1"],
        ),
    ] = None
    fees: Fees | None = None
    isolated_market: Annotated[
        str | None, Field(description="Isolated market for the account", examples=["ETHUSD-PERP"])
    ] = None
    kind: Annotated[AccountKind | None, Field(description="Account kind", examples=["main"])] = None
    parent_account: Annotated[
        str | None,
        Field(
            description="Starknet address of the parent account",
            examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d"],
        ),
    ] = None
    public_key: Annotated[
        str | None,
        Field(
            description="Starknet public key", examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d"]
        ),
    ] = None
    username: Annotated[str | None, Field(description="Username of the account", examples=["username"])] = None


class AccountProfileResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    discord: DiscordProfile | None = None
    is_username_private: Annotated[bool | None, Field(examples=[True])] = None
    market_max_slippage: dict[str, str] | None = None
    nfts: list[Nft] | None = None
    referral: ReferralConfigResp | None = None
    referral_code: Annotated[str | None, Field(examples=["cryptofox8"])] = None
    referred_by: Annotated[str | None, Field(examples=["maxDegen"])] = None
    size_currency_display: Annotated[str | None, Field(examples=["BASE"])] = None
    twitter: TwitterProfile | None = None
    username: Annotated[str | None, Field(examples=["username"])] = None


class AlgoOrderResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[
        str | None,
        Field(
            description="Account identifier (user's account address)",
            examples=["0x4638e3041366aa71720be63e32e53e1223316c7f0d56f7aa617542ed1e7512"],
        ),
    ] = None
    algo_type: Annotated[AlgoType | None, Field(description="Algo type", examples=["TWAP"])] = None
    avg_fill_price: Annotated[
        str | None, Field(description="Average fill price of the order", examples=["26000"])
    ] = None
    cancel_reason: Annotated[
        str | None,
        Field(description="Reason for algo cancellation if it was closed by cancel", examples=["NOT_ENOUGH_MARGIN"]),
    ] = None
    created_at: Annotated[int | None, Field(description="Algo creation time", examples=[1681493746016])] = None
    end_at: Annotated[int | None, Field(description="Algo end time", examples=[1681493746016])] = None
    id: Annotated[str | None, Field(description="Unique algo identifier", examples=["123456"])] = None
    last_updated_at: Annotated[
        int | None, Field(description="Algo last update time.  No changes once status=CLOSED", examples=[1681493746016])
    ] = None
    market: Annotated[str | None, Field(description="Market to which algo belongs", examples=["BTC-USD-PERP"])] = None
    remaining_size: Annotated[str | None, Field(description="Remaining size of the algo", examples=["0"])] = None
    side: Annotated[OrderSide | None, Field(description="Algo side")] = None
    size: Annotated[str | None, Field(description="Algo size", examples=["0.05"])] = None
    status: Annotated[OrderStatus | None, Field(description="Algo status")] = None


class Announcement(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    content: Annotated[str | None, Field(description="Full announcement content in Markdown format")] = None
    expiry_at: Annotated[int | None, Field(description="Announcement expiry timestamp at page")] = None
    kind: Annotated[AnnouncementKind | None, Field(description="Type of announcement (e.g., Listing)")] = None
    notification_expiry_at: Annotated[
        int | None, Field(description="Announcement expiry timestamp at notification")
    ] = None
    title: Annotated[str | None, Field(description="Short, descriptive title of the announcement")] = None
    visible_at: Annotated[int | None, Field(description="Announcement visible timestamp")] = None


class ApiError(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    data: Annotated[dict[str, Any] | None, Field(description="any additional data related to the error")] = None
    error: Annotated[
        ErrorCode | None,
        Field(description="unique immutable string identifier for specific error", examples=["NOT_ONBOARDED"]),
    ] = None
    message: Annotated[
        str | None,
        Field(
            description="detailed description of error and how to address it",
            examples=["User has never called /onboarding endpoint"],
        ),
    ] = None


class BlockTradeDetailResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    executed_at: Annotated[
        int | None, Field(description="When this trade was executed", examples=[1640995500000])
    ] = None
    failure_reason: Annotated[str | None, Field(description="Reason for failure (if failed)")] = None
    fill: Annotated[BlockTradeFillResponse | None, Field(description="Execution details (if executed)")] = None
    maker_account: Annotated[
        str | None, Field(description="Maker account (if fully executable)", examples=["0x123...abc"])
    ] = None
    maker_order: Annotated[
        BlockTradeOrder | None, Field(description="Include original orders for signature verification if needed")
    ] = None
    market: Annotated[str | None, Field(description="Trading pair for this trade", examples=["BTC-USD-PERP"])] = None
    price: Annotated[str | None, Field(description="Agreed price (if fully executable)", examples=["30000.00"])] = None
    size: Annotated[str | None, Field(description="Agreed size (if fully executable)", examples=["10.5"])] = None
    status: Annotated[str | None, Field(description="Current status of this trade", examples=["PENDING"])] = None
    taker_account: Annotated[
        str | None, Field(description="Taker account (if fully executable)", examples=["0x456...def"])
    ] = None
    taker_order: Annotated[
        BlockTradeOrder | None, Field(description="Original taker order (for signature generation)")
    ] = None
    trade_constraints: Annotated[
        BlockTradeConstraintsResponse | None, Field(description="Constraints for offers (if offer-based)")
    ] = None
    trade_id: Annotated[
        str | None, Field(description="Backend-generated unique identifier for this trade", examples=["trade_123"])
    ] = None


class CancelOrderBatchResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    results: Annotated[list[CancelOrderResult] | None, Field(description="List of cancellation results")] = None


class FillResult(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[
        str | None,
        Field(description="Account that made the fill", examples=["0x978532f46745d7fFBa1CDfa1D8C8202D09D89C9E"]),
    ] = None
    client_id: Annotated[
        str | None, Field(description="Unique client assigned ID for the order", examples=["x1234"])
    ] = None
    created_at: Annotated[int | None, Field(description="Fill time", examples=[1681375176910])] = None
    fee: Annotated[str | None, Field(description="Fee paid by the user", examples=["7.56"])] = None
    fee_currency: Annotated[str | None, Field(description="Asset that fee is charged in", examples=["USDC"])] = None
    fill_type: Annotated[
        FillType | None, Field(description="Fill type, can be FILL, LIQUIDATION or TRANSFER", examples=["FILL"])
    ] = None
    flags: Annotated[
        list[FillFlag] | None,
        Field(description="Fill flags indicating special properties", examples=[['["interactive"', ' "rpi"]']]),
    ] = None
    id: Annotated[
        str | None, Field(description="Unique string ID of fill per FillType", examples=["8615262148007718462"])
    ] = None
    liquidity: Annotated[TraderRole | None, Field(description="Maker or Taker")] = None
    market: Annotated[str | None, Field(description="Market name", examples=["BTC-USD-PERP"])] = None
    order_id: Annotated[str | None, Field(description="Order ID", examples=["1681462103821101699438490000"])] = None
    price: Annotated[str | None, Field(description="Price at which order was filled", examples=["30000.12"])] = None
    realized_funding: Annotated[str | None, Field(description="Realized funding of the fill", examples=["7.56"])] = None
    realized_pnl: Annotated[str | None, Field(description="Realized PnL of the fill", examples=["7.56"])] = None
    remaining_size: Annotated[str | None, Field(description="Remaining size of the order", examples=["0.5"])] = None
    side: Annotated[OrderSide | None, Field(description="Taker side")] = None
    size: Annotated[str | None, Field(description="Size of the fill", examples=["0.5"])] = None
    underlying_price: Annotated[
        str | None, Field(description="Underlying asset price of the fill (spot price)", examples=["7.56"])
    ] = None


class GetAccountsInfoResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    results: list[AccountInfoResponse] | None = None


class GetSubAccountsResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    results: list[AccountInfoResponse] | None = None


class OrderResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[
        str | None,
        Field(
            description="Paradex Account",
            examples=["0x4638e3041366aa71720be63e32e53e1223316c7f0d56f7aa617542ed1e7512x"],
        ),
    ] = None
    avg_fill_price: Annotated[
        str | None, Field(description="Average fill price of the order", examples=["26000"])
    ] = None
    cancel_reason: Annotated[
        str | None,
        Field(description="Reason for order cancellation if it was closed by cancel", examples=["NOT_ENOUGH_MARGIN"]),
    ] = None
    client_id: Annotated[
        str | None, Field(description="Client order id provided by the client at order creation", examples=["x1234"])
    ] = None
    created_at: Annotated[int | None, Field(description="Order creation time", examples=[1681493746016])] = None
    flags: Annotated[list[OrderFlag] | None, Field(description="Order flags, allow flag: REDUCE_ONLY")] = None
    id: Annotated[
        str | None, Field(description="Unique order identifier generated by Paradex", examples=["123456"])
    ] = None
    instruction: Annotated[
        OrderInstruction | None, Field(description="Execution instruction for order matching", examples=["GTC"])
    ] = None
    last_updated_at: Annotated[
        int | None,
        Field(description="Order last update time.  No changes once status=CLOSED", examples=[1681493746016]),
    ] = None
    market: Annotated[str | None, Field(description="Market", examples=["BTC-USD-PERP"])] = None
    price: Annotated[str | None, Field(description="Order price. 0 for MARKET orders", examples=["26000"])] = None
    published_at: Annotated[
        int | None,
        Field(description="Timestamp in milliseconds when order was sent to the client", examples=[1681493746016]),
    ] = None
    received_at: Annotated[
        int | None,
        Field(description="Timestamp in milliseconds when order was received by API service", examples=[1681493746016]),
    ] = None
    remaining_size: Annotated[str | None, Field(description="Remaining size of the order", examples=["0"])] = None
    request_info: Annotated[RequestInfo | None, Field(description="Additional request information for orders")] = None
    seq_no: Annotated[
        int | None,
        Field(
            description=(
                "Unique increasing number (non-sequential) that is assigned to this order update and changes on every"
                " order update. Can be used to deduplicate multiple feeds. WebSocket and REST responses use"
                " independently generated seq_no per event."
            ),
            examples=[1681471234972000000],
        ),
    ] = None
    side: Annotated[OrderSide | None, Field(description="Order side")] = None
    size: Annotated[str | None, Field(description="Order size", examples=["0.05"])] = None
    status: Annotated[OrderStatus | None, Field(description="Order status")] = None
    stp: Annotated[STPMode | None, Field(description="Self Trade Prevention mode", examples=["EXPIRE_MAKER"])] = None
    timestamp: Annotated[int | None, Field(description="Order signature timestamp", examples=[1681493746016])] = None
    trigger_price: Annotated[str | None, Field(description="Trigger price for stop order", examples=["26000"])] = None
    type: Annotated[OrderType | None, Field(description="Order type")] = None


class PerpetualOptionCrossMarginParams(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    imf: PerpetualOptionMarginParams | None = None
    mmf: PerpetualOptionMarginParams | None = None


class SystemStateResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    status: Annotated[SystemStatus | None, Field(description="Status of the system", examples=["ok"])] = None


class TransferResult(BaseModel):
    """
    TransferResult
    """

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    account: Annotated[
        str | None,
        Field(
            description="Starknet Account address",
            examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d9454fa"],
        ),
    ] = None
    amount: Annotated[str | None, Field(description="Transferred amount", examples=["100"])] = None
    auto_withdrawal_fee: Annotated[
        str | None, Field(description="Fee for auto withdrawal in USDC", examples=["4.5"])
    ] = None
    bridge: Annotated[
        TransferBridge | None, Field(description="Bridge used for the transfer", examples=["STARKGATE"])
    ] = None
    counterparty: Annotated[
        str | None,
        Field(
            description="Counterparty address",
            examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d9454fa"],
        ),
    ] = None
    created_at: Annotated[
        int | None, Field(description="Unix Millis timestamp transfer was created on L2", examples=[1681497002041])
    ] = None
    direction: Annotated[
        TransferDirection | None, Field(description="Transfer direction (IN, OUT)", examples=["OUT"])
    ] = None
    external_account: Annotated[
        str | None,
        Field(
            description="External chain account address",
            examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d9454fa"],
        ),
    ] = None
    external_chain: Annotated[
        str | None, Field(description="External chain used for the transfer", examples=["ETHEREUM"])
    ] = None
    external_txn_hash: Annotated[
        str | None,
        Field(
            description="Transaction hash on the external chain",
            examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d9454fa"],
        ),
    ] = None
    failure_reason: Annotated[
        str | None, Field(description="Reason for transfer failure", examples=["Gas fee too low"])
    ] = None
    id: Annotated[str | None, Field(description="Transfer auto-generated ID", examples=["123456789"])] = None
    kind: Annotated[
        TransferKind | None, Field(description="Transfer Kind (DEPOSIT, WITHDRAWAL)", examples=["DEPOSIT"])
    ] = None
    last_updated_at: Annotated[
        int | None, Field(description="Unix Millis timestamp transfer was last updated on L2", examples=[1681497002041])
    ] = None
    socialized_loss_factor: Annotated[
        str | None, Field(description="Withdrawal's socialized loss factor", examples=["0"])
    ] = None
    status: Annotated[
        TransferStatus | None,
        Field(description="Transfer External State (PENDING, AVAILABLE, COMPLETED, FAILED)", examples=["PENDING"]),
    ] = None
    token: Annotated[str | None, Field(description="Transferred token name", examples=["USDC"])] = None
    txn_hash: Annotated[
        str | None,
        Field(
            description="Transaction hash on Paradex chain",
            examples=["0x495d2eb5236a12b8b4ad7d3849ce6a203ce21c43f473c248dfd5ce70d9454fa"],
        ),
    ] = None
    vault_address: Annotated[
        str | None, Field(description="Vault address", examples=["0x7a3b1c8f9e2d4e6f8a0c2b4d6e8f0a2c4b6e8d0a"])
    ] = None
    vault_unwind_completion_percentage: Annotated[
        str | None, Field(description="Vault unwind completion percentage", examples=["0.35"])
    ] = None


class VaultResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    address: Annotated[
        str | None, Field(description="Contract address of the vault", examples=["0x1234567890abcdef"])
    ] = None
    created_at: Annotated[
        int | None,
        Field(description="Unix timestamp in milliseconds of when the vault has been created", examples=[1517171717]),
    ] = None
    description: Annotated[
        str | None, Field(description="Description of the vault", examples=["My description"])
    ] = None
    kind: Annotated[
        VaultKind | None,
        Field(
            description=(
                "Kind of the vault: 'user' for user-defined vaults, 'protocol' for vaults controlled by Paradex"
            ),
            examples=["user"],
        ),
    ] = None
    last_updated_at: Annotated[
        int | None,
        Field(description="Unix timestamp in milliseconds of when the vault was last updated", examples=[1617171717]),
    ] = None
    lockup_period: Annotated[int | None, Field(description="Lockup period of the vault in days", examples=[1])] = None
    max_tvl: Annotated[
        int | None, Field(description="Maximum amount of assets the vault can hold in USDC", examples=[1000000])
    ] = None
    name: Annotated[str | None, Field(description="Name of the vault", examples=["MyVault"])] = None
    operator_account: Annotated[
        str | None, Field(description="Operator account of the vault", examples=["0x1234567890abcdef"])
    ] = None
    owner_account: Annotated[
        str | None, Field(description="Owner account of the vault", examples=["0x0234567890abcdef"])
    ] = None
    profit_share: Annotated[
        int | None, Field(description="Profit share of the vault in percentage, i.e. 10 means 10%", examples=[10])
    ] = None
    status: Annotated[VaultStatus | None, Field(description="Status of the vault", examples=["ACTIVE"])] = None
    strategies: Annotated[list[Strategy] | None, Field(description="Strategies of the vault")] = None
    token_address: Annotated[str | None, Field(description="LP token address")] = None


class BatchResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    errors: list[ErrorResponse] | None = None
    orders: list[OrderResp] | None = None


class BlockTradeDetailFullResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    block_id: Annotated[
        str | None, Field(description="Backend-generated unique identifier", examples=["block_456"])
    ] = None
    block_type: Annotated[str | None, Field(description="Type: DIRECT or OFFER_BASED", examples=["OFFER_BASED"])] = None
    created_at: Annotated[int | None, Field(description="When block was created", examples=[1640995200000])] = None
    execution_result: Annotated[
        BlockExecutionResultResponse | None, Field(description="Final execution results (if executed)")
    ] = None
    expires_at: Annotated[int | None, Field(description="When block expires", examples=[1640995800000])] = None
    initiator: Annotated[
        str | None, Field(description="Account that initiated this block trade", examples=["0x123...abc"])
    ] = None
    last_updated_at: Annotated[
        int | None, Field(description="When block was last updated", examples=[1640995400000])
    ] = None
    nonce: Annotated[
        str | None,
        Field(description="Include signing data for signature verification and generation", examples=["67890"]),
    ] = None
    offers_summary: Annotated[
        BlockOffersSummaryResponse | None, Field(description="Summary of offers (if offer-based)")
    ] = None
    parent_block_id: Annotated[
        str | None, Field(description="Parent block ID (if offer-based)", examples=["block_123"])
    ] = None
    required_signers: Annotated[
        list[str] | None, Field(description="List of accounts that must sign (for signature verification)")
    ] = None
    signatures: Annotated[
        dict[str, BlockTradeSignature] | None,
        Field(description="Current signatures on this block (for signature verification)"),
    ] = None
    status: Annotated[
        BlockTradeStatus | None, Field(description="Current status of the block trade", examples=["COMPLETED"])
    ] = None
    trades: Annotated[
        dict[str, BlockTradeDetailResponse] | None, Field(description="Map of market to trade details")
    ] = None


class MarketResp(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )
    asset_kind: Annotated[AssetKind | None, Field(description="Type of asset", examples=["PERP"])] = None
    base_currency: Annotated[str | None, Field(description="Base currency of the market", examples=["ETH"])] = None
    chain_details: Annotated[MarketChainDetails | None, Field(description="Chain details")] = None
    clamp_rate: Annotated[str | None, Field(description="Clamp rate", examples=["0.05"])] = None
    delta1_cross_margin_params: Annotated[
        Delta1CrossMarginParams | None, Field(description="Delta1 Cross margin parameters")
    ] = None
    expiry_at: Annotated[int | None, Field(description="Market expiry time", examples=[0])] = None
    funding_period_hours: Annotated[float | None, Field(description="Funding period in hours", examples=[8])] = None
    interest_rate: Annotated[str | None, Field(description="Interest rate", examples=["0.01"])] = None
    iv_bands_width: Annotated[str | None, Field(description="IV Bands Width", examples=["0.05"])] = None
    market_kind: Annotated[MarketKind | None, Field(description="Market's margin mode", examples=["cross"])] = None
    max_funding_rate: Annotated[str | None, Field(description="Max funding rate", examples=["0.05"])] = None
    max_funding_rate_change: Annotated[
        str | None, Field(description="Max funding rate change", examples=["0.0005"])
    ] = None
    max_open_orders: Annotated[int | None, Field(description="Max open orders", examples=[100])] = None
    max_order_size: Annotated[
        str | None, Field(description="Maximum order size in base currency", examples=["100"])
    ] = None
    max_tob_spread: Annotated[
        str | None, Field(description="The maximum TOB spread allowed to apply funding rate changes", examples=["0.2"])
    ] = None
    min_notional: Annotated[
        str | None,
        Field(
            description="Minimum order notional in USD. For futures: size*mark_price, for options: size*spot_price",
            examples=["3"],
        ),
    ] = None
    open_at: Annotated[int | None, Field(description="Market open time in milliseconds", examples=[0])] = None
    option_cross_margin_params: Annotated[
        PerpetualOptionCrossMarginParams | None, Field(description="Option Cross margin parameters")
    ] = None
    option_type: Annotated[OptionType | None, Field(description="Type of option", examples=["PUT"])] = None
    oracle_ewma_factor: Annotated[str | None, Field(description="Oracle EWMA factor", examples=["0.2"])] = None
    order_size_increment: Annotated[
        str | None, Field(description="Minimum size increment for base currency", examples=["0.001"])
    ] = None
    position_limit: Annotated[str | None, Field(description="Position limit in base currency", examples=["500"])] = None
    price_bands_width: Annotated[
        str | None,
        Field(
            description="Price Bands Width, 0.05 means 5% price deviation allowed from mark price", examples=["0.05"]
        ),
    ] = None
    price_feed_id: Annotated[
        str | None,
        Field(
            description="Price feed id. Pyth price account used to price underlying asset",
            examples=["GVXRSBjFk6e6J3NbVPXohDJetcTjaeeuykUpbQF8UoMU"],
        ),
    ] = None
    price_tick_size: Annotated[
        str | None, Field(description="Minimum price increment of the market in USD", examples=["0.01"])
    ] = None
    quote_currency: Annotated[str | None, Field(description="Quote currency of the market", examples=["USD"])] = None
    settlement_currency: Annotated[
        str | None, Field(description="Settlement currency of the market", examples=["USDC"])
    ] = None
    strike_price: Annotated[str | None, Field(description="Strike price for option market", examples=["66500"])] = None
    symbol: Annotated[str | None, Field(description="Market symbol", examples=["ETH-USD-PERP"])] = None
    tags: Annotated[list[str] | None, Field(description="Market tags", examples=[["MEME", "DEFI"]])] = None
