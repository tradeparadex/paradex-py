import dataclasses
from typing import List, Optional, Union

import marshmallow_dataclass
from starknet_py.common import create_compiled_contract
from starknet_py.contract import Contract, DeclareResult, DeployResult, InvokeResult
from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.client import Client
from starknet_py.net.client_models import Calls, SentTransactionResponse
from starknet_py.net.models import AddressRepresentation, DeclareV1, InvokeV1, StarknetChainId
from starknet_py.net.signer import BaseSigner
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.net.udc_deployer.deployer import Deployer

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

    def print_invoke(self, invoke: InvokeV1):
        invoke_schema = marshmallow_dataclass.class_schema(InvokeV1)()
        print("\n---")
        print(invoke_schema.dumps(invoke))
        print("---\n")

    def sign_message(self, typed_data: TypedData) -> List[int]:
        msg_hash = typed_data_to_message_hash(typed_data, self.address)
        r, s = message_signature(msg_hash=msg_hash, priv_key=self.signer.key_pair.private_key)
        return [r, s]
