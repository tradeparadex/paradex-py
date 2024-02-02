from enum import IntEnum
from typing import Optional

from starknet_py.common import int_from_bytes, int_from_hex
from starknet_py.hash.address import compute_address
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.signer.stark_curve_signer import KeyPair

from paradex_py.account.starknet import Account as StarknetAccount
from paradex_py.account.utils import derive_stark_key, flatten_signature
from paradex_py.api.models import SystemConfig
from paradex_py.message.auth import build_auth_message
from paradex_py.message.onboarding import build_onboarding_message
from paradex_py.message.stark_key import build_stark_key_message


# For matching existing chainId type
class CustomStarknetChainId(IntEnum):
    PRIVATE_SN_MAINNET = int_from_bytes(b"PRIVATE_SN_PARACLEAR_MAINNET")
    PRIVATE_SN_TESTNET_MOCK_SEPOLIA = int_from_bytes(b"PRIVATE_SN_POTC_MOCK_SEPOLIA")
    PRIVATE_SN_TESTNET_SEPOLIA = int_from_bytes(b"PRIVATE_SN_POTC_SEPOLIA")


class ParadexAccount:
    address: int
    private_key: int
    public_key: int
    l1_address: str

    def __init__(
        self,
        config: SystemConfig,
        l1_private_key: Optional[int] = None,
        private_key: Optional[int] = None,
    ):
        self.config = config

        if l1_private_key is not None:
            stark_key_msg = build_stark_key_message(int(config.l1_chain_id))
            self.private_key = derive_stark_key(l1_private_key, stark_key_msg)
        elif private_key is not None:
            self.private_key = private_key
        else:
            raise ValueError("Paradex: Invalid private key")

        key_pair = KeyPair.from_private_key(int_from_hex(self.private_key))
        self.public_key = key_pair.public_key
        self.address = self._account_address()

        # Create starknet account
        client = FullNodeClient(node_url=config.starknet_fullnode_rpc_url)
        chain = CustomStarknetChainId(int_from_bytes(config.starknet_chain_id.encode()))
        self.starknet = StarknetAccount(
            client=client,
            address=self.address,
            key_pair=key_pair,
            chain=chain,
        )

    def _account_address(self) -> int:
        calldata = [
            int_from_hex(self.config.paraclear_account_hash),
            get_selector_from_name("initialize"),
            2,
            self.public_key,
            0,
        ]

        address = compute_address(
            class_hash=int_from_hex(self.config.paraclear_account_proxy_hash),
            constructor_calldata=calldata,
            salt=self.public_key,
        )
        return address

    def onboarding_signature(self) -> str:
        message = build_onboarding_message(int(self.config.l1_chain_id))
        sig = self.starknet.sign_message(message)
        return flatten_signature(sig)

    def auth_signature(self, timestamp: int, expiry: int) -> str:
        message = build_auth_message(int(self.config.l1_chain_id), timestamp, expiry)
        sig = self.starknet.sign_message(message)
        return flatten_signature(sig)
