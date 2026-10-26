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
PUB_X = "0x" + "ab" * 32
PUB_Y = "0x" + "cd" * 32


def _nonce(n: int) -> str:
    return hex(n)


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
        "nonce": "0x" + "f" * 32,
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
        "passkey": Passkey("Y3JlZA", PUB_X, PUB_Y, "paradex.trade", "phone"),
        "ceiling": Ceiling(["trade"], LIMITS, 86400, 5, ["0x99"], True),
        "nonce": _nonce(2),
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
        "nonce": _nonce(3),
    }
    fields.update(overrides)
    return SessionMint(**fields)


# Extra vectors cross-checked against viem's hashTypedData (EIP-712) and starknet.js typedData.getMessageHash
# (SNIP-12 rev 1); the server's own vectors are in test_session_vectors.py.
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
                environment="testnet",
                account="0x1",
                session_key="0x2",
                label="",
                scopes=["trade"],
                limits=Limits("none", "none", "none", "none", "none", ["*"]),
                builder=Builder(),
                subaccounts=[],
                nonce=_nonce(7),
                issued_at=1,
                expires_at=2,
            ),
            "4000ce1d2ba9a025233df7171dd083058cdb6550ee9eafb94da04214f9d40d07",
            0x38901D640133313BC2D493CA22A628936C0C22806068BA313D6D73D89F29350,
        ),
        (
            _passkey_grant(),
            "9b7e10632301ee6b289d044acdb44f05cb23128e4164297574f27b88d295841a",
            0x48D93FCD96683717EEDA41A492F8A32D1E64399F4B8D0A61AE2BC38B2018951,
        ),
        (
            _mint(),
            "e97f338d6aedcc360546135858b94aac97eefea5cac8906d75541f6b6de8e4f6",
            0x2C5FCA078BFA403E8E72CE892ACDE7C5F88EF5E67913492576DEC54767B6A7D,
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
        nonce=_nonce(5),
        issued_at=1,
        expires_at=2,
    )
    assert grant.eip712_hash(ARBITRUM).hex() == "0d19ed0efe6e43f3c08c58b6d8e15b1c7108a0c06236e87e117f1c0c00b08bec"
    with pytest.raises(ValueError, match="printable ASCII for SNIP-12"):
        grant.snip12_hash()
    with pytest.raises(ValueError, match="printable ASCII for SNIP-12"):
        dataclasses.replace(grant, label="tab\there").snip12_hash()


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


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"scopes": ["trade", "withdraw:owner"]}, "reserved and refused"),
        ({"scopes": ["trade:isolated"]}, "reserved and refused"),
        ({"scopes": ["read"]}, "unknown scope"),
        ({"scopes": []}, "at least one scope"),
        ({"scopes": ["trade", "trade"]}, "must not repeat"),
        ({"environment": ""}, "environment must be"),
        ({"expires_at": 1700000000}, "must be after issuedAt"),
        ({"expires_at": 1700000000 + 181 * 86400}, "at most 180 days"),
        ({"scopes": ["trade:block"], "builder": Builder(), "expires_at": 1700000000 + 8 * 86400}, "at most 7 days"),
        (
            {"scopes": ["account:settings"], "builder": Builder(), "expires_at": 1700000000 + 8 * 86400},
            "at most 7 days",
        ),
        ({"scopes": ["trade", "trade:block"]}, "builder grants may not carry"),
        ({"scopes": ["account:settings"]}, "builder grants may not carry"),
        ({"nonce": hex(2**128)}, "at most 128 bits"),
        ({"nonce": "0x0"}, "at most 128 bits"),
        ({"nonce": "0x01"}, "at most 128 bits"),
        ({"nonce": "0x" + "F" * 32}, "at most 128 bits"),
        ({"account": "0x" + "f" * 64}, "felt range"),
        ({"account": hex(2**251 + 17 * 2**192 + 1)}, "felt range"),  # the field prime itself
        ({"subaccounts": ["0x99", "0x099"]}, "must not repeat"),
        ({"subaccounts": ["0x123abc"]}, "anchor account"),
        ({"limits": dataclasses.replace(LIMITS, max_loss="")}, "maxLoss must be a positive decimal"),
        ({"limits": dataclasses.replace(LIMITS, max_leverage="1e3")}, "maxLeverage must be a positive decimal"),
        ({"limits": dataclasses.replace(LIMITS, daily_notional="-1")}, "dailyNotional must be a positive decimal"),
        ({"limits": dataclasses.replace(LIMITS, daily_notional="0")}, "dailyNotional must be a positive decimal"),
        ({"limits": dataclasses.replace(LIMITS, max_open_notional="None")}, "maxOpenNotional must be a positive"),
        ({"limits": dataclasses.replace(LIMITS, markets=[])}, "markets must not be empty"),
        ({"limits": dataclasses.replace(LIMITS, markets=["*", "BTC-USD-PERP"])}, "'\\*' stands alone"),
        ({"limits": dataclasses.replace(LIMITS, markets=["X" * 32])}, "market must be"),
        ({"limits": dataclasses.replace(LIMITS, markets=["1_2"])}, "market must be"),
        ({"limits": dataclasses.replace(LIMITS, markets=["0xab"])}, "market must be"),
        ({"limits": dataclasses.replace(LIMITS, markets=["0o7-PERP"])}, "market must be"),
        ({"limits": dataclasses.replace(LIMITS, markets=["BTC.USD"])}, "market must be"),
        ({"limits": dataclasses.replace(LIMITS, markets=["**-PERP"])}, "market pattern"),
        ({"limits": dataclasses.replace(LIMITS, markets=["*-*"])}, "market pattern"),
        ({"limits": dataclasses.replace(LIMITS, markets=["123"])}, "market must be"),
        ({"limits": dataclasses.replace(LIMITS, markets=["0XAB"])}, "market must be"),
        ({"limits": dataclasses.replace(LIMITS, markets=["0B1-PERP"])}, "market must be"),
        ({"limits": dataclasses.replace(LIMITS, markets=["-USD-PERP"])}, "market must be"),
        ({"builder": Builder("0x0", "0.0005")}, "without a builder uses"),
        ({"builder": Builder("0x00", "0", 1)}, "without a builder uses"),
        ({"limits": dataclasses.replace(LIMITS, max_loss="05")}, "maxLoss must be a positive decimal"),
        ({"builder": Builder("0xb1", "5bps")}, "maxFeeRate"),
        ({"builder": Builder("0xb1", "0.0005", 1700600001)}, "must not outlive"),
        ({"paradex_chain": "PRIVATE_SN_PARACLEAR_MAINNET_TOO_LONG"}, "1-31 ASCII"),
        ({"issued_at": -1}, "2\\^53"),
        ({"expires_at": 2**53}, "2\\^53"),
        ({"limits": dataclasses.replace(LIMITS, max_loss=5000)}, "maxLoss must be a positive decimal"),
        ({"label": None}, "label must be a string"),
    ],
)
def test_session_grant_refusals(overrides, error):
    grant = _grant(**overrides)
    with pytest.raises(ValueError, match=error):
        grant.eip712_typed_data(ARBITRUM)
    with pytest.raises(ValueError, match=error):
        grant.snip12_hash()


