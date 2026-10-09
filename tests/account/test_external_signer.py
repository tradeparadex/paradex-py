import asyncio
import base64
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starknet_py.common import int_from_hex
from starknet_py.net.signer.key_pair import KeyPair

from paradex_py.account import ExternalSignature, ExternalSignerAccount, HeaderSigner
from paradex_py.account.subkey_account import SubkeyAccount
from paradex_py.account.utils import flatten_signature, message_signature
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.generated.requests import (
    BlockExecuteRequest,
    BlockOfferInfo,
    BlockOfferRequest,
    BlockTradeInfo,
    BlockTradeRequest,
)
from paradex_py.api.generated.responses import (
    BlockTradeConstraints,
    BlockTradeDetailFullResponse,
    BlockTradeSignature,
    SignatureType,
)
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import TESTNET
from tests.api.test_account import TEST_L2_PRIVATE_KEY as L2_PRIVATE_KEY
from tests.message.test_block_trades import _maker_dto
from tests.mocks.api_client import MockApiClient

L2_ADDRESS = "0x129c135ed63df9353885e292be4426b8ed6122b13c6c0e1bb787288a1f5adfa"
FRESH_JWT_CLAIMS = base64.urlsafe_b64encode(b'{"exp":4102444800}').decode().rstrip("=")
L2_PUBLIC_KEY = hex(KeyPair.from_private_key(int_from_hex(L2_PRIVATE_KEY)).public_key)


class KeyInAnotherProcess:
    """Stands in for a signer holding the key elsewhere: signs only the hash it is handed."""

    def __init__(self):
        self.hashes: list[int] = []

    def sign_hash(self, message_hash: int) -> ExternalSignature:
        self.hashes.append(message_hash)
        r, s = message_signature(message_hash, int_from_hex(L2_PRIVATE_KEY))
        return ExternalSignature(signature=flatten_signature([r, s]), headers={"X-Signer-Header": "seen"})


def _order(order_id: str | None = None) -> Order:
    return Order(
        market="BTC-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal("50000"),
        client_id="external-signer-test",
        order_id=order_id,
        signature_timestamp=1706868900000,
    )


def _accounts():
    config = MockApiClient().fetch_system_config()
    signer = KeyInAnotherProcess()
    external = ExternalSignerAccount(config=config, l2_address=L2_ADDRESS, l2_public_key=L2_PUBLIC_KEY, signer=signer)
    local = SubkeyAccount(config=config, l2_private_key=L2_PRIVATE_KEY, l2_address=L2_ADDRESS)
    return external, local, signer


@pytest.mark.parametrize("order_id", [None, "existing-order"])
def test_external_signer_signs_the_same_order_message_as_a_local_key(order_id):
    external, local, _ = _accounts()

    assert external.sign_order(_order(order_id)) == local.sign_order(_order(order_id))
    assert external.take_request_headers() == {"X-Signer-Header": "seen"}
    assert external.take_request_headers() == {}


def test_external_signer_signs_the_same_auth_message_as_a_local_key():
    external, local, _ = _accounts()
    with patch("paradex_py.account.account.time.time", return_value=1706868900):
        external_headers = external.auth_headers()
        local_headers = local.auth_headers()

    assert external_headers["PARADEX-STARKNET-SIGNATURE"] == local_headers["PARADEX-STARKNET-SIGNATURE"]
    assert external_headers["X-Signer-Header"] == "seen"
    assert external.take_request_headers() == {}


def test_header_signer_sends_the_hash_as_32_bytes_and_returns_its_stand_in():
    result = HeaderSigner(header="X-Signer-Header", signature="stand-in").sign_hash(0xABC)

    assert result.signature == "stand-in"
    raw = base64.b64decode(result.headers["X-Signer-Header"])
    assert len(raw) == 32
    assert int.from_bytes(raw, "big") == 0xABC


def _client(account) -> ParadexApiClient:
    with patch.object(ParadexApiClient, "fetch_system_config", return_value=MockApiClient().fetch_system_config()):
        client = ParadexApiClient(env=TESTNET)
    client.account = account
    return client


def _trade() -> BlockTradeInfo:
    return BlockTradeInfo(
        maker_order=_maker_dto(account=L2_ADDRESS),
        price="1500",
        size="0.1",
        taker_order=None,
        trade_constraints=BlockTradeConstraints(min_price="1425", max_price="1575", min_size="0.1", max_size="0.5"),
    )


