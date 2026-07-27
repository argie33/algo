#!/usr/bin/env python3
"""Regression test: industry_ranking.momentum_score must use the same sign convention
as sector_ranking.momentum_score.

load_sector_industry_daily.py computes momentum_score for both sector_ranking and
industry_ranking from the same shape of data (current_rank vs. a prior rank fetched
via LEFT JOIN LATERAL). sector_ranking's formula was previously fixed (see the comment
above its query) from `current_rank - old_rank` (negative = improving, which read
backwards everywhere this value is consumed/displayed) to `old_rank - current_rank`
(positive = improving, matching sector_rotation.py's own convention).

industry_ranking's twin query was never updated to match and still used the inverted
`current_rank - COALESCE(r1.rank, current_rank)` formula. This value is returned
directly as "momentum_score" by lambda/api/routes/industries.py to the Industries
dashboard page, so the sign inversion read backwards there too - an improving
industry showed a negative momentum_score.

This test statically asserts both queries in the source use the same, correct
COALESCE(...) - current_rank ordering, so a future edit to one without the other
is caught without needing a live Postgres fixture for this SQL-heavy loader.
"""

import re
from pathlib import Path

SOURCE = Path("loaders/load_sector_industry_daily.py").read_text(encoding="utf-8")


def _momentum_expressions() -> list[str]:
    """Extract the momentum_score arithmetic expression from each ranking query."""
    # Both queries compute momentum via a `<rank ref> - <rank ref>` or
    # `<rank ref> - COALESCE(...)` expression referencing r1.rank on the line
    # immediately following the current_rank SELECT line.
    pattern = re.compile(
        r"current_rank,\s*\n\s*(?:--.*\n\s*)*"  # current_rank line, skip comment lines
        r"([^\n]*r1\.rank[^\n]*),",
        re.MULTILINE,
    )
    matches = pattern.findall(SOURCE)
    return [m.strip() for m in matches]


def test_sector_and_industry_momentum_use_same_sign_convention():
    expressions = _momentum_expressions()
    assert len(expressions) == 2, f"expected 2 momentum_score expressions (sector + industry), found: {expressions}"

    for expr in expressions:
        # Correct convention: COALESCE(r1.rank, current_rank) - current_rank
        # (old_rank - current_rank; positive when rank improved/went down)
        assert re.match(r"COALESCE\(r1\.rank,\s*\w+\.current_rank\)\s*-\s*\w+\.current_rank", expr), (
            f"momentum_score expression uses the wrong sign convention "
            f"(expected COALESCE(r1.rank, current_rank) - current_rank): {expr!r}"
        )
