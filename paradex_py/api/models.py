from dataclasses import dataclass

import marshmallow_dataclass


@dataclass
class ApiError:
    code: str
    message: str


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
    api_url: str
    ws_api_url: str
    starknet_gateway_url: str
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


ApiErrorSchema = marshmallow_dataclass.class_schema(ApiError)
SystemConfigSchema = marshmallow_dataclass.class_schema(SystemConfig)
