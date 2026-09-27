"""SBE (Simple Binary Encoding) decoder for Paradex WebSocket binary frames.

Schema ID=1 (paradex_1_0.xml). The decoder understands ``codec._SCHEMA_VERSION``;
what it asks for on connect is ``NEGOTIATED_SCHEMA_VERSION`` — see below.

Field name divergence from JSON API:
  SBE ``trade_id_str`` ↔ JSON ``id`` (TradeEvent; see below)
  SBE ``order_type`` ↔ JSON ``type``
  SBE ``seq_no``     ↔ JSON ``seq``

Trade ids: from 1:2 a ``TradeEvent`` carries ``trade_id_str``, the full
28-digit id that REST and the JSON feed call ``id``. The int64 ``trade_id`` is
deprecated: it holds only the low 64 bits of that id and can be negative, so
never key on it. ``trade_id_str`` is ``None`` only on a frame that predates it.

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
# the version it serves, and anything above the cap is a 400 at connect, not a
# downgrade — so a decoder that can read a newer version must still ask for the
# served one. The order is: ship the decoder, let installs turn over, then
# raise this once the server cap goes up.
#
# nightly, testnet and prod all serve 1:2, so this now matches the decoder.
# When the schema next moves ahead of what is served, this is the line that
# holds back, not codec._SCHEMA_VERSION.
NEGOTIATED_SCHEMA_VERSION = 2

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
