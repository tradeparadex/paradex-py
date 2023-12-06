from paradex_py.message.onboarding import build_onboarding_message


def test_build_onboarding_message():
    assert build_onboarding_message(1) == {
        "message": {
            "action": "Onboarding",
        },
        "domain": {"name": "Paradex", "chainId": "0x1", "version": "1"},
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
