import dataclasses

import pytest
from eth_account import Account as EthAccount
from eth_account.messages import encode_typed_data
from starknet_py.hash.utils import private_to_stark_key, verify_message_signature

from paradex_py.message.session import (
    Builder,
    Ceiling,
    Limits,
    Passkey,
    PasskeyGrant,
    SessionGrant,
    SessionMint,
    grant_environment,
    new_nonce,
)

MAINNET = "PRIVATE_SN_PARACLEAR_MAINNET"
LIMITS = Limits("25000", "100000", "500000", "5000.5", "10", ["BTC-USD-PERP", "*-USD-PERP"])
ARBITRUM = 42161


def _grant(**overrides) -> SessionGrant:
    fields = {
        "paradex_chain": MAINNET,
        "environment": "mainnet",
        "account": "0x0123abc",
        "session_key": "0x5678",
        "label": "Bot label that is longer than thirty-one characters",
        "scopes": ["trade", "trade:rfq"],
        "limits": LIMITS,
        "builder": Builder("0xb1", "0.0005", 0),
        "subaccounts": ["0x99", "0x98"],
        "nonce": "0xffffffffffffffffffffffffffffffff",
        "issued_at": 1700000000,
        "expires_at": 1700600000,
    }
    fields.update(overrides)
    return SessionGrant(**fields)


def _passkey_grant(**overrides) -> PasskeyGrant:
    fields = {
        "paradex_chain": MAINNET,
        "environment": "mainnet",
        "account": "0x1234",
        "passkey": Passkey("Y3JlZA", "0xaa", "0xbb", "paradex.trade", "phone"),
        "ceiling": Ceiling(["trade"], LIMITS, 86400, 5, ["0x99"], True),
        "nonce": "0x2",
        "issued_at": 1,
        "expires_at": 2,
    }
    fields.update(overrides)
    return PasskeyGrant(**fields)


def _mint(**overrides) -> SessionMint:
    fields = {
        "paradex_chain": MAINNET,
        "environment": "mainnet",
        "account": "0x1234",
        "credential_id": "Y3JlZA",
        "session_key": "0x5",
        "scopes": ["trade"],
        "limits": LIMITS,
        "expires_at": 100,
        "subaccounts": ["0x99"],
        "nonce": "0x3",
    }
    fields.update(overrides)
    return SessionMint(**fields)


# Vectors cross-checked against viem's hashTypedData (EIP-712) and starknet.js typedData.getMessageHash
# (SNIP-12 rev 1). Replace or extend with the server's golden vectors once they are published.
@pytest.mark.parametrize(
    ("message", "eip712_hash", "snip12_hash"),
    [
        (
            _grant(),
            "102a5e1e5e9ab23e0454ba71f7929090a6449c88fef29f2dca8284cdd6d5c05d",
            0x35B7BA1421553B494BCF2E308C38A17E93BE5E047CA68DC5F3D1B56A7E7FE11,
        ),
        (
            _grant(
                paradex_chain="PRIVATE_SN_PARACLEAR_TESTNET",
                environment="nightly",
                account="0x1",
                session_key="0x2",
                label="",
                scopes=["trade"],
                limits=Limits("", "", "", "", "", []),
                builder=Builder(),
                subaccounts=[],
                nonce="0x0",
                issued_at=1,
                expires_at=2,
            ),
            "40f76b05f4b2c23f5da08ffe25d6ddb24193b242a056aa35511a37049ede81cf",
            0x110A12928AC2225B47E69B56F8A7C0EE5BD766AC9DB628985E2C03D96A2C8A8,
        ),
        (
            _passkey_grant(),
            "b69f4df791210ffb62f74829aa69686fe8d24040d2c4d0b341a7ecb5df1f7bc1",
            0x72854BA05E52D7BD457A5631D9709ED7C1F534575D7114219F3F0EF82C6A9EE,
        ),
        (
            _mint(),
            "877bef2d8f63288fc76b4541106bb624eeec84666a69b44fc5fdd1d9ffbae1b9",
            0x1AE0F551EA18CCEE36491D72635614372ADAC6C40995A4672B8148C8FCEFA8F,
        ),
    ],
    ids=["session-grant-builder", "session-grant-minimal", "passkey-grant", "session-mint"],
)
def test_hash_vectors(message, eip712_hash, snip12_hash):
    assert message.eip712_hash(ARBITRUM).hex() == eip712_hash
    assert message.snip12_hash() == snip12_hash


