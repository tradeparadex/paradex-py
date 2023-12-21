from paradex_py.message.stark_key import build_stark_key_message


def test_build_onboarding_message():
    assert build_stark_key_message(11155111) == {
        "message": {
            "action": "STARK Key",
        },
        "domain": {"name": "Paradex", "chainId": 11155111, "version": "1"},
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
