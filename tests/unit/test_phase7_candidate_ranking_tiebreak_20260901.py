#!/usr/bin/env python3
"""Regression test: the primary candidate-ranking query must have a deterministic
tiebreaker, not sort purely by composite_score.

BUG FOUND 2026-09-01 (/goal session, fringe-case sweep): `_get_candidates_from_buysell`'s
ranking query used `ORDER BY composite_score DESC LIMIT %s` with no secondary sort key.
composite_score is a rounded, percentile-derived value across a universe of thousands of
symbols - ties at the LIMIT boundary are plausible, not a hypothetical corner case. Without a
tiebreaker, PostgreSQL's row order for tied rows is undefined, so which symbol(s) land exactly
at the cutoff (selected vs. not selected) could differ across otherwise-identical runs against
identical underlying data - not a safety bug, but a real reproducibility/fairness gap for a
system whose whole premise is ranking candidates by quality.

Fixed by adding `rs_percentile DESC NULLS LAST, symbol ASC` as tiebreakers: rs_percentile is a
real secondary ranking signal already selected by this same query (not an arbitrary tiebreak),
NULLS LAST because a NULL-rs_percentile candidate gets filtered out downstream anyway (see this
same function's Python-side skip) and must not rank ahead of a real candidate on a tie, and
`symbol ASC` as a final guarantee of total determinism even if rs_percentile also ties.
"""

import inspect

from algo.orchestrator.phase7_signal_generation import _get_candidates_from_buysell


def test_ranking_query_has_deterministic_tiebreak():
    src = inspect.getsource(_get_candidates_from_buysell)
    assert "ORDER BY composite_score DESC, rs_percentile DESC NULLS LAST, symbol ASC" in src, (
        "the primary candidate-ranking query must break composite_score ties deterministically "
        "(rs_percentile then symbol), not sort by composite_score alone"
    )


def test_ranking_query_does_not_regress_to_bare_composite_score_order():
    """A more permissive guard against the exact regression this bug was: an ORDER BY
    clause containing 'composite_score DESC' with nothing else immediately after it before
    the closing quote/LIMIT would mean the tiebreak got silently dropped in a future edit."""
    src = inspect.getsource(_get_candidates_from_buysell)
    assert "ORDER BY composite_score DESC\n" not in src, (
        "found a bare 'ORDER BY composite_score DESC' with no tiebreaker on its own line - "
        "the deterministic tiebreak (rs_percentile, symbol) appears to have been dropped"
    )
