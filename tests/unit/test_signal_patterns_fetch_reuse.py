#!/usr/bin/env python3
"""Regression test for a 2026-08-23 fix in algo/signals/signal_patterns.py: classify_base_type()
previously issued three independent price_daily queries for a single classification -
base_detection()'s own fetch, classify_base_type()'s redundant re-fetch of the identical window,
and vcp_detection()'s separate fetch of the same window again. Fixed by having base_detection()
stash its already-fetched arrays under "_price_history" for classify_base_type() to reuse
directly, and passing that same data into vcp_detection() via its new _prefetched param -
reducing this to exactly one price_daily query per classification.

Constructs a real (non-mocked) price series shaped to land classify_base_type() in the
"consolidation" fallback branch (past the wide_and_loose/vcp/flat_base/cup/saucer/double-bottom/
ascending-base branches), counting every cur.execute() call the closures make.
"""

from unittest.mock import MagicMock, patch

from algo.signals.signal_patterns import SignalPatternsMixin


class TestFetchReuse:
    def test_classify_base_type_issues_exactly_one_query(self):
        n = 60
        # In-base depth (20%), enough bars, monotonic-ish but not matching any specific shape
        # branch's tighter gates - lands in the "consolidation" fallback deterministically.
        rows = [
            (f"2026-0{1 + (i // 28)}-{1 + (i % 28):02d}", 100.0 + (i % 7) * 0.3, 80.0 - (i % 5) * 0.2, 90.0, 500_000.0)
            for i in range(n)
        ]
        mixin = SignalPatternsMixin()
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = list(reversed(rows))

        call_count = {"n": 0}

        def counting_with_cursor(operation):
            call_count["n"] += 1
            return operation(fake_cursor)

        with patch.object(mixin, "_with_cursor", side_effect=counting_with_cursor):
            result = mixin.classify_base_type("REUSE", "2026-08-21")

        # _with_cursor is entered once for base_detection()'s own fetch. classify_base_type()'s
        # shape-classification closure and vcp_detection() (called with _prefetched from inside
        # it) also route through _with_cursor for uniform error-handling (per design), but must
        # NOT issue a second/third real cur.execute() price_daily query - only the one from
        # base_detection() should ever call fetchall() with real query args.
        assert fake_cursor.execute.call_count == 1, (
            f"Expected exactly 1 price_daily query, got {fake_cursor.execute.call_count}. "
            f"classify_base_type() result: {result}"
        )
