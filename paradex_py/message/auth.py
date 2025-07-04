from poseidon_py.poseidon_hash import poseidon_hash_many
from starknet_py.net.models.typed_data import TypedData
from starknet_py.serialization.data_serializers.byte_array_serializer import ByteArraySerializer


def build_auth_message(chain_id: int, timestamp: int, expiry: int) -> TypedData:
    message = {
        "message": {
            "method": "POST",
            "path": "/v1/auth",
            "body": "",
            "timestamp": timestamp,
            "expiration": expiry,
        },
        "domain": {"name": "Paradex", "chainId": hex(chain_id), "version": "1"},
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
    return message


def poseidon_hash(input_str: str) -> int:
    byte_array_serializer = ByteArraySerializer()
    input_felts = byte_array_serializer.serialize(input_str)
    return poseidon_hash_many(input_felts)


def build_fullnode_message(
    chainId: int, account: str, json_payload: str, signature_timestamp: int, signature_version: str
) -> TypedData:
    payload_hash = poseidon_hash(json_payload)
    message = {
        "message": {
            "account": account,
            "payload": payload_hash,
            "timestamp": signature_timestamp,
            "version": signature_version,
        },
        "domain": {"name": "Paradex", "chainId": hex(chainId), "version": "1"},
        "primaryType": "Request",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
            "Request": [
                {"name": "account", "type": "felt"},
                {"name": "payload", "type": "felt"},
                {"name": "timestamp", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
        },
    }
    return message