def test_eip712_unicode_label_vector():
    grant = _grant(
        account="0x1",
        session_key="0x2",
        label="Bøt 🤖",
        scopes=["trade"],
        builder=Builder(),
        subaccounts=[],
        nonce="0x5",
        issued_at=1,
        expires_at=2,
    )
    assert grant.eip712_hash(ARBITRUM).hex() == "0d19ed0efe6e43f3c08c58b6d8e15b1c7108a0c06236e87e117f1c0c00b08bec"
    with pytest.raises(ValueError, match="ASCII for SNIP-12"):
        grant.snip12_hash()


def test_eip712_typed_data_shape():
    typed = _grant().eip712_typed_data(ARBITRUM)
    assert typed["domain"] == {"name": "Paradex Session", "version": "1", "chainId": ARBITRUM}
    assert typed["primaryType"] == "SessionGrant"
    assert [f["name"] for f in typed["types"]["SessionGrant"]] == [
        "paradexChain",
        "environment",
        "account",
        "sessionKey",
        "label",
        "scopes",
        "limits",
        "builder",
        "subaccounts",
        "nonce",
        "issuedAt",
        "expiresAt",
    ]
    assert typed["message"]["account"] == "0x123abc"  # canonical: lowercase, no leading zeros


def test_snip12_typed_data_shape():
    typed = _grant().snip12_typed_data()
    assert typed["domain"] == {"name": "Paradex Session", "version": "1", "chainId": MAINNET, "revision": "1"}
    types = {f["name"]: f["type"] for f in typed["types"]["SessionGrant"]}
    assert types["account"] == "ContractAddress"
    assert types["subaccounts"] == "ContractAddress*"
    assert types["scopes"] == "shortstring*"
    assert types["issuedAt"] == "timestamp"


def test_hash_depends_on_signature_chain():
    grant = _grant()
    assert grant.eip712_hash(1) != grant.eip712_hash(ARBITRUM)


def test_sign_eip712_recovers_owner():
    owner = EthAccount.create()
    grant = _grant()
    signature = grant.sign_eip712(owner.key.hex(), ARBITRUM)
    signable = encode_typed_data(full_message=grant.eip712_typed_data(ARBITRUM))
    assert EthAccount.recover_message(signable, signature=signature) == owner.address


def test_sign_snip12_verifies():
    private_key = 0x1234567
    grant = _grant()
    r, s = grant.sign_snip12(hex(private_key))
    assert verify_message_signature(grant.snip12_hash(), [int(r), int(s)], private_to_stark_key(private_key))


def test_accounts_lists_anchor_then_subaccounts():
    assert _grant(account="0x00AB", subaccounts=["0x0C", "0xd"]).accounts == ["0xab", "0xc", "0xd"]


def test_new_sets_window_and_fresh_nonce():
    a = SessionGrant.new(
        ttl_seconds=3600,
        paradex_chain=MAINNET,
        environment="mainnet",
        account="0x1",
        session_key="0x2",
        label="x",
        scopes=["trade"],
        limits=LIMITS,
    )
    b = dataclasses.replace(a, nonce=new_nonce())
    assert a.expires_at - a.issued_at == 3600
    assert a.nonce != b.nonce
    assert int(a.nonce, 16) < 2**128