def _block_request() -> BlockTradeRequest:
    return BlockTradeRequest(
        nonce="1",
        block_expiration=1700000300000,
        required_signers=[L2_ADDRESS],
        signatures={},
        trades={"ETH-USD-PERP": _trade()},
    )


def _offer_request() -> BlockOfferRequest:
    placeholder = BlockTradeSignature(
        nonce="0",
        signature_data="unsigned",
        signature_expiration=0,
        signature_timestamp=0,
        signature_type=SignatureType.starknet,
        signer_account=L2_ADDRESS,
    )
    return BlockOfferRequest(
        nonce="1",
        offering_account=L2_ADDRESS,
        signature=placeholder,
        trades={"ETH-USD-PERP": BlockOfferInfo(offerer_order=_maker_dto(account=L2_ADDRESS), price="1500", size="0.1")},
    )


def _block_response(block_id: str) -> BlockTradeDetailFullResponse:
    return BlockTradeDetailFullResponse.model_validate(
        {"block_id": block_id, "trades": {"ETH-USD-PERP": _trade().model_dump()}}
    )


def test_submit_and_modify_send_the_signer_headers_with_the_order():
    client = _client(_accounts()[0])

    with patch.object(client, "_post_authorized", return_value={}) as post:
        client.submit_order(_order())
    assert post.call_args.kwargs["headers"] == {"X-Signer-Header": "seen"}

    with patch.object(client, "_put_authorized", return_value={}) as put:
        client.modify_order("existing-order", _order("existing-order"))
    assert put.call_args.kwargs["headers"] == {"X-Signer-Header": "seen"}


def test_a_batch_of_one_order_sends_the_signer_headers():
    client = _client(_accounts()[0])

    with patch.object(client, "_post_authorized", return_value={}) as post:
        client.submit_orders_batch([_order()])
    assert post.call_args.kwargs["headers"] == {"X-Signer-Header": "seen"}


def test_a_batch_of_several_orders_is_refused_and_the_next_order_goes_through():
    client = _client(_accounts()[0])

    with patch.object(client, "_post_authorized", return_value={}) as post:
        with pytest.raises(ValueError, match="one signature"):
            client.submit_orders_batch([_order(), _order()])
        post.assert_not_called()

        client.submit_order(_order())
    assert post.call_args.kwargs["headers"] == {"X-Signer-Header": "seen"}


def test_an_order_whose_request_failed_leaves_nothing_behind():
    client = _client(_accounts()[0])

    with (
        patch.object(client, "_post_authorized", side_effect=ConnectionError("down")),
        pytest.raises(ConnectionError),
    ):
        client.submit_order(_order())

    with patch.object(client, "_post_authorized", return_value={}) as post:
        client.submit_order(_order())
    assert post.call_args.kwargs["headers"] == {"X-Signer-Header": "seen"}


def test_a_signature_never_sent_is_refused_once_then_signing_works_again():
    external, _, _ = _accounts()
    external.sign_order(_order())

    with pytest.raises(ValueError, match="one signature"):
        external.sign_order(_order())

    external.sign_order(_order())
    assert external.take_request_headers() == {"X-Signer-Header": "seen"}


def test_an_algo_order_sends_the_signer_headers():
    client = _client(_accounts()[0])

    with patch.object(client, "_post_authorized", return_value={}) as post:
        client.submit_algo_order(_order(), algo_type="TWAP", duration_seconds=60)
    assert post.call_args.kwargs["headers"] == {"X-Signer-Header": "seen"}


def _record_posts(client: ParadexApiClient) -> list[tuple[str, dict | None]]:
    """Expire the JWT and record every POST, answering auth with a fresh token."""
    client.auto_auth = True
    client._token_exp = 0
    sent: list[tuple[str, dict | None]] = []

    def post(api_url, path, payload=None, params=None, headers=None):
        sent.append((path, headers))
        return {"jwt_token": f"a.{FRESH_JWT_CLAIMS}.c"} if path.startswith("auth/") else {}

    client.post = post
    return sent


def test_an_order_with_an_expired_jwt_reauthenticates_and_carries_only_its_own_header():
    client = _client(_accounts()[0])
    sent = _record_posts(client)

    client.submit_order(_order())

    assert [path.split("/")[0] for path, _ in sent] == ["auth", "orders"]
    assert sent[1][1] == {"X-Signer-Header": "seen"}


