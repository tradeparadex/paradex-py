import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paradex_py.api.api_client import ParadexApiClient
    from paradex_py.api.ws_client import ParadexWebsocketClient


class _ClientBase:
    """Shared ``close()`` / ``__del__`` logic for Paradex client classes.

    Subclasses must set ``self.ws_client`` and ``self.api_client`` in ``__init__``.
    """

    ws_client: "ParadexWebsocketClient | None"
    api_client: "ParadexApiClient"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self):
        """Close all connections and clean up resources.

        This method should be called when done using the client instance
        to properly clean up websocket connections and background tasks.

        Examples:
            >>> import asyncio
            >>> from paradex_py import Paradex
            >>> from paradex_py.environment import Environment
            >>> async def main():
            ...     paradex = Paradex(env=Environment.TESTNET)
            ...     try:
            ...         # Use paradex instance
            ...         pass
            ...     finally:
            ...         await paradex.close()
            >>> asyncio.run(main())
        """
        if hasattr(self, "ws_client") and self.ws_client:
            await self.ws_client.close()
        if hasattr(self, "api_client") and self.api_client and hasattr(self.api_client, "client"):
            self.api_client.client.close()

    def __del__(self):
        """Cleanup when instance is destroyed."""
        if (
            hasattr(self, "ws_client")
            and self.ws_client
            and hasattr(self.ws_client, "_reader_task")
            and self.ws_client._reader_task
        ):
            try:
                asyncio.get_running_loop()
                if not self.ws_client._reader_task.done():
                    self.ws_client._reader_task.cancel()
            except (RuntimeError, AttributeError):
                pass
