"""Standalone builder approvals: validation and the fields the server signs over."""

import dataclasses

import pytest

from paradex_py.message.session import BUILDER_APPROVAL_MAX_SECONDS, Builder, BuilderApproval

ISSUED = 1767225600
BUILDER = "0x1b2c"


def _approval(**overrides) -> BuilderApproval:
    fields = {
        "paradex_chain": "PRIVATE_SN_PARACLEAR_MAINNET",
        "environment": "mainnet",
        "account": "0x62cf",
        "builder": Builder(BUILDER, "0.0005", ISSUED + 86400),
        "nonce": "0x88888888888888888888888888888888",
        "issued_at": ISSUED,
    }
    fields.update(overrides)
    return BuilderApproval(**fields)


def test_message_has_the_server_field_order():
    message = _approval(subaccounts=["0x0abc"]).to_message()
    assert list(message) == ["paradexChain", "environment", "account", "builder", "subaccounts", "nonce", "issuedAt"]
    assert message["builder"] == {"account": BUILDER, "maxFeeRate": "0.0005", "expiresAt": ISSUED + 86400}
    assert message["subaccounts"] == ["0xabc"]
    assert BuilderApproval.from_message(message).to_message() == message


def test_typed_data_is_eip712_builder_approval():
    typed = _approval().eip712_typed_data(42161)
    assert typed["primaryType"] == "BuilderApproval"
    assert typed["domain"] == {"name": "Paradex Session", "version": "1", "chainId": 42161}
    assert [f["name"] for f in typed["types"]["BuilderApproval"]] == [
        "paradexChain",
        "environment",
        "account",
        "builder",
        "subaccounts",
        "nonce",
        "issuedAt",
    ]
    assert set(typed["types"]) == {"EIP712Domain", "BuilderApproval", "Builder"}


def test_new_stamps_issued_at_from_server_time():
    approval = BuilderApproval.new(
        server_time=ISSUED,
        ttl_seconds=3600,
        paradex_chain="PRIVATE_SN_PARACLEAR_MAINNET",
        environment="mainnet",
        account="0x62cf",
        builder=Builder(BUILDER, "0.0005"),
    )
    assert approval.issued_at == ISSUED
    assert approval.builder.expires_at == ISSUED + 3600
    approval.to_message()


@pytest.mark.parametrize(
    ("builder", "error"),
    [
        (Builder("0x0", "0", 0), "names a builder"),
        (Builder("0x62cf", "0.0005", ISSUED + 1), "must not be the approving account"),
        (Builder(BUILDER, "0", ISSUED + 1), "above 0"),
        (Builder(BUILDER, "0.000000001", ISSUED + 1), "more than 8 decimal places"),
        (Builder(BUILDER, "0.000500000", ISSUED + 1), "more than 8 decimal places"),
        (Builder(BUILDER, "-0.0005", ISSUED + 1), "plain non-negative decimal"),
        (Builder(BUILDER, "0.0005", 0), "expiresAt is required"),
        (Builder(BUILDER, "0.0005", ISSUED), "must be after issuedAt"),
        (Builder(BUILDER, "0.0005", ISSUED + BUILDER_APPROVAL_MAX_SECONDS + 1), "at most 180 days"),
    ],
)
def test_refuses_what_the_server_refuses(builder, error):
    with pytest.raises(ValueError, match=error):
        _approval(builder=builder).to_message()


def test_new_refuses_a_zero_ttl():
    approval = BuilderApproval.new(
        server_time=ISSUED,
        ttl_seconds=0,
        paradex_chain="PRIVATE_SN_PARACLEAR_MAINNET",
        environment="mainnet",
        account="0x62cf",
        builder=Builder(BUILDER, "0.0005"),
    )
    with pytest.raises(ValueError, match="must be after issuedAt"):
        approval.to_message()


def test_accepts_the_limits():
    _approval(builder=Builder(BUILDER, "0.0025", ISSUED + BUILDER_APPROVAL_MAX_SECONDS)).to_message()
    # The server sets the highest rate it accepts, so a rate above 25 bps signs.
    _approval(builder=Builder(BUILDER, "0.01", ISSUED + 1)).to_message()
    _approval(builder=Builder(BUILDER, "0.00000001", ISSUED + 1)).to_message()


def test_refuses_repeated_or_anchor_subaccounts():
    with pytest.raises(ValueError, match="must not repeat"):
        _approval(subaccounts=["0x5", "0x05"]).to_message()
    with pytest.raises(ValueError, match="anchor account"):
        _approval(subaccounts=["0x62cf"]).to_message()


def test_is_signed_with_eip712_only():
    with pytest.raises(ValueError, match="EIP-712 only"):
        _approval().sign_snip12("0x1")


def test_issued_at_is_required():
    fields = dataclasses.asdict(_approval())
    del fields["issued_at"]
    fields["builder"] = Builder(**fields["builder"])
    with pytest.raises(TypeError, match="issued_at"):
        BuilderApproval(**fields)
