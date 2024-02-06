from typing import List, Optional

from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.client import Client
from starknet_py.net.models import AddressRepresentation, StarknetChainId
from starknet_py.net.signer import BaseSigner
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.utils.typed_data import TypedData as TypedDataDataclass

from .typed_data import TypedData
from .utils import message_signature


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
        typed_data_dataclass = TypedDataDataclass.from_dict(typed_data)
        msg_hash = typed_data_dataclass.message_hash(self.address)
        r, s = message_signature(msg_hash=msg_hash, priv_key=self.signer.key_pair.private_key)
        return [r, s]
