from dataclasses import dataclass

import marshmallow_dataclass


@dataclass
class ApiError:
    class Meta:
        # Error bodies are loaded without an explicit `unknown`, so tolerate
        # fields the server adds rather than raising while handling an error.
        unknown = "exclude"

    error: str
    message: str
    data: dict | None


@dataclass
class BridgedToken:
    class Meta:
        # `unknown` passed to load() does not reach a nested schema, so say it
        # here or a released SDK breaks on the first field the server adds to a
        # bridged token -- and fetch_system_config() runs at client startup.
        unknown = "exclude"

    name: str
    symbol: str
    decimals: int
    l1_token_address: str
    l1_bridge_address: str
    l2_token_address: str
    l2_bridge_address: str


@dataclass
class SystemConfig:
    class Meta:
        unknown = "exclude"

    starknet_fullnode_rpc_url: str
    starknet_fullnode_rpc_base_url: str
    starknet_chain_id: str
    block_explorer_url: str
    paraclear_address: str
    paraclear_decimals: int
    paraclear_account_proxy_hash: str
    paraclear_account_hash: str
    oracle_address: str
    bridged_tokens: list[BridgedToken]
    l1_core_contract_address: str
    l1_operator_address: str
    l1_chain_id: str
    liquidation_fee: str
    paraclear_evm_account_hash: str | None = None
    starknet_gateway_url: str | None = None


@dataclass
class AccountSummary:
    class Meta:
        unknown = "exclude"

    account: str
    initial_margin_requirement: str
    maintenance_margin_requirement: str
    account_value: str
    total_collateral: str
    free_collateral: str
    margin_cushion: str
    settlement_asset: str
    updated_at: int
    status: str
    seq_no: int


@dataclass
class Auth:
    class Meta:
        unknown = "exclude"

    jwt_token: str


@dataclass
class RateLimitInfo:
    """Rate limit info parsed from response headers (x-ratelimit-*).

    All fields are None when the server does not send the header.
    - limit: Max requests allowed in the window.
    - remaining: Requests left in the current window.
    - reset: Unix timestamp (seconds) when the current window resets.
    - window: Window duration in seconds (e.g. 1 = per-second limit).
    """

    limit: int | None
    remaining: int | None
    reset: int | None
    window: int | None


@dataclass
class MmpConfig:
    """Market Maker Protection config for one base asset, with its live state.

    A limit of "0" means that check is disabled.

    The live fields are None when the matching engine could not be asked, or is
    still enforcing an older version of the config: right after a change its
    window belongs to the old limits, so the server omits it rather than showing
    it beside the new ones. `frozen_until` is 0 both when a freeze lasts until a
    manual reset and when nothing is frozen, so read `is_frozen` for that.
    """

    class Meta:
        unknown = "exclude"

    base_asset: str
    interval_ms: int
    frozen_time_ms: int
    size_limit: str
    delta_limit: str
    vega_limit: str
    updated_at: int
    is_frozen: bool | None = None
    frozen_until: int | None = None
    window_size: str | None = None
    window_delta: str | None = None
    window_vega: str | None = None


@dataclass
class AccountMmpConfigs:
    """All Market Maker Protection configs of an account, one per base asset.

    A base asset with no entry has MMP off. `enabled` is whether the account may
    use MMP at all: when it is false the configs listed are still enforced, and
    can only be removed.
    """

    class Meta:
        unknown = "exclude"

    account: str
    enabled: bool
    results: list[MmpConfig]


@dataclass
class MmpResetResult:
    """One base asset whose Market Maker Protection freeze and window were cleared."""

    class Meta:
        unknown = "exclude"

    base_asset: str
    reset_at: int


@dataclass
class AccountMmpReset:
    """Base assets a reset cleared, ordered by base asset.

    Empty when no base asset has MMP enabled.
    """

    class Meta:
        unknown = "exclude"

    results: list[MmpResetResult]


ApiErrorSchema = marshmallow_dataclass.class_schema(ApiError)
SystemConfigSchema = marshmallow_dataclass.class_schema(SystemConfig)
AuthSchema = marshmallow_dataclass.class_schema(Auth)
AccountSummarySchema = marshmallow_dataclass.class_schema(AccountSummary)
MmpConfigSchema = marshmallow_dataclass.class_schema(MmpConfig)
AccountMmpConfigsSchema = marshmallow_dataclass.class_schema(AccountMmpConfigs)
AccountMmpResetSchema = marshmallow_dataclass.class_schema(AccountMmpReset)
