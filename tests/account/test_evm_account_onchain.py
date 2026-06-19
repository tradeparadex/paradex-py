"""Tests that EvmAccount wires a StarkNet account backed by the EIP-191 signer,
so on-chain operations (deposit/withdraw/transfer/guardian) can be signed with
the Ethereum key."""

from eth_account import Account as EthAccount

from paradex_py.account.eip191_signer import Eip191Signer
from paradex_py.account.evm_account import EvmAccount
from tests.mocks.api_client import MockApiClient

# Throwaway EVM key (anvil dev key #2) — test fixture only.
EVM_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
EVM_ADDR = EthAccount.from_key(EVM_KEY).address
L2_ADDR = "0x51f2207a15e14b0a7b21e1b2ec3541f19380429f4269e8c65548170c4f7f2f8"


def _account() -> EvmAccount:
    config = MockApiClient().fetch_system_config()
    return EvmAccount(
        config=config,
        env="testnet",
        evm_address=EVM_ADDR,
        evm_private_key=EVM_KEY,
        l2_address=L2_ADDR,
    )


def test_evm_account_has_starknet_account_with_eip191_signer():
    acct = _account()
    assert hasattr(acct, "starknet")
    assert isinstance(acct.starknet.signer, Eip191Signer)


def test_starknet_account_address_is_l2_address():
    acct = _account()
    assert acct.starknet.address == int(L2_ADDR, 16)


def test_signer_public_key_is_eth_address():
    acct = _account()
    assert acct.starknet.signer.public_key == int(EVM_ADDR, 16)


def test_set_jwt_token_is_picked_up_for_rpc_auth():
    acct = _account()
    assert acct.jwt_token is None
    token = "header.payload.sig"  # noqa: S105 — placeholder JWT, not a secret
    acct.set_jwt_token(token)
    assert acct.jwt_token == token


def test_rpc_version_check_skipped_on_client():
    # The proxy serves a newer spec version and gates the probe; the patch must
    # mark the check done so the first real call doesn't error on it.
    acct = _account()
    assert acct.starknet.client._client._is_spec_version_verified is True
