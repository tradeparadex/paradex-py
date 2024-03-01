from dataclasses import dataclass
from typing import Optional

import marshmallow_dataclass


@dataclass
class ApiError:
    error: str
    message: str
    data: Optional[dict]


@dataclass
class BridgedToken:
    name: str
    symbol: str
    decimals: int
    l1_token_address: str
    l1_bridge_address: str
    l2_token_address: str
    l2_bridge_address: str


@dataclass
class SystemConfig:
    starknet_gateway_url: str
    starknet_fullnode_rpc_url: str
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


@dataclass
class AccountSummary:
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
    jwt_token: str


ApiErrorSchema = marshmallow_dataclass.class_schema(ApiError)
SystemConfigSchema = marshmallow_dataclass.class_schema(SystemConfig)
AuthSchema = marshmallow_dataclass.class_schema(Auth)
AccountSummarySchema = marshmallow_dataclass.class_schema(AccountSummary)
