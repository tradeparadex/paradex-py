import dataclasses
import logging
import re
from typing import Callable, List, Optional, Union

import marshmallow_dataclass
from starknet_py.common import create_compiled_contract
from starknet_py.constants import RPC_CONTRACT_ERROR
from starknet_py.contract import Contract, DeclareResult, DeployResult, InvokeResult
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.client import Client
from starknet_py.net.client_errors import ClientError
from starknet_py.net.client_models import Call, Calls, SentTransactionResponse
from starknet_py.net.models import Address, AddressRepresentation, DeclareV1, InvokeV1, StarknetChainId
from starknet_py.net.signer import BaseSigner
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.net.udc_deployer.deployer import Deployer
from starknet_py.proxy.contract_abi_resolver import ProxyConfig
from starknet_py.proxy.proxy_check import ArgentProxyCheck, OpenZeppelinProxyCheck, ProxyCheck

from paradex_py.utils import random_max_fee

from .typed_data import TypedData
from .utils import message_signature, typed_data_to_message_hash


class Account(StarknetAccount):
    def __init__(
        self,
        *,
        address: AddressRepresentation,
        client: Client,
        signer: Optional[BaseSigner] = None,
        key_pair: Optional[KeyPair] = None,
        chain: Optional[StarknetChainId] = None,
    ):
        super().__init__(address=address, client=client, signer=signer, key_pair=key_pair, chain=chain)

    def _add_signature(self, invoke: InvokeV1, signature: list[int]) -> InvokeV1:
        return dataclasses.replace(invoke, signature=signature)

    async def prepare_invoke(
        self,
        calls: Calls,
        max_fee: Optional[int] = None,
        nonce: Optional[int] = None,
    ) -> InvokeV1:
        if max_fee is None:
            max_fee = random_max_fee()
        return await self._prepare_invoke(calls, max_fee=max_fee, nonce=nonce)

    async def prepare_declare(self, compiled_contract: str, max_fee: int) -> DeclareV1:
        declare_tx = await self._make_declare_v1_transaction(compiled_contract)
        declare_tx = dataclasses.replace(declare_tx, max_fee=max_fee)
        return declare_tx

    async def prepare_deploy(
        self,
        declare_result: DeclareResult,
        deployer_address: int,
        constructor_args: Optional[Union[list, dict]] = None,
        salt: Optional[int] = None,
        unique: bool = True,
        max_fee: Optional[int] = None,
    ) -> tuple[InvokeV1, Contract]:
        if max_fee is None:
            max_fee = random_max_fee()
        abi = create_compiled_contract(compiled_contract=declare_result.compiled_contract).abi
        deployer = Deployer(
            deployer_address=deployer_address,
            account_address=self.address if unique else None,
        )
        deploy_call, address = deployer.create_contract_deployment(
            class_hash=declare_result.class_hash,
            salt=salt,
            abi=abi,
            calldata=constructor_args,
            cairo_version=self.cairo_version,
        )
        contract = Contract(
            provider=self,
            address=address,
            abi=abi,
            cairo_version=self.cairo_version,
        )

        invoke_tx = await self._prepare_invoke(deploy_call, max_fee=max_fee)
        return invoke_tx, contract

    async def send_transaction(
        self,
        prepared_invoke: InvokeV1,
        signature: list[int],
    ) -> SentTransactionResponse:
        signed_invoke = self._add_signature(prepared_invoke, signature)
        return await self.client.send_transaction(signed_invoke)

    async def invoke(
        self,
        contract: Contract,
        prepared_invoke: InvokeV1,
        signature: list[int],
    ) -> InvokeResult:
        invoke_transaction = self._add_signature(prepared_invoke, signature)
        res = await self.client.send_transaction(invoke_transaction)

        invoke_result = InvokeResult(
            hash=res.transaction_hash,
            _client=self.client,
            contract=contract.data,
            invoke_transaction=invoke_transaction,
        )
        return invoke_result

    async def declare(
        self,
        compiled_contract: str,
        prepared_invoke: InvokeV1,
        signature: list[int],
    ) -> DeclareResult:
        res = await self.send_transaction(prepared_invoke=prepared_invoke, signature=signature)

        declare_result = DeclareResult(
            hash=res.transaction_hash,
            _client=self.client,
            class_hash=res.class_hash,
            _account=self,
            compiled_contract=compiled_contract,
            _cairo_version=self.cairo_version,
        )
        return declare_result

    async def deploy(
        self,
        contract: Contract,
        prepared_invoke: InvokeV1,
        signature: list[int],
    ) -> DeployResult:
        res = await self.send_transaction(prepared_invoke=prepared_invoke, signature=signature)

        deploy_result = DeployResult(
            hash=res.transaction_hash,
            _client=self.client,
            deployed_contract=contract,
        )

        return deploy_result

    async def load_contract(self, address: AddressRepresentation) -> Contract:
        try:
            contract = await Contract.from_address(address=address, provider=self, proxy_config=get_proxy_config())
        except Exception as e:
            logging.error(f"Error loading contract at address {hex(address)}: {e}")
            raise
        else:
            return contract

    async def check_multisig_required(self, contract: Contract) -> bool:
        try:
            get_signer_call = await contract.functions["getSigner"].call()
            current_signer = hex(get_signer_call.signer)
            logging.info(f"Current signer: {current_signer}")

            get_guardian_call = await contract.functions["getGuardian"].call()
            current_guardian = hex(get_guardian_call.guardian)
            logging.info(f"Current guardian: {current_guardian}")

            get_guardian_backup_call = await contract.functions["getGuardianBackup"].call()
            current_guardian_backup = hex(get_guardian_backup_call.guardianBackup)
            logging.info(f"Current guardian backup: {current_guardian_backup}")

            need_multisig = current_guardian != "0x0" or current_guardian_backup != "0x0"
        except Exception as e:
            logging.error(f"Error checking multisig requirement: {e}")
            raise
        else:
            return need_multisig

    async def process_invoke(
        self,
        contract: Contract,
        need_multisig: bool,
        prepared_invoke: InvokeV1,
        func_name: str,
    ):
        try:
            if not need_multisig:
                # Sign and send the transaction
                owner_signature = self.signer.sign_transaction(prepared_invoke)
                invoke_result = await self.invoke(contract, prepared_invoke, owner_signature)
                logging.info(f"Transaction sent with hash: {hex(invoke_result.hash)}")
                await invoke_result.wait_for_acceptance()
                logging.info("Transaction accepted on chain.")
            else:
                # Save transaction data for multisig signing
                multisig_filename = f"{func_name}_multisig.json"
                with open(multisig_filename, "w"):
                    self.print_invoke(prepared_invoke)
                logging.warning("Action requires multiple signatures.")
                logging.info(f"Prepared invoke saved to {multisig_filename}")
                logging.info(
                    "Please sign the transaction with the sign-invoke-tx command and submit with the submit-invoke-tx"
                    " command."
                )
        except Exception as e:
            logging.error(f"Error processing invoke: {e}")
            raise

    def print_invoke(self, invoke: InvokeV1):
        invoke_schema = marshmallow_dataclass.class_schema(InvokeV1)()
        print("\n---")
        print(invoke_schema.dumps(invoke))
        print("---\n")

    def sign_message(self, typed_data: TypedData) -> List[int]:
        msg_hash = typed_data_to_message_hash(typed_data, self.address)
        r, s = message_signature(msg_hash=msg_hash, priv_key=self.signer.key_pair.private_key)
        return [r, s]


