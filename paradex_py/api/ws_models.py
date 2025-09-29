"""
WebSocket RPC message models for type-safe simulation and validation.

Simplified models focusing on JSON-RPC 2.0 structure for WebSocket messages.
"""
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JSONRPCRequest(BaseModel):
    """Standard JSON-RPC 2.0 request."""

    model_config = ConfigDict(extra="allow")

    jsonrpc: str = Field("2.0", description="JSON-RPC version")
    method: str = Field(..., description="RPC method name")
    params: Any | None = Field(None, description="Method parameters")
    request_id: str | int | None = Field(None, alias="id", description="Request ID (string, number, or null)")


class JSONRPCResponse(BaseModel):
    """Standard JSON-RPC 2.0 response."""

    model_config = ConfigDict(extra="allow")

    jsonrpc: str = Field("2.0", description="JSON-RPC version")
    response_id: str | int | None = Field(None, alias="id", description="Request ID (string, number, or null)")
    result: Any | None = Field(None, description="Success result")
    error: dict[str, Any] | None = Field(None, description="Error object")


class WebSocketDataMessage(BaseModel):
    """WebSocket data message (non-RPC)."""

    model_config = ConfigDict(extra="allow")

    params: dict[str, Any] = Field(..., description="Message parameters")
    data: Any = Field(..., description="Message data payload")


# Utility functions for WebSocket simulation
def validate_ws_message(message_data: dict[str, Any]) -> BaseModel | None:
    """Validate a WebSocket message against appropriate structure.

    Args:
        message_data: Raw WebSocket message data

    Returns:
        Validated message model or None if validation fails
    """
    try:
        # Try as JSON-RPC request
        if "method" in message_data:
            return JSONRPCRequest.model_validate(message_data)
        # Try as JSON-RPC response
        elif "jsonrpc" in message_data:
            return JSONRPCResponse.model_validate(message_data)
        # Try as data message
        elif "params" in message_data and "data" in message_data:
            return WebSocketDataMessage.model_validate(message_data)
        else:
            return None
    except Exception as e:
        # Log validation errors for debugging
        import logging

        logging.getLogger(__name__).debug(f"WebSocket message validation failed: {e}")
        return None


def create_subscription_request(channel: str, request_id: str | int | None = None) -> str:
    """Create a WebSocket subscription request JSON string."""
    import time

    if request_id is None:
        request_id = str(int(time.time() * 1_000_000))

    request = JSONRPCRequest(method="subscribe", params={"channel": channel}, id=request_id)

    return json.dumps(request.model_dump())


def create_auth_request(jwt_token: str, request_id: str | int | None = None) -> str:
    """Create a WebSocket authentication request JSON string."""
    import time

    if request_id is None:
        request_id = str(int(time.time() * 1_000_000))

    request = JSONRPCRequest(method="auth", params={"bearer": jwt_token}, id=request_id)

    return json.dumps(request.model_dump())


def create_data_message(channel: str, data: Any) -> str:
    """Create a WebSocket data message JSON string."""
    message = WebSocketDataMessage(params={"channel": channel}, data=data)

    return json.dumps(message.model_dump())


def create_success_response(request_id: str | int, result: Any) -> str:
    """Create a successful JSON-RPC response."""
    response = JSONRPCResponse(id=request_id, result=result)

    return json.dumps(response.model_dump())


def create_error_response(request_id: str | int, code: int, message: str) -> str:
    """Create an error JSON-RPC response."""
    response = JSONRPCResponse(id=request_id, error={"code": code, "message": message})

    return json.dumps(response.model_dump())


# Note: For payload validation, use the generated models in paradex_py.api.generated.responses
# This module focuses on JSON-RPC message structure only


# Re-export for convenience
__all__ = [
    # JSON-RPC 2.0 models
    "JSONRPCRequest",
    "JSONRPCResponse",
    "WebSocketDataMessage",
    # Utility functions
    "validate_ws_message",
    "create_subscription_request",
    "create_auth_request",
    "create_data_message",
    "create_success_response",
    "create_error_response",
]
