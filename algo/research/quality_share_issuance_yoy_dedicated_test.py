#!/usr/bin/env python3
"""Dedicated full-sample + half-split Fama-MacBeth test for share_issuance_yoy, controlling for
the CURRENT live 8 non-trend Quality components (roa/roce/debt_to_equity/fcf_margin/roe/
interest_coverage/payout_ratio/margin_volatility_3y). operating_margin_trend/net_margin_trend/
roe_trend are NOT available in build_quality_panel() (need a separate point-in-time margin/ROE-
delta panel this script doesn't build) - disclosed omission, not fabricated, same convention as
fama_macbeth_composite_weights.py's growth_proxy.

Prompted by the 2026-08-27 pillar-agnostic clustering/joint-importance diagnostic finding
share_issuance_yoy ranks #12/54 in joint SHAP importance - never before tested full-sample +
half-split on its own (only ever tested in EXTENDED_CANDIDATE_COLS' full-sample-only pass, or as
part of the SHAP sweep's interaction-strength ranking, neither of which is this repo's
established inclusion bar).
"""

import logging

import numpy as np

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LIVE_CONTROL_COLS = [
    "roa",
    "roce",
    "debt_to_equity",
    "fcf_margin",
    "roe",
    "interest_coverage",
    "payout_ratio",
    "margin_volatility_3y",
]
ALL_COLS = [*LIVE_CONTROL_COLS, "share_issuance_yoy"]


def main() -> None:
    fund = fetch_annual_quality_fundamentals()
    panel = build_quality_panel(fund)
    price_df = fetch_month_end_prices("2014-01-01", "2026-08-01")
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly = merge_asof_monthly(months, panel, cols=ALL_COLS)

    records = []
    for i, month in enumerate(months):
        frame = monthly.get(month)
        if frame is None or frame.empty:
            continue
        frame = frame.dropna(subset=ALL_COLS)
        if len(frame) < 30:
            continue
        price_now = px.iloc[i].reindex(frame.index)
        if i + 1 >= len(months):
            continue
        price_fwd = px.iloc[i + 1].reindex(frame.index)
        fwd_ret = (price_fwd - price_now) / price_now
        f = frame.copy()
        f["fwd_ret"] = fwd_ret
        f = f.dropna(subset=["fwd_ret"])
        if len(f) < 30:
            continue
        # BUG CAUGHT mid-test: share_issuance_yoy has no implausible-ratio bound (same bug class
        # as margin_volatility/fcf_margin's own pre-fix history elsewhere in this repo) - raw max
        # 971,453 (a near-zero-prior-shares artifact) corrupts z-scoring's mean/std. Cap at 200%
        # YoY (a generous real-world ceiling - genuine share counts rarely more than triple in a
        # year outside SPAC-merger-type events, which aren't the mechanism this factor is meant
        # to capture) before z-scoring, same "cap don't fabricate" discipline used throughout.
        f["share_issuance_yoy"] = f["share_issuance_yoy"].clip(-1.0, 2.0)
        for c in ALL_COLS:
            s = f[c]
            std = s.std()
            f[c] = (s - s.mean()) / std if std and std > 0 else 0.0
        records.append((month, f))

    if not records:
        print("NO USABLE MONTHS - merge_asof_monthly likely returned a different shape than assumed")
        return

    print(f"Usable months: {len(records)} ({records[0][0]} to {records[-1][0]})")
    coverage = np.mean([len(f) for _, f in records])
    print(f"Mean cross-section size: {coverage:.0f}")

    uni = _fama_macbeth(records, ["share_issuance_yoy"])
    print(
        f"\nUnivariate share_issuance_yoy: mean={uni['share_issuance_yoy'][0]:.5f} t={uni['share_issuance_yoy'][1]:.2f}"
    )

    multi = _fama_macbeth(records, ALL_COLS)
    print(
        f"Multivariate (controlling for live 8) share_issuance_yoy: mean={multi['share_issuance_yoy'][0]:.5f} t={multi['share_issuance_yoy'][1]:.2f}"
    )

    split = len(records) // 2
    for label, half in (("FIRST HALF", records[:split]), ("SECOND HALF", records[split:])):
        uni_h = _fama_macbeth(half, ["share_issuance_yoy"])
        multi_h = _fama_macbeth(half, ALL_COLS)
        print(
            f"{label} ({half[0][0]} to {half[-1][0]}, n={len(half)}): "
            f"uni t={uni_h['share_issuance_yoy'][1]:.2f}  multi t={multi_h['share_issuance_yoy'][1]:.2f}"
        )


if __name__ == "__main__":
    main()
