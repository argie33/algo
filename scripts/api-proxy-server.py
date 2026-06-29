#!/usr/bin/env python3
"""Local API server that runs the Lambda handler directly against local Docker PostgreSQL.

Set DB env vars before running (defaults match docker-compose.yml):
  DB_HOST       - PostgreSQL host (default: localhost)
  DB_PORT       - PostgreSQL port (default: 5432)
  DB_NAME       - Database name (default: stocks)
  DB_PASSWORD   - Database password (default: stocks)

Cognito JWT validation uses real AWS Cognito (internet required):
  COGNITO_USER_POOL_ID    - User pool ID (from setup-local-dev.ps1 or PowerShell profile)
  COGNITO_CLIENT_ID       - App client ID
  COGNITO_REGION          - Region (default: us-east-1)
"""

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

# --- Set DB env vars for local Docker PostgreSQL BEFORE importing lambda modules ---
# FAIL-FAST: Require explicit database configuration for local dev
# Do NOT cascade to fake defaults like "localhost" or "stocks" password
if not os.environ.get("DB_HOST") and not os.environ.get("LOCAL_DB_HOST"):
    raise RuntimeError(
        "[CRITICAL] Database configuration required for local API server.\n"
        "Set either:\n"
        "  DB_HOST (preferred for production-like config)\n"
        "  LOCAL_DB_HOST (for local Docker PostgreSQL)\n"
        "Do not allow silent fallback to fake/default values."
    )
if not os.environ.get("DB_PASSWORD") and not os.environ.get("LOCAL_DB_PASSWORD"):
    raise RuntimeError(
        "[CRITICAL] Database password required for local API server.\n"
        "Set either:\n"
        "  DB_PASSWORD (preferred for production-like config)\n"
        "  LOCAL_DB_PASSWORD (for local Docker PostgreSQL)\n"
        "Do not use placeholder passwords like 'stocks'."
    )

# Now set explicit values from provided env vars or LOCAL_* variants
os.environ.setdefault("DB_HOST", os.environ.get("LOCAL_DB_HOST", ""))
os.environ.setdefault("DB_PORT", os.environ.get("LOCAL_DB_PORT", ""))
os.environ.setdefault("DB_NAME", os.environ.get("LOCAL_DB_NAME", ""))
os.environ.setdefault("DB_PASSWORD", os.environ.get("LOCAL_DB_PASSWORD", ""))
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")

# --- Set up sys.path for lambda imports ---
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LAMBDA_API_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "lambda", "api"))
_PROJECT_ROOT = os.path.normpath(os.path.join(_THIS_DIR, ".."))
for _p in (_LAMBDA_API_DIR, _PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

try:
    import lambda_function

    _handler = lambda_function.lambda_handler
    logger.info(
        f"Lambda handler loaded — DB_HOST={os.environ['DB_HOST']} DB_PORT={os.environ['DB_PORT']} DB_NAME={os.environ['DB_NAME']}"
    )
except Exception as _err:
    logger.error(f"Failed to import lambda_function: {_err}", exc_info=True)
    _handler = None


class _MockContext:
    function_name = "algo-api-local"
    function_version = "$LATEST"
    invoked_function_arn = "arn:aws:lambda:local:000000000000:function:algo-api-local"
    memory_limit_in_mb = 512
    aws_request_id = "local-dev-request"
    log_group_name = "/local/algo-api"
    log_stream_name = "local"

    def get_remaining_time_in_millis(self) -> int:
        return 28000


class _APIHandler(BaseHTTPRequestHandler):
    def _cors_headers(self) -> dict[str, str]:
        origin = self.headers.get("Origin", "")
        if origin.startswith("http://localhost"):
            return {
                "Access-Control-Allow-Origin": origin,
                "Vary": "Origin",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
                "Access-Control-Allow-Credentials": "true",
            }
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
        }

    def _read_body(self) -> str | None:
        """Read request body from stream. Returns None if no Content-Length or zero-length body.

        Logs at DEBUG level when body is empty (typical for GET/DELETE with no payload).
        """
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            logger.debug("No request body (Content-Length: 0)")
            return None
        body = self.rfile.read(length).decode("utf-8")
        logger.debug(f"Request body read: {len(body)} bytes")
        return body

    def _build_event(self, method: str, body: str | None = None) -> dict[str, Any]:
        parsed = urlparse(self.path)
        qs = parsed.query
        params = {k: v[0] for k, v in parse_qs(qs, keep_blank_values=True).items()} if qs else None
        headers = {k.lower(): v for k, v in self.headers.items()}
        event = {
            "version": "2.0",
            "routeKey": f"{method} {parsed.path}",
            "rawPath": parsed.path,
            "path": parsed.path,
            "rawQueryString": qs,
            "queryStringParameters": params,
            "headers": headers,
            "requestContext": {
                "http": {
                    "method": method,
                    "path": parsed.path,
                    "sourceIp": "127.0.0.1",
                    "userAgent": headers.get("user-agent", "local-dev"),
                }
            },
            "isBase64Encoded": False,
        }
        if body is not None:
            event["body"] = body
        return event

    def _invoke(self, method: str, body: str | None = None) -> None:
        if not _handler:
            self._write(503, '{"error":"Lambda handler not loaded — check startup logs"}')
            return
        event = self._build_event(method, body)
        path = event.get("path", "?")

        try:
            open("C:\\Users\\arger\\AppData\\Local\\Temp\\proxy_calling_handler.txt", "w").write(f"path={path}")
            result = _handler(event, _MockContext())
            open("C:\\Users\\arger\\AppData\\Local\\Temp\\proxy_handler_returned.txt", "w").write(
                f"status={result.get('statusCode')}"
            )
        except Exception as exc:
            logger.error(f"Handler raised: {exc}", exc_info=True)
            result = {"statusCode": 500, "body": json.dumps({"error": str(exc)})}

        status = result.get("statusCode", 200)
        body_out = result.get("body", "{}")
        if isinstance(body_out, (dict, list)):
            body_out = json.dumps(body_out)
        lambda_headers = {
            k: v for k, v in (result.get("headers") or {}).items() if not k.lower().startswith("access-control")
        }
        self._write(status, body_out, lambda_headers)

    def _write(self, status: int, body_str: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for k, v in self._cors_headers().items():
            self.send_header(k, v)
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body_str.encode("utf-8"))

    def do_GET(self) -> None:
        self._invoke("GET")

    def do_DELETE(self) -> None:
        self._invoke("DELETE")

    def do_POST(self) -> None:
        self._invoke("POST", self._read_body())

    def do_PUT(self) -> None:
        self._invoke("PUT", self._read_body())

    def do_PATCH(self) -> None:
        self._invoke("PATCH", self._read_body())

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        for k, v in self._cors_headers().items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        status = args[1] if len(args) >= 2 else "?"
        logger.info(f"{self.command} {self.path} -> {status}")


if __name__ == "__main__":
    port = int(os.environ.get("LOCAL_API_PORT", "3001"))
    httpd = HTTPServer(("127.0.0.1", port), _APIHandler)
    logger.info(f"Local API server on http://localhost:{port}")
    logger.info("Requests routed through lambda_function.lambda_handler → local PostgreSQL")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()
        logger.info("Server stopped")
