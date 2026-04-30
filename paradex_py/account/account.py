import json
import logging
import time
import types
from decimal import Decimal
from enum import IntEnum

from httpx import AsyncClient
from starknet_py.common import int_from_bytes, int_from_hex
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.http_client import HttpMethod

from paradex_py.account.starknet import Account as StarknetAccount
from paradex_py.account.utils import derive_l2_address_starknet, flatten_signature, resolve_l2_keypair
from paradex_py.api.generated.responses import BlockTradeDetailFullResponse, BlockTradeSignature, SignatureType
from paradex_py.api.models import SystemConfig
from paradex_py.common.order import Order
from paradex_py.message.auth import build_auth_message, build_fullnode_message
from paradex_py.message.block_trades import (
    BlockTrade,
    BlockTradeOffer,
    block_trade_from_response,
    build_block_trade_message,
    build_block_trade_offer_message,
)
from paradex_py.message.onboarding import build_onboarding_message
from paradex_py.message.order import build_modify_order_message, build_order_message
from paradex_py.utils import raise_value_error, time_now_milli_secs

FULLNODE_SIGNATURE_VERSION = "1.0.0"


# For matching existing chainId type
class CustomStarknetChainId(IntEnum):
    PRIVATE_SN_MAINNET = int_from_bytes(b"PRIVATE_SN_PARACLEAR_MAINNET")
    PRIVATE_SN_TESTNET_MOCK_SEPOLIA = int_from_bytes(b"PRIVATE_SN_POTC_MOCK_SEPOLIA")
    PRIVATE_SN_TESTNET_SEPOLIA = int_from_bytes(b"PRIVATE_SN_POTC_SEPOLIA")
    PRIVATE_SN_PARACLEAR_TESTNET = int_from_bytes(b"PRIVATE_SN_PARACLEAR_TESTNET")


