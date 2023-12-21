import hashlib

from starknet_py.common import int_from_hex  # type: ignore[import-untyped]

SHA256_EC_MAX_DIGEST = 2**256


def _padded_hex(x: int) -> str:
    # Hex string should have an even
    # number of characters to convert to bytes.
    hex_str = hex(x)[2:]
    return hex_str if len(hex_str) % 2 == 0 else "0" + hex_str


def _indexed_sha256(seed: int, index: int) -> int:
    digest = hashlib.sha256(bytes.fromhex(_padded_hex(seed) + _padded_hex(index))).hexdigest()
    return int_from_hex(digest)


def grind_key(key_seed: int, key_value_limit: int) -> int:
    max_allowed_value = SHA256_EC_MAX_DIGEST - (SHA256_EC_MAX_DIGEST % key_value_limit)
    current_index = 0

    key = _indexed_sha256(seed=key_seed, index=current_index)
    while key >= max_allowed_value:
        current_index += 1
        key = _indexed_sha256(seed=key_seed, index=current_index)

    return key % key_value_limit
