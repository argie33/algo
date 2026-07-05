#!/usr/bin/env python3
"""Response Formatter - Standard API response formatting."""

from __future__ import annotations

from typing import Any


class ResponseFormatter:
    """Formats API responses consistently."""

    @staticmethod
    def success(data: Any, status: int = 200, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        """Format successful response."""
        response = {
            "status": status,
            "success": True,
            "data": data,
        }
        if meta:
            response["meta"] = meta
        return response

    @staticmethod
    def error(error_code: str, message: str, status: int = 400) -> dict[str, Any]:
        """Format error response."""
        return {
            "status": status,
            "success": False,
            "error": error_code,
            "message": message,
        }

    @staticmethod
    def paginated(items: list[Any], total: int, page: int, page_size: int) -> dict[str, Any]:
        """Format paginated response."""
        return {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": (total + page_size - 1) // page_size,
            },
        }
