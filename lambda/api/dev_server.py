#!/usr/bin/env python3
"""Local development server for Lambda API.

Runs the Lambda function locally on port 3001 for frontend development.
Usage: python dev_server.py
"""

import importlib
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

os.environ["ENVIRONMENT"] = "development"

# For dev_server: Default to LOCAL_MODE=true unless explicitly disabled (LOCAL_MODE=false)
# This ensures local development "just works" without extra configuration
if "LOCAL_MODE" not in os.environ:
    os.environ["LOCAL_MODE"] = "true"
    print("[DEV_SERVER] AUTO: Setting LOCAL_MODE=true for local development", flush=True)


# Load database credentials from AWS Secrets Manager (real AWS data) or environment variables
def _load_db_credentials() -> dict[str, Any]:
    """Load DB credentials from AWS Secrets Manager if available, else environment variables.

    Behavior controlled by LOCAL_MODE environment variable:
    - LOCAL_MODE=true (default): Use localhost postgres (development only)
    - LOCAL_MODE=false: Use AWS Secrets Manager (production/testing against RDS)
    """
    # Check if explicitly running in local mode (defaults to true for dev_server)
    local_mode = os.getenv("LOCAL_MODE", "").lower() == "true"

    # If LOCAL_MODE is explicitly enabled, skip AWS and use localhost immediately
    if local_mode:
        print("[DEV_SERVER] Using localhost postgres (LOCAL_MODE=true)", flush=True)
        return {
            "host": "localhost",
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "stocks"),
            "database": os.getenv("DB_NAME", "stocks"),
        }

    # Try to load from Secrets Manager first (requires AWS credentials)
    try:
        import json

        import boto3

        sm = boto3.client("secretsmanager")
        secret_arn = os.getenv("DB_SECRET_ARN", "algo/database")
        secret = sm.get_secret_value(SecretId=secret_arn)
        secret_string = secret.get("SecretString")
        if not secret_string:
            raise ValueError("[CRITICAL] SecretString missing from AWS Secrets Manager response")
        creds = json.loads(secret_string)

        host = creds.get("host")
        user = creds.get("username")
        password = creds.get("password")

        if not host or not user or not password:
            raise ValueError(
                f"Secrets Manager returned incomplete credentials: "
                f"host={host}, user={user}, password={'***' if password else None}"
            )

        dbname = creds.get("dbname")
        if not dbname:
            raise ValueError("Database name (dbname) not found in Secrets Manager")

        port = creds.get("port")
        if not port:
            raise ValueError("Database port not found in Secrets Manager")

        return {
            "host": host,
            "port": int(port),
            "user": user,
            "password": password,
            "database": dbname,
        }
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"

        # If local mode is enabled, fall back to localhost
        if local_mode:
            print(
                f"[DEV_SERVER] AWS Secrets Manager unavailable ({error_msg})",
                flush=True,
            )
            print(
                "[DEV_SERVER] LOCAL_MODE=true, falling back to localhost postgres",
                flush=True,
            )
            return {
                "host": "localhost",
                "port": int(os.getenv("DB_PORT", 5432)),
                "user": os.getenv("DB_USER", "stocks"),
                "password": os.getenv("DB_PASSWORD", "stocks"),
                "database": os.getenv("DB_NAME", "stocks"),
            }

        # In production mode, raise exception for Lambda handler to return 500 error
        # Don't call sys.exit(1) — that's inappropriate for Lambda (terminates process)
        error_detail = (
            f"FATAL: AWS Secrets Manager failed. "
            f"Error: {error_msg}. "
            f"Ensure DB_SECRET_ARN is set and Secrets Manager secret exists in AWS account."
        )
        print(f"[DEV_SERVER] {error_detail}", flush=True)
        raise RuntimeError(error_detail) from e


creds = _load_db_credentials()
os.environ["DB_HOST"] = creds["host"]
os.environ["DB_PORT"] = str(creds["port"])
os.environ["DB_NAME"] = creds["database"]
os.environ["DB_USER"] = creds["user"]
os.environ["DB_PASSWORD"] = creds["password"]

# Determine data source
is_aws = creds["host"] != "localhost"
db_source = "AWS Secrets Manager (RDS Proxy)" if is_aws else "localhost (LOCAL_MODE)"
print(f"[DEV_SERVER] DB_HOST={os.environ['DB_HOST']} ({db_source})", flush=True)

