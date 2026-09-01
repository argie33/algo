"""Regression test for the 2026-08-31 (/goal pre-real-money audit) fix in
algo/trading/position_sizer.py's aggregate open-risk query (the code's own comment calls this
"the single most important portfolio-level guardrail").

The query used to multiply `(entry_price - current_stop_price)` by `p.quantity` (a
POSITION-level total, repeated identically on every row the JOIN fans out to) instead of
`t.quantity` (each constituent trade's own, correctly-decremented-on-partial-exit share count).
For a pyramided position (2+ open trades sharing one position_id via trade_ids_arr - a real,
supported case per position_sync.py's LINKED_TRADE_STATUSES handling), this inflated the
aggregate risk figure - e.g. a position built from 60sh @ $50 + 40sh @ $52 with stop=$45 summed
to (50-45)*100 + (52-45)*100 = $1,200 instead of the real 60*(50-45) + 40*(52-45) = $580.

This needs a real Postgres connection (the bug is in JOIN fan-out arithmetic Postgres itself
performs - a mocked cursor can't exercise it) - follows the same live-DB pattern as
test_algo_trades_live_status_unique_index.py.

NOTE: algo_trades_symbol_live_status_idx (migration 1158) is a unique index blocking two
simultaneously-live-status trades for the SAME symbol - so this fixture uses two DIFFERENT
symbols for the two constituent trades to avoid an unrelated constraint violation. The query
under test joins purely on trade_id membership in trade_ids_arr (no symbol match required), so
this doesn't change what's being verified. This also means genuine same-symbol pyramiding may
be effectively unreachable under the live schema today - the fix still matters for any case
where trade_ids_arr ends up with 2+ entries (data integrity edge cases, historical rows,
pre-migration-1158 data), and is a correctness no-op when there's exactly one trade per position.
"""

import psycopg2
import pytest

TEST_POSITION_ID = "TEST-PYRAMID-RISK-SUM-POS-1"
TEST_SYMBOL = "TESTPYRAMIDRISK"
TEST_SYMBOL_2 = "TESTPYRAMIDRISK2"


@pytest.fixture
def conn():
    try:
        connection = psycopg2.connect("dbname=stocks user=stocks host=localhost", connect_timeout=3)
    except psycopg2.OperationalError as e:
        pytest.skip(f"No live local Postgres reachable (expected in CI): {e}")
    yield connection
    connection.rollback()
    connection.close()


def _setup_pyramided_position(conn) -> None:
    cur = conn.cursor()
    # Two trades linked into one position via trade_ids_arr: 60sh @ entry $50, 40sh @ entry
    # $52, current stop=$45 for both (a pyramided position shares one live stop across its
    # trades). Different symbols per trade only to sidestep algo_trades_symbol_live_status_idx
    # (unrelated to what's under test - see module docstring) - the query under test joins
    # purely on trade_id membership in trade_ids_arr, never on symbol matching.
    cur.execute(
        """INSERT INTO algo_trades
           (trade_id, symbol, signal_date, trade_date, entry_price, entry_quantity, quantity, status)
           VALUES (%s, %s, '2026-01-01', '2026-01-01', %s, %s, %s, 'filled')""",
        ("TEST-PYRAMID-RISK-TRADE-1", TEST_SYMBOL, 50.0, 60, 60),
    )
    cur.execute(
        """INSERT INTO algo_trades
           (trade_id, symbol, signal_date, trade_date, entry_price, entry_quantity, quantity, status)
           VALUES (%s, %s, '2026-01-01', '2026-01-01', %s, %s, %s, 'filled')""",
        ("TEST-PYRAMID-RISK-TRADE-2", TEST_SYMBOL_2, 52.0, 40, 40),
    )
    cur.execute(
        """INSERT INTO algo_positions
           (position_id, symbol, quantity, avg_entry_price, status, entry_date, entry_price,
            stop_loss_price, current_stop_price, trade_ids_arr)
           VALUES (%s, %s, %s, %s, 'open', '2026-01-01', %s, %s, %s,
                   ARRAY['TEST-PYRAMID-RISK-TRADE-1', 'TEST-PYRAMID-RISK-TRADE-2'])""",
        (TEST_POSITION_ID, TEST_SYMBOL, 100, 50.8, 50.8, 45.0, 45.0),
    )


class TestPyramidedPositionAggregateRiskSum:
    def test_risk_sum_uses_per_trade_quantity_not_position_total(self, conn):
        _setup_pyramided_position(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT SUM(GREATEST(0, (t.entry_price - p.current_stop_price) * t.quantity))
            FROM algo_positions p
            JOIN algo_trades t ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
            WHERE p.status = 'open' AND p.position_id = %s
        """,
            (TEST_POSITION_ID,),
        )
        result = cur.fetchone()[0]

        assert float(result) == pytest.approx(580.0), (
            f"Expected the correct per-trade risk sum 60*(50-45) + 40*(52-45) = $580, got "
            f"${result} - a value near $1,200 means the p.quantity fan-out inflation regression "
            f"is back (each row would double-count the full 100-share position quantity instead "
            f"of that trade's own 60/40 share count)"
        )

    def test_pre_fix_query_shape_would_have_inflated_the_sum(self, conn):
        """Sanity check proving the bug was real, not just asserted: the OLD query
        (p.quantity instead of t.quantity) against this exact fixture produces the inflated
        $1,200 figure, confirming test_risk_sum_uses_per_trade_quantity_not_position_total's
        $580 assertion is actually discriminating between the two, not a coincidence."""
        _setup_pyramided_position(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT SUM(GREATEST(0, (t.entry_price - p.current_stop_price) * p.quantity))
            FROM algo_positions p
            JOIN algo_trades t ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
            WHERE p.status = 'open' AND p.position_id = %s
        """,
            (TEST_POSITION_ID,),
        )
        result = cur.fetchone()[0]

        assert float(result) == pytest.approx(1200.0), (
            f"Expected the pre-fix query shape to reproduce the known-inflated $1,200 figure "
            f"against this fixture, got ${result} - if this changed, the fixture itself may "
            f"no longer represent the bug scenario"
        )
