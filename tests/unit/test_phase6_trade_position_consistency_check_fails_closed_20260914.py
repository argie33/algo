"""Regression test: phase6_exit_execution.py's trade-position consistency check (the
"filled/open algo_trades row with a NULL position_id" integrity query) must FAIL CLOSED
(halt) if the check itself cannot be run, not silently continue as if it had passed clean.

Bug (found 2026-09-14, real-money-readiness audit - "really question everything as if your
own money was on the line"): the query was wrapped `except RuntimeError: raise / except
Exception as e: logger.error(...)` - a genuinely detected orphaned trade correctly halted
(RuntimeError re-raised), but any OTHER failure running the query at all (DB connection
hiccup, timeout, permissions) was swallowed with just a log line, and execution fell through
to exit_execution as if the integrity check had run and found nothing wrong. This was
inconsistent with the orphaned-trade-cleanup step immediately above it in the same function
(raises RuntimeError on any Exception) and the position_recs-is-None check immediately below
it (also raises) - both of those correctly halt on their own failure-to-verify. Fixed to
match: any exception now raises RuntimeError, halting Phase 6 rather than proceeding without
having actually verified trade/position consistency.

Source inspection rather than a full mocked run: same rationale as
test_phase6_orphaned_trade_with_broker_order_not_deleted_20260906.py - this function has a
large dependency graph, and the fix is a small, self-contained control-flow change that a
targeted source assertion verifies precisely without needing to construct the full Phase 6
execution environment.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "orchestrator" / "phase6_exit_execution.py").read_text(encoding="utf-8")


def _consistency_check_block() -> str:
    start = SOURCE.index("# VALIDATION: Check for orphaned trades that made it past cleanup")
    end = SOURCE.index("# Detect Phase 3 crash - if position monitor errored")
    return SOURCE[start:end]


class TestTradePositionConsistencyCheckFailsClosed:
    def test_generic_exception_handler_raises_not_just_logs(self):
        block = _consistency_check_block()
        except_idx = block.index("except Exception as e:")
        handler_body = block[except_idx:]
        assert "raise RuntimeError" in handler_body, (
            "a failure to even RUN the trade-position consistency check must halt Phase 6 "
            "(fail closed) - silently logging and continuing is indistinguishable from the "
            "check having passed clean."
        )

    def test_detected_orphan_runtimeerror_still_reraised_directly(self):
        block = _consistency_check_block()
        # The specific RuntimeError raised when the query finds a real orphaned row must
        # still propagate via the dedicated `except RuntimeError: raise` clause, not get
        # rewrapped by the generic handler.
        assert "except RuntimeError:\n            raise" in block
        reraise_idx = block.index("except RuntimeError:\n            raise")
        generic_idx = block.index("except Exception as e:")
        assert reraise_idx < generic_idx, (
            "the specific RuntimeError re-raise clause must come before the generic "
            "Exception handler, or it would never be reached."
        )