if is_aws:
    print(
        f"[DEV_SERVER] [OK] Using real AWS RDS Proxy in {creds['host'].split('.')[2]}",
        flush=True,
    )
else:
    print("[DEV_SERVER] [OK] Using localhost postgres (LOCAL_MODE=true)", flush=True)
    print("[DEV_SERVER] Note: This uses demo/stub data only", flush=True)

# Add lambda/api and parent directories to path so we can import all modules
# NOTE: For dev_server, we prioritize root_dir so that utils.timezone_utils resolves correctly
# (In production Lambda, api_router.py handles the ordering differently)
api_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.dirname(api_dir)
root_dir = os.path.dirname(lambda_dir)
# Add root_dir first so imports like "from utils.infrastructure.timezone" find /root/utils
sys.path.insert(0, root_dir)
sys.path.insert(1, lambda_dir)
sys.path.insert(2, api_dir)

import lambda_function  # noqa: E402

importlib.reload(lambda_function)  # Force fresh reload in case module was cached

log_file = os.path.join(os.environ.get("TEMP", "/tmp"), "dev_server.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(log_file, mode="w")],
)
logger = logging.getLogger(__name__)

# Also write a marker to show the script started
try:
    with open(log_file, "a") as f:
        f.write("[DEV_SERVER_INIT] Script started\n")
        f.flush()
except OSError:
    pass


