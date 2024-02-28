import functools
import hashlib
from typing import List, Sequence

from eth_account.messages import encode_typed_data
from starknet_crypto_py import get_public_key as rs_get_public_key
from starknet_crypto_py import pedersen_hash as rs_pedersen_hash
from starknet_crypto_py import sign as rs_sign
from starknet_crypto_py import verify as rs_verify
from starknet_py.common import int_from_hex
from starknet_py.constants import EC_ORDER
from starknet_py.net.models.typed_data import TypedData
from web3.auto import w3

SHA256_EC_MAX_DIGEST = 2**256
DEFAULT_K = 32


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


def _get_private_key_from_eth_signature(eth_signature_hex: str) -> int:
    r = eth_signature_hex[2 : 64 + 2]
    return _grind_key(int_from_hex(r), EC_ORDER)


def derive_stark_key(l1_private_key: int, stark_key_msg: TypedData) -> int:
    message_signature = _sign_stark_key_message(stark_key_msg, l1_private_key)
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


def message_signature(msg_hash: int, priv_key: int) -> tuple[int, int]:
    """
    Signs the message with private key.
    """
    return rs_sign(private_key=priv_key, msg_hash=msg_hash, k=DEFAULT_K)


def verify_message_signature(msg_hash: int, signature: List[int], public_key: int) -> bool:
    """
    Verifies ECDSA signature of a given message hash with a given public key.
    Returns true if public_key signs the message.
    """
    sig_r, sig_s = signature
    sig_w = pow(sig_s, -1, EC_ORDER)
    return rs_verify(msg_hash=msg_hash, r=sig_r, s=sig_w, public_key=public_key)
