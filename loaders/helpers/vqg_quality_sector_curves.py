"""Sector-conditioned curve/score helpers and the gross_profitability-through-asset_turnover
"unavailable_reason" label chain, extracted verbatim from `QualityMetricsMixin.
_compute_quality_metrics()` (loaders/helpers/vqg_quality.py, 2026-09-08, file-size-ratchet
compliance split - the rebased-in sector-neutral-zscore rewrite pushed that file back over its
recorded 3440-line baseline). No behavior change.

Split into two independent pieces that both happened to live in the same region of the
original method:

1. `roa_breakpoints_for_industry`/`roce_breakpoints_for_industry`/
   `debt_to_equity_score_for_industry`: the depository-bank/insurance-underwriter/utility
   Pass-1 curve overrides (see each function's own docstring for the live-verified evidence
   behind its breakpoints). Pure functions of (value, industry) - no database access, no
   `self`.

2. `compute_gross_profitability_through_asset_turnover_reasons`: the
   gross_profitability/operating_profitability/accruals_ratio/margin_volatility/fcf_margin/
   asset_turnover value+reason assignments. Needs the 39-gate `SymbolGateMixin` surface
   (`_get_no_recent_revenue_symbols()` etc.), so it takes the loader instance itself
   (duck-typed as `Any`, same as this repo's `_owner()` indirection) as its first argument
   and calls those gates on it directly rather than requiring a real mixin relationship -
   this module intentionally does NOT subclass anything from vqg_quality.py, so
   ValueQualityGrowthMetricsLoader's own base-class list (loaders/
   load_value_quality_growth_metrics.py) needs no change for this split.
"""

from typing import Any


def _owner() -> Any:
    """See vqg_quality.py's own `_owner()` docstring for the two load-bearing reasons this
    lazy, per-call import exists (DatabaseContext test-patching + avoiding a circular import
    when the owner module is run as a script) - identical rationale, just needed here too for
    the DEPOSITORY_BANK_INDUSTRIES/INSURANCE_UNDERWRITER_INDUSTRIES/UTILITY_INDUSTRIES industry
    sets."""
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


def roa_breakpoints_for_industry(industry: str | None) -> list[tuple[float, float]]:
    """ROA (net_income/total_assets) `_margin_curve` breakpoints, sector-conditioned.

    FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, JPM/BAC/WFC/C/GS
    live-confirmed): same industrial-curve-applied-to-every-sector bug class as
    debt_to_equity_score_for_industry, for a DIFFERENT input - ROA is structurally deflated
    for depository banks by their huge deposit-funded balance sheet (a healthy bank's ROA is
    ~1-1.5%; the (3.0,40)/(8.0,80)/(15.0,100) industrial curve, calibrated for asset-light
    industrial/services margins, floors JPM's real ROA=1.29% to a ~17 score, WFC's 0.99% to
    ~13, etc.) - not a quality problem, the same leverage-by-design fact the debt_to_equity
    bank/insurer curve fix already accounts for on the liability side. Insurers get their own,
    less extreme curve: P&C underwriters (PGR/TRV/ALL live-confirmed ROA 4.4-9.2%) run
    meaningfully higher than life insurers (MET/PRU live-confirmed ROA ~0.45%) whose
    reserve-heavy balance sheets behave more bank-like - INSURANCE_UNDERWRITER_INDUSTRIES
    lumps both (same precedent as debt_to_equity_score_for_industry's single blended insurer
    curve), hand-calibrated to credit P&C-typical ROA highly without being so generous it
    validates a genuinely weak life-insurer ROA. Thresholds hand-set (not FM-backtested), same
    as every other curve in this function.

    FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, 10-electric-utility +
    water/gas-distribution live-confirmed): same bug class again, for regulated rate-base
    utilities - see UTILITY_INDUSTRIES's own comment for the full live-verified evidence (ROA
    clustered 2.26-3.67% across 16 symbols).
    """
    if industry in _owner().DEPOSITORY_BANK_INDUSTRIES:
        return [(0.85, 40.0), (1.3, 80.0), (1.7, 100.0)]  # recalibrated+IC-validated 20260907
    if industry in _owner().INSURANCE_UNDERWRITER_INDUSTRIES:
        return [(2.5, 40.0), (5.5, 80.0), (10.0, 100.0)]
    if industry in _owner().UTILITY_INDUSTRIES:
        return [(2.2, 40.0), (3.3, 80.0), (5.0, 100.0)]
    return [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)]


