from starknet_py.utils.typed_data import TypedData


def build_onboarding_message(chain_id: int) -> TypedData:
    message = TypedData.from_dict(
        {
            "message": {
                "action": "Onboarding",
            },
            "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},  # type: ignore[typeddict-item]
            "primaryType": "Constant",
            "types": {
                "StarkNetDomain": [
                    {"name": "name", "type": "felt"},
                    {"name": "chainId", "type": "felt"},
                    {"name": "version", "type": "felt"},
                ],
                "Constant": [
                    {"name": "action", "type": "felt"},
                ],
            },
        }
    )
    return message