def test_first_party_grants_may_leave_limits_uncapped():
    limits = _grant(builder=Builder(), limits=Limits("none", "none", "none", "none", "none", ["*"])).to_message()[
        "limits"
    ]
    assert limits == {
        "maxOrderNotional": "none",
        "maxOpenNotional": "none",
        "dailyNotional": "none",
        "maxLoss": "none",
        "maxLeverage": "none",
        "markets": ["*"],
    }


def test_builder_grants_may_leave_limits_other_than_max_loss_uncapped():
    limits = dataclasses.replace(LIMITS, max_order_notional="none", max_leverage="none", markets=["*"])
    assert _grant(limits=limits).to_message()["limits"]["maxLeverage"] == "none"


def test_loss_wording():
    assert LIMITS.loss_wording() == "Cannot withdraw; can lose up to 5000.5 USD by trading"
    assert dataclasses.replace(LIMITS, max_loss="none").loss_wording() == (
        "Cannot withdraw; trading losses are not capped by this session"
    )


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
        ({"passkey": Passkey("", PUB_X, PUB_Y, "paradex.trade")}, "credentialId and rpId"),
        ({"passkey": Passkey("c", "0xaa", PUB_Y, "paradex.trade")}, "pubkeyX"),
        ({"passkey": Passkey("c", PUB_X, "0x" + "CD" * 32, "paradex.trade")}, "pubkeyY"),
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
        ({"expires_at": 2**64}, "2\\^53"),
        ({"session_key": "0xzz"}, "0x hex"),
    ],
)
def test_session_mint_refusals(overrides, error):
    with pytest.raises(ValueError, match=error):
        _mint(**overrides).to_message()


def test_new_nonce_format():
    for _ in range(50):
        nonce = new_nonce()
        assert len(nonce) == 34
        assert nonce == nonce.lower()
        assert nonce[2] != "0"


def test_webauthn_challenge_is_unpadded_base64url_of_the_snip12_hash():
    import base64

    mint = _mint()
    challenge = mint.webauthn_challenge()
    assert "=" not in challenge
    assert int.from_bytes(base64.urlsafe_b64decode(challenge + "="), "big") == mint.snip12_hash()