def roce_breakpoints_for_industry(industry: str | None) -> list[tuple[float, float]]:
    """ROCE (NOPAT/capital_employed) `_margin_curve` breakpoints, sector-conditioned.

    ROCE score: same curve shape as the old roic_score (both are "return on capital deployed"
    measures, similar scale) - see the roce_pct computation's own comment (near roic_pct in
    vqg_quality.py) for why ROCE replaces ROIC in the composite.

    FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, JPM/BAC/WFC/C/GS/MS/
    MET/PRU live-confirmed): same industrial-curve-applied-to-every-sector bug class as
    debt_to_equity_score_for_industry/roa_breakpoints_for_industry above, for the SAME
    underlying cause - capital_employed already uses debt_for_roic=total_liabilities for
    depository banks/insurers (see that override's own comment in vqg_quality.py), so a bank's
    capital_employed is ~its entire (deposit-funded, hence enormous) balance sheet,
    structurally floors roce_pct into single digits regardless of real capital efficiency
    (JPM=3.85%, BAC=3.40%, WFC=3.03%, C=3.87%, GS=12.55%, MS=4.21% - the
    8.0-floors-to-~19/25.0-caps-to-100 industrial curve scored JPM/BAC/WFC/C around 15-20
    despite GS's genuinely-higher 12.55% showing real cross-sectional variation exists to
    reward). Insurers get the same single blended curve precedent as
    debt_to_equity_score_for_industry/roa_breakpoints_for_industry's
    INSURANCE_UNDERWRITER_INDUSTRIES override (P&C underwriters PGR/TRV/ALL live-confirmed
    5.72-11.79% run meaningfully higher than life insurers MET/PRU's ~0.82-0.85%, same
    reserve-heavy-balance-sheet split ROA's curve already accounts for) - hand-calibrated to
    credit P&C-typical ROCE highly without being so generous it validates a genuinely weak
    life-insurer ROCE. Breakpoints hand-set (not FM-backtested), same as every other curve in
    this function - this curve-scored roce_score is provisional only, see the quality_
    components comment in vqg_quality.py: update_quality_sector_neutral_scores() overwrites
    the final quality_score for every sector via sector-neutral z-scoring of raw roce_pct.

    FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, same utility evidence
    as roa_breakpoints_for_industry/debt_to_equity_score_for_industry): capital_employed for a
    regulated utility is ~its entire rate-base-financed balance sheet, same structural
    compression as banks/insurers - live-confirmed ROCE 3.96-7.23% across the same 16-symbol
    utility set (see UTILITY_INDUSTRIES's own comment).
    """
    if industry in _owner().DEPOSITORY_BANK_INDUSTRIES:
        return [(3.0, 40.0), (6.0, 75.0), (10.0, 100.0)]
    if industry in _owner().INSURANCE_UNDERWRITER_INDUSTRIES:
        return [(3.5, 40.0), (7.0, 80.0), (12.0, 100.0)]  # recalibrated+IC-validated 20260907
    if industry in _owner().UTILITY_INDUSTRIES:
        return [(5.2, 40.0), (8.0, 80.0), (13.0, 100.0)]
    return [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)]


