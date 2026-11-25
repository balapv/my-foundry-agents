"""Consistent error responses for the mock tools.

Foundry's OpenAPI tool treats any non-2xx response as a failed tool call and ends the
agent response before the model sees the error body. The model then cannot tell the
customer that a reservation was not found or that a system is temporarily unavailable.
Tool endpoints therefore return HTTP 200 with ``{"error": {code, message, httpStatus,
retryable}}``. ``httpStatus`` records the conventional status for logs and clients.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def error_body(status_code: int, code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "httpStatus": status_code,
                      "retryable": status_code in RETRYABLE_STATUSES}}


def tool_error(status_code: int, code: str, message: str) -> JSONResponse:
    """Error returned to the agent: HTTP 200 so the model can read and explain it."""
    return JSONResponse(status_code=200, content=error_body(status_code, code, message))


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Plain HTTP error for non-tool endpoints."""
    return JSONResponse(status_code=status_code, content=error_body(status_code, code, message))
