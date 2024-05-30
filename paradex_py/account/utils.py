import functools
import hashlib
from typing import List, Optional, Sequence

from eth_account.messages import SignableMessage, encode_typed_data
from ledgereth.accounts import find_account
from ledgereth.comms import init_dongle
from ledgereth.messages import sign_typed_data_draft
from starknet_crypto_py import get_public_key as rs_get_public_key
from starknet_crypto_py import pedersen_hash as rs_pedersen_hash
from starknet_crypto_py import sign as rs_sign
from starknet_crypto_py import verify as rs_verify
from starknet_py.common import int_from_hex
from starknet_py.constants import EC_ORDER
from starknet_py.net.models.typed_data import TypedData
from starkware.crypto.signature.signature import generate_k_rfc6979
from web3.auto import w3

SHA256_EC_MAX_DIGEST = 2**256


def _padded_hex(x: int) -> str:
    # Hex string should have an even
    # number of characters to convert to bytes.
    hex_str = hex(x)[2:]
    return hex_str if len(hex_str) % 2 == 0 else "0" + hex_str


def _indexed_sha256(seed: int, index: int) -> int:
    digest = hashlib.sha256(bytes.fromhex(_padded_hex(seed) + _padded_hex(index))).hexdigest()
    return int_from_hex(digest)


def _grind_key(key_seed: int, key_value_limit: int) -> int:
    max_allowed_value = SHA256_EC_MAX_DIGEST - (SHA256_EC_MAX_DIGEST % key_value_limit)
    current_index = 0

    key = _indexed_sha256(seed=key_seed, index=current_index)
    while key >= max_allowed_value:
        current_index += 1
        key = _indexed_sha256(seed=key_seed, index=current_index)

    return key % key_value_limit


def _sign_stark_key_message(stark_key_message, l1_private_key: int) -> str:
    encoded = encode_typed_data(full_message=stark_key_message)
    signed = w3.eth.account.sign_message(encoded, l1_private_key)
    return signed.signature.hex()


def _sign_stark_key_message_ledger(message: SignableMessage, eth_account_address: str) -> str:
    dongle = init_dongle()
    account = find_account(eth_account_address, dongle, count=10)
    if account is None:
        raise ValueError(f"Account {eth_account_address} not found on Ledger")
    # header/body is eth_account naming, presumably to be generic
    domain_hash = message.header
    message_hash = message.body
    signed = sign_typed_data_draft(
        domain_hash=domain_hash,
        message_hash=message_hash,
        sender_path=account.path,
        dongle=dongle,
    )
    return signed.signature


def _get_private_key_from_eth_signature(eth_signature_hex: str) -> int:
    r = eth_signature_hex[2 : 64 + 2]
    return _grind_key(int_from_hex(r), EC_ORDER)


def derive_stark_key(l1_private_key: int, stark_key_msg: TypedData) -> int:
    message_signature = _sign_stark_key_message(stark_key_msg, l1_private_key)
    l2_private_key = _get_private_key_from_eth_signature(message_signature)
    return l2_private_key


def derive_stark_key_from_ledger(eth_account_address: str, stark_key_msg: TypedData) -> int:
    signable_message = encode_typed_data(full_message=stark_key_msg)
    message_signature = _sign_stark_key_message_ledger(signable_message, eth_account_address)
    l2_private_key = _get_private_key_from_eth_signature(message_signature)
    return l2_private_key


def flatten_signature(sig: List[int]) -> str:
    return f'["{sig[0]}","{sig[1]}"]'


# ###
# Override functions in starknet_py.hash.utils that use cpp
# to use the starknet_crypto_py library
# ###


def private_to_stark_key(priv_key: int) -> int:
    """
    Deduces the public key given a private key.
    """
    return rs_get_public_key(priv_key)


def pedersen_hash(left: int, right: int) -> int:
    """
    One of two hash functions (along with _starknet_keccak) used throughout Starknet.
    """
    # return cpp_hash(left, right)
    return rs_pedersen_hash(left, right)


def compute_hash_on_elements(data: Sequence) -> int:
    """
    Computes a hash chain over the data, in the following order:
        h(h(h(h(0, data[0]), data[1]), ...), data[n-1]), n).

    The hash is initialized with 0 and ends with the data length appended.
    The length is appended in order to avoid collisions of the following kind:
    H([x,y,z]) = h(h(x,y),z) = H([w, z]) where w = h(x,y).
    """
    return functools.reduce(pedersen_hash, [*data, len(data)], 0)


def message_signature(msg_hash: int, priv_key: int, seed: Optional[int] = None) -> tuple[int, int]:
    """
    Signs the message with private key.
    """
    # k should be a strong cryptographical random
    # See: https://tools.ietf.org/html/rfc6979
    k = generate_k_rfc6979(msg_hash, priv_key, seed)
    return rs_sign(private_key=priv_key, msg_hash=msg_hash, k=k)


def verify_message_signature(msg_hash: int, signature: List[int], public_key: int) -> bool:
    """
    Verifies ECDSA signature of a given message hash with a given public key.
    Returns true if public_key signs the message.
    """
    sig_r, sig_s = signature
    sig_w = pow(sig_s, -1, EC_ORDER)
    return rs_verify(msg_hash=msg_hash, r=sig_r, s=sig_w, public_key=public_key)