def debt_to_equity_score_for_industry(debt_to_equity_val: float | None, industry: str | None) -> float | None:
    """Debt-to-Equity score: inverted (lower leverage = higher score), sector-conditioned.

    Industrial default: 0.5 maps to 75, 1.0 to 50, 2.0+ to 0. Negative D/E (negative book
    equity, real financial distress) floors to 0 rather than inverting into a spuriously high
    score.

    FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit): this industrial-
    leverage curve was being fed the SAME debt_to_equity value the depository-bank/insurance-
    underwriter override (see vqg_quality.py's `debt_for_roic` computation) deliberately
    inflates by using total_liabilities (deposits/policy reserves) as the debt numerator. A
    deposit-funded bank sits at 8-15x by construction (JPM/BAC/WFC live-verified at
    10.25/11.21/10.85), so the 2.0-floors-to-0 curve zeroed this component for essentially
    every bank/insurer in the universe regardless of actual balance-sheet health, dragging
    down ~25-27% of their Quality safety_cluster_score no matter how well-capitalized they
    actually were. The curve's breakpoints were never recalibrated when the metric definition
    changed for these two sectors. Separate curves below, scaled to each sector's typical
    deposit/reserve-inclusive range (banks ~8-15x, insurers ~2.5-11.5x per the override
    comment's live-verified figures) rather than the industrial 0.5/1.0/2.0x scale.

    FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, 16-utility live-
    confirmed): regulated rate-base utilities run 1.11-1.91x debt_to_equity by design
    (regulators set allowed ROE against a rate base partly debt-financed) - see
    UTILITY_INDUSTRIES's own comment. Unlike the bank/insurer overrides above, this uses the
    SAME debt_to_equity value (long_term_debt-based, not total_liabilities) - utilities don't
    get the deposit/reserve-style debt_for_roic override, so no separate inflated-input
    caveat applies here, just a rescaled curve.
    """
    if debt_to_equity_val is None:
        return None
    if debt_to_equity_val < 0:
        return 0.0
    if industry in _owner().DEPOSITORY_BANK_INDUSTRIES:
        return max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 20.0) * 100.0))
    if industry in _owner().INSURANCE_UNDERWRITER_INDUSTRIES:
        return max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 12.0) * 100.0))
    if industry in _owner().UTILITY_INDUSTRIES:
        return max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 4.0) * 100.0))
    return max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 2.0) * 100.0))


