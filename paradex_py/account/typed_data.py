from typing import List, Union, cast

from starknet_py.cairo.felt import encode_shortstring
from starknet_py.utils.typed_data import TypedData as StarknetTypedDataDataclass
from starknet_py.utils.typed_data import (
    get_hex,
    is_pointer,
    strip_pointer,
)

from .utils import compute_hash_on_elements


class TypedData(StarknetTypedDataDataclass):
    def _encode_data(self, type_name: str, data: dict) -> List[int]:
        values = []
        for param in self.types[type_name]:
            encoded_value = self._encode_value(param.type, data[param.name])
            values.append(encoded_value)

        return values

    def _encode_value(self, type_name: str, value: Union[int, str, dict, list]) -> int:
        if is_pointer(type_name) and isinstance(value, list):
            type_name = strip_pointer(type_name)

            if self._is_struct(type_name):
                return compute_hash_on_elements([self.struct_hash(type_name, data) for data in value])
            return compute_hash_on_elements([int(get_hex(val), 16) for val in value])

        if self._is_struct(type_name) and isinstance(value, dict):
            return self.struct_hash(type_name, value)

        value = cast(Union[int, str], value)
        return int(get_hex(value), 16)

    def struct_hash(self, type_name: str, data: dict) -> int:
        """
        Calculate the hash of a struct.

        :param type_name: Name of the type.
        :param data: Data defining the struct.
        :return: Hash of the struct.
        """
        return compute_hash_on_elements([self.type_hash(type_name), *self._encode_data(type_name, data)])

    def message_hash(self, account_address: int) -> int:
        message = [
            encode_shortstring("StarkNet Message"),
            self.struct_hash("StarkNetDomain", cast(dict, self.domain)),
            account_address,
            self.struct_hash(self.primary_type, self.message),
        ]

        return compute_hash_on_elements(message)
