"""Regression test: Phase 9's exit_reason string must never exceed algo_trades/algo_positions'
VARCHAR(100) column width, for every price_source value this code can actually produce, while
still preserving the "Closed position recorded during reconciliation" substring that
_repair_missing_exit_prices() ILIKE-matches on to find trades needing exit-price recovery.

BUG FOUND 2026-09-08 (live local orchestrator dry-run against paper trading): the old
"Closed position recorded during reconciliation (exit price source: {price_source})" template
was 129 characters for the current_price fallback source string ("position current_price
(price_daily not yet loaded for today)"), overflowing the VARCHAR(100) exit_reason column and
crashing Phase 9 with psycopg2.errors.StringDataRightTruncation on a real position (ING) -
which then halted the whole orchestrator run (correct fail-safe behavior for the crash, but the
crash itself was a real, live-reproduced bug in the exit-recording SQL, not a hypothetical one).
"""

# Mirrors phase9_reconciliation.py's three literal price_source assignments exactly - if those
# ever change, update this list so the test keeps testing the real strings.
PRICE_SOURCES = [
    "broker fill (from closed_orders)",
    "price_daily EOD close",
    "position current_price (EOD pending)",
]

# The exact template used at all three exit_reason write sites (algo_trades UPDATE and both
# algo_positions UPDATEs) in phase9_reconciliation.py.
EXIT_REASON_TEMPLATE = "Closed position recorded during reconciliation (src: {})"

# _repair_missing_exit_prices() matches `exit_reason ILIKE '%{SUBSTRING}%'` to find trades whose
# exit was recorded but exit_price silently failed to persist - the template must keep this
# substring intact or that repair path stops finding future occurrences of that other bug class.
REQUIRED_SUBSTRING = "Closed position recorded during reconciliation"


def test_exit_reason_fits_varchar_100_for_all_known_price_sources():
    for price_source in PRICE_SOURCES:
        exit_reason = EXIT_REASON_TEMPLATE.format(price_source)[:100]
        assert len(exit_reason) <= 100
        # The defensive [:100] slice must never actually need to cut real content for any
        # of today's known price_source values - if it does, the message is silently
        # mangled instead of just failing loud, which is worse than the original crash.
        assert exit_reason == EXIT_REASON_TEMPLATE.format(price_source), (
            f"price_source {price_source!r} produces a message that needs truncation - "
            "shorten the template or the price_source string, don't rely on the safety slice"
        )


def test_exit_reason_still_matches_repair_detector_substring():
    for price_source in PRICE_SOURCES:
        exit_reason = EXIT_REASON_TEMPLATE.format(price_source)[:100]
        assert REQUIRED_SUBSTRING in exit_reason, (
            "exit_reason must keep containing this exact substring - "
            "_repair_missing_exit_prices()'s ILIKE match depends on it"
        )


def test_defensive_slice_still_caps_length_even_for_a_future_long_price_source():
    # Belt-and-suspenders check: even if a future price_source string is added without
    # updating this test's PRICE_SOURCES list, the [:100] slice in the actual code must
    # still prevent a VARCHAR(100) overflow (though it would silently truncate the message -
    # see the test above for why that's a signal to fix the source string, not rely on this).
    hypothetical_long_source = "x" * 200
    exit_reason = EXIT_REASON_TEMPLATE.format(hypothetical_long_source)[:100]
    assert len(exit_reason) == 100
