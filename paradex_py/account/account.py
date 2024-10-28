import logging
import time
from decimal import Decimal
from enum import IntEnum
from typing import Optional

from starknet_py.common import int_from_bytes, int_from_hex
from starknet_py.hash.address import compute_address
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.signer.stark_curve_signer import KeyPair

from paradex_py.account.starknet import Account as StarknetAccount
from paradex_py.account.utils import derive_stark_key, derive_stark_key_from_ledger, flatten_signature
from paradex_py.api.models import SystemConfig
from paradex_py.common.order import Order
from paradex_py.message.auth import build_auth_message
from paradex_py.message.onboarding import build_onboarding_message
from paradex_py.message.order import build_order_message
from paradex_py.message.stark_key import build_stark_key_message
from paradex_py.utils import raise_value_error


# For matching existing chainId type
class CustomStarknetChainId(IntEnum):
    PRIVATE_SN_MAINNET = int_from_bytes(b"PRIVATE_SN_PARACLEAR_MAINNET")
    PRIVATE_SN_TESTNET_MOCK_SEPOLIA = int_from_bytes(b"PRIVATE_SN_POTC_MOCK_SEPOLIA")
    PRIVATE_SN_TESTNET_SEPOLIA = int_from_bytes(b"PRIVATE_SN_POTC_SEPOLIA")


class ParadexAccount:
    """Class to generate and manage Paradex account.
        Initialized along with `Paradex` class.

    Args:
        config (SystemConfig): SystemConfig
        l1_address (str): Ethereum address
        l1_private_key (Optional[str], optional): Ethereum private key. Defaults to None.
        l2_private_key (Optional[str], optional): Paradex private key. Defaults to None.

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> paradex = Paradex(env=Environment.TESTNET, l1_address="0x...", l1_private_key="0x...")
        >>> paradex.account.l2_address # 0x...
        >>> paradex.account.l2_public_key # 0x...
        >>> paradex.account.l2_private_key # 0x...
    """

    def __init__(
        self,
        config: SystemConfig,
        l1_address: str,
        l1_private_key_from_ledger: Optional[bool] = False,
        l1_private_key: Optional[str] = None,
        l2_private_key: Optional[str] = None,
    ):
        self.config = config

        if l1_address is None:
            return raise_value_error("Paradex: Provide Ethereum address")
        self.l1_address = l1_address

        if l1_private_key is not None:
            self.l1_private_key = int_from_hex(l1_private_key)
            stark_key_msg = build_stark_key_message(int(config.l1_chain_id))
            self.l2_private_key = derive_stark_key(self.l1_private_key, stark_key_msg)
        elif l1_private_key_from_ledger:
            stark_key_msg = build_stark_key_message(int(config.l1_chain_id))
            self.l2_private_key = derive_stark_key_from_ledger(l1_address, stark_key_msg)
        elif l2_private_key is not None:
            self.l2_private_key = int_from_hex(l2_private_key)
        else:
            return raise_value_error("Paradex: Provide Ethereum or Paradex private key")

        key_pair = KeyPair.from_private_key(self.l2_private_key)
        self.l2_public_key = key_pair.public_key
        self.l2_address = self._account_address()

        # Create starknet account
        client = FullNodeClient(node_url=config.starknet_fullnode_rpc_url)
        self.l2_chain_id = int_from_bytes(config.starknet_chain_id.encode())
        self.starknet = StarknetAccount(
            client=client,
            address=self.l2_address,
            key_pair=key_pair,
            chain=CustomStarknetChainId(self.l2_chain_id),
        )

    def _account_address(self) -> int:
        calldata = [
            int_from_hex(self.config.paraclear_account_hash),
            get_selector_from_name("initialize"),
            2,
            self.l2_public_key,
            0,
        ]

        address = compute_address(
            class_hash=int_from_hex(self.config.paraclear_account_proxy_hash),
            constructor_calldata=calldata,
            salt=self.l2_public_key,
        )
        return address

    def set_jwt_token(self, jwt_token: str) -> None:
        self.jwt_token = jwt_token

    def onboarding_signature(self) -> str:
        if self.config is None:
            return raise_value_error("Paradex: System config not loaded")
        message = build_onboarding_message(self.l2_chain_id)
        sig = self.starknet.sign_message(message)
        return flatten_signature(sig)

    def onboarding_headers(self) -> dict:
        return {
            "PARADEX-ETHEREUM-ACCOUNT": self.l1_address,
            "PARADEX-STARKNET-ACCOUNT": hex(self.l2_address),
            "PARADEX-STARKNET-SIGNATURE": self.onboarding_signature(),
        }

    def auth_signature(self, timestamp: int, expiry: int) -> str:
        message = build_auth_message(self.l2_chain_id, timestamp, expiry)
        sig = self.starknet.sign_message(message)
        return flatten_signature(sig)

    def auth_headers(self) -> dict:
        timestamp = int(time.time())
        expiry = timestamp + 24 * 60 * 60
        return {
            "PARADEX-STARKNET-ACCOUNT": hex(self.l2_address),
            "PARADEX-STARKNET-SIGNATURE": self.auth_signature(timestamp, expiry),
            "PARADEX-TIMESTAMP": str(timestamp),
            "PARADEX-SIGNATURE-EXPIRATION": str(expiry),
        }

    def sign_order(self, order: Order) -> str:
        sig = self.starknet.sign_message(build_order_message(self.l2_chain_id, order))
        return flatten_signature(sig)

    async def transfer_on_l2(self, target_l2_address: str, amount_decimal: Decimal):
        try:
            # Load contracts
            paraclear_address = int_from_hex(self.config.paraclear_address)
            usdc_address = int_from_hex(self.config.bridged_tokens[0].l2_token_address)
            paraclear_contract = await self.starknet.load_contract(paraclear_address)
            account_contract = await self.starknet.load_contract(self.l2_address)

            usdc_decimals = self.config.bridged_tokens[0].decimals
            paraclear_decimals = self.config.paraclear_decimals

            # Get token asset balance
            token_asset_balance = await paraclear_contract.functions["getTokenAssetBalance"].call(
                account=self.l2_address, token_address=usdc_address
            )
            logging.info(f"USDC balance on Paraclear: {token_asset_balance.balance / 10**paraclear_decimals}")

            # Calculate amounts
            amount_paraclear = int(amount_decimal * 10**paraclear_decimals)
            amount_bridge = int(amount_decimal * 10**usdc_decimals)
            logging.info(f"Amount to withdraw from Paraclear: {amount_paraclear}")
            logging.info(f"Amount to transfer to {target_l2_address}: {amount_bridge}")

            # Prepare calls
            calls = [
                paraclear_contract.functions["transfer"].prepare_invoke_v1(
                    recipient=int_from_hex(target_l2_address),
                    token_address=usdc_address,
                    amount=amount_paraclear,
                ),
            ]

            # Check if multisig is required
            need_multisig = await self.starknet.check_multisig_required(account_contract)

            # Prepare and send transaction
            func_name = "transferOnL2"
            prepared_invoke = await self.starknet.prepare_invoke(calls=calls)
            await self.starknet.process_invoke(account_contract, need_multisig, prepared_invoke, func_name)

        except Exception as e:
            logging.error(f"Error during transfer_on_l2: {e}")
            # Re-raise the exception to handle it upstream if necessary
            raise
