#!/usr/bin/env python3
"""Regression test: a psycopg2.DatabaseError/OperationalError while running the post-load
signal-degradation sanity check must NOT be silently swallowed into a warning that lets
main() fall through to mark the loader COMPLETED with an unverified signal count.

BUG FOUND (goal session, real-money-readiness "check the logs" audit): live-observed
2026-08-31 - buy_sell_daily's real BUY-signal count had been declining for a week
(80->25/day), correctly triggering _check_signal_degradation()'s RuntimeError at 15:18, yet
data_loader_status showed a clean COMPLETED with no error from a later 20:17 run despite the
persisted count still being 25 - the same degraded value, unresolved. The exact mechanism for
that specific incident wasn't pinned down with certainty (no log survived for the 20:17 run),
but the try/except wrapping _check_signal_degradation() at the call site inside main() was a
real, demonstrable way this COULD happen regardless: on a psycopg2.DatabaseError/
OperationalError (e.g. a transient connection-pool hiccup - this loader runs alongside many
others sharing a finite pool), the old code just logged a warning and continued straight past
the check to the unconditional mark_completed() calls - treating "the check couldn't run" as
equivalent to "the check ran and found no problem," directly contradicting the check's own
stated purpose ("Do NOT accept this as normal - investigate immediately").

Fixed to re-raise as a RuntimeError, hitting the same fail-loud, retry-safe path the real
degradation case already uses - this loader's watermark is deliberately unused (Session 262
fix), so a failed run costs nothing but a retry.

Static source check (main() is a single ~480-line function with a very large mocking surface
for one specific except-clause branch - same technique/precedent as
test_phase6_portfolio_rotation_writes_audit_log.py for an analogous case).
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent / "loaders" / "load_buy_sell_daily.py").read_text()


def _sanity_check_call_site() -> str:
    match = re.search(
        r"# SANITY CHECK \(Session 267 FIX.*?from sanity_check_err",
        SOURCE,
        re.DOTALL,
    )
    assert match, "expected to find the sanity-check call site - source may have been restructured"
    return match.group(0)


def test_db_error_during_sanity_check_is_not_silently_swallowed():
    block = _sanity_check_call_site()
    # The old bug: `logger.warning(...)` with no raise, letting execution fall through.
    except_clause = block[block.index("except (psycopg2.DatabaseError, psycopg2.OperationalError)") :]
    assert "raise RuntimeError" in except_clause, (
        "a DB error while running the signal-degradation sanity check must raise, not just "
        "log a warning and continue - continuing lets main() reach the unconditional "
        "mark_completed() calls with an UNVERIFIED signal count, silently defeating the "
        "check's whole purpose"
    )


def test_sanity_check_still_actually_runs_the_real_check():
    block = _sanity_check_call_site()
    assert "_check_signal_degradation(cur)" in block, (
        "the real degradation check must still be called - this fix must not have "
        "accidentally removed or bypassed it while changing the error handling around it"
    )
