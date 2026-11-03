"""Reproduce the server's session typed-data vectors from the SDK's own message classes."""

import json
from pathlib import Path

import pytest
from starknet_py.hash.utils import verify_message_signature

from paradex_py.message.session import (
    Builder,
    Ceiling,
    Limits,
    Passkey,
    PasskeyGrant,
    SessionGrant,
    SessionMint,
)

DATA = json.loads((Path(__file__).parent / "testdata" / "session_vectors.json").read_text())
KEYS = DATA["keys"]


def _limits(m: dict) -> Limits:
    return Limits(
        m["maxOrderNotional"], m["maxOpenNotional"], m["dailyNotional"], m["maxLoss"], m["maxLeverage"], m["markets"]
    )


def _build(primary_type: str, m: dict):
    common = {"paradex_chain": m["paradexChain"], "environment": m["environment"], "account": m["account"]}
    if primary_type == "SessionGrant":
        b = m["builder"]
        return SessionGrant(
            **common,
            session_key=m["sessionKey"],
            label=m["label"],
            scopes=m["scopes"],
            limits=_limits(m["limits"]),
            builder=Builder(b["account"], b["maxFeeRate"], int(b["expiresAt"])),
            subaccounts=m["subaccounts"],
            nonce=m["nonce"],
            issued_at=int(m["issuedAt"]),
            expires_at=int(m["expiresAt"]),
        )
    if primary_type == "PasskeyGrant":
        p, c = m["passkey"], m["ceiling"]
        return PasskeyGrant(
            **common,
            passkey=Passkey(p["credentialId"], p["pubkeyX"], p["pubkeyY"], p["rpId"], p["label"]),
            ceiling=Ceiling(
                scopes=c["scopes"],
                limits=_limits(c["limits"]),
                max_session_ttl=int(c["maxSessionTtl"]),
                max_concurrent_sessions=int(c["maxConcurrentSessions"]),
                subaccounts=c["subaccounts"],
                include_future_subaccounts=c["includeFutureSubaccounts"],
            ),
            builder_account=m["builderAccount"],
            nonce=m["nonce"],
            issued_at=int(m["issuedAt"]),
            expires_at=int(m["expiresAt"]),
        )
    return SessionMint(
        **common,
        credential_id=m["credentialId"],
        session_key=m["sessionKey"],
        scopes=m["scopes"],
        limits=_limits(m["limits"]),
        subaccounts=m["subaccounts"],
        nonce=m["nonce"],
        expires_at=int(m["expiresAt"]),
    )


@pytest.mark.parametrize("vector", DATA["vectors"], ids=[v["name"] for v in DATA["vectors"]])
def test_server_vector(vector):
    message = _build(vector["primaryType"], vector["message"])

    eip712 = vector["eip712"]
    chain_id = eip712["signatureChainId"]
    assert message.eip712_typed_data(chain_id) == eip712["typedData"]
    assert "0x" + message.eip712_hash(chain_id).hex() == eip712["digest"]

    snip12 = vector["snip12"]
    assert message.snip12_typed_data() == snip12["typedData"]
    assert message.snip12_hash() == int(snip12["messageHash"], 16)
    if "signature" in snip12:
        # Stark signatures use a random nonce, so verify the server's rather than reproduce it.
        r, s = (int(x, 0) for x in snip12["signature"])
        assert verify_message_signature(message.snip12_hash(), [r, s], int(KEYS["starkPublicKey"], 16))

    if vector["signer"] == "eip191":
        # EIP-712 signatures are deterministic (RFC 6979), so the server's signature reproduces exactly.
        assert message.sign_eip712(KEYS["evmPrivateKey"], chain_id) == eip712["signature"]
    if "mintChallenge" in vector:
        assert message.webauthn_challenge() == vector["mintChallenge"]


def test_vectors_cover_every_message_type():
    assert {v["primaryType"] for v in DATA["vectors"]} == {"SessionGrant", "PasskeyGrant", "SessionMint"}
