"""Tests for EVM vault-operator L2 address derivation.

The reference vector below was verified end-to-end against testnet on
2026-07-13: the operator address was returned by
``GET /onboarding?...&vault_operator_index=0``, the vault was created with
``operator_signer_type=eip191``, and the operator contract was confirmed
deployed at that address on-chain (``starknet_getClassHashAt`` returned the
expected class hash). A derivation change that breaks this vector breaks
address compatibility with the backend.
"""

from types import SimpleNamespace

import pytest

from paradex_py.account.utils import (
    VAULT_OPERATOR_CHILD_KIND_TAG,
    derive_l2_address_eip191,
    derive_vault_operator_l2_address_eip191,
)

# Testnet Argent v0.5.0 EVM account class hash at the time the vector was taken.
CONFIG = SimpleNamespace(
    paraclear_evm_account_hash="0x073414441639dcd11d1846f287650a00c60c416b9d3ba45d31c651672125b2c2"
)
ETH_ADDRESS = "0x53A3ca2Fcf33f82de111B5E3Ce4d0B76C8f6f938"
OWNER_L2 = 0x26EA01C2D5CCB55F9CCE7F715296C4BB7108E3E2C9DA2371FE8E5462B0B81EF
OPERATOR_IDX0 = 0x3B9F56A4A522916321F60037E1A00E177A9166B9B1289E19A8CF6CB76EDCAE8


def test_kind_tag_is_pinned():
    # sn_keccak("paradex.child.vault_operator") — mirrors VaultOperatorChildKindTag
    # in the backend. The tag feeds the on-chain deployment salt: it must never
    # change once any operator is deployed with it.
    assert VAULT_OPERATOR_CHILD_KIND_TAG == 0x19B452917784423BFEE0CAEE1D05E35F32F4874FDCF99C43B3F9BF197D42E60


def test_owner_derivation_matches_testnet_vector():
    assert derive_l2_address_eip191(CONFIG, ETH_ADDRESS) == OWNER_L2


def test_operator_derivation_matches_testnet_vector():
    assert derive_vault_operator_l2_address_eip191(CONFIG, ETH_ADDRESS, 0) == OPERATOR_IDX0


def test_operator_addresses_distinct_per_index_and_from_owner():
    idx0 = derive_vault_operator_l2_address_eip191(CONFIG, ETH_ADDRESS, 0)
    idx1 = derive_vault_operator_l2_address_eip191(CONFIG, ETH_ADDRESS, 1)
    owner = derive_l2_address_eip191(CONFIG, ETH_ADDRESS)
    assert idx0 != idx1
    assert owner not in (idx0, idx1)


def test_negative_operator_index_raises():
    with pytest.raises(ValueError):
        derive_vault_operator_l2_address_eip191(CONFIG, ETH_ADDRESS, -1)
