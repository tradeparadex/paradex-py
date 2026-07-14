"""Tests for the EIP-191 signer used by Argent v0.5.0 (Eip191) accounts."""

from unittest.mock import MagicMock

from eth_account import Account as EthAccount
from eth_account.messages import encode_defunct

from paradex_py.account.eip191_signer import (
    Eip191Signer,
    sign_hash_eip191,
)

# Anvil dev key #1 — test fixture only, never funded.
EVM_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
EVM_ADDR = EthAccount.from_key(EVM_KEY).address
CHAIN_ID = 0x534E5F5345504F4C4941  # arbitrary felt chain id for tests


def _recover(sig, message_hash):
    """Recover the signer address from a serialized SignerSignature span."""
    _count, _variant, _eth, r_lo, r_hi, s_lo, s_hi, y = sig
    r = r_lo + (r_hi << 128)
    s = s_lo + (s_hi << 128)
    digest = message_hash.to_bytes(32, "big")
    return EthAccount.recover_message(encode_defunct(primitive=digest), vrs=(y + 27, r, s))


def test_sign_hash_envelope_and_variant():
    sig = sign_hash_eip191(0xABCDEF, EVM_KEY)
    assert sig[0] == 1  # owner-only count
    assert sig[1] == 3  # SignerSignature::Eip191 variant
    assert sig[2] == int(EVM_ADDR, 16)  # Eip191Signer.eth_address
    assert len(sig) == 8  # count, variant, eth, r.lo, r.hi, s.lo, s.hi, y_parity


def test_sign_hash_recovers_to_owner_address():
    """The signature must recover to the account's ETH address — exactly what
    Argent's on-chain secp256k1_verify(calculate_eip191_hash(...)) checks."""
    h = 0x123456789ABCDEF
    sig = sign_hash_eip191(h, EVM_KEY)
    assert _recover(sig, h) == EVM_ADDR


def test_u256_split_roundtrips():
    # r/s are split into u256 {low, high}; recompose must equal the original.
    big_hash = (1 << 250) - 7
    sig = sign_hash_eip191(big_hash, EVM_KEY)
    r = sig[3] + (sig[4] << 128)
    s = sig[5] + (sig[6] << 128)
    assert 0 < r < (1 << 256)
    assert 0 < s < (1 << 256)
    assert _recover(sig, big_hash) == EVM_ADDR


def test_signer_public_key_is_eth_address():
    signer = Eip191Signer(EVM_KEY, CHAIN_ID)
    assert signer.public_key == int(EVM_ADDR, 16)


def test_signer_sign_transaction_hashes_tx():
    signer = Eip191Signer(EVM_KEY, CHAIN_ID)
    tx = MagicMock()
    tx.calculate_hash.return_value = 0xDEADBEEF
    sig = signer.sign_transaction(tx)
    tx.calculate_hash.assert_called_once_with(CHAIN_ID)
    assert _recover(sig, 0xDEADBEEF) == EVM_ADDR


def test_signer_sign_message_hashes_typed_data():
    signer = Eip191Signer(EVM_KEY, CHAIN_ID)
    td = MagicMock()
    td.message_hash.return_value = 0xC0FFEE
    sig = signer.sign_message(td, account_address=0x123)
    td.message_hash.assert_called_once_with(0x123)
    assert _recover(sig, 0xC0FFEE) == EVM_ADDR
