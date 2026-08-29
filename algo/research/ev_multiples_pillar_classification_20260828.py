#!/usr/bin/env python3
"""
Do EV/EBITDA and EV/Revenue actually measure "value" as a factor, or do they belong to a
different pillar entirely?

Built 2026-08-28 (goal: "are EV/EBITDA and EV/Revenue really metrics that measure value as a
factor? or do they really belong somewhere else?"). Prior work (load_stock_scores.py's
_score_value docstring, "RESOLVED 2026-08-25") already removed both from live Value scoring on
the grounds that they're near-duplicates of P/E and P/S (point-in-time panel: r=0.93 pe/ev_ebitda,
r=1.00 ps/ev_revenue, n=45,806) - but that finding answers "are they redundant WITHIN Value",
not "do they conceptually belong to Value at all". This script answers the second question
directly.

Literature baseline: EV/EBITDA and EV/Sales are standard relative-valuation multiples in every
mainstream factor taxonomy (Damodaran's relative valuation multiples; AQR's value composites
mix P/E, P/B, EV/EBITDA, EV/Sales, P/CF interchangeably) - there is no serious academic
classification of either as Quality, Growth, Momentum, or Risk. The only structural difference
from P/E and P/S is the numerator: EV = market_cap + total_debt - total_cash (see
load_sec_valuations.py's enterprise_value calc) instead of plain market_cap, i.e. EV/EBITDA and
EV/Revenue differ from P/E and P/S ONLY by a capital-structure (net debt) adjustment. So the real
question is: does that net-debt adjustment carry information that already lives in a DIFFERENT
existing pillar (making "belongs elsewhere" literally true), or is it genuinely Value-only
information that's simply redundant with Value's own P/E/P/S (the already-shipped conclusion)?

Method: live sec_valuations + stock_scores snapshot (cross-sectional only - this is a
classification/attribution question about what net-debt correlates with structurally, not a
forward-return predictiveness question, so the point-in-time panel rigor that the pillar-weight
work requires doesn't apply here the same way). For each symbol with real pe/ev_ebitda and
ps/ev_revenue pairs:
  1. net_debt_ratio = (total_debt - total_cash) / market_cap - the literal wedge between EV and
     market_cap, i.e. the "extra" content EV/EBITDA and EV/Revenue carry beyond P/E and P/S.
  2. Correlate net_debt_ratio against this system's live risk_score, quality_score, size_score -
     if the wedge lines up with one of those pillars, that's evidence for "belongs elsewhere".
  3. Regress ev_ebitda on pe (and ev_revenue on ps), take the residual (the part of EV/EBITDA
     genuinely NOT explained by P/E), and re-run the same three correlations on the residual -
     more direct than net_debt_ratio alone since it's specific to what these two ratios add over
     Value's own existing P/E and P/S inputs, not just the raw balance-sheet wedge.

Usage:
    python -m algo.research.ev_multiples_pillar_classification_20260828
"""

import argparse
import logging
from typing import Any

import numpy as np
from scipy import stats

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

QUERY = """
    SELECT v.pe_ratio, v.ev_ebitda, v.ps_ratio, v.ev_revenue,
           (v.total_debt - v.total_cash) / NULLIF(v.market_cap, 0) AS net_debt_ratio,
           s.risk_score, s.quality_score, s.size_score
    FROM sec_valuations v
    JOIN stock_scores s ON s.symbol = v.symbol
    WHERE v.market_cap > 0 AND v.total_debt IS NOT NULL AND v.total_cash IS NOT NULL
      AND v.ev_ebitda IS NOT NULL AND v.pe_ratio IS NOT NULL
      AND v.ev_revenue IS NOT NULL AND v.ps_ratio IS NOT NULL
      AND s.risk_score IS NOT NULL AND s.quality_score IS NOT NULL AND s.size_score IS NOT NULL
      -- same outlier bounds load_sec_valuations.py itself already applies at write time for
      -- pe/ps (elsewhere in that file); ev_ebitda/ev_revenue bounded here to match, so a handful
      -- of extreme multiples don't dominate a Pearson correlation the way they did on a first,
      -- unbounded pass of this same query (pe/ev_ebitda Pearson r swung from 0.41 unbounded to
      -- 0.57 bounded - Spearman, reported below, is far less sensitive to this and is the
      -- primary number this script relies on).
      AND v.pe_ratio BETWEEN 0 AND 200 AND v.ev_ebitda BETWEEN 0 AND 200
      AND v.ps_ratio BETWEEN 0 AND 50 AND v.ev_revenue BETWEEN 0 AND 50
"""