class APIHandler(BaseHTTPRequestHandler):
    """HTTP request handler that routes to Lambda function."""

    def do_GET(self) -> None:
        msg = f"[HTTP] GET {self.path}"
        print(msg, flush=True)
        logger.info(f"[HTTP_GET] {self.path}")
        try:
            with open(log_file, "a") as f:
                f.write(f"{msg}\n")
                f.flush()
        except OSError:
            pass
        self._handle_request("GET")

    def do_POST(self) -> None:
        print(f"[HTTP] POST {self.path}", flush=True)
        logger.info(f"[HTTP_POST] {self.path}")
        self._handle_request("POST")

    def do_PUT(self) -> None:
        print(f"[HTTP] PUT {self.path}", flush=True)
        logger.info(f"[HTTP_PUT] {self.path}")
        self._handle_request("PUT")

    def do_DELETE(self) -> None:
        print(f"[HTTP] DELETE {self.path}", flush=True)
        logger.info(f"[HTTP_DELETE] {self.path}")
        self._handle_request("DELETE")

    def do_PATCH(self) -> None:
        print(f"[HTTP] PATCH {self.path}", flush=True)
        logger.info(f"[HTTP_PATCH] {self.path}")
        self._handle_request("PATCH")

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight."""
        print(f"[HTTP] OPTIONS {self.path}", flush=True)
        logger.info(f"[HTTP_OPTIONS] {self.path}")
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _set_cors_headers(self) -> None:
        """Set CORS headers - accept any localhost origin in dev."""
        origin = self.headers.get("Origin", "")
        # In development, accept any localhost origin (5173, 5176, 5177, etc.)
        if origin and (origin.startswith(("http://localhost:", "http://127.0.0.1:"))):
            self.send_header("Access-Control-Allow-Origin", origin)
        elif not origin:
            self.send_header("Access-Control-Allow-Origin", "http://localhost:5173")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, PATCH, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Requested-With",
        )
        self.send_header("Access-Control-Max-Age", "3600")

    def _handle_request(self, method: str) -> None:
        """Route request to Lambda handler."""
        path = None
        try:
            # Parse URL
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query_string = parsed_url.query

            # Very early logging
            print(f"[DEV_SERVER] Handling {method} {path}", flush=True)

            # Get body
            content_length_header = self.headers.get("Content-Length")
            if content_length_header is None:
                logger.warning(
                    f"[DEV_SERVER] Missing Content-Length header for {method} {path}. "
                    f"Request body may be lost."
                )
                content_length = 0
                body_raw = b""
            else:
                try:
                    content_length = int(content_length_header)
                    body_raw = self.rfile.read(content_length) if content_length > 0 else b""
                except ValueError as e:
                    logger.error(
                        f"[DEV_SERVER CRITICAL] Invalid Content-Length header: {content_length_header}. "
                        f"Cannot read request body safely."
                    )
                    raise ValueError(f"Invalid Content-Length header: {content_length_header}") from e

            try:
                body = json.loads(body_raw.decode("utf-8")) if body_raw else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = None

            # Parse query params
            params = parse_qs(query_string) if query_string else {}

            # Get Authorization header (may be None/missing for CORS preflight or unauthenticated requests)
            auth_header = self.headers.get("Authorization")

            # Simulate Lambda event (API Gateway v2 HTTP API format)
            event: dict[str, Any] = {
                "httpMethod": method,
                "rawPath": path,
                "path": path,
                "queryStringParameters": ({k: v[0] if v else "" for k, v in params.items()} if params else None),
                "rawQueryString": query_string,
                "headers": dict(self.headers),
                "body": json.dumps(body) if body else None,
                "requestContext": {
                    "http": {
                        "method": method,
                        "path": path,
                    },
                    "identity": {
                        "sourceIp": (self.client_address[0] if self.client_address else "127.0.0.1"),
                    },
                },
            }

            # Add Authorization to headers if present
            if auth_header:
                headers = event.get("headers")
                if isinstance(headers, dict):
                    headers["Authorization"] = auth_header

            # Call Lambda handler with timing info
            logger.info(f"[REQ_START] {method} {path}")
            import time

            start = time.time()
            response = lambda_function.lambda_handler(event, None)
            elapsed = time.time() - start
            logger.info(f"[REQ_END] {method} {path} in {elapsed:.2f}s")

            # Debug: Log actual response from lambda_function
            if response.get("statusCode") >= 400:
                logger.debug(f"[HANDLER_RESPONSE] {method} {path}: status={response.get('statusCode')}")

            # Parse response
            status_code = response.get("statusCode")
            if status_code is None:
                raise RuntimeError(
                    "[DEV_SERVER] Lambda handler returned response without statusCode. "
                    "All responses must include explicit statusCode. "
                    f"Response: {response}"
                )
            response_body = response.get("body", "{}")
            response_headers = response.get("headers")
            if response_headers is None:
                logger.warning("[DEV_SERVER] Lambda handler returned response without headers dict")
                response_headers = {}

            # Encode response body
            if isinstance(response_body, str):
                response_body_bytes = response_body.encode("utf-8")
            else:
                response_body_bytes = response_body

            # Send response
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body_bytes)))

            # CORS headers come from lambda_function; don't double-send them
            cors_keys = {
                "access-control-allow-origin",
                "access-control-allow-credentials",
                "access-control-allow-methods",
                "access-control-allow-headers",
            }
            has_cors = any(k.lower() in cors_keys for k in response_headers)
            if not has_cors:
                self._set_cors_headers()

            # Add response headers (skip Content-Length if already in response_headers)
            for k, v in response_headers.items():
                if k.lower() != "content-length":
                    self.send_header(k, v)

            self.end_headers()
            self.wfile.write(response_body_bytes)

        except Exception as e:
            # Catch all exceptions (not just FileNotFoundError/OSError) to log details
            path_str = path or self.path or "unknown"
            error_type = type(e).__name__
            error_msg = str(e)[:500]
            print(f"[DEV_SERVER_EXCEPTION] {error_type} in {method} {path_str}: {error_msg}", flush=True)
            logger.error(
                f"[DEV_SERVER_EXCEPTION] Exception handling {method} {path_str}: "
                f"{error_type}: {error_msg}",
                exc_info=True
            )
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self._set_cors_headers()
                self.end_headers()
                error_response = json.dumps({"statusCode": 500, "message": "Internal server error"})
                self.wfile.write(error_response.encode("utf-8"))
            except Exception as send_err:
                logger.error(f"[DEV_SERVER] Failed to send error response: {send_err}")

    def log_message(self, fmt: str, *args: Any) -> None:
        """Suppress default HTTP logging."""


def run_dev_server(port: int = 3001) -> None:
    """Run the development server."""
    server_address = ("", port)
    httpd = HTTPServer(server_address, APIHandler)
    logger.info(f"Starting API dev server on http://localhost:{port}")
    logger.info("Press Ctrl+C to stop")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        httpd.shutdown()


if __name__ == "__main__":
    port = int(os.getenv("API_PORT", 3001))
    run_dev_server(port)
