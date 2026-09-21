"""SBE (Simple Binary Encoding) decoder for Paradex WebSocket binary frames.

Schema ID=1 (paradex_1_0.xml). The decoder understands ``codec._SCHEMA_VERSION``;
what it asks for on connect is ``NEGOTIATED_SCHEMA_VERSION``, which lags behind
on purpose — see below.

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

# Version requested in the connect URL. Every environment caps negotiation at
# FEATURE_FLAG_SBE_MAX_VERSION, and anything above the cap is a 400 at connect,
# not a downgrade — so a decoder that can read a newer version must still ask
# for the served one. The order is: ship the decoder, let installs turn over,
# then raise this once the server cap goes up.
NEGOTIATED_SCHEMA_VERSION = 1

__all__ = [
    "NEGOTIATED_SCHEMA_VERSION",
    "AccountEventData",
    "BboEventData",
    "BookEventData",
    "FillEventData",
    "FundingDataEventData",
    "MarketSummaryEventData",
    "OrderEventData",
    "PositionEventData",
    "SbeDecodeError",
    "TradeEventData",
    "decode_frame",
]