def test_grant_environment():
    assert grant_environment("prod") == "mainnet"
    assert grant_environment("testnet") == "testnet"
    assert grant_environment("nightly") == "nightly"
    with pytest.raises(ValueError, match="Unknown environment"):
        grant_environment("mainnet")


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"scopes": ["trade", "withdraw:owner"]}, "reserved and refused"),
        ({"scopes": ["trade:isolated"]}, "reserved and refused"),
        ({"scopes": ["read"]}, "unknown scope"),
        ({"scopes": []}, "at least one scope"),
        ({"scopes": ["trade", "trade"]}, "must not repeat"),
        ({"environment": "prod"}, "environment must be one of"),
        ({"expires_at": 1700000000}, "must be after issuedAt"),
        ({"expires_at": 1700000000 + 181 * 86400}, "at most 180 days"),
        ({"scopes": ["trade:block"], "expires_at": 1700000000 + 8 * 86400}, "at most 7 days"),
        ({"scopes": ["account:settings"], "expires_at": 1700000000 + 8 * 86400}, "at most 7 days"),
        ({"nonce": hex(2**128)}, "128 bits"),
        ({"nonce": "nope"}, "0x hex"),
        ({"account": "0x" + "f" * 64}, "felt range"),
        ({"subaccounts": ["0x99", "0x099"]}, "must not repeat"),
        ({"subaccounts": ["0x123abc"]}, "anchor account"),
        ({"limits": dataclasses.replace(LIMITS, max_loss="")}, "maxLoss"),
        ({"limits": dataclasses.replace(LIMITS, max_leverage="1e3")}, "plain non-negative decimal"),
        ({"limits": dataclasses.replace(LIMITS, daily_notional="-1")}, "plain non-negative decimal"),
        ({"limits": dataclasses.replace(LIMITS, markets=["X" * 32])}, "1-31 ASCII"),
        ({"builder": Builder("0xb1", "5bps")}, "maxFeeRate"),
        ({"builder": Builder("0xb1", "0.0005", 1700600001)}, "must not outlive"),
        ({"paradex_chain": "PRIVATE_SN_PARACLEAR_MAINNET_TOO_LONG"}, "1-31 ASCII"),
        ({"issued_at": -1}, "uint64"),
        ({"limits": dataclasses.replace(LIMITS, max_loss=5000)}, "must be a decimal string"),
        ({"label": None}, "label must be a string"),
    ],
)
def test_session_grant_refusals(overrides, error):
    grant = _grant(**overrides)
    with pytest.raises(ValueError, match=error):
        grant.eip712_typed_data(ARBITRUM)
    with pytest.raises(ValueError, match=error):
        grant.snip12_hash()


def test_limits_may_be_left_to_server_without_a_builder():
    grant = _grant(builder=Builder(), limits=Limits("", "", "", "", "", []))
    assert grant.to_message()["limits"]["maxLoss"] == ""


@pytest.mark.parametrize("chain_id", [0, -1, True, "1"])
def test_bad_signature_chain_refused(chain_id):
    with pytest.raises(ValueError, match="signature_chain_id"):
        _grant().eip712_typed_data(chain_id)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"builder_account": "0xb1"}, "first-party passkeys"),
        ({"ceiling": Ceiling(["trade"], LIMITS, 0, 5)}, "maxSessionTtl"),
        ({"ceiling": Ceiling(["trade"], LIMITS, 181 * 86400, 5)}, "maxSessionTtl"),
        ({"ceiling": Ceiling(["trade"], LIMITS, 86400, 0)}, "maxConcurrentSessions"),
        ({"ceiling": Ceiling(["withdraw:owner"], LIMITS, 86400, 5)}, "reserved and refused"),
        ({"ceiling": Ceiling(["trade"], LIMITS, 86400, 5, ["0x1234"])}, "anchor account"),
        ({"passkey": Passkey("", "0xaa", "0xbb", "paradex.trade")}, "credentialId and rpId"),
        ({"environment": "staging"}, "environment must be one of"),
        ({"expires_at": 1}, "must be after issuedAt"),
    ],
)
def test_passkey_grant_refusals(overrides, error):
    with pytest.raises(ValueError, match=error):
        _passkey_grant(**overrides).to_message()


def test_builder_passkey_without_future_subaccounts_is_accepted():
    ceiling = Ceiling(["trade"], LIMITS, 86400, 5, ["0x99"], False)
    message = _passkey_grant(builder_account="0xb1", ceiling=ceiling).to_message()
    assert message["builderAccount"] == "0xb1"
    assert message["ceiling"]["includeFutureSubaccounts"] is False


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"credential_id": ""}, "credentialId is required"),
        ({"scopes": ["trade:isolated"]}, "reserved and refused"),
        ({"environment": "local"}, "environment must be one of"),
        ({"expires_at": 2**64}, "uint64"),
        ({"session_key": "0xzz"}, "0x hex"),
    ],
)
def test_session_mint_refusals(overrides, error):
    with pytest.raises(ValueError, match=error):
        _mint(**overrides).to_message()
