from typing import cast

from starknet_py.net.models.typed_data import TypedDataDict


def build_parent_link_message(chain_id: int, account: str, environment: str) -> TypedDataDict:
    """EIP-712 link an Ethereum parent signs so ``POST /v1/onboarding`` accepts it as
    the parent of ``account``.

    Must match ``BuildParentLinkTypedData`` in the Paradex API.

    Args:
        chain_id: L1 chain id (``l1_chain_id`` from ``GET /system/config``).
        account: the ``PARADEX-STARKNET-ACCOUNT`` header, exactly as sent.
        environment: ``environment`` from ``GET /system/config``.
    """
    message = {
        "message": {
            "account": account,
            "environment": environment,
        },
        "domain": {"name": "Paradex", "chainId": chain_id, "version": "1"},
        "primaryType": "ParadexAccountLink",
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "ParadexAccountLink": [
                {"name": "account", "type": "string"},
                {"name": "environment", "type": "string"},
            ],
        },
    }
    return cast(TypedDataDict, message)
