from eth_account.messages import encode_typed_data
from starknet_py.common import int_from_hex  # type: ignore[import-untyped]
from starknet_py.hash.address import compute_address  # type: ignore[import-untyped]
from starknet_py.hash.selector import get_selector_from_name  # type: ignore[import-untyped]
from starknet_py.net.signer.stark_curve_signer import KeyPair  # type: ignore[import-untyped]
from starkware.crypto.signature.signature import EC_ORDER  # type: ignore[import-untyped]
from web3.auto import w3

from paradex_py.account.utils import grind_key
from paradex_py.api.models import SystemConfig
from paradex_py.message.stark_key import build_stark_key_message


class ParadexAccount:
    def __init__(self, config: SystemConfig, eth_private_key: str):
        self.config = config
        self.eth_private_key = eth_private_key

        private_key = self._derive_stark_key()
        key_pair = KeyPair.from_private_key(private_key)

        self.public_key = hex(key_pair.public_key)
        self.private_key = hex(key_pair.private_key)
        self.address = self._get_account_address(self.public_key)

    def _sign_stark_key_message(self, stark_key_message) -> str:
        encoded = encode_typed_data(full_message=stark_key_message)
        signed = w3.eth.account.sign_message(encoded, int_from_hex(self.eth_private_key))
        return signed.signature.hex()

    def _get_private_key_from_eth_signature(self, eth_signature_hex: str) -> int:
        r = eth_signature_hex[2 : 64 + 2]
        return grind_key(int_from_hex(r), EC_ORDER)

    def _derive_stark_key(self) -> int:
        eth_chain_id = int(self.config.l1_chain_id)
        stark_key_msg = build_stark_key_message(eth_chain_id)
        message_signature = self._sign_stark_key_message(stark_key_msg)
        private_key = self._get_private_key_from_eth_signature(message_signature)
        return private_key

    def _get_account_address(self, public_key: str) -> str:
        calldata = [
            int_from_hex(self.config.paraclear_account_hash),
            get_selector_from_name("initialize"),
            2,
            int_from_hex(public_key),
            0,
        ]

        address = compute_address(
            class_hash=int_from_hex(self.config.paraclear_account_proxy_hash),
            constructor_calldata=calldata,
            salt=int_from_hex(public_key),
        )
        return hex(address)
