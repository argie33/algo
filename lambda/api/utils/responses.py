"""
API Response utilities for Lambda handler.
Handles JSON response formatting and error responses with proper security headers.
"""

import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional


def json_response(status_code: int, body: Dict[str, Any], headers: Optional[Dict] = None) -> Dict:
    """Return properly formatted API Gateway response with security headers."""
    frontend_origin = os.environ.get('FRONTEND_ORIGIN', '')
    if not frontend_origin:
        frontend_origin = ''

    default_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': frontend_origin,
        'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '86400',
        'X-Frame-Options': 'DENY',
        'X-Content-Type-Options': 'nosniff',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains' if os.environ.get('ENVIRONMENT') == 'production' else '',
    }
    if not default_headers.get('Strict-Transport-Security'):
        del default_headers['Strict-Transport-Security']

    if headers:
        default_headers.update(headers)

    if 'success' not in body:
        body['success'] = True
    if 'timestamp' not in body:
        body['timestamp'] = datetime.now(timezone.utc).isoformat()

    return {
        'statusCode': status_code,
        'headers': default_headers,
        'body': json.dumps(body, default=str),
    }


def error_response(status_code: int, error_code: str, message: str = '') -> Dict:
    """Return standardized error response."""
    safe_message = message if status_code < 500 else 'An internal error occurred'

    return {
        'statusCode': status_code,
        'body': json.dumps({
            'success': False,
            'error': error_code,
            'message': safe_message,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }, default=str),
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': os.environ.get('FRONTEND_ORIGIN', ''),
        },
    }
