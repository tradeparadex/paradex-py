"""The /v2 SIWE messages EvmAccount signs, built by the shared builder in paradex_py.message.siwe."""

import base64
from datetime import datetime, timedelta

from eth_account import Account as EthAccount
from eth_account.messages import encode_defunct

from paradex_py.account.evm_account import EvmAccount
from tests.mocks.api_client import MockApiClient

# Throwaway EVM key (anvil dev key #2) — test fixture only.
EVM_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
EVM_ADDR = EthAccount.from_key(EVM_KEY).address
L2_ADDR = "0x51f2207a15e14b0a7b21e1b2ec3541f19380429f4269e8c65548170c4f7f2f8"


def _account() -> EvmAccount:
    return EvmAccount(
        config=MockApiClient().fetch_system_config(),
        env="testnet",
        evm_address=EVM_ADDR,
        evm_private_key=EVM_KEY,
        l2_address=L2_ADDR,
    )


def _signed_lines(headers: dict) -> list[str]:
    message = base64.b64decode(headers["PARADEX-SIWE-MESSAGE"]).decode()
    signer = EthAccount.recover_message(encode_defunct(text=message), signature=headers["PARADEX-EVM-SIGNATURE"])
    assert signer == EVM_ADDR
    return message.split("\n")


def _time(line: str, prefix: str) -> datetime:
    assert line.startswith(prefix)
    return datetime.strptime(line[len(prefix) :], "%Y-%m-%dT%H:%M:%SZ")


def test_onboarding_message_layout():
    lines = _signed_lines(_account().onboarding_headers())

    assert lines[:9] == [
        "app.testnet.paradex.trade wants you to sign in with your Ethereum account:",
        EVM_ADDR,
        "",
        "Paradex Onboarding",
        "",
        "URI: https://app.testnet.paradex.trade",
        "Version: 1",
        "Chain ID: 11155111",
        lines[8],
    ]
    assert len(lines[8]) == len("Nonce: ") + 32
    assert len(lines) == 10
    _time(lines[9], "Issued At: ")


def test_auth_message_expires_five_minutes_after_issue():
    lines = _signed_lines(_account().auth_headers())

    assert lines[3] == "Paradex Auth"
    assert len(lines) == 11
    issued = _time(lines[9], "Issued At: ")
    expires = _time(lines[10], "Expiration Time: ")
    assert expires - issued == timedelta(minutes=5)
