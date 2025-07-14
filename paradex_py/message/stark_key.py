from starknet_py.utils.typed_data import TypedData


def build_stark_key_message(chain_id: int) -> TypedData:
    message = TypedData.from_dict(
        {
            "message": {
                "action": "STARK Key",
            },
            "domain": {"name": "Paradex", "chainId": chain_id, "version": "1"},  # type: ignore[typeddict-item]
            "primaryType": "Constant",
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                ],
                "Constant": [
                    {"name": "action", "type": "string"},
                ],
            },
        }
    )
    return message
