#!/usr/bin/env python3
"""SEC EDGAR direct client for official fundamentals.

Backward-compatibility wrapper that re-exports from sec_edgar_client and sec_statements.
"""

from utils.external.sec_edgar_client import RateLimiter, SecEdgarClient
from utils.external import sec_statements

__all__ = ["RateLimiter", "SecEdgarClient", "sec_statements"]
