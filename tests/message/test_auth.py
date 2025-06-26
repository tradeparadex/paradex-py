import json

from paradex_py.message.auth import build_auth_message, build_fullnode_message


def test_build_auth_message():
    assert build_auth_message(1, 2, 3) == {
        "message": {
            "method": "POST",
            "path": "/v1/auth",
            "body": "",
            "timestamp": 2,
            "expiration": 3,
        },
        "domain": {"name": "Paradex", "chainId": "0x1", "version": "1"},
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


def test_build_fullnode_message():
    chain_id = 42
    account = "0x1"
    timestamp = 1750962555
    version = "1.0.0"
    json_payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "starknet_getTransactionStatus",
            "params": ["0x1"],
            "id": 1,
        }
    )
    payload_hash = 2542254075546871898725420793330915700567851405709402681030792058741266708376
    assert build_fullnode_message(chain_id, account, json_payload, timestamp, version) == {
        "message": {
            "account": account,
            "payload": payload_hash,
            "timestamp": timestamp,
            "version": version,
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
                {"name": "account", "type": "felt"},
                {"name": "payload", "type": "felt"},
                {"name": "timestamp", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
        },
    }
