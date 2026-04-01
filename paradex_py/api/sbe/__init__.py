"""SBE (Simple Binary Encoding) decoder for Paradex WebSocket binary frames.

Schema ID=1, Version=0 (paradex_1_0.xml).

Field name divergence from JSON API:
  SBE ``trade_id``   ↔ JSON ``id``
  SBE ``order_type`` ↔ JSON ``type``
  SBE ``seq_no``     ↔ JSON ``seq``

BookEvent produces ``bids``/``asks`` arrays of ``[price_str, size_str]`` pairs.
The JSON ``order_book`` channel produces ``inserts``/``updates``/``deletes`` dicts.
"""

from .codec import (
    AccountEventData,
    BboEventData,
    BookEventData,
    FillEventData,
    FundingDataEventData,
    MarketSummaryEventData,
    OrderEventData,
    PositionEventData,
    SbeDecodeError,
    TradeEventData,
    decode_frame,
)

__all__ = [
    "decode_frame",
    "SbeDecodeError",
    "TradeEventData",
    "BboEventData",
    "BookEventData",
    "MarketSummaryEventData",
    "FundingDataEventData",
    "OrderEventData",
    "FillEventData",
    "PositionEventData",
    "AccountEventData",
]
