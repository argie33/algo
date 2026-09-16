#!/usr/bin/env python3
"""Per-pillar validation: how well does our raw pillar score (momentum/quality/value/growth/
risk) agree with a real, liquid, single-factor ETF's actual live holdings weights?

Added 2026-09-15 (goal: "layers of slop" scoring audit) as a standing, reusable version of an
ad hoc check (see scratch/live_pillar_vs_factor_etf_20260915.py and
scratch/momentum_mtum_fulldist_rank_check_20260914.py) that validated the momentum pillar's
2026-09-15 mom_6m/mom_12_1 rebalance by correlating momentum_score against real MTUM holdings
(Spearman rho improved 0.186 -> 0.564 after that fix). This generalizes the same method to all
five pillars.

METHODOLOGY: for each pillar, fetch that ETF's holdings, preferring a cached daily-holdings CSV
(%TEMP%/algo-nport-cache/<etf>_daily_holdings_*.csv, ticker-keyed directly) over the cached
quarterly N-PORT XML (%TEMP%/algo-nport-cache/<ticker>_nport.xml, CUSIP-keyed, resolved via
sec_13f_cusip_crosswalk) - see `_load_ticker_weights`'s own docstring (FIXED 2026-09-16) for why:
N-PORT is a quarterly regulatory filing that can lag the actual holdings by months, which
produced a false alarm on Momentum specifically (see that docstring for the live numbers). This
script does NOT re-fetch from EDGAR/iShares itself - it reads the existing cache and skips a
pillar (does not raise) if neither file is cached. Then, for the intersection of
(top-800-by-market-cap, non-ETF universe) and (fund's held names), compute Spearman rank
correlation between the fund's per-holding weight and our own raw pillar score.

PRIMARY METRIC IS TOP-N RANK AGREEMENT, NOT CORPUS-WIDE CORRELATION (FIXED 2026-09-15, same-day
follow-up #2): a whole-corpus Spearman rho is the wrong shape of answer to the question that
actually matters - "does our leaderboard surface the same names a real factor fund would pick" -
because it averages agreement across the full ~100-160 name overlap, most of which nobody would
ever trade off either list. Live-confirmed failure mode: risk_score vs USMV showed a positive,
significant bulk rho (0.179, p=0.024) while precision@25 was only 2/25 (8%) - broad direction
roughly right, but the ordering of the names that would actually get selected onto a leaderboard
was essentially uncorrelated. A single corpus-wide number can hide that. So this script now
reports, per pillar, PRIMARY: precision@10/25/50 (of our top-N by raw score, what fraction also
land in the ETF's own top-N by cap-neutral tilt) and a top-N-restricted rank correlation
(Spearman computed only over the union of both sides' top-50 tilt/score names, so disagreement
among the serious contenders counts and disagreement among the hundreds of names neither side
would ever pick doesn't dilute it). SECONDARY (diagnostic only, kept for continuity/comparison
with the numbers already recorded in this session): whole-corpus Spearman rho, both cap-neutral
and raw-weight.

CAP-NEUTRALIZATION (FIXED 2026-09-15, same-day follow-up): the initial version of this script
correlated our pillar score directly against each ETF's RAW per-holding weight. That's wrong -
these are cap-weighted-with-a-tilt funds, not pure factor-rank funds, so raw weight is dominated
by market cap, not by the factor itself (live-confirmed for VLUE: Spearman(weight, market_cap) =
0.763, p<1e-28). Our own pillar scores are correctly cap-independent cross-sectional percentiles
by construction (see each pillar's own sector-neutral z-scoring), so correlating them against a
cap-dominated weight conflates "is this stock big" with "does this stock have the factor
characteristic" and understates every pillar's true agreement - confirmed on value: raw-weight
rho was -0.075 (p=0.384, looked like a real problem), cap-neutral rho is +0.255 (p=0.002, a real
significant signal, no actual defect). Fix: correlate our score against `weight / market_cap`
instead of raw `weight` - a simple "tilt intensity" proxy (how overweight is this holding
relative to what pure cap-weighting alone would give it) that's still well-defined and stable
enough for a periodic sanity check even though a small number of tiny holdings can make the
ratio noisy in the tail; a regression-residual approach (weight ~ cap, correlate residuals)
would be more statistically rigorous but adds real complexity for a rank-correlation check that
just needs monotonic cap-independence, not exact residualization - not adopted here, revisit if
the ratio approach turns out too noisy in practice. Both old (raw-weight) and new (cap-neutral)
numbers are reported side by side so the effect of this fix stays visible over time.

INTERPRETING THE NUMBERS: do not expect anything close to 1.0/100% on any metric here, ever -
even two legitimate, independently-built implementations of "the same" factor rarely exceed
~0.7 correlation with each other, because universe selection, rebalancing cadence, and
secondary-factor blending differ between any two real constructions of a factor. A single ETF
is one reasonable reference point, not a ground-truth oracle to converge to exactly - chasing a
much higher number here would mean cloning that one fund's idiosyncratic construction choices,
not building a more correct factor. A cap-neutral corpus-wide rho in the ~0.25-0.6 range is a
healthy secondary signal (matches momentum's known-good 0.564 and value's 0.255). For the
primary top-N metrics, there's no similarly-established "healthy" band yet (this is the first
run of this version of the check) - use the THREE-WAY PATTERN below to triage instead of a
single threshold:
  - HEALTHY: precision@25 and top-N rank correlation both positive/reasonable alongside a
    decent bulk rho - the pillar agrees with the reference fund at both scales.
  - BULK-OK-TOP-BAD (the risk-pillar pattern found this session): decent/significant bulk rho
    but poor top-N precision - broad direction is right, but the specific names a leaderboard
    would surface diverge from what the reference fund would pick. Worth investigating the
    pillar's behavior specifically among its own highest-ranked names, not its overall
    construction.
  - WEAK-BOTH: poor at both scales - the more serious case, worth investigating the pillar's
    core construction, not just its tail behavior.

REFERENCE ETF PER PILLAR (one representative, liquid, real single-factor fund each - not our
choice to be "correct", just the standard institutional proxy for that factor):
  momentum -> MTUM (iShares MSCI USA Momentum Factor ETF)
  quality  -> QUAL (iShares MSCI USA Quality Factor ETF)
  value    -> VLUE (iShares MSCI USA Value Factor ETF)
  growth   -> QGRO (American Century US Quality Growth ETF) - CAVEAT: unlike the other four,
              there is no widely-tracked pure "MSCI USA Growth Factor" single-factor ETF as
              liquid/well-known as MTUM/QUAL/VLUE - style-box growth funds (IWF/VUG) mostly
              proxy growth via low value multiples (P/E, P/B), which is closer to "inverse
              value" than an independent growth factor. QGRO is a closer analogue (real
              quality-growth factor construction) but is a weaker ground truth than the other
              three reference funds - treat the growth pillar's number as directionally
              informative, not as strong a bar as the others.
  risk     -> USMV (iShares MSCI USA Min Volatility Factor ETF) - risk_score in this codebase
              is "higher = safer" (see loaders/stock_scores/risk_scoring.py), so a well-built
              risk pillar should positively correlate with USMV weight the same direction as
              the other four pillars, not inversely.

COMPOSITE IS DELIBERATELY NOT INCLUDED HERE: no single real ETF targets "best overall
opportunity" the way our composite_score claims to - a composite validated this way would just
be measuring agreement with whichever multi-factor fund's own (different, undisclosed) blend
you happened to pick, not correctness. Composite needs a different validation approach entirely
(forward-return Information Coefficient against actual subsequent returns, the same approach
scripts/score_realized_ic_monitor.py already takes for the live-scored universe) - not covered
by this script.

Usage:
    python scripts/factor_etf_correlation_check.py                  # all 5 pillars
    python scripts/factor_etf_correlation_check.py --pillar momentum
    python scripts/factor_etf_correlation_check.py --top-n 50
    python scripts/factor_etf_correlation_check.py --dry-run         # same as default; no DB
                                                                       # writes happen either
                                                                       # way (read-only tool),
                                                                       # flag kept for CLI
                                                                       # consistency with the
                                                                       # other periodic-check
                                                                       # scripts in this repo
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from pathlib import Path

from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

NPORT_CACHE = Path(os.environ.get("TEMP", "/tmp")) / "algo-nport-cache"

PILLARS: dict[str, dict[str, str]] = {
    "momentum": {"etf": "MTUM", "file": "mtum_nport.xml", "score_col": "momentum_score"},
    "quality": {"etf": "QUAL", "file": "qual_nport.xml", "score_col": "quality_score"},
    "value": {"etf": "VLUE", "file": "vlue_nport.xml", "score_col": "value_score"},
    "growth": {"etf": "QGRO", "file": "qgro_nport.xml", "score_col": "growth_score"},
    "risk": {"etf": "USMV", "file": "usmv_nport.xml", "score_col": "risk_score"},
}

TOP_N_UNIVERSE = 800  # top-N-by-market-cap non-ETF universe, matches the ad hoc script's band


def parse_cusip_weights(path: Path) -> dict[str, float]:
    with open(path, encoding="utf-8", errors="ignore") as f:
        xml = f.read()
    out: dict[str, float] = {}
    for block in xml.split("<invstOrSec>")[1:]:
        cm = re.search(r"<cusip>([A-Z0-9]{9})</cusip>", block)
        wm = re.search(r"<pctVal>([\d.\-]+)</pctVal>", block)
        if cm and wm:
            out[cm.group(1)] = float(wm.group(1))
    return out


def _nport_report_date(path: Path) -> str | None:
    """N-PORT's own <repPdDate> - the holdings-as-of date the filing actually reports, which
    can lag the filing/cache date by months (N-PORT is a quarterly filing with up to a 60-day
    lag) - see check_pillar's own docstring note for why this matters for momentum specifically."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        m = re.search(r"<repPdDate>([\d-]+)</repPdDate>", f.read())
    return m.group(1) if m else None


