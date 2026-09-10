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
            return None
        components = [safe_float(c, f"{symbol}.total_debt_components_fallback", allow_none=True) for c in row]
        if all(c is None for c in components):
            return None
        return self._nan_to_none(sum(c or 0.0 for c in components))