class StarkwareETHProxyCheck(ProxyCheck):
    async def implementation_address(self, address: Address, client: Client) -> Optional[int]:
        return await self.get_implementation(
            address=address,
            client=client,
            get_class_func=client.get_class_hash_at,
            regex_err_msg=r"(is not deployed)",
        )

    async def implementation_hash(self, address: Address, client: Client) -> Optional[int]:
        return await self.get_implementation(
            address=address,
            client=client,
            get_class_func=client.get_class_by_hash,
            regex_err_msg=r"(is not declared)",
        )

    @staticmethod
    async def get_implementation(
        address: Address, client: Client, get_class_func: Callable, regex_err_msg: str
    ) -> Optional[int]:
        call = StarkwareETHProxyCheck._get_implementation_call(address=address)
        err_msg = r"(Entry point 0x[0-9a-f]+ not found in contract)|" + regex_err_msg
        try:
            (implementation,) = await client.call_contract(call=call)
            await get_class_func(implementation)
        except ClientError as err:
            if re.search(err_msg, err.message, re.IGNORECASE) or err.code == RPC_CONTRACT_ERROR:
                return None
            raise err
        return implementation

    @staticmethod
    def _get_implementation_call(address: Address) -> Call:
        return Call(
            to_addr=address,
            selector=get_selector_from_name("implementation"),
            calldata=[],
        )


def get_proxy_config():
    return ProxyConfig(
        max_steps=5,
        proxy_checks=[StarkwareETHProxyCheck(), ArgentProxyCheck(), OpenZeppelinProxyCheck()],
    )
