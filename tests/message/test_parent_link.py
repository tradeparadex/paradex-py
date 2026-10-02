from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

from paradex_py.account.utils import sign_l1_typed_data
from paradex_py.message.parent_link import build_parent_link_message

# The same vector is pinned in the Paradex API (TestBuildParentLinkTypedData_PinnedVector)
# and UI, so this fails if the typed data drifts from what /v1/onboarding verifies.
ACCOUNT = "0x37756a3b8e443aecf9b48f8e75cb69d8dfe41abe11888288c5957937e4b20f2"
# Test-only key, shared with the API's EVM onboarding tests.
L1_PRIVATE_KEY = 0x3535CEC5F1B1CCD9B44024F791C1A2D16DA7753DFBA5F7F59AD5984ED5CA61C6
L1_ADDRESS = "0x1d90b59d4A3322F2502853a51afFA82Cb11E340b"


def test_parent_link_message_hash():
    signable = encode_typed_data(full_message=build_parent_link_message(11155111, ACCOUNT, "testnet"))
    digest = b"\x19" + signable.version + signable.header + signable.body
    assert "0x" + keccak(digest).hex() == "0x380fdd30049873c17cf43d831a672d40e4af2b1309f7ed780e400ded0b311567"


def test_parent_link_signature():
    message = build_parent_link_message(11155111, ACCOUNT, "testnet")
    signature = sign_l1_typed_data(message, l1_address=L1_ADDRESS, l1_private_key=L1_PRIVATE_KEY)

    assert signature == (
        "0x987fcd632f675c9e27b01235c1b197f10aab695b255c77be897b4004d5c36fd6"
        "6b76ed32d13f03034313afa78cf44caa3b06795c00b47a3676cb094622bd35061c"
    )
    assert Account.recover_message(encode_typed_data(full_message=message), signature=signature) == L1_ADDRESS


def test_sign_l1_typed_data_without_a_signer():
    message = build_parent_link_message(11155111, ACCOUNT, "testnet")
    assert sign_l1_typed_data(message, l1_address=L1_ADDRESS) is None