def test_session_mint_field_order():
    names = [f["name"] for f in _mint().eip712_typed_data(ARBITRUM)["types"]["SessionMint"]]
    assert names == [
        "paradexChain",
        "environment",
        "account",
        "credentialId",
        "sessionKey",
        "scopes",
        "limits",
        "subaccounts",
        "nonce",
        "expiresAt",
    ]


def test_short_nonces_are_valid():
    assert _grant(nonce="0x1").to_message()["nonce"] == "0x1"


def _ceiling_grant(limits: Limits, **ceiling) -> PasskeyGrant:
    fields = {"scopes": ["trade"], "limits": limits, "max_session_ttl": 86400, "max_concurrent_sessions": 5}
    fields.update(ceiling)
    return _passkey_grant(ceiling=Ceiling(**fields), issued_at=1000, expires_at=10**6)


def _markets(*markets: str) -> Limits:
    return dataclasses.replace(LIMITS, markets=list(markets))


UNCAPPED = Limits("none", "none", "none", "none", "none", ["*"])


@pytest.mark.parametrize(
    ("ceiling", "mint", "error"),
    [
        (LIMITS, LIMITS, None),
        (LIMITS, dataclasses.replace(LIMITS, max_loss="100", markets=["BTC-USD-PERP"]), None),
        (UNCAPPED, UNCAPPED, None),
        (UNCAPPED, LIMITS, None),
        (dataclasses.replace(LIMITS, markets=["*"]), dataclasses.replace(LIMITS, markets=["SOL-USD-PERP"]), None),
        (LIMITS, dataclasses.replace(LIMITS, max_loss="5000.6"), "maxLoss must be a number at most"),
        (LIMITS, dataclasses.replace(LIMITS, max_loss="none"), "maxLoss must be a number at most"),
        (LIMITS, dataclasses.replace(LIMITS, markets=["*"]), "covered by the ceiling's markets"),
        (LIMITS, dataclasses.replace(LIMITS, markets=["ETH-USD-27NOV26"]), "covered by the ceiling's markets"),
        (_markets("*-USD-PERP"), _markets("BTC-USD-PERP", "kPEPE-USD-PERP"), None),
        (_markets("*-USD-PERP"), _markets("*-USD-PERP"), None),
        (_markets("NEAR-USD-*-C"), _markets("NEAR-USD-27NOV26-5_4-C"), None),
        (_markets("*-USD-PERP"), _markets("BTC-USD-27NOV26"), "covered by the ceiling's markets"),
        (_markets("*-USD-PERP"), _markets("BTC-*"), "covered by the ceiling's markets"),
        (_markets("*-PERP"), _markets("BTC-*-PERP"), "covered by the ceiling's markets"),
    ],
)
def test_mint_limits_must_match_the_ceiling(ceiling, mint, error):
    grant = _ceiling_grant(ceiling)
    session_mint = _mint(limits=mint, subaccounts=[], expires_at=2000)
    if error is None:
        session_mint.check_within(grant, now=1500)
    else:
        with pytest.raises(ValueError, match=error):
            session_mint.check_within(grant, now=1500)


@pytest.mark.parametrize(
    ("mint", "ceiling", "error"),
    [
        ({"account": "0x9"}, {}, "mint account is not the grant's"),
        ({"credential_id": "other"}, {}, "credentialId is not the grant's passkey"),
        ({"paradex_chain": "PRIVATE_SN_PARACLEAR_TESTNET"}, {}, "mint paradexChain is not the grant's"),
        ({"environment": "testnet"}, {}, "mint environment is not the grant's"),
        ({"expires_at": 1500}, {}, "already expired"),
        ({"scopes": ["trade", "trade:rfq"]}, {}, "exceed the ceiling"),
        ({"subaccounts": ["0x77"]}, {"subaccounts": ["0x99"]}, "sub-accounts the ceiling does not"),
        ({"expires_at": 1500 + 86401}, {}, "outlives"),
        ({"expires_at": 10**6 + 1}, {"max_session_ttl": 180 * 86400}, "outlives"),
    ],
)
def test_mint_refused_outside_the_ceiling(mint, ceiling, error):
    grant = _ceiling_grant(LIMITS, **ceiling)
    fields = {"limits": LIMITS, "subaccounts": [], "expires_at": 2000}
    fields.update(mint)
    with pytest.raises(ValueError, match=error):
        _mint(**fields).check_within(grant, now=1500)


def test_mint_may_name_future_subaccounts_when_the_ceiling_allows():
    grant = _ceiling_grant(LIMITS, subaccounts=[], include_future_subaccounts=True)
    _mint(limits=LIMITS, subaccounts=["0x77"], expires_at=2000).check_within(grant, now=1500)


