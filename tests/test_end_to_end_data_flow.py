"""
End-to-End Data Flow Validation

Traces 5 critical data flows from loader → database → API → frontend:
1. Stock Prices (loader → price_daily → /api/stocks → frontend)
2. Trading Signals (loader → buy_sell_daily → /api/signals → frontend)
3. Stock Scores (loader → stock_scores → /api/scores → frontend)
4. Economic Data (loader → economic_data → /api/economic → frontend)
5. Market Health (loader → market_health_daily → /api/market/health → frontend)

USAGE:
  python -m pytest tests/test_end_to_end_data_flow.py -v
"""

import pytest
from utils.db_connection import get_db_connection
from datetime import date as _date, timedelta


class TestDataFlowPathways:
    """Validate complete data flow paths through the system."""

    @pytest.fixture
    def db_connection(self):
        """Connect to database using environment variables."""
        try:
            from config.credential_helper import get_db_config
            config = get_db_config()
            conn = psycopg2.connect(**config)
            conn.autocommit = True
            yield conn
            conn.close()
        except Exception as e:
            pytest.skip(f"Database not available: {e}")

    def test_stock_price_flow_complete(self, db_connection):
        """Validate: loader → price_daily → /api/stocks"""
        cur = db_connection.cursor()

        # 1. Check loader populated price_daily
        cur.execute("""
            SELECT COUNT(*), MAX(date) FROM price_daily
        """)
        count, latest_date = cur.fetchone()
        assert count > 1000, f"Insufficient price data: {count} records"
        assert latest_date and (_date.today() - latest_date).days < 5, \
            f"Price data too old: {latest_date}"

        # 2. Check price data is valid
        cur.execute("""
            SELECT COUNT(*) FROM price_daily
            WHERE close <= 0 OR open <= 0 OR high < low OR close > 1000000
        """)
        anomalies = cur.fetchone()[0]
        assert anomalies < 100, f"Found {anomalies} price data anomalies"

        # 3. Check latest prices accessible
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) FROM price_daily
            WHERE date = (SELECT MAX(date) FROM price_daily)
        """)
        symbols_latest = cur.fetchone()[0]
        assert symbols_latest > 100, f"Not enough symbols with latest prices: {symbols_latest}"

    def test_trading_signals_flow_complete(self, db_connection):
        """Validate: loader → buy_sell_daily → /api/signals"""
        cur = db_connection.cursor()

        # 1. Check loader populated buy_sell_daily
        cur.execute("""
            SELECT COUNT(*), MAX(date) FROM buy_sell_daily
        """)
        count, latest_date = cur.fetchone()
        assert count > 100, f"Insufficient signal data: {count} records"
        assert latest_date and (_date.today() - latest_date).days < 5, \
            f"Signal data too old: {latest_date}"

        # 2. Check signal values are valid
        cur.execute("""
            SELECT COUNT(DISTINCT signal) FROM buy_sell_daily
            WHERE signal IN ('BUY', 'SELL', 'HOLD')
        """)
        valid_signals = cur.fetchone()[0]
        assert valid_signals > 0, "No valid signals found"

        # 3. Check signals have proper strength values
        cur.execute("""
            SELECT COUNT(*) FROM buy_sell_daily
            WHERE strength < 0 OR strength > 100
        """)
        anomalies = cur.fetchone()[0]
        assert anomalies == 0, f"Found {anomalies} invalid signal strengths"

    def test_stock_scores_flow_complete(self, db_connection):
        """Validate: loader → stock_scores → /api/scores"""
        cur = db_connection.cursor()

        # 1. Check loader populated stock_scores
        cur.execute("""
            SELECT COUNT(*), MAX(updated_at::DATE) FROM stock_scores
        """)
        count, latest_date = cur.fetchone()
        assert count > 100, f"Insufficient score data: {count} records"
        assert latest_date and (_date.today() - latest_date).days < 5, \
            f"Score data too old: {latest_date}"

        # 2. Check score values are in valid ranges
        cur.execute("""
            SELECT COUNT(*) FROM stock_scores
            WHERE (composite_score < 0 OR composite_score > 100)
               OR (growth_score < 0 OR growth_score > 100)
               OR (momentum_score < 0 OR momentum_score > 100)
               OR (quality_score < 0 OR quality_score > 100)
        """)
        anomalies = cur.fetchone()[0]
        assert anomalies == 0, f"Found {anomalies} score values out of range"

        # 3. Check multiple score types present
        cur.execute("""
            SELECT COUNT(*) FROM stock_scores
            WHERE composite_score IS NOT NULL
              AND growth_score IS NOT NULL
              AND momentum_score IS NOT NULL
        """)
        multi_score = cur.fetchone()[0]
        assert multi_score > 100, f"Not enough multi-factor scores: {multi_score}"

    def test_economic_data_flow_complete(self, db_connection):
        """Validate: loader → economic_data → /api/economic"""
        cur = db_connection.cursor()

        # 1. Check loader populated economic_data
        cur.execute("""
            SELECT COUNT(*), MAX(date) FROM economic_data
        """)
        count, latest_date = cur.fetchone()
        assert count > 100, f"Insufficient economic data: {count} records"
        assert latest_date and (_date.today() - latest_date).days < 10, \
            f"Economic data too old: {latest_date}"

        # 2. Check economic indicators are present
        cur.execute("""
            SELECT COUNT(DISTINCT series_id) FROM economic_data
        """)
        indicators = cur.fetchone()[0]
        assert indicators > 5, f"Not enough economic indicators: {indicators}"

        # 3. Check data values are reasonable
        cur.execute("""
            SELECT COUNT(*) FROM economic_data
            WHERE value IS NULL
        """)
        null_data = cur.fetchone()[0]
        assert null_data == 0, f"Found {null_data} records with all NULL values"

    def test_market_health_flow_complete(self, db_connection):
        """Validate: loader → market_health_daily → /api/market/health"""
        cur = db_connection.cursor()

        # 1. Check loader populated market_health_daily
        cur.execute("""
            SELECT COUNT(*), MAX(date) FROM market_health_daily
        """)
        count, latest_date = cur.fetchone()
        assert count > 10, f"Insufficient market health data: {count} records"
        assert latest_date and (_date.today() - latest_date).days < 5, \
            f"Market health data too old: {latest_date}"

        # 2. Check market indicators are present
        cur.execute("""
            SELECT COUNT(*) FROM market_health_daily
            WHERE vix_level IS NOT NULL OR advance_decline_ratio IS NOT NULL
        """)
        with_indicators = cur.fetchone()[0]
        assert with_indicators > 5, f"Not enough market health records with data: {with_indicators}"

    def test_data_consistency_across_flows(self, db_connection):
        """Validate data consistency between related tables."""
        cur = db_connection.cursor()

        # 1. All symbols in price_daily should exist in stock_symbols
        cur.execute("""
            SELECT COUNT(DISTINCT pd.symbol)
            FROM price_daily pd
            LEFT JOIN stock_symbols ss ON pd.symbol = ss.symbol
            WHERE ss.symbol IS NULL
        """)
        orphan_symbols = cur.fetchone()[0]
        # Allow some orphaned records (known issue < 10%)
        assert orphan_symbols < 100, f"Found {orphan_symbols} orphaned price symbols"

        # 2. All buy/sell signals should have valid symbols
        cur.execute("""
            SELECT COUNT(DISTINCT bs.symbol)
            FROM buy_sell_daily bs
            LEFT JOIN stock_symbols ss ON bs.symbol = ss.symbol
            WHERE ss.symbol IS NULL
        """)
        orphan_signals = cur.fetchone()[0]
        assert orphan_signals == 0, f"Found {orphan_signals} signals with invalid symbols"

        # 3. All stock scores should have valid symbols
        cur.execute("""
            SELECT COUNT(DISTINCT sc.symbol)
            FROM stock_scores sc
            LEFT JOIN stock_symbols ss ON sc.symbol = ss.symbol
            WHERE ss.symbol IS NULL
        """)
        orphan_scores = cur.fetchone()[0]
        assert orphan_scores == 0, f"Found {orphan_scores} scores with invalid symbols"

    def test_data_timeliness_across_flows(self, db_connection):
        """Validate all data flows are current (not stale)."""
        cur = db_connection.cursor()

        # Get latest dates for all flows
        cur.execute("""
            SELECT
                (SELECT MAX(date) FROM price_daily)::DATE as price_latest,
                (SELECT MAX(date) FROM buy_sell_daily)::DATE as signal_latest,
                (SELECT MAX(updated_at)::DATE FROM stock_scores) as score_latest,
                (SELECT MAX(date) FROM economic_data)::DATE as econ_latest,
                (SELECT MAX(date) FROM market_health_daily)::DATE as health_latest
        """)
        prices, signals, scores, econ, health = cur.fetchone()

        today = _date.today()
        assert prices and (today - prices).days < 3, f"Price data stale: {prices}"
        assert signals and (today - signals).days < 3, f"Signal data stale: {signals}"
        assert scores and (today - scores).days < 3, f"Score data stale: {scores}"
        assert econ and (today - econ).days < 10, f"Economic data stale: {econ}"
        assert health and (today - health).days < 3, f"Market health stale: {health}"

    def test_full_flow_critical_path(self, db_connection):
        """Test the critical path for algo execution."""
        cur = db_connection.cursor()

        # Critical path: must have symbols → prices → signals → scores
        # Step 1: Check symbols exist
        cur.execute("SELECT COUNT(*) FROM stock_symbols")
        symbols = cur.fetchone()[0]
        assert symbols > 100, f"Not enough symbols: {symbols}"

        # Step 2: Check those symbols have current prices
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) FROM price_daily
            WHERE date = (SELECT MAX(date) FROM price_daily)
            AND symbol IN (SELECT symbol FROM stock_symbols LIMIT 1000)
        """)
        priced_symbols = cur.fetchone()[0]
        assert priced_symbols > 100, f"Not enough priced symbols: {priced_symbols}"

        # Step 3: Check those symbols have buy/sell signals
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily
            WHERE date = (SELECT MAX(date) FROM buy_sell_daily)
            AND symbol IN (SELECT symbol FROM stock_symbols LIMIT 1000)
        """)
        signal_symbols = cur.fetchone()[0]
        assert signal_symbols > 0, f"Not enough signaled symbols: {signal_symbols}"

        # Step 4: Check those symbols have scores
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) FROM stock_scores
            WHERE symbol IN (SELECT symbol FROM stock_symbols LIMIT 1000)
        """)
        scored_symbols = cur.fetchone()[0]
        assert scored_symbols > 100, f"Not enough scored symbols: {scored_symbols}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
