#!/usr/bin/env python3
"""
Sector-neutral vs universe-wide composite scoring: does within-sector percentile ranking of the
5 pillars beat the current cross-universe ranking on forward returns?

Built 2026-09-07 (goal session: "best companies scoring lower than obscure ones" investigation).
Direct trigger: live query found Financial Services is 15% of the scored universe but 63% of the
top-200 composite_score names (747/5,015 vs 126/200) - traced to 4 same-day commits (5b6921d9a,
56faea426, 5994b4d31, b8a6ee5e3) that correctly fixed Quality's ROA/ROCE/debt-to-equity/FCF-margin
curves for banks/insurers/utilities (previously an industrial-company curve floored these to ~0
regardless of actual health - a real bug, not disputed here). The open question this script
answers: now that Quality is fixed, does the CURRENT universe-wide-percentile architecture let one
currently-strong sector mechanically dominate every pillar at once, and would ranking each pillar
WITHIN its own sector before combining (same percentile-rank mechanism this repo already uses for
Value's PE/PB/PS via update_value_multiples_percentiles(), just sector-conditioned) predict forward
returns better - by this repo's own established bar (era-robust: same-signed and significant in
both a full-sample and a half-split test, per fama_macbeth_composite_weights.py's own precedent).

Reuses fama_macbeth_composite_weights.py's build_pillar_proxy_records() wholesale (same 5 pillar
proxies, same point-in-time fundamentals reconstruction, same monthly cross-sections) rather than
rebuilding it - this script only asks a NEW question of that same data (sector-neutral vs
universe-wide combination), not a different pillar-formula question. Uses records_raw (the
pre-top-level-normalization frames) so both the universe-wide and sector-neutral treatments can be
built from the identical underlying data with only the normalization step differing.

Usage:
    python -m algo.research.sector_neutral_composite_test_20260907 [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import (
    PILLAR_COLS,
    PILLAR_TO_LIVE_KEY,
    build_pillar_proxy_records,
)
from algo.research.fama_macbeth_price_factors import _fama_macbeth
from loaders.stock_scores.pillar_weights import BASE_PILLAR_WEIGHTS
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def fetch_symbol_sectors() -> dict[str, str]:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT symbol, sector FROM company_profile WHERE sector IS NOT NULL")
        rows = cur.fetchall()
    return dict(rows)


def _pct_rank(s: pd.Series) -> pd.Series:
    """[0,1] percentile rank, NaN-safe (NaNs stay NaN, not ranked)."""
    return s.rank(pct=True, na_option="keep")


def build_composites(
    records_raw: list[tuple[pd.Timestamp, pd.DataFrame]],
    sector_map: dict[str, str],
    min_sector_size: int,
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    """For each month, builds THREE composite scores from the same raw pillar proxies:
      - composite_universe: each pillar percentile-ranked across the WHOLE month's cross-section
        (this is what live production's percentile mechanism, and this repo's own z-score proxy
        convention, both already do - the current architecture).
      - composite_sector: each pillar percentile-ranked WITHIN the symbol's own sector that month
        (symbols in a sector smaller than min_sector_size that month are dropped from this column
        only - too few peers for a meaningful within-sector percentile).
    Both use the same live BASE_PILLAR_WEIGHTS. Also carries `sector` through for the per-sector
    breakdown.
    """
    live_weight_map = {c: BASE_PILLAR_WEIGHTS[k] for c, k in PILLAR_TO_LIVE_KEY.items()}
    out: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for month, raw in records_raw:
        df = raw.copy()
        df["sector"] = df.index.map(sector_map)
        df = df.dropna(subset=["sector"])
        if df.empty:
            continue

        uni_pct = df[PILLAR_COLS].apply(_pct_rank)
        df["composite_universe"] = sum(uni_pct[c] * w for c, w in live_weight_map.items())

        sec_sizes = df.groupby("sector")[PILLAR_COLS[0]].transform("count")
        sector_pct = df.groupby("sector")[PILLAR_COLS].transform(_pct_rank)
        sector_composite = sum(sector_pct[c] * w for c, w in live_weight_map.items())
        df["composite_sector"] = sector_composite.where(sec_sizes >= min_sector_size)

        keep = df.dropna(subset=["composite_universe", "fwd_ret"])
        if len(keep) < 20:
            continue
        out.append((month, keep))
    return out


def _spearman_by_month(records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> list[float]:
    corrs = []
    for _month, frame in records:
        f = frame.dropna(subset=[col, "fwd_ret"])
        if len(f) < 20:
            continue
        corrs.append(f[col].corr(f["fwd_ret"], method="spearman"))
    return corrs


def _report_ic(label: str, corrs: list[float]) -> None:
    arr = np.array([c for c in corrs if not np.isnan(c)])
    if len(arr) == 0:
        print(f"{label:40s}  no usable months")
        return
    mean = arr.mean()
    se = arr.std(ddof=1) / np.sqrt(len(arr)) if len(arr) > 1 else float("nan")
    t = mean / se if se and se > 0 else float("nan")
    print(f"{label:40s}  mean_IC={mean:8.4f}  t={t:7.2f}  n_months={len(arr):4d}")


def run(start_date: str, end_date: str, min_cross_section: int, min_sector_size: int) -> None:
    logger.info("Building pillar-proxy panel (reusing fama_macbeth_composite_weights)")
    _records_partial, _records_complete, records_raw = build_pillar_proxy_records(
        start_date, end_date, min_cross_section
    )
    logger.info(f"{len(records_raw)} usable months")

    sector_map = fetch_symbol_sectors()
    records = build_composites(records_raw, sector_map, min_sector_size)
    if not records:
        raise RuntimeError("No usable months after sector join - check min_sector_size/min_cross_section")

    print(f"\n########## SECTOR-NEUTRAL vs UNIVERSE-WIDE COMPOSITE: {len(records)} months ##########")
    print(f"({records[0][0]} to {records[-1][0]})")

    print("\n=== Full-sample monthly IC (Spearman rank-IC of composite vs next-month return) ===")
    uni_ic = _spearman_by_month(records, "composite_universe")
    sec_ic = _spearman_by_month(records, "composite_sector")
    _report_ic("composite_universe (current architecture)", uni_ic)
    _report_ic("composite_sector (sector-neutral proposal)", sec_ic)

    split = len(records) // 2
    halves = [
        ("FIRST HALF", records[:split]),
        ("SECOND HALF", records[split:]),
    ]
    print("\n=== Half-split robustness (same era-robust bar this repo's other FM scripts use) ===")
    for half_label, half in halves:
        if not half:
            continue
        print(f"\n-- {half_label} ({half[0][0]} to {half[-1][0]}) --")
        _report_ic("  composite_universe", _spearman_by_month(half, "composite_universe"))
        _report_ic("  composite_sector", _spearman_by_month(half, "composite_sector"))

    print("\n=== Multivariate FM regression (fwd_ret ~ composite_universe + composite_sector jointly) ===")
    joint = [(m, f.dropna(subset=["composite_universe", "composite_sector", "fwd_ret"])) for m, f in records]
    joint = [(m, f) for m, f in joint if len(f) >= 20]
    if joint:
        res = _fama_macbeth(joint, ["composite_universe", "composite_sector"])
        for name, (mean, t) in res.items():
            print(f"  {name:25s} mean_coef={mean:10.5f}  t={t:7.2f}  n_months={len(joint)}")
    else:
        print("  not enough joint-coverage months")

    print("\n=== Does the CURRENT (universe-wide) composite predict worse inside Financial Services? ===")
    print("Per-sector mean monthly Spearman IC of composite_universe vs fwd_ret, pooled across all months:")
    all_rows = []
    for month, frame in records:
        f = frame.copy()
        f["month"] = month
        all_rows.append(f)
    panel = pd.concat(all_rows, ignore_index=False)
    sector_ic: dict[str, list[float]] = {}
    for (_month, sector), grp in panel.groupby(["month", "sector"]):
        g = grp.dropna(subset=["composite_universe", "fwd_ret"])
        if len(g) < 15:
            continue
        ic = g["composite_universe"].corr(g["fwd_ret"], method="spearman")
        if not np.isnan(ic):
            sector_ic.setdefault(sector, []).append(ic)
    rows = []
    for sector, ics in sector_ic.items():
        arr = np.array(ics)
        mean = arr.mean()
        se = arr.std(ddof=1) / np.sqrt(len(arr)) if len(arr) > 1 else float("nan")
        t = mean / se if se and se > 0 else float("nan")
        rows.append((sector, mean, t, len(arr)))
    rows.sort(key=lambda r: r[1], reverse=True)
    print(f"{'sector':28s} {'mean_IC':>10s} {'t':>7s} {'n_months':>9s}")
    for sector, mean, t, n in rows:
        flag = "  <-- FINANCIAL SERVICES" if sector == "Financial Services" else ""
        print(f"{sector:28s} {mean:10.4f} {t:7.2f} {n:9d}{flag}")

    print("\n=== Current top-decile sector concentration this test's own sample would produce ===")
    for month, frame in records[-1:]:
        top_decile = frame.nlargest(max(1, len(frame) // 10), "composite_universe")
        print(f"Last month ({month}): top decile n={len(top_decile)}")
        print(top_decile["sector"].value_counts(normalize=True).round(3).to_string())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2015-06-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument(
        "--min-sector-size",
        type=int,
        default=15,
        help="Minimum symbols in a sector that month for composite_sector to be computed",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.min_sector_size)


if __name__ == "__main__":
    main()
