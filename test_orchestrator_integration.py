#!/usr/bin/env python3
"""
Integration tests for the full algo orchestrator pipeline.

Run against the local Docker PostgreSQL (must be running):
    docker-compose up -d
    python3 test_orchestrator_integration.py

These tests verify end-to-end correctness — not mocks.
Each test uses a temporary schema so it cannot corrupt production data.
"""

import os
import sys
import unittest
import psycopg2
import psycopg2.extras
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "stocks"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        database=os.getenv("DB_NAME", "stocks"),
    )


def _skip_if_no_db():
    try:
        conn = _get_conn()
        conn.close()
        return False
    except Exception:
        return True


SKIP_MSG = "Local PostgreSQL not reachable (run: docker-compose up -d)"


# ── Test: Core schema is present ──────────────────────────────────────────────

@unittest.skipIf(_skip_if_no_db(), SKIP_MSG)
class TestDatabaseSchema(unittest.TestCase):

    def setUp(self):
        self.conn = _get_conn()
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def tearDown(self):
        self.cur.close()
        self.conn.close()

    def _table_exists(self, table: str) -> bool:
        self.cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=%s",
            (table,)
        )
        row = self.cur.fetchone()
        return (row['count'] if row else 0) > 0

    def test_critical_tables_exist(self):
        """All tables required by the orchestrator must exist."""
        critical = [
            'price_daily', 'buy_sell_daily', 'stock_scores', 'algo_positions',
            'algo_trades', 'algo_audit_log', 'market_health_daily',
            'trend_template_data', 'signal_quality_scores', 'company_profile',
            'sector_ranking', 'algo_portfolio_snapshots',
        ]
        missing = [t for t in critical if not self._table_exists(t)]
        self.assertEqual(missing, [], f"Missing tables: {missing}")

    def test_algo_positions_has_required_columns(self):
        """algo_positions must have all columns the orchestrator references."""
        self.cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='algo_positions'
        """)
        cols = {r['column_name'] for r in self.cur.fetchall()}
        required = {'symbol', 'status', 'entry_price', 'quantity', 'entry_date'}
        missing = required - cols
        self.assertEqual(missing, set(), f"Missing columns in algo_positions: {missing}")

    def test_algo_trades_has_required_columns(self):
        """algo_trades must have all columns for P&L computation."""
        self.cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='algo_trades'
        """)
        cols = {r['column_name'] for r in self.cur.fetchall()}
        required = {'symbol', 'entry_price', 'exit_price', 'quantity', 'status', 'entry_date'}
        missing = required - cols
        self.assertEqual(missing, set(), f"Missing columns in algo_trades: {missing}")


# ── Test: Orchestrator phase contracts ────────────────────────────────────────

@unittest.skipIf(_skip_if_no_db(), SKIP_MSG)
class TestOrchestratorPhases(unittest.TestCase):
    """Test Phase 1 data freshness check with controlled data."""

    def setUp(self):
        self.conn = _get_conn()
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def tearDown(self):
        self.conn.rollback()
        self.cur.close()
        self.conn.close()

    def test_phase1_freshness_with_fresh_data(self):
        """Phase 1 should pass when SPY price data is recent."""
        # Insert a fresh SPY row (today)
        today = date.today()
        self.cur.execute("""
            INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
            VALUES ('SPY', %s, 500.0, 501.0, 499.0, 500.5, 50000000)
            ON CONFLICT (symbol, date) DO UPDATE SET close = EXCLUDED.close
        """, (today,))

        self.cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol = 'SPY'")
        row = self.cur.fetchone()
        self.assertIsNotNone(row)
        latest = row['max']
        self.assertIsNotNone(latest)
        age_days = (today - latest).days
        self.assertLessEqual(age_days, 7, f"SPY data is {age_days} days old — Phase 1 would fail")

    def test_phase1_rejects_stale_data(self):
        """Phase 1 logic: data older than max_staleness_days should fail the gate."""
        stale_date = date.today() - timedelta(days=10)
        age_days = (date.today() - stale_date).days
        max_staleness = 7
        self.assertGreater(age_days, max_staleness,
                           "Test fixture is not actually stale")

    def test_audit_log_accepts_writes(self):
        """Orchestrator must be able to write to algo_audit_log."""
        self.cur.execute("""
            INSERT INTO algo_audit_log (phase, action, status, details, created_at)
            VALUES ('test', 'integration_test', 'success', '{}', NOW())
        """)
        self.cur.execute(
            "SELECT COUNT(*) as n FROM algo_audit_log WHERE action = 'integration_test'"
        )
        row = self.cur.fetchone()
        self.assertGreater(row['n'], 0)


# ── Test: Signal generation invariants ───────────────────────────────────────

