"""Regression test: /api/financials/{symbol}/ownership must exist and return the fields
StockDetail.jsx's StatsTab reads.

BUG FOUND 2026-08-10 (frontend/dashboard audit pass): StockDetail.jsx has called
`/api/financials/${symbol}/ownership` since it was written (StatsTab's segment count,
largest-segment concentration, and diversification tiles), but this handler never existed
in lambda/api/routes/financials.py - every stock detail page load 404'd on it, permanently
blanking those fields site-wide even though the source table (sec_segment_metrics) is
populated and fresh.

REMOVED 2026-08-24: insider_ownership_pct/number_of_insiders/recent_buys assertions -
insider_ownership_pct was removed entirely (static governance metric, near-zero
information content for weeks-scale swing trading, recurring source of real bugs). See
loaders/DEPRECATED_LOADERS.md. This endpoint's segment-metrics coverage is unrelated and
kept intact.
"""

import importlib
import inspect

financials = importlib.import_module("lambda.api.routes.financials")


def _ownership_block() -> str:
    source = inspect.getsource(financials.handle)
    start = source.index('if endpoint == "ownership"')
    end = source.index("if endpoint ==", start + 1)
    return source[start:end]


def test_ownership_endpoint_branch_exists():
    # Raises ValueError via .index() if the branch is missing - that's the assertion.
    block = _ownership_block()
    assert 'endpoint == "ownership"' in block


def test_ownership_select_includes_all_frontend_fields():
    block = _ownership_block()
    frontend_fields = [
        "segment_count",
        "largest_segment_revenue_pct",
        "revenue_concentration_hhi",
        "is_diversified",
    ]
    for field in frontend_fields:
        assert field in block, f"ownership endpoint SELECT must include {field} - StatsTab reads it from o.{field}"


def test_ownership_queries_segment_source_table():
    block = _ownership_block()
    assert "sec_segment_metrics" in block
    # No LEFT JOIN insider_holdings_sec left in the actual query - a plain substring check
    # would also flag this file's own explanatory "REMOVED 2026-08-24" comment, which
    # legitimately names the dropped table for context.
    assert "LEFT JOIN insider_holdings_sec" not in block


def test_ownership_returns_success_response_shape():
    # Frontend does `ownershipData?.data || {}` (a plain object, not `.data.items[...]`),
    # so this must use success_response (data: {...}), not list_response (data: {items: [...]}).
    block = _ownership_block()
    assert "success_response(" in block
    assert "list_response(" not in block
