"""GrowthMetricsMixin._compute_growth_metrics, extracted from
load_value_quality_growth_metrics.py (2026-09-05, file-size-ratchet compliance split).

Computes the `growth_metrics` table (revenue/EPS growth, book-value growth, sustainable
growth rate) from annual financial-statement history. Moved verbatim - no behavior change -
except `DatabaseContext(...)` call sites now go through `_owner()` (see that helper's own
docstring for why).

Mixed into ValueQualityGrowthMetricsLoader via multiple inheritance alongside
ValueMetricsMixin/QualityMetricsMixin - every `self.` call here resolves normally through
the instance regardless of which mixin file defines it.
"""

import logging
from typing import TYPE_CHECKING, Any

from loaders.helpers.vqg_shared import (
    _SHARED_TREND_FIELDS,
    get_loader_timestamp,
)
from loaders.helpers.vqg_symbol_gates import SymbolGateMixin


def _owner() -> Any:
    """Lazy reference to the owner module, resolved at call time (not import time).

    Two reasons this indirection exists, both load-bearing:
    (1) DatabaseContext: dozens of existing unit tests monkeypatch
    ``loaders.load_value_quality_growth_metrics.DatabaseContext`` directly. A module-level
    ``from utils.db.context import DatabaseContext`` here would bind this module's own
    separate copy of the name, which those patches can never reach - going through
    ``_owner().DatabaseContext`` always reads whatever the owner module's current attribute
    is, mocked or real.
    (2) Avoids importing anything from the owner module at THIS module's top level, which
    is what caused a real circular-import crash on 2026-09-05 (see
    vqg_and_stock_scores_dead_split_files_deleted_20260905 in memory): when the owner is run
    as a script (``python loaders/load_value_quality_growth_metrics.py``) rather than
    imported as a package, it registers under ``sys.modules["__main__"]``, not its dotted
    path - a top-level `from loaders.load_value_quality_growth_metrics import X` here then
    re-imports the owner from scratch while it's still mid-import, before this class exists
    yet, raising ImportError. Importing lazily inside a function body sidesteps this
    entirely since it only runs after both modules have finished importing.
    """
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


logger = logging.getLogger("loaders.load_value_quality_growth_metrics")