def test_first_party_grants_may_carry_block_and_settings_scopes():
    grant = _grant(builder=Builder(), scopes=["trade", "trade:block", "account:settings"])
    assert grant.to_message()["scopes"] == ["trade", "trade:block", "account:settings"]


def test_no_caps_by_default():
    big = dataclasses.replace(LIMITS, max_order_notional="100000000")
    assert _grant(limits=big).to_message()["limits"]["maxOrderNotional"] == "100000000"


@pytest.mark.parametrize(
    "build",
    [
        lambda limits: _grant(limits=limits),
        lambda limits: _passkey_grant(ceiling=Ceiling(["trade"], limits, 86400, 5)),
        lambda limits: _mint(limits=limits),
    ],
    ids=["session-grant", "passkey-ceiling", "session-mint"],
)
def test_caps_apply_wherever_limits_are_signed(build):
    caps = {"maxOrderNotional": "250000"}
    assert build(dataclasses.replace(LIMITS, max_order_notional="250000", caps=caps)).to_message()
    with pytest.raises(ValueError, match=r"limits.maxOrderNotional 250000.01 is over the cap of 250000"):
        build(dataclasses.replace(LIMITS, max_order_notional="250000.01", caps=caps)).to_message()


def test_limit_caps_are_configurable():
    big = dataclasses.replace(LIMITS, max_order_notional="1000000")
    assert _grant(limits=dataclasses.replace(big, caps={})).to_message()
    assert _grant(limits=dataclasses.replace(big, caps={"maxOrderNotional": "2000000"})).to_message()
    with pytest.raises(ValueError, match=r"limits.maxLoss 5000.5 is over the cap of 1000"):
        _grant(limits=dataclasses.replace(LIMITS, caps={"maxLoss": "1000"})).to_message()
    with pytest.raises(ValueError, match="unknown limit"):
        _grant(limits=dataclasses.replace(LIMITS, caps={"markets": "1"})).to_message()


def test_caps_do_not_change_equality_or_hashes():
    capped = dataclasses.replace(LIMITS, caps={"maxOrderNotional": "1000000"})
    assert capped == LIMITS
    assert _grant(limits=capped).eip712_hash(ARBITRUM) == _grant().eip712_hash(ARBITRUM)


def test_none_is_over_any_cap():
    limits = dataclasses.replace(UNCAPPED, caps={"maxLeverage": "50"})
    with pytest.raises(ValueError, match=r"limits\.maxLeverage none is over the cap of 50"):
        _grant(builder=Builder(), limits=limits).to_message()


def test_no_builder_renders_as_the_canonical_none():
    assert _grant(builder=Builder("0x00", "0", 0), limits=LIMITS).to_message()["builder"] == {
        "account": "0x0",
        "maxFeeRate": "0",
        "expiresAt": 0,
    }


@pytest.mark.parametrize(
    "market", ["kPEPE-USD-PERP", "NEAR-USD-27NOV26-5_4-C", "btc-usd-perp", "*-USD-PERP", "BTC-*", "*", "X"]
)
def test_valid_markets(market):
    assert _grant(limits=_markets(market)).to_message()["limits"]["markets"] == [market]


def test_address_fields_accept_ints():
    message = _grant(builder=Builder(0xB1, "0.0005"), account=0x123ABC).to_message()
    assert message["builder"]["account"] == "0xb1"
    assert message["account"] == "0x123abc"


@pytest.mark.parametrize(("ttl", "sessions"), [("86400", 5), (86400, "5"), (True, 5)])
def test_ceiling_integers_are_type_checked(ttl, sessions):
    with pytest.raises(ValueError, match=r"2\^53"):
        _passkey_grant(ceiling=Ceiling(["trade"], LIMITS, ttl, sessions)).to_message()


def test_snip12_message_carries_integers_as_decimal_strings():
    message = _grant().snip12_typed_data()["message"]
    assert message["issuedAt"] == "1700000000"
    assert message["builder"]["expiresAt"] == "0"


def test_limits_default_to_no_caps():
    assert Limits().to_message() == {
        "maxOrderNotional": "none",
        "maxOpenNotional": "none",
        "dailyNotional": "none",
        "maxLoss": "none",
        "maxLeverage": "none",
        "markets": ["*"],
    }
    grant = SessionGrant(
        paradex_chain=MAINNET, environment="mainnet", account="0x1", session_key="0x2", label="", scopes=["trade"]
    )
    assert grant.limits == Limits()


def test_builder_grants_and_passkeys_may_leave_max_loss_uncapped():
    assert _grant(limits=Limits()).to_message()["limits"]["maxLoss"] == "none"
    ceiling = Ceiling(["trade"], Limits(), 86400, 5)
    assert (
        _passkey_grant(ceiling=ceiling, builder_account="0xb1").to_message()["ceiling"]["limits"]["maxLoss"] == "none"
    )
