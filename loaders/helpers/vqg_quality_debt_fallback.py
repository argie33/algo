"""DebtComponentsFallbackMixin._fetch_total_debt_components_fallback, extracted into its own
file rather than added to vqg_quality.py or load_value_quality_growth_metrics.py (2026-09-10,
file-size ratchet: both are already at/past their growth ceiling - see
.file-size-baseline.json). Mixed into ValueQualityGrowthMetricsLoader alongside every other
vqg_* mixin.
"""

from typing import TYPE_CHECKING, Any

from utils.type_conversion import safe_float


class DebtComponentsFallbackMixin:
    """See module docstring. Every `self.` call here resolves normally through the instance."""

    if TYPE_CHECKING:

        def _nan_to_none(self, value: float | None) -> float | None: ...

        def _fetch_annual_fallback_row(
            self, table: str, columns: str, extra_where: str, symbol: str
        ) -> tuple[Any, ...] | None: ...

    def _fetch_total_debt_components_fallback(self, symbol: str) -> float | None:
        """Last-resort debt fallback for _compute_quality_metrics's debt_for_roic (feeds
        roic_pct/roce_pct/debt_to_equity) - sums long_term_debt + short_term_debt +
        operating_lease_liability + finance_lease_liability, the SAME 4-component definition
        sec_valuations_checks.py's own _get_total_cash_and_debt fallback already uses for
        sec_valuations.total_debt (and the primary EV computation before that).

        FIXED 2026-09-10 (goal: "under 500" push): debt_for_roic's only fallback before this
        was a bare `long_term_debt` column search - live-confirmed 2 universe symbols
        (ATHR/short_term_debt only, BRNS/operating_lease_liability only) have a real,
        non-zero debt component of ONE of the other 3 kinds but have NEVER tagged
        long_term_debt itself in any fiscal year - debt_for_roic (and therefore
        debt_to_equity/roce_pct/roic_pct) fell through to the generic "missing_sec_data"
        reason for a company that isn't actually missing SEC debt data, just tagging a
        component this narrower fallback didn't look at. Deliberately NOT the primary
        source (long_term_debt/total_debt_ev stay preferred everywhere they're available) -
        only reached once every existing fallback tier has already failed, same "last
        resort, not a silent substitution" discipline as
        _fetch_balance_sheet_anchor_fallback's own callers.
        """
        row = self._fetch_annual_fallback_row(
            "annual_balance_sheet",
            "long_term_debt, short_term_debt, operating_lease_liability, finance_lease_liability",
            (
                "AND (long_term_debt IS NOT NULL OR short_term_debt IS NOT NULL"
                " OR operating_lease_liability IS NOT NULL OR finance_lease_liability IS NOT NULL)"
            ),
            symbol,
        )
        if not row:
            return self._fetch_total_debt_components_quarterly_fallback(symbol)
        components = [safe_float(c, f"{symbol}.total_debt_components_fallback", allow_none=True) for c in row]
        if all(c is None for c in components):
            return self._fetch_total_debt_components_quarterly_fallback(symbol)
        return self._nan_to_none(sum(c or 0.0 for c in components))

    def _fetch_total_debt_components_quarterly_fallback(self, symbol: str) -> float | None:
        """Quarterly tier for _fetch_total_debt_components_fallback, reached only when
        annual_balance_sheet has never tagged any of the 4 debt components at all.

        FIXED 2026-09-10 (goal: "under 500" push, total_debt_not_itemized bucket): a filer
        can have a real, non-zero debt balance tagged in its 10-Q quarterly filings while its
        annual_balance_sheet row has every debt-component column NULL (e.g. an early-stage
        company whose 10-K balance-sheet extraction predates a debt raise reflected in a
        later 10-Q, or whose 10-K simply omits a concept its 10-Qs do tag). Live-confirmed 3
        universe symbols: KWM ($1.8M long_term_debt, FY2025 Q4), NUR ($5.8M, FY2026 Q1), VOXR
        ($6.7M, FY2025 Q4) - all three have zero debt-component data anywhere in
        annual_balance_sheet but a real, recent quarterly figure. Same 4-component sum and
        "last resort" discipline as the annual tier above - only reached after annual is
        confirmed empty, never preferred over it.

        Deliberately its own query rather than reusing `_fetch_annual_fallback_row` (this
        file's other tier calls it against annual_balance_sheet): that helper's `ORDER BY
        fiscal_year DESC LIMIT 1` has no `fiscal_quarter` tiebreak - fine for annual tables
        (one row per fiscal_year) but non-deterministic across quarterly_balance_sheet's
        multiple rows per fiscal_year. Can't add a quarterly sibling method to
        load_value_quality_growth_metrics.py itself either - that file is already past its
        2000-line file-size-ratchet hard ceiling (no baseline raise accepted).

        Imports `loaders.load_value_quality_growth_metrics` for its `DatabaseContext`
        LOCALLY (not at module level - this file is imported BY that module's import chain
        via vqg_quality_batch.py's `QualityBatchMixin`, so a module-level import here would
        be circular, same "local import" convention sec_valuations_income_context.py's
        `_fetch_income_statement_context` already uses for the identical reason) and calls
        it as `mod.DatabaseContext(...)` (an attribute lookup at call time) rather than
        `from ... import DatabaseContext` (which would bind a snapshot at import time) - this
        is what lets the many existing tests that already monkeypatch
        `loaders.load_value_quality_growth_metrics.DatabaseContext` transparently cover this
        new tier too, without needing to touch every one of them individually.
        """
        import loaders.load_value_quality_growth_metrics as _vqg_mod

        # DatabaseContext isn't explicitly re-exported by that module (it's just imported
        # there from utils.db.context) - mypy's implicit-reexport check flags the attribute
        # access below; see this method's own docstring for why it's deliberate anyway.
        with _vqg_mod.DatabaseContext("read") as cur:  # type: ignore[attr-defined]
            cur.execute(
                """
                SELECT long_term_debt, short_term_debt, operating_lease_liability, finance_lease_liability
                FROM quarterly_balance_sheet
                WHERE symbol = %s AND data_unavailable IS NOT TRUE
                  AND (long_term_debt IS NOT NULL OR short_term_debt IS NOT NULL
                       OR operating_lease_liability IS NOT NULL OR finance_lease_liability IS NOT NULL)
                ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT 1
                """,
                (symbol,),
            )
            row = cur.fetchone()
        if not row:
            return None
        components = [safe_float(c, f"{symbol}.total_debt_components_quarterly_fallback", allow_none=True) for c in row]
        if all(c is None for c in components):
            return None
        return self._nan_to_none(sum(c or 0.0 for c in components))
