from typing import Any, Dict, List, Optional, Protocol, Union

from paradex_py.api.generated.requests import (
    BlockExecuteRequest,
    BlockOfferRequest,
    BlockTradeRequest,
)
from paradex_py.api.generated.responses import (
    APIResults,
    BlockTradeDetailFullResponse,
    PaginatedAPIResults,
)


class ApiClientProtocol(Protocol):
    """Protocol defining the interface expected by BlockTradesMixin."""

    def _get_authorized(self, path: str, params: Optional[dict] = None) -> dict:
        """Make authorized GET request."""
        ...

    def _post_authorized(
        self,
        path: str,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        """Make authorized POST request."""
        ...

    def _delete_authorized(self, path: str, params: Optional[dict] = None, payload: Optional[dict] = None) -> dict:
        """Make authorized DELETE request."""
        ...


class BlockTradesMixin:
    """Mixin class for Block Trades API endpoints.

    This mixin provides all block trades functionality to be mixed into ParadexApiClient.
    """

    # Type hint for the mixin to indicate it expects these methods
    _get_authorized: Any
    _post_authorized: Any
    _delete_authorized: Any

    def _parse_block_trade_list_response(self, response: dict) -> PaginatedAPIResults:
        """Parse block trade list response to typed model."""
        try:
            # Transform the results to typed BlockTradeDetailFullResponse objects
            typed_results = []
            if response.get("results"):
                for item in response["results"]:
                    typed_results.append(BlockTradeDetailFullResponse.model_validate(item))

            return PaginatedAPIResults(
                next=response.get("next"),
                prev=response.get("prev"),
                results=[result.model_dump() for result in typed_results],
            )
        except Exception:
            # Fallback to original response if parsing fails
            return PaginatedAPIResults.model_validate(response)

    def _parse_block_trade_response(self, response: dict) -> BlockTradeDetailFullResponse:
        """Parse single block trade response to typed model."""
        try:
            # Pre-process the response to add missing required fields
            if isinstance(response, dict) and "trades" in response:
                for _trade_key, trade_data in response["trades"].items():
                    if "maker_order" in trade_data and isinstance(trade_data["maker_order"], dict):
                        # Add default instruction if missing
                        if "instruction" not in trade_data["maker_order"]:
                            trade_data["maker_order"]["instruction"] = "GTC"

            return BlockTradeDetailFullResponse.model_validate(response)
        except Exception:
            # Fallback to simple response with just the ID
            block_id = response.get("id") or response.get("block_id") if isinstance(response, dict) else None
            return BlockTradeDetailFullResponse.model_validate({"block_id": block_id})

    def _parse_offers_response(self, response: dict) -> APIResults:
        """Parse offers list response to typed model."""
        try:
            return APIResults.model_validate(response)
        except Exception:
            # Fallback to original response if parsing fails
            return APIResults.model_validate({"results": [response]})

    def list_block_trades(
        self,
        status: Optional[str] = None,
        market: Optional[str] = None,
    ) -> PaginatedAPIResults:
        """Get a paginated list of block trades with filtering.

        Returns block trades where user is initiator, required signer,
        or has submitted an offer.

        Args:
            status: Block trade status filter (CREATED, OFFER_COLLECTION, READY_TO_EXECUTE, EXECUTING, COMPLETED, CANCELLED)
            market: Market symbol filter (e.g., BTC-USD-PERP)

        Returns:
            Paginated list with block trade details and navigation metadata.
        """
        params = {}
        if status:
            params["status"] = status
        if market:
            params["market"] = market

        response = self._get_authorized(path="block-trades", params=params)
        return self._parse_block_trade_list_response(response)

    def create_block_trade(self, block_trade: BlockTradeRequest) -> BlockTradeDetailFullResponse:
        """Create a parent block trade for multi-party execution.

        Block trades coordinate execution across multiple parties.
        The initiator creates a parent block trade specifying trade details and
        required signers, who must submit offers before execution.

        Args:
            block_trade: Block trade request with trade details and signatures

        Returns:
            Created block trade details
        """
        payload = block_trade.model_dump() if hasattr(block_trade, "model_dump") else block_trade.model_dump()
        response = self._post_authorized(path="block-trades", payload=payload)
        return self._parse_block_trade_response(response)

    def get_block_trade(self, block_trade_id: str) -> BlockTradeDetailFullResponse:
        """Retrieve a specific block trade by ID with full details.

        Returns complete block trade information including status, trade details,
        signatures, and offers.

        Args:
            block_trade_id: Block Trade ID

        Returns:
            Block trade details with status, signatures, and offers
        """
        response = self._get_authorized(path=f"block-trades/{block_trade_id}")
        return self._parse_block_trade_response(response)

    def cancel_block_trade(self, block_trade_id: str) -> Dict:
        """Cancel a pending block trade.

        Only the initiator can cancel a block trade in cancellable state
        (CREATED, OFFER_COLLECTION, READY_TO_EXECUTE).
        Once cancelled, all associated offers become invalid.

        Args:
            block_trade_id: Block Trade ID

        Returns:
            Success message confirming cancellation
        """
        return self._delete_authorized(path=f"block-trades/{block_trade_id}")

    def execute_block_trade(
        self, block_trade_id: str, execution_request: BlockExecuteRequest
    ) -> BlockTradeDetailFullResponse:
        """Execute a block trade with selected offers.

        Executes a parent block trade by selecting specific offers from required signers.

        Args:
            block_trade_id: Block Trade ID
            execution_request: Block execution parameters with selected offers

        Returns:
            Executed block trade with status and fill details
        """
        payload = (
            execution_request.model_dump()
            if hasattr(execution_request, "model_dump")
            else execution_request.model_dump()
        )
        response = self._post_authorized(path=f"block-trades/{block_trade_id}/execute", payload=payload)
        return self._parse_block_trade_response(response)

    def get_block_trade_offers(self, block_trade_id: str) -> APIResults:
        """Get all offers for a specific block trade.

        Returns all offers submitted for a parent block trade by required signers.

        Args:
            block_trade_id: Parent Block Trade ID

        Returns:
            Array of offers with offer details and signatures
        """
        response = self._get_authorized(path=f"block-trades/{block_trade_id}/offers")
        return self._parse_offers_response(response)

    def create_block_trade_offer(self, block_trade_id: str, offer: BlockOfferRequest) -> BlockTradeDetailFullResponse:
        """Create a sub-block offer for an existing block trade.

        Required signers submit their order details and pricing for
        markets defined in the parent block trade.

        Args:
            block_trade_id: Parent Block Trade ID
            offer: Block offer content with order details and signatures

        Returns:
            Created offer with unique ID and parent reference
        """
        payload = offer.model_dump() if hasattr(offer, "model_dump") else offer.model_dump()
        response = self._post_authorized(path=f"block-trades/{block_trade_id}/offers", payload=payload)
        return self._parse_block_trade_response(response)

    def get_block_trade_offer(self, block_trade_id: str, offer_id: str) -> BlockTradeDetailFullResponse:
        """Get a specific offer by ID for a block trade.

        Retrieves detailed information about an offer submitted for a parent block trade.

        Args:
            block_trade_id: Parent Block Trade ID
            offer_id: Offer ID

        Returns:
            Offer details with market-specific order information
        """
        response = self._get_authorized(path=f"block-trades/{block_trade_id}/offers/{offer_id}")
        return self._parse_block_trade_response(response)

    def cancel_block_trade_offer(self, block_trade_id: str, offer_id: str) -> Dict:
        """Cancel a pending offer for a block trade.

        Only the offering account can cancel their own offer if it's in
        a cancellable state and the parent block trade is still active.

        Args:
            block_trade_id: Parent Block Trade ID
            offer_id: Offer ID

        Returns:
            Success message confirming offer cancellation
        """
        return self._delete_authorized(path=f"block-trades/{block_trade_id}/offers/{offer_id}")

    def execute_block_trade_offer(
        self, block_trade_id: str, offer_id: str, execution_request: BlockExecuteRequest
    ) -> BlockTradeDetailFullResponse:
        """Execute a specific offer independently of the parent block trade.

        Executes an individual offer without waiting for full block trade execution.

        Args:
            block_trade_id: Parent Block Trade ID
            offer_id: Offer ID
            execution_request: Offer execution parameters

        Returns:
            Executed offer with status, fill details, and timestamps
        """
        payload = (
            execution_request.model_dump()
            if hasattr(execution_request, "model_dump")
            else execution_request.model_dump()
        )
        response = self._post_authorized(
            path=f"block-trades/{block_trade_id}/offers/{offer_id}/execute", payload=payload
        )
        return self._parse_block_trade_response(response)