def parse_daily_holdings_csv(path: Path) -> dict[str, float]:
    """Parse an iShares-style 'daily holdings' CSV (Ticker/Weight (%) columns after a
    metadata preamble) directly to {ticker: weight_pct} - no CUSIP crosswalk needed, and
    genuinely daily (not quarterly-lagged like N-PORT - see check_pillar's docstring)."""
    out: dict[str, float] = {}
    with open(path, encoding="utf-8-sig", errors="ignore") as f:
        lines = f.readlines()
    header_idx = next((i for i, line in enumerate(lines) if line.startswith("Ticker,")), None)
    if header_idx is None:
        return out
    for row in csv.DictReader(lines[header_idx:]):
        ticker = (row.get("Ticker") or "").strip()
        weight_raw = (row.get("Weight (%)") or "").strip()
        if not ticker or not weight_raw:
            continue
        try:
            out[ticker] = float(weight_raw)
        except ValueError:
            continue
    return out


def _load_ticker_weights(cur: object, pillar: str, cfg: dict[str, str]) -> dict[str, float] | None:
    """Prefer the daily-holdings CSV over the quarterly N-PORT XML (FIXED 2026-09-16, see
    factor_etf_pillar_check_stale_nport_vs_daily_csv_20260916): live-verified the cached
    mtum_nport.xml's own <repPdDate> is 2026-04-30 - 4.5 months stale relative to today - while
    mtum_daily_holdings_*.csv is genuinely current (iShares publishes this daily). For a
    slow-moving factor (Quality/Value fundamentals barely change month to month) that lag barely
    matters, but Momentum's whole point is that the winning names ROTATE - comparing today's
    momentum_score against an April holdings snapshot produced a false WEAK-BOTH/negative
    top-N-rho alarm (cap-neutral rho 0.088 via stale N-PORT vs. 0.44 via the fresh CSV,
    independently re-verified against live stock_scores this session) that looked like a real
    scoring-architecture defect but was entirely a data-freshness bug in THIS script, not in
    momentum_scoring.py. CSV also skips the CUSIP->crosswalk step entirely (one less place to
    silently drift/mismap). Falls back to N-PORT (with its staleness logged) only when no CSV is
    cached for that ETF - matches this script's own "read the existing cache only" convention.
    """
    csv_candidates = sorted(NPORT_CACHE.glob(f"{cfg['etf'].lower()}_daily_holdings_*.csv"))
    if csv_candidates:
        csv_path = csv_candidates[-1]
        weights = parse_daily_holdings_csv(csv_path)
        if weights:
            logger.info(f"[FACTOR_ETF] {pillar}: using daily-holdings CSV {csv_path.name} ({len(weights)} holdings)")
            return weights
        logger.warning(f"[FACTOR_ETF] {pillar}: {csv_path.name} parsed to 0 holdings - falling back to N-PORT.")

    nport_path = NPORT_CACHE / cfg["file"]
    if not nport_path.exists():
        logger.warning(
            f"[FACTOR_ETF] {pillar}: no cached daily-holdings CSV or N-PORT XML - skipping "
            f"(this script reads the existing cache only, it does not fetch from EDGAR itself)."
        )
        return None

    report_date = _nport_report_date(nport_path)
    logger.warning(
        f"[FACTOR_ETF] {pillar}: no daily-holdings CSV cached, falling back to N-PORT "
        f"{nport_path.name} (holdings as of {report_date or 'unknown date'} - may be stale "
        f"for a fast-rotating factor like momentum, see _load_ticker_weights docstring)."
    )
    cusip_weights = parse_cusip_weights(nport_path)
    cur.execute("SELECT cusip, ticker FROM sec_13f_cusip_crosswalk")  # type: ignore[attr-defined]
    cusip_to_ticker = dict(cur.fetchall())  # type: ignore[attr-defined]
    return {cusip_to_ticker[c]: w for c, w in cusip_weights.items() if c in cusip_to_ticker}


