from unittest.mock import Mock

import pytest

from paradex_py.account.account import ParadexAccount
from paradex_py.api.generated.requests import BlockTradeRequest
from paradex_py.api.generated.responses import BlockTradeDetailFullResponse


def _account() -> ParadexAccount:
    """An account stubbed below the guard.

    `sign_block_trade` is what actually hashes the typed data, and hashing an
    empty merkle tree is the failure being guarded. Mocking it proves the guard
    fires first and that nothing was signed.
    """
    account = ParadexAccount.__new__(ParadexAccount)
    account.l2_address = 1
    account.sign_block_trade = Mock()
    return account


def test_signing_refuses_a_block_with_no_trades():
    """An unparseable response reduced to its id must not sign as an empty tree.

    Without this the failure surfaces from inside the typed-data library as
    "Cannot build Merkle tree from an empty list of leaves", naming leaves
    rather than the block that had none.
    """
    account = _account()
    stub = BlockTradeDetailFullResponse.model_validate({"block_id": "0xabc"})

    with pytest.raises(ValueError, match="has no trades to sign"):
        account.build_executor_signature_for_block(stub)

    account.sign_block_trade.assert_not_called()


def test_signing_refuses_an_offer_with_no_trades():
    """Same guard on the offer-based path, which signs one block per offer."""
    account = _account()
    stub = BlockTradeDetailFullResponse.model_validate({"block_id": "0xoffer"})

    with pytest.raises(ValueError, match="has no trades to sign"):
        account.build_executor_signatures_for_offers([stub])

    account.sign_block_trade.assert_not_called()


def test_signing_a_request_with_no_trades_is_refused():
    """The third caller: a request built locally rather than from a response.

    It reaches the same merkle failure on empty trades, which is why the check
    lives in build_block_trade_signature rather than at each call site.
    """
    account = _account()
    request = BlockTradeRequest.model_validate(
        {"nonce": "1", "block_expiration": 1, "trades": {}, "signatures": {}, "required_signers": []}
    )

    with pytest.raises(ValueError, match="has no trades to sign"):
        account.sign_block_trade_request(request)

    account.sign_block_trade.assert_not_called()