def test_a_block_trade_with_an_expired_jwt_reauthenticates_and_carries_its_header():
    external, _, _ = _accounts()
    client = _client(external)
    sent = _record_posts(client)

    client.create_block_trade(external.sign_block_trade_request(_block_request()))

    assert [path.split("/")[0] for path, _ in sent] == ["auth", "block-trades"]
    assert sent[1][1] == {"X-Signer-Header": "seen"}


def test_a_jwt_refresh_between_signing_and_sending_keeps_the_pending_headers():
    external, _, _ = _accounts()
    client = _client(external)
    sent = _record_posts(client)
    request = external.sign_block_trade_request(_block_request())

    with patch.object(client, "get", return_value={"results": []}):
        client.fetch_orders()
    client.create_block_trade(request)

    assert [path.split("/")[0] for path, _ in sent] == ["auth", "block-trades"]
    assert sent[0][1]["X-Signer-Header"] == "seen"
    assert sent[1][1] == {"X-Signer-Header": "seen"}


def test_block_trade_requests_with_one_signature_send_the_signer_headers():
    external, _, _ = _accounts()
    client = _client(external)

    with patch.object(client, "_post_authorized", return_value={}) as post:
        client.create_block_trade(external.sign_block_trade_request(_block_request()))
        assert post.call_args.kwargs["headers"] == {"X-Signer-Header": "seen"}

        signatures = external.build_executor_signature_for_block(_block_response("b1"))
        client.execute_block_trade("b1", BlockExecuteRequest(execution_nonce="1", signatures=signatures))
        assert post.call_args.kwargs["headers"] == {"X-Signer-Header": "seen"}

        client.create_block_trade_offer("b1", external.sign_block_offer_request(_offer_request(), "b1"))
        assert post.call_args.kwargs["headers"] == {"X-Signer-Header": "seen"}

        signatures = external.build_executor_signatures_for_offers([_block_response("o1")])
        client.execute_block_trade_offer("b1", "o1", BlockExecuteRequest(execution_nonce="2", signatures=signatures))
        assert post.call_args.kwargs["headers"] == {"X-Signer-Header": "seen"}


def test_executing_several_offers_is_refused_before_anything_is_sent():
    external, _, _ = _accounts()

    with pytest.raises(ValueError, match="one signature"):
        external.build_executor_signatures_for_offers([_block_response("o1"), _block_response("o2")])
    assert external.take_request_headers() == {}


def test_a_websocket_order_is_refused():
    ws_client = ParadexWebsocketClient(env=TESTNET, auto_start_reader=False)
    ws_client.ws = MagicMock(send=AsyncMock())
    ws_client.account = _accounts()[0]

    with pytest.raises(ValueError, match="REST only"):
        asyncio.run(ws_client.submit_order(_order()))
    ws_client.ws.send.assert_not_called()


def test_a_local_key_account_sends_no_extra_headers():
    _, local, _ = _accounts()
    client = _client(local)

    with patch.object(client, "_post_authorized", return_value={}) as post:
        client.submit_order(_order())
        client.create_block_trade(local.sign_block_trade_request(_block_request()))
    assert all("headers" not in call.kwargs for call in post.call_args_list)


@pytest.mark.parametrize(("header", "signature"), [("", "stand-in"), ("X-Signer-Header", "")])
def test_header_signer_requires_a_header_and_a_stand_in(header, signature):
    with pytest.raises(ValueError, match="header and signature are required"):
        HeaderSigner(header=header, signature=signature)


def test_on_chain_operations_are_refused():
    with pytest.raises(ValueError, match="On-chain operations not supported"):
        _accounts()[0].transfer_on_l2("0x1", Decimal("1"))


def test_an_account_needs_an_address_and_a_public_key():
    config = MockApiClient().fetch_system_config()
    with pytest.raises(ValueError, match="L2 address and public key are required"):
        ExternalSignerAccount(config=config, l2_address="", l2_public_key=L2_PUBLIC_KEY, signer=KeyInAnotherProcess())
    with pytest.raises(ValueError, match="L2 address and public key are required"):
        ExternalSignerAccount(config=config, l2_address=L2_ADDRESS, l2_public_key="", signer=KeyInAnotherProcess())


def test_onboarding_signs_nothing():
    external, _, signer = _accounts()
    client = _client(external)

    with patch.object(client, "post") as post:
        client.onboarding()
    assert post.call_args.kwargs["headers"] == {}
    assert signer.hashes == []