def check_pillar(cur: object, pillar: str, cfg: dict[str, str], top_n: int) -> dict[str, object] | None:
    ticker_weights = _load_ticker_weights(cur, pillar, cfg)
    if not ticker_weights:
        return None

    score_col = cfg["score_col"]
    cur.execute(  # type: ignore[attr-defined]
        f"""
        SELECT ss.symbol, ss.{score_col}, vm.market_cap
        FROM stock_scores ss
        JOIN value_metrics vm ON vm.symbol = ss.symbol
        JOIN stock_symbols su ON su.symbol = ss.symbol
        WHERE su.symbol NOT IN (SELECT symbol FROM etf_symbols)
          AND COALESCE(vm.market_cap, 0) > 0
          AND ss.{score_col} IS NOT NULL
        ORDER BY vm.market_cap DESC
        LIMIT %s
        """,
        (top_n,),
    )
    rows = cur.fetchall()  # type: ignore[attr-defined]
    score_map = {sym: float(score) for sym, score, _cap in rows}
    cap_map = {sym: float(cap) for sym, _score, cap in rows}

    held_pairs = [(sym, wt) for sym, wt in ticker_weights.items() if sym in score_map]
    n = len(held_pairs)
    if n < 5:
        logger.warning(
            f"[FACTOR_ETF] {pillar}: only {n} of {cfg['etf']}'s holdings overlap our "
            f"top-{top_n}-by-market-cap scored universe - too few to correlate."
        )
        return {
            "pillar": pillar,
            "etf": cfg["etf"],
            "n": n,
            "rho": None,
            "pval": None,
            "rho_raw": None,
            "pval_raw": None,
            "hit_rate": None,
        }

    weights = [wt for _, wt in held_pairs]
    scores = [score_map[sym] for sym, _ in held_pairs]
    # Cap-neutralized "tilt intensity": how overweight is this holding relative to pure
    # cap-weighting alone. See module docstring's CAP-NEUTRALIZATION note for why raw weight
    # alone is the wrong comparison (dominated by market cap, not the factor itself).
    tilt_map = {sym: wt / cap_map[sym] for sym, wt in held_pairs}
    tilt = [tilt_map[sym] for sym, _ in held_pairs]
    rho, pval = stats.spearmanr(tilt, scores)
    rho_raw, pval_raw = stats.spearmanr(weights, scores)

    # PRIMARY metrics: top-N rank agreement, computed over the overlap population (held_pairs) -
    # both "our top-N by score" and "the fund's top-N by cap-neutral tilt" are ranked within
    # this same overlap set, so precision@N answers "of the names both sides could even agree
    # on, how many did they actually agree belong near the top" rather than being diluted by
    # names only one side covers at all.
    our_ranked = sorted(held_pairs, key=lambda t: score_map[t[0]], reverse=True)
    etf_ranked = sorted(held_pairs, key=lambda t: tilt_map[t[0]], reverse=True)
    precision: dict[int, float | None] = {}
    for top_n_k in (10, 25, 50):
        if n < top_n_k:
            precision[top_n_k] = None
            continue
        our_top = {sym for sym, _ in our_ranked[:top_n_k]}
        etf_top = {sym for sym, _ in etf_ranked[:top_n_k]}
        precision[top_n_k] = len(our_top & etf_top) / top_n_k

    # Top-N-restricted rank correlation: Spearman over the union of both sides' top-50 names
    # only - this is what "agreement among the serious contenders" looks like, uncontaminated
    # by the hundreds of names neither side would ever put on a leaderboard.
    union_top50 = {sym for sym, _ in our_ranked[:50]} | {sym for sym, _ in etf_ranked[:50]}
    if len(union_top50) >= 5:
        u_scores = [score_map[sym] for sym in union_top50]
        u_tilts = [tilt_map[sym] for sym in union_top50]
        topn_rho, topn_pval = stats.spearmanr(u_tilts, u_scores)
    else:
        topn_rho, topn_pval = None, None

    ranked = sorted(score_map.items(), key=lambda t: t[1], reverse=True)
    our_top25 = [sym for sym, _ in ranked[:25]]
    held_set = set(ticker_weights)
    hit_count = sum(1 for sym in our_top25 if sym in held_set)

    result = {
        "pillar": pillar,
        "etf": cfg["etf"],
        "n": n,
        "precision_10": precision[10],
        "precision_25": precision[25],
        "precision_50": precision[50],
        "topn_rho": topn_rho,
        "topn_pval": topn_pval,
        "topn_union_size": len(union_top50),
        "rho": rho,
        "pval": pval,
        "rho_raw": rho_raw,
        "pval_raw": pval_raw,
        "hit_rate": hit_count / 25.0,
        "hit_count": hit_count,
    }

    def _fmt_pct(v: float | None) -> str:
        return f"{v * 100:.0f}%" if v is not None else "n/a"

    topn_rho_s = f"{topn_rho:.3f} (p={topn_pval:.3f})" if topn_rho is not None else "n/a"
    logger.info(
        f"[FACTOR_ETF] {pillar.upper():9s} vs {cfg['etf']}: "
        f"PRIMARY precision@10/25/50 = {_fmt_pct(precision[10])}/{_fmt_pct(precision[25])}/"
        f"{_fmt_pct(precision[50])}, top-N rank rho={topn_rho_s} (n_union={len(union_top50)}) | "
        f"secondary bulk Spearman(weight/cap, {score_col}) rho={rho:.3f} (p={pval:.3f}, n={n}) "
        f"[raw-weight rho={rho_raw:.3f}, p={pval_raw:.3f}]"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pillar", choices=sorted(PILLARS), help="Check a single pillar only")
    parser.add_argument("--top-n", type=int, default=TOP_N_UNIVERSE, help="Market-cap-ranked universe size")
    parser.add_argument("--dry-run", action="store_true", help="No-op flag; this tool never writes to the DB")
    args = parser.parse_args()

    targets = {args.pillar: PILLARS[args.pillar]} if args.pillar else PILLARS

    results = []
    with DatabaseContext("read") as cur:
        for pillar, cfg in targets.items():
            result = check_pillar(cur, pillar, cfg, args.top_n)
            if result:
                results.append(result)

    def _pct(v: object) -> str:
        return f"{v * 100:.0f}%" if isinstance(v, float) else "n/a"

    print("\n=== PRIMARY: top-N rank agreement ===")
    print(f"{'PILLAR':<10} {'ETF':<6} {'N':>5} {'P@10':>6} {'P@25':>6} {'P@50':>6} {'TOP-N RHO':>10} {'P-VALUE':>9}")
    for r in results:
        topn_rho_s = f"{r['topn_rho']:.3f}" if isinstance(r.get("topn_rho"), float) else "n/a"
        topn_pval_s = f"{r['topn_pval']:.3f}" if isinstance(r.get("topn_pval"), float) else "n/a"
        print(
            f"{r['pillar']:<10} {r['etf']:<6} {r['n']:>5} "
            f"{_pct(r.get('precision_10')):>6} {_pct(r.get('precision_25')):>6} {_pct(r.get('precision_50')):>6} "
            f"{topn_rho_s:>10} {topn_pval_s:>9}"
        )

    print("\n=== SECONDARY: whole-corpus correlation (diagnostic only, see module docstring) ===")
    print(
        f"{'PILLAR':<10} {'ETF':<6} {'N':>5} {'RHO(cap-neutral)':>17} {'P-VALUE':>9} "
        f"{'RHO(raw-weight)':>16} {'P-VALUE':>9} {'TOP-25 HIT':>11}"
    )
    for r in results:
        rho_s = f"{r['rho']:.3f}" if r["rho"] is not None else "n/a"
        pval_s = f"{r['pval']:.3f}" if r["pval"] is not None else "n/a"
        rho_raw_s = f"{r['rho_raw']:.3f}" if r.get("rho_raw") is not None else "n/a"
        pval_raw_s = f"{r['pval_raw']:.3f}" if r.get("pval_raw") is not None else "n/a"
        hit_s = f"{r['hit_count']}/25" if r.get("hit_count") is not None else "n/a"
        print(
            f"{r['pillar']:<10} {r['etf']:<6} {r['n']:>5} {rho_s:>17} {pval_s:>9} "
            f"{rho_raw_s:>16} {pval_raw_s:>9} {hit_s:>11}"
        )

    print("\n=== TRIAGE (see module docstring's THREE-WAY PATTERN) ===")
    for r in results:
        p25 = r.get("precision_25")
        bulk_rho = r.get("rho")
        if not isinstance(p25, float) or not isinstance(bulk_rho, float):
            category = "INSUFFICIENT DATA"
        elif bulk_rho >= 0.15 and p25 >= 0.30:
            category = "HEALTHY"
        elif bulk_rho >= 0.15 and p25 < 0.30:
            category = "BULK-OK-TOP-BAD (investigate top-ranked-name behavior specifically)"
        else:
            category = "WEAK-BOTH (investigate core construction)"
        print(f"{r['pillar']:<10} {category}")


if __name__ == "__main__":
    main()