class ParadexAccount:
    """Class to generate and manage Paradex account.
        Initialized along with `Paradex` class.

    Args:
        config (SystemConfig): SystemConfig
        l1_address (str): Ethereum address
        l1_private_key (Optional[str], optional): Ethereum private key. Defaults to None.
        l2_private_key (Optional[str], optional): Paradex private key. Defaults to None.
        rpc_version (Optional[str], optional): RPC version (e.g., "v0_9"). If provided, constructs URL as {base_url}/rpc/{rpc_version}. Defaults to None.

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> paradex = Paradex(env=Environment.TESTNET, l1_address="0x...", l1_private_key="0x...")
        >>> paradex.account.l2_address
        >>> paradex.account.l2_public_key
        >>> paradex.account.l2_private_key
    """

    def __init__(
        self,
        config: SystemConfig,
        l1_address: str,
        l1_private_key_from_ledger: bool | None = False,
        l1_private_key: str | None = None,
        l2_private_key: str | None = None,
        rpc_version: str | None = None,
        l2_address: str | None = None,
        is_onboarded: bool | None = None,
    ):
        self.config = config

        if l1_address is None:
            raise_value_error("Paradex: Provide Ethereum address")
        self.l1_address = l1_address

        if l1_private_key is not None:
            self.l1_private_key = int_from_hex(l1_private_key)

        key_pair = resolve_l2_keypair(
            config=config,
            l1_address=l1_address,
            l1_private_key=l1_private_key,
            l1_private_key_from_ledger=bool(l1_private_key_from_ledger),
            l2_private_key=l2_private_key,
        )
        self.l2_private_key = key_pair.private_key
        self.l2_public_key = key_pair.public_key
        if l2_address is not None:
            self.l2_address = int_from_hex(l2_address)
        else:
            # Backwards-compat fallback: callers that construct ParadexAccount directly
            # (without going through the Paradex orchestrator) still get their address
            # derived for them. The Paradex orchestrator always resolves the address
            # outside via the same helper, so this branch is only hit for direct
            # construction and is intended for eventual removal.
            self.l2_address = derive_l2_address_starknet(config, self.l2_public_key)
        self.is_onboarded = is_onboarded

        # Create starknet account
        if rpc_version:
            node_url = f"{config.starknet_fullnode_rpc_base_url}/rpc/{rpc_version}"
        else:
            node_url = config.starknet_fullnode_rpc_url
        client = FullNodeClient(node_url=node_url)
        self.l2_chain_id = int_from_bytes(config.starknet_chain_id.encode())
        self.starknet = StarknetAccount(
            client=client,
            address=self.l2_address,
            key_pair=key_pair,
            chain=CustomStarknetChainId(self.l2_chain_id),  # type: ignore[arg-type]
        )

        # Apply the fullnode headers patch
        self._apply_fullnode_headers_patch(client)

    # Monkey patch of _make_request method of starknet.py client
    # to inject http headers requested by Paradex full node:
    # - PARADEX-STARKNET-ACCOUNT: account address signing the request
    # - PARADEX-STARKNET-SIGNATURE: signature of the request
    # - PARADEX-STARKNET-SIGNATURE-TIMESTAMP: timestamp of the signature
    # - PARADEX-STARKNET-SIGNATURE-VERSION: version of the signature
    def _apply_fullnode_headers_patch(self, client):
        """Apply the fullnode headers patch for Paradex-specific headers."""
        current_self = self

        async def monkey_patched_make_request(
            self,
            session: AsyncClient,
            address: str,
            http_method: HttpMethod,
            params: dict,
            payload: dict,
        ) -> dict:
            json_payload = json.dumps(payload)
            headers = current_self.fullnode_request_headers(
                current_self.starknet, current_self.l2_chain_id, json_payload
            )

            response = await session.request(
                method=http_method.value, url=address, params=params, json=payload, headers=headers
            )
            await self.handle_request_error(response)
            return await response.json()

        client._client._make_request = types.MethodType(monkey_patched_make_request, client._client)

    def set_jwt_token(self, jwt_token: str) -> None:
        self.jwt_token = jwt_token

    def onboarding_signature(self) -> str:
        if self.config is None:
            raise_value_error("Paradex: System config not loaded")
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

    def fullnode_request_headers(self, account: StarknetAccount, chain_id: int, json_payload: str):
        signature_timestamp = int(time.time())
        account_address = hex(account.address)
        message = build_fullnode_message(
            chain_id,
            account_address,
            json_payload,
            signature_timestamp,
            FULLNODE_SIGNATURE_VERSION,
        )
        sig = account.sign_message(message)
        return {
            "Content-Type": "application/json",
            "PARADEX-STARKNET-ACCOUNT": account_address,
            "PARADEX-STARKNET-SIGNATURE": f'["{sig[0]}","{sig[1]}"]',
            "PARADEX-STARKNET-SIGNATURE-TIMESTAMP": str(signature_timestamp),
            "PARADEX-STARKNET-SIGNATURE-VERSION": FULLNODE_SIGNATURE_VERSION,
        }

    def sign_order(self, order: Order) -> str:
        if order.id:
            sig = self.starknet.sign_message(build_modify_order_message(self.l2_chain_id, order))
        else:
            sig = self.starknet.sign_message(build_order_message(self.l2_chain_id, order))
        return flatten_signature(sig)

    def sign_block_trade(self, block_trade_data: BlockTrade) -> str:
        """Sign a BlockTrade and return the flattened "[r,s]" signature string.

        Lower-level entrypoint. Most callers should use `build_block_trade_signature` which
        returns a complete `BlockTradeSignature` with metadata fields populated.
        """
        typed_data = build_block_trade_message(self.l2_chain_id, block_trade_data)
        sig = self.starknet.sign_message(typed_data)
        return flatten_signature(sig)

    def sign_block_trade_offer(self, offer: BlockTradeOffer) -> str:
        """Sign a BlockTradeOffer and return the flattened "[r,s]" signature string.

        Lower-level entrypoint. Most callers should use `build_block_trade_offer_signature`
        which returns a complete `BlockTradeSignature` with metadata fields populated.
        """
        typed_data = build_block_trade_offer_message(self.l2_chain_id, offer)
        sig = self.starknet.sign_message(typed_data)
        return flatten_signature(sig)

    def _build_block_trade_signature_dto(self, signature_data: str, nonce: str, expiration: int) -> BlockTradeSignature:
        """Construct the BlockTradeSignature with the metadata fields the server
        expects. Single source of truth to build_block_trade_signature
        and build_block_trade_offer_signature stay aligned if the schema evolves
        (e.g. a new field added to BlockTradeSignature must not be forgotten in one path).
        """
        return BlockTradeSignature(
            nonce=nonce,
            signature_data=signature_data,
            signature_expiration=expiration,
            signature_timestamp=time_now_milli_secs(),
            signature_type=SignatureType.starknet,
            signer_account=hex(self.l2_address),
            signer_public_key=hex(self.l2_public_key),
        )

    def build_block_trade_offer_signature(self, offer: BlockTradeOffer) -> BlockTradeSignature:
        """Sign a BlockTradeOffer and return the full `BlockTradeSignature`.

        For the offerer to attach to a `BlockOfferRequest.signature`. Auto-populates
        `signer_public_key` with the account's signing key (main or active subkey).
        """
        return self._build_block_trade_signature_dto(self.sign_block_trade_offer(offer), offer.nonce, offer.expiration)

    def build_block_trade_signature(self, block_trade: BlockTrade) -> BlockTradeSignature:
        """Sign a BlockTrade and return the full `BlockTradeSignature` ready to attach to a
        BlockTradeRequest / BlockOfferRequest / BlockExecuteRequest.

        Auto-populates `signer_public_key` with the account's signing key (main account or
        subkey, depending on which account class instantiated this). The server uses this
        hint to look up the right pubkey for verification.
        """
        return self._build_block_trade_signature_dto(
            self.sign_block_trade(block_trade), block_trade.nonce, block_trade.expiration
        )

    def build_executor_signature_for_block(
        self,
        block_response: BlockTradeDetailFullResponse,
        nonce: str | None = None,
        expiration_minutes: int = 5,
    ) -> dict[str, BlockTradeSignature]:
        """Build the executor-side signature for a DIRECT block trade execute.

        Pass the `BlockTradeDetailFullResponse` returned by `get_block_trade()`. Returns a
        dict ready to assign to `BlockExecuteRequest.signatures` — keyed by block_id with
        a single entry. The executor (this account) signs the merkle root of the block's
        trades using a fresh nonce/expiration.

        Use this for direct block trades. For offer-based blocks, use
        `build_executor_signatures_for_offers` instead.
        """
        if not block_response.block_id:
            raise ValueError("block_response.block_id is required")
        nonce, expiration = self._executor_nonce_expiration(nonce, expiration_minutes)
        bt = block_trade_from_response(block_response, nonce, expiration)
        return {block_response.block_id: self.build_block_trade_signature(bt)}

    def build_executor_signatures_for_offers(
        self,
        offer_responses: list[BlockTradeDetailFullResponse],
        nonce: str | None = None,
        expiration_minutes: int = 5,
    ) -> dict[str, BlockTradeSignature]:
        """Build executor-side signatures for an OFFER-BASED block trade execute.

        Pass a list of `BlockTradeDetailFullResponse` objects (one per offer being
        accepted, fetched via `get_block_trade_offer()`). Returns a dict keyed by
        offer_id with one signature per offer — each commits the executor (this account)
        to that specific offer's trade fills.
        """
        nonce, expiration = self._executor_nonce_expiration(nonce, expiration_minutes)
        sigs: dict[str, BlockTradeSignature] = {}
        for offer in offer_responses:
            if not offer.block_id:
                raise ValueError("each offer_response must have block_id set")
            bt = block_trade_from_response(offer, nonce, expiration)
            sigs[offer.block_id] = self.build_block_trade_signature(bt)
        return sigs

    def _executor_nonce_expiration(self, nonce: str | None, expiration_minutes: int) -> tuple[str, int]:
        if nonce is None:
            nonce = str(time.time_ns())
        expiration = time_now_milli_secs() + expiration_minutes * 60 * 1000
        return nonce, expiration

    async def transfer_on_l2(self, target_l2_address: str, amount_decimal: Decimal):
        try:
            # Load contracts
            paraclear_address = int_from_hex(self.config.paraclear_address)
            usdc_address = int_from_hex(self.config.bridged_tokens[0].l2_token_address)
            paraclear_contract = await self.starknet.load_contract(paraclear_address, is_cairo0_contract=False)
            account_contract = await self.starknet.load_contract(self.l2_address, is_cairo0_contract=True)

            paraclear_decimals = self.config.paraclear_decimals

            # Get token asset balance
            token_asset_balance = await paraclear_contract.functions["getTokenAssetBalance"].call(
                account=self.l2_address, token_address=usdc_address
            )
            logging.info(f"USDC balance on Paraclear: {token_asset_balance[0] / 10**paraclear_decimals}")

            # Calculate amounts
            amount_paraclear = int(amount_decimal * 10**paraclear_decimals)
            logging.info(f"Amount to transfer to {target_l2_address}: {amount_paraclear}")

            # Prepare calls
            calls = [
                paraclear_contract.functions["transfer"].prepare_invoke_v3(
                    recipient=int_from_hex(target_l2_address),
                    token_address=usdc_address,
                    amount=amount_paraclear,
                ),
            ]

            # Check if multisig is required
            need_multisig = await self.starknet.check_multisig_required(account_contract)

            # Prepare and send transaction
            func_name = "transferOnL2"
            prepared_invoke = await self.starknet.prepare_invoke(calls=calls, auto_estimate=True)
            await self.starknet.process_invoke(account_contract, need_multisig, prepared_invoke, func_name)

        except Exception as e:
            logging.exception(f"Error during transfer_on_l2: {e}")
            # Re-raise the exception to handle it upstream if necessary
            raise
