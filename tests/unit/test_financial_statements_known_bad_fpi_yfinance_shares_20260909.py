"""Regression test for the 2026-09-09 fix: SKHY (SK hynix, an unsponsored OTC ADR with no
SEC filings, financials sourced entirely via sec_base.py's yfinance fallback) has a
shares_outstanding_basic/diluted (~6.9-7.1B) that is internally consistent with its own
net_income/diluted_eps across every fiscal year - so every existing same-row/cross-year
consistency guard in this file correctly finds nothing wrong - but implies a $1.32T market
cap and pb_ratio=15.78/ps_ratio=19.58 in value_metrics, both many-fold outside SK hynix's
real-world range (~$130-150B market cap, low-single-digit pb/ps). No independent reference
exists for this class of symbol (company_info_sec.shares_outstanding is NULL - it's only
ever populated from SEC data this symbol doesn't have), so neither the relative cross-check
nor the loose absolute ceiling in _reject_implausible_shares_outstanding can catch it.

See KNOWN_BAD_FPI_YFINANCE_SHARES_OUTSTANDING's own module-level docstring in
loaders/helpers/financial_statements_share_count_validation.py for the full evidence trail
and why this took the "reject rather than guess a ratio" path instead of an ADS-ratio
registry entry (DOMESTIC_FILER_ADS_RATIO_OVERRIDES/FPI_EPS_ADS_RATIO_OVERRIDES in
load_sec_valuations.py) - those only ever adjust SEC-XBRL-tagged EPS, and SKHY has no SEC
filings to adjust.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _transform(loader: ConsolidatedFinancialStatementsLoader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
        return loader.transform(rows)


class TestKnownBadFpiYfinanceSharesOutstanding:
    def test_skhy_shares_rejected_regardless_of_plausible_absolute_ceiling(self) -> None:
        """SKHY's ~7.1B diluted share count clears both the absolute ceiling (500B) and
        would never trip the relative cross-check (no company_info_sec reference exists for
        this symbol) - the registry must reject it outright rather than rely on either."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "SKHY",
                "fiscal_year": 2025,
                "revenue": Decimal("67266773992.52"),
                "net_income": Decimal("29718381803.07"),
                "diluted_eps": Decimal("4.180722891566265"),
                "shares_outstanding_basic": Decimal("6917556412.0"),
                "shares_outstanding_diluted": Decimal("7108431382.0"),
                "shares_outstanding_dei": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert transformed[0]["shares_outstanding_basic"] is None
        assert transformed[0]["shares_outstanding_diluted"] is None
        rejected_fields = {
            field for pk, field in loader._explicit_null_rejections if pk == {"symbol": "SKHY", "fiscal_year": 2025}
        }
        assert rejected_fields == {"shares_outstanding_basic", "shares_outstanding_diluted"}

    def test_unrelated_symbol_not_affected_by_registry(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "PJT",
                "fiscal_year": 2020,
                "revenue": Decimal("400000000"),
                "net_income": Decimal("50000000"),
                "shares_outstanding_basic": 28000000.0,
                "shares_outstanding_diluted": 28500000.0,
                "shares_outstanding_dei": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert transformed[0]["shares_outstanding_basic"] == 28000000.0
        assert transformed[0]["shares_outstanding_diluted"] == 28500000.0
        assert loader._explicit_null_rejections == []
