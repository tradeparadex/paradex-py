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


ApiErrorSchema = marshmallow_dataclass.class_schema(ApiError)
SystemConfigSchema = marshmallow_dataclass.class_schema(SystemConfig)
AuthSchema = marshmallow_dataclass.class_schema(Auth)
AccountSummarySchema = marshmallow_dataclass.class_schema(AccountSummary)
