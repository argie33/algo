"""Test Phase 1 afternoon re-validation fix (2026-08-05 refined).

INITIAL ISSUE (2026-08-02): Phase 1 checked for pipeline_context in ("AFTERNOON", "EVENING")
but pipeline_context was set to ("MORNING", "INTRADAY", "EOD"). This meant the
afternoon re-validation was dead code.

FIRST FIX: Changed to check for ("INTRADAY", "EOD") instead.

REFINED FIX (2026-08-05): Realized that during INTRADAY (market hours, 10 AM-4 PM),
today's close isn't published yet - only yesterday's close is available. Only after
market close (EOD, 4 PM+) should we expect today's close data. Changed the check
to only validate today's prices during EOD context, not INTRADAY.
"""

import re


def test_phase1_afternoon_revalidation_uses_correct_context():
    """Verify that Phase 1 validates today's prices only during EOD context."""
    with open("algo/orchestrator/phase1_data_freshness.py") as f:
        content = f.read()

    # Verify the refined fix: should check only "EOD", not "INTRADAY"
    # During INTRADAY hours, today's close doesn't exist yet - only after market close
    pattern = r'if pipeline_context == "EOD":'
    assert re.search(pattern, content), (
        "Phase 1 should only validate today's price data during EOD (4 PM+) context. "
        "During INTRADAY (market hours), today's close isn't published yet, so only "
        "yesterday's close is available and appropriate for technical analysis."
    )

    # Verify the old buggy pattern is NOT in the code
    buggy_pattern = r'if pipeline_context in \("AFTERNOON", "EVENING"\):'
    assert not re.search(buggy_pattern, content), (
        "Phase 1 should NOT check for ('AFTERNOON', 'EVENING') contexts since those "
        "values are never assigned to pipeline_context."
    )


def test_phase1_pipeline_context_assignment_matches_validation():
    """Verify that assigned pipeline_context values match what is validated."""
    with open("algo/orchestrator/phase1_data_freshness.py") as f:
        content = f.read()

    # Find where pipeline_context is assigned - check for any order of the three values
    assignment_patterns = [
        r'pipeline_context = "EOD" if.*else "INTRADAY" if.*else "MORNING"',
        r'pipeline_context = "EOD" if.*else "MORNING" if.*else "INTRADAY"',
    ]
    found = any(re.search(pattern, content, re.DOTALL) for pattern in assignment_patterns)
    assert found, (
        "Phase 1 should assign pipeline_context to exactly ('MORNING', 'INTRADAY', 'EOD'). "
        "Expected pattern like: pipeline_context = \"EOD\" if ... else \"INTRADAY\" if ... else \"MORNING\""
    )

    # Find where it's used for today's price validation (EOD only)
    # During INTRADAY, today's close doesn't exist yet - yesterday's close is appropriate
    validation_pattern = r'if pipeline_context == "EOD":'
    assert re.search(validation_pattern, content), (
        "Phase 1 should only validate today's prices during EOD context when today's close is available"
    )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
