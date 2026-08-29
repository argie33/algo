#!/usr/bin/env python3
"""Regression test guarding StockDetail.jsx's top-level FACTOR_WEIGHTS radar (Quality/Growth/
Value/Risk/Momentum pillar mix) against drifting away from
loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS - the real, live composite-score weights.

Positioning REMOVED 2026-08-27: retired as a top-level composite pillar entirely (evidence-
driven - see BASE_PILLAR_WEIGHTS for the full trail), not just a stale-weight drift case.

Size RE-ADDED 2026-08-27, then RETIRED ENTIRELY 2026-08-28 (direct user directive "just get
rid of size", triggered by its imputed-regime evidence not surviving a strict complete-case
retest even after fixing the data-coverage bugs that retest required first) - see
loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS for the full history.

Found live 2026-08-26 (goal: reconstruct a composite-weights reweight lost to an uncommitted-
work race, verify nothing else drifted while at it): StockDetail.jsx's FACTOR_WEIGHTS was
already stale BEFORE that reweight (growth=0.2/positioning=0.15/stability=0.12/momentum=0.08
matched none of the live weights, old or new) - a hand-copied duplicate that had never been
regression-tested (unlike webapp/frontend/src/components/StockScoreAccordion.jsx's
PILLAR-INTERNAL weight badges, already guarded by
test_scores_frontend_weight_badges_match_backend.py). This is the top-level pillar-MIX
counterpart to that existing test - same "extract from live Python source, don't hardcode a
second copy" approach, so future reweights get caught here automatically.
"""

import re

from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

with open("webapp/frontend/src/pages/StockDetail.jsx", encoding="utf-8") as f:
    _JSX_SOURCE = f.read()

_PILLAR_TO_JSX_KEY = {
    "quality": "quality_score",
    "growth": "growth_score",
    "value": "value_score",
    "risk": "risk_score",
    "momentum": "momentum_score",
}


def test_base_pillar_weights_sum_to_one() -> None:
    assert abs(sum(BASE_PILLAR_WEIGHTS.values()) - 1.0) < 1e-9


def test_factor_weights_block_matches_backend() -> None:
    match = re.search(r"const FACTOR_WEIGHTS = \[([\s\S]*?)\];", _JSX_SOURCE)
    assert match, "expected StockDetail.jsx to have a `const FACTOR_WEIGHTS = [...]` array"
    rows = re.findall(r'\["([^"]+)",\s*"(\w+)",\s*(0\.\d+)\]', match.group(1))
    assert rows, 'expected FACTOR_WEIGHTS rows shaped ["Label", "score_key", 0.NN]'

    jsx_weight_by_key = {score_key: float(weight) for _label, score_key, weight in rows}
    assert set(jsx_weight_by_key) == set(_PILLAR_TO_JSX_KEY.values()), (
        "FACTOR_WEIGHTS keys changed - update _PILLAR_TO_JSX_KEY in this test to match"
    )

    for pillar, jsx_key in _PILLAR_TO_JSX_KEY.items():
        backend_weight = BASE_PILLAR_WEIGHTS[pillar]
        jsx_weight = jsx_weight_by_key[jsx_key]
        assert jsx_weight == backend_weight, (
            f"StockDetail.jsx FACTOR_WEIGHTS[{jsx_key!r}]={jsx_weight} but "
            f"BASE_PILLAR_WEIGHTS[{pillar!r}]={backend_weight} - keep them in sync"
        )
