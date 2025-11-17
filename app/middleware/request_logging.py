import logging
from typing import Any, Dict, Optional

from fastapi import Request
from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger("vizai.request_logger")


class RequestResponseLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs incoming requests and outgoing responses for all endpoints.
    Captures method, path, query parameters, status codes, and truncated bodies for readability.
    """

    def __init__(self, app, max_body_length: int = 2048) -> None:
        super().__init__(app)
        self.max_body_length = max_body_length

    async def dispatch(self, request: Request, call_next) -> Response:
        request_body = await request.body()
        # Reconstruct the receive method so downstream handlers can access body again
        async def receive() -> Dict[str, Any]:
            return {"type": "http.request", "body": request_body, "more_body": False}

        request._receive = receive  # noqa: SLF001 - Starlette pattern for resetting body

        # Prepare request log entry
        request_payload = self._format_body(
            body_bytes=request_body, content_type=request.headers.get("content-type")
        )

        logger.info(
            "HTTP Request | %s %s | query=%s | body=%s",
            request.method,
            request.url.path,
            dict(request.query_params),
            request_payload,
        )

        response = await call_next(request)

        # Buffer response body so we can both log it and return it
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        response_payload = self._format_body(
            body_bytes=response_body, content_type=response.headers.get("content-type")
        )

        logger.info(
            "HTTP Response | %s %s | status=%s | body=%s",
            request.method,
            request.url.path,
            response.status_code,
            response_payload,
        )

        response.body_iterator = iterate_in_threadpool(iter([response_body]))
        return response

    def _format_body(self, body_bytes: bytes, content_type: Optional[str]) -> str:
        """
        Safely format body content for logging. Handles JSON and text responses,
        truncating large payloads to keep logs readable.
        """
        if not body_bytes:
            return ""

        if not content_type:
            content_type = ""

        try:
            if "application/json" in content_type:
                body_text = body_bytes.decode("utf-8")
            elif "text/" in content_type:
                body_text = body_bytes.decode("utf-8", errors="replace")
            else:
                # Non-text content; log size only
                return f"<{len(body_bytes)} bytes>"
        except UnicodeDecodeError:
            return f"<binary {len(body_bytes)} bytes>"

        if len(body_text) > self.max_body_length:
            return f"{body_text[: self.max_body_length]}... [truncated]"
        return body_text

