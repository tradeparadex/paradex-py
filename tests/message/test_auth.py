from paradex_py.message.auth import build_auth_message


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
