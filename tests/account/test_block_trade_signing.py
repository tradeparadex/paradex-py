from unittest.mock import Mock

import pytest

from paradex_py.account.account import ParadexAccount
from paradex_py.api.generated.responses import BlockTradeDetailFullResponse


def test_signing_refuses_a_block_with_no_trades():
    """An unparseable response reduced to its id must not sign as an empty tree.

    Without this the failure surfaces from inside the typed-data library as
    "Cannot build Merkle tree from an empty list of leaves", naming leaves
    rather than the block that had none.
    """
    account = ParadexAccount.__new__(ParadexAccount)
    account.build_block_trade_signature = Mock()
    stub = BlockTradeDetailFullResponse.model_validate({"block_id": "0xabc"})

    with pytest.raises(ValueError, match="has no trades to sign"):
        account.build_executor_signature_for_block(stub)

    account.build_block_trade_signature.assert_not_called()


def test_signing_refuses_an_offer_with_no_trades():
    """Same guard on the offer-based path, which signs one block per offer."""
    account = ParadexAccount.__new__(ParadexAccount)
    account.build_block_trade_signature = Mock()
    stub = BlockTradeDetailFullResponse.model_validate({"block_id": "0xoffer"})

    with pytest.raises(ValueError, match="has no trades to sign"):
        account.build_executor_signatures_for_offers([stub])

    account.build_block_trade_signature.assert_not_called()