def compute_gross_profitability_through_asset_turnover_reasons(
    loader: Any,
    symbol: str,
    *,
    gross_profitability: float | None,
    no_gross_profit_concept: bool,
    total_assets: float | None,
    operating_profitability: float | None,
    operating_profitability_negative_equity: bool,
    no_operating_income_concept: bool,
    operating_income_for_margin: float | None,
    stockholders_equity: float | None,
    accruals_ratio: float | None,
    operating_cash_flow: float | None,
    net_income: float | None,
    margin_volatility: float | None,
    fcf_margin: float | None,
    asset_turnover: float | None,
    revenue: float | None,
    implausible_ratio_metrics: list[str],
) -> dict[str, Any]:
    """Value + `_unavailable_reason` assignments for gross_profitability, operating_
    profitability, accruals_ratio, margin_volatility, fcf_margin, and asset_turnover - moved
    verbatim out of `_compute_quality_metrics()`, no logic change. `loader` is the
    `QualityMetricsMixin` instance (duck-typed `Any` here, same pattern as this module's own
    `_owner()`) - every gate call below (`_get_no_recent_revenue_symbols()` etc.) resolves
    against it exactly as it did as a bare `self.` call in the original method.

    Returns a dict of the 12 `metrics[...]` keys this block used to set directly; the caller
    does `metrics.update(...)` with the result.
    """
    metrics: dict[str, Any] = {}

    metrics["gross_profitability"] = gross_profitability
    metrics["gross_profitability_unavailable_reason"] = (
        (
            "implausible_ratio"
            if "gross_profitability" in implausible_ratio_metrics
            else "reit_special_entity"
            if no_gross_profit_concept
            else "no_revenue_reported"
            if symbol in loader._get_blank_check_symbols()
            or symbol in loader._get_no_recent_revenue_symbols()
            or symbol in loader._get_never_tagged_revenue_symbols()
            else "no_recent_total_assets_reported"
            if (total_assets is None or total_assets <= 0)
            and (
                symbol in loader._get_no_recent_total_assets_symbols()
                or symbol in loader._get_never_tagged_total_assets_symbols()
            )
            else "missing_sec_data"
        )
        if gross_profitability is None
        else None
    )
    metrics["operating_profitability"] = operating_profitability
    metrics["operating_profitability_unavailable_reason"] = (
        (
            "implausible_ratio"
            if "operating_profitability" in implausible_ratio_metrics
            else "negative_book_value"
            if operating_profitability_negative_equity
            else "reit_special_entity"
            if no_operating_income_concept
            # Label-only: the anchor year's income statement can lack operating_income
            # (and its EBIT fallback) even when the symbol reports it in other years.
            else "operating_income_absent_from_anchor_year"
            if operating_income_for_margin is None
            and symbol in loader._get_operating_income_available_elsewhere_symbols()
            # operating_profitability_negative_equity only fires when stockholders_equity
            # is a real value <=0 - stays False (not caught) when equity is None.
            else "stockholders_equity_not_reported"
            if stockholders_equity is None
            and (
                symbol in loader._get_no_recent_stockholders_equity_symbols()
                or symbol in loader._get_never_tagged_stockholders_equity_symbols()
            )
            else "operating_income_not_itemized"
            if symbol in loader._get_no_recent_operating_income_symbols()
            or symbol in loader._get_never_tagged_operating_income_symbols()
            else "missing_sec_data"
        )
        if operating_profitability is None
        else None
    )
    metrics["accruals_ratio"] = accruals_ratio
    metrics["accruals_ratio_unavailable_reason"] = (
        (
            "implausible_ratio"
            if "accruals_ratio" in implausible_ratio_metrics
            # FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" follow-up): a
            # registered investment company files a "Statement of Changes in Net
            # Assets" instead of a conventional cash-flow statement, leaving it with
            # ZERO fiscal_year>0 annual_cash_flow rows - too sparse to match
            # _get_no_recent_operating_cash_flow_symbols()'s own pattern. Live-confirmed
            # GGN (GAMCO Global Gold, Natural Resources & Income Trust). Checked first,
            # same priority as fcf_margin/fcf_yield's identical RIC check elsewhere.
            else "registered_investment_company_no_xbrl"
            if accruals_ratio is None and symbol in loader._get_registered_investment_company_symbols()
            # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): same
            # ETF-trust sibling-wiring gap ocf_to_net_income/fcf_to_net_income already
            # closed (an ETF/commodity/currency trust files no cash-flow statement at
            # all, same as a RIC) - accruals_ratio shares operating_cash_flow as an
            # input but was never given the matching ETF check.
            else "etf_trust_no_gaap_financials"
            if operating_cash_flow is None and symbol in loader._get_etf_trust_no_stockholders_equity_symbols()
            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): OR in the
            # full-history sibling gate - see _get_never_tagged_operating_cash_flow_symbols()'s
            # docstring for why this was a real, unmirrored gap versus free_cash_flow's
            # own identical pair of gates.
            else "no_recent_operating_cash_flow_reported"
            if operating_cash_flow is None
            and (
                symbol in loader._get_no_recent_operating_cash_flow_symbols()
                or symbol in loader._get_never_tagged_operating_cash_flow_symbols()
            )
            # Label-only: operating_cash_flow is None because the anchor year's own
            # cash-flow row is unavailable, not because the symbol lacks real OCF.
            else "operating_cash_flow_absent_from_anchor_year"
            if operating_cash_flow is None and symbol in loader._get_operating_cash_flow_available_elsewhere_symbols()
            else "no_recent_total_assets_reported"
            if (total_assets is None or total_assets <= 0)
            and (
                symbol in loader._get_no_recent_total_assets_symbols()
                or symbol in loader._get_never_tagged_total_assets_symbols()
            )
            # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): accruals_ratio
            # = (net_income - operating_cash_flow) / total_assets - the OCF numerator and
            # total_assets denominator were both already gated above, but the net_income
            # numerator never was, so a symbol with real net_income missing only for this
            # anchor year (or never tagged at all) fell straight to the generic fallback.
            # Same fcf_to_net_income/ocf_to_net_income sibling gate pair just above in this
            # file.
            else "net_income_not_reported"
            if net_income is None
            and (
                symbol in loader._get_no_recent_net_income_symbols()
                or symbol in loader._get_never_tagged_net_income_symbols()
            )
            else "net_income_absent_from_anchor_year"
            if net_income is None and symbol in loader._get_net_income_available_elsewhere_symbols()
            else "missing_sec_data"
        )
        if accruals_ratio is None
        else None
    )
    metrics["margin_volatility"] = margin_volatility
    metrics["margin_volatility_unavailable_reason"] = "insufficient_history" if margin_volatility is None else None
    # Gate on `X is None` directly (not `"X" in failed_metrics`) - the compute blocks
    # above don't append fcf_margin/asset_turnover to failed_metrics when inputs are
    # merely missing (only when the |ratio|>1000 bound fires), so gating on
    # failed_metrics left many rows with a NULL value and no reason recorded.
    metrics["fcf_margin"] = fcf_margin
    metrics["fcf_margin_unavailable_reason"] = (
        (
            "implausible_ratio"
            if "fcf_margin" in implausible_ratio_metrics
            # Closed-end funds/investment trusts file no cash-flow statement at all
            # (see _get_registered_investment_company_symbols' docstring) - checked
            # before the generic never-tagged-FCF gate below so this more specific,
            # correctly-categorized ("Legitimate / not applicable") reason wins.
            else "registered_investment_company_no_xbrl"
            if symbol in loader._get_registered_investment_company_symbols()
            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): fcf_yield's
            # own reason chain (vqg_value.py) already checks
            # _get_etf_trust_no_stockholders_equity_symbols() alongside the RIC gate;
            # fcf_margin's sibling chain here never did, despite ETF/commodity/currency
            # trusts (FXY, AAAU, GLDM, GBTC, ETHE, BITB/BITW, CANE/CORN/SOYB/WEAT/TAGS/
            # USCI, ...) filing no cash-flow statement at all for the identical reason a
            # RIC doesn't. Live-confirmed 32 universe symbols mislabeled
            # capex_never_tagged_in_recent_filings/no_recent_free_cash_flow_reported/
            # no_revenue_reported instead of this correctly-categorized
            # ("Legitimate / not applicable") reason.
            else "etf_trust_no_gaap_financials"
            if symbol in loader._get_etf_trust_no_stockholders_equity_symbols()
            # ADDED 2026-09-05: fcf_yield's own reason chain already checks this gate;
            # fcf_margin's sibling chain here never did (AIG-verified: real OCF every
            # year, capex-shaped concept stops after FY2023, not PPE-delta-recoverable
            # since AIG never tags depreciation either).
            else "capex_never_tagged_in_recent_filings"
            if symbol in loader._get_no_recent_capex_symbols()
            # fcf_margin's own cross-year fallback (fcf_margin_free_cash_flow/
            # fcf_margin_revenue above) already looks past the anchor row, so a
            # remaining None here means both inputs are genuinely absent across recent
            # fiscal years, not just off the anchor.
            else "no_recent_free_cash_flow_reported"
            if symbol in loader._get_no_recent_free_cash_flow_symbols()
            or symbol in loader._get_never_tagged_free_cash_flow_symbols()
            else "no_revenue_reported"
            if symbol in loader._get_no_recent_revenue_symbols() or symbol in loader._get_never_tagged_revenue_symbols()
            # A real free_cash_flow value exists somewhere in the symbol's history but
            # not in the same fiscal year as a real revenue value (the cross-year
            # fallback above requires both in the SAME year) - live-confirmed FTW/OBX/
            # AADX/AVEX/ALLO. Same reason free_cash_flow_unavailable_reason already
            # uses for this exact gate above - label-only, no value recomputed.
            else "free_cash_flow_absent_from_anchor_year"
            if symbol in loader._get_free_cash_flow_available_elsewhere_symbols()
            else "missing_sec_data"
        )
        if fcf_margin is None
        else None
    )
    metrics["asset_turnover"] = asset_turnover
    metrics["asset_turnover_unavailable_reason"] = (
        (
            "implausible_ratio"
            if "asset_turnover" in implausible_ratio_metrics
            else "no_revenue_reported"
            if symbol in loader._get_no_recent_revenue_symbols() or symbol in loader._get_never_tagged_revenue_symbols()
            else "no_recent_total_assets_reported"
            if (total_assets is None or total_assets <= 0)
            and (
                symbol in loader._get_no_recent_total_assets_symbols()
                or symbol in loader._get_never_tagged_total_assets_symbols()
            )
            # Label-only: revenue is None because the balance-sheet anchor year's own
            # income-statement row is unavailable, not because the symbol lacks real
            # revenue - the windowed gate above already ruled that out.
            else "revenue_absent_from_anchor_year"
            if revenue is None and symbol in loader._get_revenue_available_elsewhere_symbols()
            else "missing_sec_data"
        )
        if asset_turnover is None
        else None
    )

    return metrics
