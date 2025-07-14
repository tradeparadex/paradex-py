from starknet_py.utils.typed_data import TypedData


def build_auth_message(chain_id: int, timestamp: int, expiry: int) -> TypedData:
    message = TypedData.from_dict(
        {
            "message": {
                "method": "POST",
                "path": "/v1/auth",
                "body": "",
                "timestamp": timestamp,
                "expiration": expiry,
            },
            "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},  # type: ignore[typeddict-item]
            "primaryType": "Request",
            "types": {
                "StarkNetDomain": [
                    {"name": "name", "type": "felt"},
                    {"name": "chainId", "type": "felt"},
                    {"name": "version", "type": "felt"},
                ],
                "Request": [
                    {"name": "method", "type": "felt"},
                    {"name": "path", "type": "felt"},
                    {"name": "body", "type": "felt"},
                    {"name": "timestamp", "type": "felt"},
                    {"name": "expiration", "type": "felt"},
                ],
            },
        }
    )
    return message
