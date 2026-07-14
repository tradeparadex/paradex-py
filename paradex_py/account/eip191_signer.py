"""EIP-191 signer for Argent v0.5.0 (Eip191) Paradex accounts.

An EVM-onboarded Paradex account is an Argent v0.5.0 account whose owner is an
Ethereum (secp256k1) key, validated on-chain via EIP-191 ``personal_sign``.
This signer plugs into ``starknet_py``'s ``Account`` in place of the stark-curve
``KeyPair`` so the SDK can sign StarkNet transactions (and SNIP-12 messages) for
such an account.

How Argent validates an EIP-191 signature (argent-contracts-starknet v0.5.0,
``src/signer/eip191.cairo`` ``calculate_eip191_hash`` /
``is_valid_eip191_signature``):

    secp256k1_verify(
        keccak256("\\x19Ethereum Signed Message:\\n32" || felt_to_be32(tx_hash)),
        eth_address,
        signature,
    )

i.e. the StarkNet transaction hash (a felt) is right-padded to 32 bytes, run
through the standard EIP-191 personal_sign envelope, and signed with secp256k1.
``eth_account.sign_message(encode_defunct(primitive=<32 bytes>))`` produces
exactly that.

The signature is serialized as Argent's ``SignerSignature`` span
(``src/signer/signer_signature.cairo``), wrapped in the account's
``parse_account_signature`` ``[count, ...]`` envelope::

    [1, 3, eth_address, r.low, r.high, s.low, s.high, y_parity]
     │  │  │            └──────── Secp256Signature {r:u256, s:u256, y_parity} ───────┘
     │  │  └─ Eip191Signer { eth_address }
     │  └─ SignerSignature::Eip191 variant index
     └─ signature count = 1 (owner only; no guardian)
"""

from eth_account import Account as EthAccount
from eth_account.messages import encode_defunct
from starknet_py.net.models import AccountTransaction
from starknet_py.net.signer import BaseSigner
from starknet_py.utils.typed_data import TypedData

# SignerSignature::Eip191 enum variant index (signer_signature.cairo).
_EIP191_SIGNER_VARIANT = 3
# parse_account_signature envelope: 1 signer signature (owner only, no guardian).
_OWNER_ONLY_COUNT = 1
_U128_MASK = (1 << 128) - 1


def _u256_low_high(value: int) -> tuple[int, int]:
    return value & _U128_MASK, value >> 128


def _serialize_eip191_signer_signature(eth_address: int, r: int, s: int, y_parity: int) -> list[int]:
    """Serialize the owner ``SignerSignature`` span for an Eip191 account."""
    r_low, r_high = _u256_low_high(r)
    s_low, s_high = _u256_low_high(s)
    return [
        _OWNER_ONLY_COUNT,
        _EIP191_SIGNER_VARIANT,
        eth_address,
        r_low,
        r_high,
        s_low,
        s_high,
        y_parity,
    ]


def sign_hash_eip191(message_hash: int, eth_private_key: str) -> list[int]:
    """Sign a StarkNet felt hash for an Argent Eip191 account.

    Returns the serialized ``SignerSignature`` span (with the owner-only count
    prefix) ready to use as a transaction/message signature.
    """
    digest = message_hash.to_bytes(32, "big")
    signed = EthAccount.sign_message(encode_defunct(primitive=digest), eth_private_key)
    eth_address = int(EthAccount.from_key(eth_private_key).address, 16)
    # eth_account returns v in {27, 28}; Argent's Secp256Signature wants y_parity {0, 1}.
    y_parity = signed.v - 27
    return _serialize_eip191_signer_signature(eth_address, signed.r, signed.s, y_parity)


class Eip191Signer(BaseSigner):
    """A ``starknet_py`` signer that signs with an Ethereum key via EIP-191.

    Drop-in for the stark-curve ``KeyPair`` when the Paradex account is an
    Argent v0.5.0 Eip191 account. ``public_key`` returns the Ethereum address as
    an int (the account's on-chain owner identifier), not a stark pubkey.
    """

    def __init__(self, eth_private_key: str, chain_id: int):
        # chain_id is the Paradex appchain id (a felt); accepted as a plain int
        # so the custom CustomStarknetChainId enum can be passed through.
        self._eth_private_key = eth_private_key
        self._eth_address = int(EthAccount.from_key(eth_private_key).address, 16)
        self.chain_id = chain_id

    @property
    def private_key(self) -> int:
        return int(self._eth_private_key, 16) if isinstance(self._eth_private_key, str) else int(self._eth_private_key)

    @property
    def public_key(self) -> int:
        # The Eip191 account's owner is identified by its Ethereum address.
        return self._eth_address

    def sign_transaction(self, transaction: AccountTransaction) -> list[int]:
        tx_hash = transaction.calculate_hash(self.chain_id)
        return sign_hash_eip191(tx_hash, self._eth_private_key)

    def sign_message(self, typed_data: TypedData, account_address: int) -> list[int]:
        msg_hash = typed_data.message_hash(account_address)
        return sign_hash_eip191(msg_hash, self._eth_private_key)
