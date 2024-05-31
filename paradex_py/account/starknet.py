from typing import List, Optional

from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.client import Client
from starknet_py.net.models import AddressRepresentation, StarknetChainId
from starknet_py.net.signer import BaseSigner
from starknet_py.net.signer.stark_curve_signer import KeyPair

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

    def sign_message(self, typed_data: TypedData) -> List[int]:
        msg_hash = typed_data_to_message_hash(typed_data, self.address)
        r, s = message_signature(msg_hash=msg_hash, priv_key=self.signer.key_pair.private_key)
        return [r, s]