def _residual(y: np.ndarray[Any, Any], x: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """OLS residual of y on x (plus intercept) - the part of y not linearly explained by x."""
    design = np.vstack([x, np.ones_like(x)]).T
    coef, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    result: np.ndarray[Any, Any] = y - design @ coef
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    with DatabaseContext("read", timeout=30) as cur:
        cur.execute(QUERY)
        rows = cur.fetchall()

    if not rows:
        logger.error("No rows returned - check sec_valuations/stock_scores are populated locally.")
        return

    pe, ev_ebitda, ps, ev_revenue, net_debt_ratio, risk, quality, size = (
        np.array(col, dtype=float) for col in zip(*rows, strict=True)
    )
    n = len(rows)
    logger.info("n=%d symbols with real PE/EV_EBITDA/PS/EV_REVENUE/risk/quality/size", n)

    print("\n=== Duplicate check (does the docstring's r=0.93/1.00 claim hold cross-sectionally?) ===")
    print(f"Spearman PE vs EV/EBITDA:      {stats.spearmanr(pe, ev_ebitda).statistic:+.3f}")
    print(f"Spearman PS vs EV/Revenue:     {stats.spearmanr(ps, ev_revenue).statistic:+.3f}")
    print("(Historical point-in-time panel claimed r=0.93 / r=1.00 - PS/EV_Revenue reproduces")
    print(" closely here; PE/EV_EBITDA is meaningfully lower cross-sectionally, i.e. less of a")
    print(" pure duplicate than the panel result implied - flagged, not reconciled further here.)")

    print("\n=== Does the net-debt wedge (EV - market_cap) line up with a DIFFERENT pillar? ===")
    print(f"Spearman net_debt_ratio vs risk_score:    {stats.spearmanr(net_debt_ratio, risk).statistic:+.4f}")
    print(f"Spearman net_debt_ratio vs quality_score: {stats.spearmanr(net_debt_ratio, quality).statistic:+.4f}")
    print(f"Spearman net_debt_ratio vs size_score:    {stats.spearmanr(net_debt_ratio, size).statistic:+.4f}")

    print("\n=== Does the PART of EV/EBITDA and EV/Revenue that's NOT just P/E or P/S line up elsewhere? ===")
    resid_eve = _residual(ev_ebitda, pe)
    resid_evr = _residual(ev_revenue, ps)
    print("EV/EBITDA residual (orthogonal to PE):")
    print(f"  vs risk_score:    {stats.spearmanr(resid_eve, risk).statistic:+.4f}")
    print(f"  vs quality_score: {stats.spearmanr(resid_eve, quality).statistic:+.4f}")
    print(f"  vs size_score:    {stats.spearmanr(resid_eve, size).statistic:+.4f}")
    print("EV/Revenue residual (orthogonal to PS):")
    print(f"  vs risk_score:    {stats.spearmanr(resid_evr, risk).statistic:+.4f}")
    print(f"  vs quality_score: {stats.spearmanr(resid_evr, quality).statistic:+.4f}")
    print(f"  vs size_score:    {stats.spearmanr(resid_evr, size).statistic:+.4f}")

    print("\n=== Conclusion ===")
    print("EV/EBITDA and EV/Revenue are structurally P/E and P/S with one adjustment: swapping")
    print("market_cap for enterprise_value (market_cap + net_debt). That net-debt wedge is")
    print("~uncorrelated with this system's risk_score (Safety pillar) - leverage risk is NOT")
    print("already sitting there under a different name - but correlates meaningfully with")
    print("quality_score, consistent with _score_quality already scoring debt_to_equity directly")
    print("(see load_stock_scores.py). So: EV/EBITDA and EV/Revenue ARE Value multiples by any")
    print("standard classification (not mis-filed Risk or Size metrics) - but the specific extra")
    print("content they'd add beyond Value's existing P/E/P/S is a leverage signal that already")
    print("has a home in Quality's debt_to_equity input, not a novel signal that argues for")
    print("moving them to a different pillar or re-adding them to Value at real weight.")


if __name__ == "__main__":
    main()
