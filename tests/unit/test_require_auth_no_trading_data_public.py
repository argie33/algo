#!/usr/bin/env python3
"""Regression test: PUBLIC_PREFIXES in lambda_function.require_auth() must never contain
live trading-position endpoints.

Found 2026-07-26: /api/algo/portfolio, /api/algo/positions, /api/algo/trades,
/api/algo/performance, /api/algo/risk-metrics, /api/algo/circuit-breakers, and a dozen
related endpoints were listed in PUBLIC_PREFIXES with comments claiming a secondary
"dev tokens (local dev)" check enforced auth in production. That check never ran:
`is_public=True` makes require_auth() return (requires_auth=False, is_authorized=True)
immediately, before any token - Cognito or dev - is inspected. Terraform's own comment
confirms Lambda is the *only* auth boundary (API Gateway routes all use
authorization_type = "NONE"), so this was a full unauthenticated information-disclosure
hole exposing live positions, entry prices, portfolio value, and trade history to anyone
on the internet - directly contradicting this same function's header comment ("Strategy
and trading endpoints require authentication").

This test parses the source directly (not `import lambda_function`) because that module
runs a real DB migration check as an import-time side effect (see
tests/test_session_282_integration.py's TestBasicValidation.test_import_all_critical_modules
docstring) - unsuitable for a unit test with no DB available.
"""

import ast
from pathlib import Path

LAMBDA_FUNCTION_PATH = Path(__file__).resolve().parents[2] / "lambda" / "api" / "lambda_function.py"

# Endpoints that expose live trading state and must never be reachable without a valid
# Cognito (or, in local dev, dev-mode) token.
MUST_NOT_BE_PUBLIC = {
    "/api/algo/portfolio",
    "/api/algo/positions",
    "/api/algo/trades",
    "/api/algo/performance",
    "/api/algo/dashboard-signals",
    "/api/algo/risk-metrics",
    "/api/algo/circuit-breakers",
    "/api/algo/daily-return-histogram",
    "/api/algo/equity-curve",
    "/api/algo/holding-period-distribution",
    "/api/algo/stage-distribution",
    "/api/algo/trade-distribution",
    "/api/algo/execution/stats",
    "/api/algo/execution/recent",
    "/api/algo/notifications",
    "/api/algo/patrol",
    "/api/algo/patrol-log",
    "/api/algo/audit-log",
    "/api/algo/performance-analytics",
    "/api/algo/rejection-funnel",
    "/api/portfolio",
    "/api/positions",
}


def _extract_public_prefixes() -> set[str]:
    """Parse lambda_function.py's AST and pull the literal string constants assigned to
    the PUBLIC_PREFIXES set inside require_auth(), without executing the module."""
    source = LAMBDA_FUNCTION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(LAMBDA_FUNCTION_PATH))

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "require_auth":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Set):
                    targets = [t.id for t in sub.targets if isinstance(t, ast.Name)]
                    if "PUBLIC_PREFIXES" in targets:
                        return {
                            elt.value
                            for elt in sub.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        }
    raise AssertionError("Could not find PUBLIC_PREFIXES assignment inside require_auth() - has it moved/renamed?")


def test_trading_data_endpoints_are_not_in_public_prefixes():
    public_prefixes = _extract_public_prefixes()
    leaked = public_prefixes & MUST_NOT_BE_PUBLIC
    assert not leaked, (
        f"These trading-data endpoints are unauthenticated (in PUBLIC_PREFIXES): {sorted(leaked)}. "
        "require_auth() returns before any token is checked for public-prefix paths, and API "
        "Gateway's routes all use authorization_type=NONE (Lambda is the only auth boundary) - "
        "this exposes live positions/trades/portfolio value to anyone on the internet."
    )


def test_public_prefixes_extraction_actually_found_entries():
    """Guard against the AST walk silently matching nothing (e.g. after a refactor) and
    the test above passing vacuously."""
    public_prefixes = _extract_public_prefixes()
    assert len(public_prefixes) > 10, (
        f"Only found {len(public_prefixes)} PUBLIC_PREFIXES entries - expected 20+. "
        "The AST extraction may no longer match require_auth()'s current structure."
    )
