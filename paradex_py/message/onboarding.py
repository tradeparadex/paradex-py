from typing import cast

from starknet_py.utils.typed_data import TypedDataDict


def build_onboarding_message(chain_id: int) -> TypedDataDict:
    message = {
        "message": {
            "action": "Onboarding",
        },
        "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},
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
    return cast(TypedDataDict, message)
