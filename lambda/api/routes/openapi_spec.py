"""Route: openapi_spec - Serve OpenAPI specification and UI."""

import logging
from typing import Any, cast

from openapi_spec import generate_openapi_spec
from routes.utils import error_response, json_response

logger = logging.getLogger(__name__)


def handle(
    cur,
    path: str,
    method: str,
    params: dict,
    body: dict | None = None,
    jwt_claims: dict | None = None,
) -> dict[str, Any]:
    """Handle OpenAPI spec endpoints.

    /api/openapi.json - OpenAPI 3.0 specification (machine-readable)
    /api/swagger - Swagger UI (interactive documentation)
    /api/redoc - ReDoc UI (interactive documentation)
    """
    if path == "/api/openapi.json" or path.startswith("/api/openapi.json?"):
        return _handle_openapi_json()
    elif path == "/api/swagger" or path.startswith("/api/swagger?"):
        return _handle_swagger_ui()
    elif path == "/api/redoc" or path.startswith("/api/redoc?"):
        return _handle_redoc_ui()
    else:
        return cast(dict[str, Any], error_response(404, "not_found", "OpenAPI endpoint not found"))


def _handle_openapi_json() -> dict[str, Any]:
    """Serve the OpenAPI specification as JSON.

    Returns the complete OpenAPI 3.0 spec that can be used by:
    - API documentation tools (Swagger UI, ReDoc)
    - Code generators (OpenAPI Generator, Swagger Codegen)
    - API clients (HTTP client libraries)
    - Frontend TypeScript type generators
    """
    try:
        spec = generate_openapi_spec()
        return cast(dict[str, Any], json_response(200, spec))
    except Exception as e:
        logger.error(f"Error generating OpenAPI spec: {e}", exc_info=True)
        return cast(dict[str, Any], error_response(500, "internal_error", "Failed to generate OpenAPI specification"))


def _handle_swagger_ui() -> dict[str, Any]:
    """Serve Swagger UI for interactive API documentation.

    Returns HTML with Swagger UI pointing to /api/openapi.json.
    Allows users to:
    - View all endpoints and schemas
    - Try API requests directly
    - See example responses
    """
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>API Documentation - Swagger UI</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@3/swagger-ui.css">
        <style>
          body {
            margin: 0;
            padding: 0;
          }
        </style>
      </head>
      <body>
        <div id="swagger-ui"></div>
        <script src="https://unpkg.com/swagger-ui-dist@3/swagger-ui.js"></script>
        <script>
          const ui = SwaggerUIBundle({
            url: '/api/openapi.json',
            dom_id: '#swagger-ui',
            presets: [
              SwaggerUIBundle.presets.apis,
              SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
            layout: 'StandaloneLayout'
          });
          window.ui = ui;
        </script>
      </body>
    </html>
    """
    return {
        "statusCode": 200,
        "body": html,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
    }


def _handle_redoc_ui() -> dict[str, Any]:
    """Serve ReDoc UI for API documentation.

    Returns HTML with ReDoc pointing to /api/openapi.json.
    Alternative to Swagger UI with focus on documentation clarity.
    """
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>API Documentation - ReDoc</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
        <style>
          body {
            margin: 0;
            padding: 0;
          }
        </style>
      </head>
      <body>
        <redoc spec-url='/api/openapi.json'></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js"></script>
      </body>
    </html>
    """
    return {
        "statusCode": 200,
        "body": html,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
    }