class GrowthMetricsMixin(SymbolGateMixin):
    """See module docstring.

    Inherits SymbolGateMixin (also a base of ValueQualityGrowthMetricsLoader itself - a
    diamond, harmless since it's the same class both times) purely so mypy can see the
    `_get_*_symbols` gate methods called via `self.` below.
    """

    if TYPE_CHECKING:

        def _nan_to_none(self, value: float | None) -> float | None: ...

        def _unavailable_marker(self, table: str, symbol: str, reason: str | None = None) -> dict[str, Any]: ...

        def _fetch_annual_fallback_row(
            self, table: str, columns: str, extra_where: str, symbol: str
        ) -> tuple[Any, ...] | None: ...

        def _compute_period_growth(
            self,
            symbol: str,
            values: list[tuple[int, float]],
            offset: int,
            metric_key: str,
            metrics: dict[str, Any],
            failed_metrics: list[str],
            sign_change_metrics: set[str],
            split_discontinuity_metrics: set[str] | None = None,
            shares_by_year: dict[int, float] | None = None,
            *,
            min_abs_target: float = 0.0,
            immaterial_base_metrics: set[str] | None = None,
            implausible_growth_metrics: set[str] | None = None,
        ) -> None: ...

    def _compute_growth_metrics(  # noqa: C901 -- pre-existing complexity debt from the book_value_growth addition (migration 1242), not introduced by this change
        self, symbol: str, income_rows: list[Any]
    ) -> dict[str, Any]:
        """Compute multi-year growth rates from annual income statement history.

        Calculates CAGR for 1y, 3y, 5y periods using compound annual growth rate formula.
        income_rows: List of (fiscal_year, total_revenue, operating_income, net_income,
        earnings_per_share[, shares_outstanding_diluted, shares_outstanding_basic[,
        stockholders_equity]]) sorted DESC by fiscal_year (most recent first). The two shares
        columns are optional (older 5-tuple test fixtures still work) and feed the
        EPS_SPLIT_GUARD_CLEAN_MULTIPLES guard; stockholders_equity is also optional and feeds
        only book_value_growth's BVPS computation - every other field is unaffected by its absence.
        """
        if not income_rows:
            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, growth_metrics
            # sibling of the identical vqg_quality.py._compute_quality_metrics fix): an ETF
            # (SPY/QQQ/IWM - files N-1A/N-CSR, never a 10-K) has ZERO annual_income_statement
            # rows, so this early return was mislabeling its entire growth_metrics row as the
            # generic "missing_sec_data" instead of the permanent business-model fact
            # "etf_no_sec_filings" already used for the identical case elsewhere (see that
            # method's own comment).
            reason = "etf_no_sec_filings" if symbol in self._get_etf_symbols() else None
            return self._unavailable_marker("growth_metrics", symbol, reason=reason)

        metrics: dict[str, Any] = {
            "symbol": symbol,
            "revenue_growth_1y": None,
            "revenue_growth_3y": None,
            "revenue_growth_5y": None,
            "eps_growth_1y": None,
            "eps_growth_3y": None,
            "eps_growth_5y": None,
            "book_value_growth": None,
            "updated_at": get_loader_timestamp(),
            "data_unavailable": False,
            "data_source": "sec_audited",
        }

        revenues: list[tuple[int, float]] = []
        eps_values: list[tuple[int, float]] = []
        # bvps = stockholders_equity/shares_outstanding_diluted, book_value_growth = bvps/prior_bvps - 1.
        # Reuses _compute_period_growth's offset=1 CAGR machinery (same sign-change/split-guard
        # protection EPS gets) - BVPS is just another (fiscal_year, value) series.
        bvps_values: list[tuple[int, float]] = []
        shares_by_year: dict[int, float] = {}
        # company_info_sec.shares_outstanding is a point-in-time snapshot (not historical per
        # fiscal year) but is used as a fallback when annual_income_statement lacks shares for
        # a given year, since the split-guard below needs a shares_by_year entry per year to
        # detect splits and would otherwise block book_value_growth entirely for that symbol.
        company_info_shares: dict[int, float] = {}
        try:
            with _owner().DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT shares_outstanding FROM company_info_sec WHERE symbol = %s",
                    (symbol,),
                )
                result = cur.fetchone()
                fallback_shares = result[0] if result and result[0] else None
                if fallback_shares and fallback_shares > 0:
                    # Applied to ALL years lacking income-statement shares; assumes share
                    # count didn't change dramatically between years - imprecise but better
                    # than leaving book_value_growth unavailable.
                    for row in income_rows:
                        if row is not None and len(row) > 7:
                            fiscal_year = int(row[0]) if row[0] is not None else None
                            if fiscal_year is not None:
                                company_info_shares[fiscal_year] = fallback_shares
        except Exception as e:
            logger.debug(f"[{symbol}] Could not fetch company_info_sec shares fallback: {e}")
        for row in income_rows:
            try:
                fiscal_year = int(row[0]) if row[0] is not None else None
                rev = float(row[1]) if row[1] is not None else None
                eps = float(row[4]) if row[4] is not None else None
                # row[5]/row[6] only present in the live query - len() check keeps older
                # 5-tuple test fixtures working.
                shares = None
                if len(row) > 5 and row[5] is not None:
                    shares = float(row[5])
                elif len(row) > 6 and row[6] is not None:
                    shares = float(row[6])
                # row[7] (LEFT JOIN annual_balance_sheet) same len() guard as shares above.
                stockholders_equity = None
                if len(row) > 7 and row[7] is not None:
                    stockholders_equity = float(row[7])
                rev = self._nan_to_none(rev)
                eps = self._nan_to_none(eps)
                stockholders_equity = self._nan_to_none(stockholders_equity)
                if fiscal_year is None:
                    continue
                if rev is not None and rev > 0:
                    revenues.append((fiscal_year, rev))
                if eps is not None and eps != 0:
                    eps_values.append((fiscal_year, eps))
                # Use income statement shares if available, fallback to company_info_sec if not
                # (see fallback-fetch logic above for context)
                shares_for_year = shares
                if (shares_for_year is None or shares_for_year <= 0) and fiscal_year in company_info_shares:
                    shares_for_year = company_info_shares[fiscal_year]
                if shares_for_year is not None and shares_for_year > 0 and fiscal_year not in shares_by_year:
                    shares_by_year[fiscal_year] = shares_for_year
                # Book value per share can be legitimately negative (heavily-levered/buyback-
                # heavy firms) - only require shares > 0 (a real, positive share count to
                # divide by), same convention as _compute_period_growth's own sign-change
                # guard handling negative-to-positive transitions correctly rather than
                # excluding negative values outright.
                if stockholders_equity is not None and shares_for_year is not None and shares_for_year > 0:
                    bvps_values.append((fiscal_year, stockholders_equity / shares_for_year))
            except (ValueError, TypeError):
                continue

        failed_metrics: list[str] = []
        sign_change_metrics: set[str] = set()
        split_discontinuity_metrics: set[str] = set()
        immaterial_base_metrics: set[str] = set()
        # Real CAGR computed but beyond MAX_PLAUSIBLE_GROWTH_PCT (2000%) - see
        # _compute_period_growth's own comment on this branch for the full rationale.
        implausible_growth_metrics: set[str] = set()
        self._compute_period_growth(
            symbol,
            revenues,
            1,
            "revenue_growth_1y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            implausible_growth_metrics=implausible_growth_metrics,
        )
        self._compute_period_growth(
            symbol,
            eps_values,
            1,
            "eps_growth_1y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            split_discontinuity_metrics,
            shares_by_year,
            min_abs_target=0.10,
            immaterial_base_metrics=immaterial_base_metrics,
            implausible_growth_metrics=implausible_growth_metrics,
        )
        # book_value_growth uses the same split-guard as EPS since BVPS is equally sensitive
        # to a split changing the per-share denominator across the two CAGR endpoints.
        self._compute_period_growth(
            symbol,
            bvps_values,
            1,
            "book_value_growth",
            metrics,
            failed_metrics,
            sign_change_metrics,
            split_discontinuity_metrics,
            shares_by_year,
            implausible_growth_metrics=implausible_growth_metrics,
        )
        self._compute_period_growth(
            symbol,
            revenues,
            3,
            "revenue_growth_3y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            implausible_growth_metrics=implausible_growth_metrics,
        )
        self._compute_period_growth(
            symbol,
            eps_values,
            3,
            "eps_growth_3y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            split_discontinuity_metrics,
            shares_by_year,
            min_abs_target=0.10,
            immaterial_base_metrics=immaterial_base_metrics,
            implausible_growth_metrics=implausible_growth_metrics,
        )
        self._compute_period_growth(
            symbol,
            revenues,
            5,
            "revenue_growth_5y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            implausible_growth_metrics=implausible_growth_metrics,
        )
        self._compute_period_growth(
            symbol,
            eps_values,
            5,
            "eps_growth_5y",
            metrics,
            failed_metrics,
            sign_change_metrics,
            split_discontinuity_metrics,
            shares_by_year,
            min_abs_target=0.10,
            immaterial_base_metrics=immaterial_base_metrics,
            implausible_growth_metrics=implausible_growth_metrics,
        )

        if not revenues and not eps_values and not bvps_values:
            return self._unavailable_marker("growth_metrics", symbol)

        def _growth_reason(metric_key: str) -> str | None:
            if metric_key in sign_change_metrics:
                return "growth_undefined_sign_change"
            if metric_key in split_discontinuity_metrics:
                return "growth_undefined_share_count_discontinuity"
            if metric_key in immaterial_base_metrics:
                return "immaterial_prior_year_base"
            if metric_key in implausible_growth_metrics:
                return "garbage_metric_value_implausible_growth_rate"
            if metric_key in failed_metrics:
                return "insufficient_history"
            return None

        metrics["revenue_growth_1y_unavailable_reason"] = _growth_reason("revenue_growth_1y")
        metrics["revenue_growth_3y_unavailable_reason"] = _growth_reason("revenue_growth_3y")
        metrics["revenue_growth_5y_unavailable_reason"] = _growth_reason("revenue_growth_5y")
        metrics["eps_growth_1y_unavailable_reason"] = _growth_reason("eps_growth_1y")
        metrics["eps_growth_3y_unavailable_reason"] = _growth_reason("eps_growth_3y")
        metrics["eps_growth_5y_unavailable_reason"] = _growth_reason("eps_growth_5y")
        metrics["book_value_growth_unavailable_reason"] = _growth_reason("book_value_growth")

        if failed_metrics:
            # 7 possible periods (book_value_growth included).
            if len(failed_metrics) == 7:
                # Keep the per-field reasons _growth_reason() already computed (e.g. a real
                # sign-change) instead of overwriting them all with a blanket
                # "insufficient_history" - the values are None either way, but the reason
                # should stay honest per field.
                metrics["data_unavailable"] = True
                metrics["data_source"] = "none"
                metrics["reason"] = (
                    f"Insufficient historical data: {', '.join(sorted(set(failed_metrics)))} could not be computed"
                )
                # _SHARED_TREND_FIELDS are normally copied in from quality_dict by the caller,
                # gated on `not data_unavailable` - since this branch sets data_unavailable=True,
                # that copy never runs, so set a real reason here too (matching every other
                # data_unavailable path, which goes through _unavailable_marker()).
                for field in _SHARED_TREND_FIELDS:
                    metrics.setdefault(field, None)
                    metrics[f"{field}_unavailable_reason"] = metrics["reason"]
            else:
                # Partial failure (1-6 of 7 periods): periods that DID compute are real values,
                # so leave data_unavailable=False - downstream scoring renormalizes over
                # whatever fields are present rather than discarding the whole row.
                metrics["reason"] = (
                    f"Incomplete growth metrics: {', '.join(sorted(set(failed_metrics)))} failed to compute (insufficient history or invalid data)"
                )
            logger.debug(
                f"[VALUE_QUALITY_GROWTH] {symbol}: Partial growth metrics (failed: {', '.join(sorted(set(failed_metrics)))})"
            )

        # Initialize trend fields to None (same as quality_metrics) - these are not computed
        # from income statement history in this method, they come from quality_metrics which
        # has access to balance sheet data. Initializing them here prevents database errors
        # from missing column values in the growth_metrics INSERT.
        for field in [
            "net_income_growth_yoy",
            "operating_income_growth_yoy",
            "gross_margin_trend",
            "operating_margin_trend",
            "net_margin_trend",
            "roe_trend",
            "sustainable_growth_rate",
            "quarterly_growth_momentum",
            "fcf_growth_yoy",
            "ocf_growth_yoy",
            "asset_growth_yoy",
        ]:
            if field not in metrics:
                metrics[field] = None

        return metrics