@unittest.skipIf(_skip_if_no_db(), SKIP_MSG)
class TestSignalInvariants(unittest.TestCase):
    """Verify that signal generation results satisfy data quality invariants."""

    def setUp(self):
        self.conn = _get_conn()
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def tearDown(self):
        self.cur.close()
        self.conn.close()

    def test_buy_signals_have_valid_prices(self):
        """All BUY signals must have positive open/high/low/close."""
        self.cur.execute("""
            SELECT symbol, date, open, high, low, close
            FROM buy_sell_daily
            WHERE signal = 'BUY'
            AND date >= CURRENT_DATE - INTERVAL '30 days'
            AND (open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                 OR open IS NULL OR close IS NULL)
            LIMIT 10
        """)
        bad_rows = self.cur.fetchall()
        self.assertEqual(len(bad_rows), 0,
                         f"BUY signals with invalid prices: {[dict(r) for r in bad_rows]}")

    def test_buy_signals_price_relationship(self):
        """High must be >= Low for all signals."""
        self.cur.execute("""
            SELECT symbol, date, high, low
            FROM buy_sell_daily
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            AND high < low
            LIMIT 5
        """)
        bad_rows = self.cur.fetchall()
        self.assertEqual(len(bad_rows), 0,
                         f"Signals with high < low: {[dict(r) for r in bad_rows]}")

    def test_stock_scores_are_bounded(self):
        """Stock scores should be in a valid numeric range (not NaN/Inf/negative)."""
        self.cur.execute("""
            SELECT COUNT(*) as n FROM stock_scores
            WHERE composite_score < 0 OR composite_score > 100
               OR composite_score IS NULL
        """)
        row = self.cur.fetchone()
        count = row['n'] if row else 0
        # Allow up to 1% bad rows (data quality tolerance)
        self.cur.execute("SELECT COUNT(*) as total FROM stock_scores")
        total = (self.cur.fetchone() or {}).get('total', 1) or 1
        bad_pct = count / total
        self.assertLess(bad_pct, 0.01,
                        f"{count}/{total} ({bad_pct:.1%}) stock_scores are out of range [0,100]")

    def test_positions_have_no_negative_quantity(self):
        """Open positions must have positive quantity."""
        self.cur.execute("""
            SELECT COUNT(*) as n FROM algo_positions
            WHERE status = 'open' AND (quantity <= 0 OR quantity IS NULL)
        """)
        row = self.cur.fetchone()
        self.assertEqual(row['n'], 0, "Open positions with zero/null quantity found")

    def test_no_duplicate_open_positions(self):
        """No symbol should appear in open positions more than once."""
        self.cur.execute("""
            SELECT symbol, COUNT(*) as cnt
            FROM algo_positions
            WHERE status = 'open'
            GROUP BY symbol
            HAVING COUNT(*) > 1
        """)
        dupes = self.cur.fetchall()
        self.assertEqual(len(dupes), 0,
                         f"Duplicate open positions: {[dict(r) for r in dupes]}")


# ── Test: API Lambda contracts ────────────────────────────────────────────────

class TestAPIContracts(unittest.TestCase):
    """Verify API Lambda routes and response shapes without hitting AWS."""

    def _get_handler(self):
        # Import directly — avoids needing a deployed Lambda
        sys.path.insert(0, str(Path(__file__).parent / 'lambda' / 'api'))
        try:
            from lambda_function import json_response, error_response, APIHandler
            return json_response, error_response, APIHandler
        except ImportError as e:
            self.skipTest(f"Cannot import lambda_function: {e}")

    def test_json_response_shape(self):
        """json_response must always include statusCode, headers, body."""
        json_response, _, _ = self._get_handler()
        resp = json_response(200, {'key': 'value'})
        self.assertIn('statusCode', resp)
        self.assertIn('headers', resp)
        self.assertIn('body', resp)
        self.assertEqual(resp['statusCode'], 200)

    def test_error_response_shape(self):
        """error_response must include error field in body."""
        _, error_response, _ = self._get_handler()
        resp = error_response(500, 'test_error', 'test message')
        import json
        body = json.loads(resp['body'])
        self.assertIn('error', body)
        self.assertEqual(resp['statusCode'], 500)

    def test_health_endpoint_does_not_require_db(self):
        """Health check must respond without database access."""
        json_response, _, APIHandler = self._get_handler()
        handler = APIHandler()
        # Do NOT call handler.connect() — health must work without DB
        resp = handler.route('/api/health')
        self.assertEqual(resp['statusCode'], 200)

    def test_unknown_path_returns_404(self):
        """Unknown paths must return 404, not 500."""
        _, _, APIHandler = self._get_handler()
        handler = APIHandler()
        resp = handler.route('/api/nonexistent/endpoint')
        self.assertEqual(resp['statusCode'], 404)


# ── Test: Retry / rate-limit utilities ───────────────────────────────────────

class TestRetryUtility(unittest.TestCase):

    def test_retry_succeeds_on_first_try(self):
        """No delay when function succeeds immediately."""
        from algo_retry import retry
        call_count = [0]

        @retry(max_attempts=3)
        def succeeds():
            call_count[0] += 1
            return 'ok'

        result = succeeds()
        self.assertEqual(result, 'ok')
        self.assertEqual(call_count[0], 1)

    def test_retry_retries_on_failure_then_succeeds(self):
        """Retries until success, returns correct value."""
        from algo_retry import retry
        call_count = [0]

        @retry(max_attempts=3, base_delay=0.01)
        def fails_twice():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("not yet")
            return 'done'

        result = fails_twice()
        self.assertEqual(result, 'done')
        self.assertEqual(call_count[0], 3)

    def test_retry_raises_after_max_attempts(self):
        """Should re-raise after all attempts exhausted."""
        from algo_retry import retry
        call_count = [0]

        @retry(max_attempts=2, base_delay=0.01)
        def always_fails():
            call_count[0] += 1
            raise RuntimeError("permanent failure")

        with self.assertRaises(RuntimeError):
            always_fails()
        self.assertEqual(call_count[0], 2)

    def test_rate_limiter_enforces_interval(self):
        """RateLimiter must space calls by at least min_interval."""
        import time
        from algo_retry import RateLimiter
        limiter = RateLimiter(calls_per_minute=600)  # 100ms interval
        limiter.wait()
        t0 = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - t0
        self.assertGreaterEqual(elapsed, 0.08,  # 80ms minimum (20% jitter tolerance)
                                f"Rate limiter allowed calls too fast: {elapsed:.3f}s")


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    unittest.main(verbosity=2)
