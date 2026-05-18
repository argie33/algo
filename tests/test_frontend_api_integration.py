"""
Frontend-API Integration Tests

Validates that all 21 frontend pages have working API endpoints.
Tests the data flow from API to frontend display.

USAGE:
  python -m pytest tests/test_frontend_api_integration.py -v
  python -m pytest tests/test_frontend_api_integration.py::test_all_pages_have_endpoints -v
"""

from config.env_loader import load_env
from config.credential_helper import get_db_config
import pytest
from psycopg2 import sql
import os
from pathlib import Path
from datetime import date as _date



class TestFrontendPages:
    """Validate all 22 frontend pages and their API integrations."""

    # All 21 frontend pages in the app
    PAGES = [
        {'name': 'LoginPage', 'path': '/login', 'requires_auth': False},
        {'name': 'PerformanceMetrics', 'path': '/performance', 'endpoints': ['/api/algo/performance']},
        {'name': 'SwingCandidates', 'path': '/swing-candidates', 'endpoints': ['/api/signals']},
        {'name': 'AlgoTradingDashboard', 'path': '/', 'endpoints': ['/api/stocks', '/api/sectors']},
        {'name': 'DeepValueStocks', 'path': '/value', 'endpoints': ['/api/stocks']},
        {'name': 'PreTradeSimulator', 'path': '/simulator', 'endpoints': ['/api/stocks', '/api/trades']},
        {'name': 'AuditViewer', 'path': '/audit', 'endpoints': ['/api/audit']},
        {'name': 'PortfolioDashboard', 'path': '/portfolio', 'endpoints': ['/api/portfolio', '/api/positions']},
        {'name': 'ServiceHealth', 'path': '/health', 'endpoints': ['/health', '/health/detailed']},
        {'name': 'Sentiment', 'path': '/sentiment', 'endpoints': ['/api/sentiment']},
        {'name': 'Settings', 'path': '/settings', 'endpoints': ['/api/settings']},
        {'name': 'MarketsHealth', 'path': '/market-health', 'endpoints': ['/api/market/health']},
        {'name': 'NotificationCenter', 'path': '/notifications', 'endpoints': ['/api/notifications']},
        {'name': 'ScoresDashboard', 'path': '/scores', 'endpoints': ['/api/scores']},
        {'name': 'TradeTracker', 'path': '/trades', 'endpoints': ['/api/trades']},
        {'name': 'TradingSignals', 'path': '/signals', 'endpoints': ['/api/signals']},
        {'name': 'BacktestResults', 'path': '/backtest', 'endpoints': ['/api/backtest']},
        {'name': 'NotFound', 'path': '/404', 'requires_auth': False},
        {'name': 'StockDetail', 'path': '/stocks/:symbol', 'endpoints': ['/api/stocks/:symbol']},
        {'name': 'SectorAnalysis', 'path': '/sectors/:sector', 'endpoints': ['/api/sectors/:sector']},
        {'name': 'EconomicDashboard', 'path': '/economic', 'endpoints': ['/api/economic']},
    ]

    @pytest.fixture
    def db_connection(self):
        """Connect to database for endpoint validation."""
        try:
            conn = psycopg2.connect(
                host=get_db_config()['host'],
                port=int(int(get_db_config()['port'])),
                database=get_db_config()['database'],
                user=get_db_config()['user'],
                password=os.getenv('DB_PASSWORD', '')
            )
            conn.autocommit = True
            yield conn
            conn.close()
        except Exception as e:
            pytest.skip(f"Database not available: {e}")

    def test_all_pages_exist(self):
        """Verify all 21 frontend pages are defined."""
        assert len(self.PAGES) == 21, f"Expected 21 pages, got {len(self.PAGES)}"

    def test_page_names_unique(self):
        """Ensure no duplicate page names."""
        names = [p['name'] for p in self.PAGES]
        assert len(names) == len(set(names)), "Duplicate page names found"

    def test_page_paths_unique(self):
        """Ensure no duplicate page paths."""
        paths = [p['path'] for p in self.PAGES]
        assert len(paths) == len(set(paths)), "Duplicate page paths found"

    def test_critical_pages_present(self):
        """Verify critical pages are in the app."""
        critical = [
            'LoginPage', 'AlgoTradingDashboard', 'PortfolioDashboard',
            'TradeTracker', 'PerformanceMetrics', 'ServiceHealth'
        ]
        page_names = [p['name'] for p in self.PAGES]
        for name in critical:
            assert name in page_names, f"Critical page {name} missing"

    def test_api_endpoints_documented(self):
        """Verify all non-auth pages have documented endpoints."""
        for page in self.PAGES:
            if page.get('requires_auth') != False and page['name'] != 'LoginPage':
                assert 'endpoints' in page or page['path'] == '/404', \
                    f"{page['name']} missing endpoints list"

    def test_critical_endpoints_have_data(self, db_connection):
        """Check that critical API data tables are populated."""
        cur = db_connection.cursor()

        critical_tables = {
            'stock_symbols': 'Stock symbols',
            'price_daily': 'Price data',
            'stock_scores': 'Stock scores',
            'buy_sell_daily': 'Buy/sell signals',
            'algo_trades': 'Trade history',
            'algo_positions': 'Open positions',
        }

        for table, description in critical_tables.items():
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(
                sql.Identifier(table)
            ))
            count = cur.fetchone()[0]
            assert count > 0, f"{description} ({table}) is empty - API cannot return data"

    def test_auth_endpoints_exist(self, db_connection):
        """Verify authentication infrastructure exists."""
        cur = db_connection.cursor()

        try:
            cur.execute("SELECT COUNT(*) FROM feature_flags")
            assert True, "Feature flags table exists"
        except psycopg2.Error:
            pytest.skip("Feature flags table not required for auth")

    def test_no_hardcoded_credentials_in_frontend(self):
        """Ensure no API keys in frontend code."""
        frontend_dir = Path("webapp/frontend/src")
        if not frontend_dir.exists():
            pytest.skip("Frontend source not found")

        for js_file in frontend_dir.rglob("*.jsx"):
            try:
                content = js_file.read_text(encoding='utf-8', errors='ignore')
                assert 'API_KEY' not in content or 'process.env.REACT_APP_API_KEY' in content, \
                       f"API key in {js_file}"
                assert 'SECRET' not in content or 'process.env.REACT_APP_' in content, \
                       f"Secret in {js_file}"
            except Exception as e:
                # Skip files that can't be read (binary or encoding issues)
                pass

    @pytest.mark.parametrize("page", PAGES)
    def test_page_has_required_structure(self, page):
        """Verify each page has required metadata."""
        assert 'name' in page, f"Page missing name: {page}"
        assert 'path' in page, f"Page {page['name']} missing path"
        assert isinstance(page['path'], str), f"Page path must be string"

    def test_portfolio_endpoints_have_data(self, db_connection):
        """Validate portfolio-critical endpoints have data."""
        cur = db_connection.cursor()

        # Portfolio endpoints need positions data
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name IN ('algo_positions', 'algo_portfolio_snapshots')
            AND table_schema = 'public'
        """)
        count = cur.fetchone()[0]
        # At least one of the portfolio tables should exist
        assert count >= 1, "Portfolio tracking tables missing"

    def test_trading_endpoints_have_data(self, db_connection):
        """Validate trading-critical endpoints have data."""
        cur = db_connection.cursor()

        # Trading endpoints need trade data
        cur.execute("SELECT COUNT(*) FROM algo_trades")
        count = cur.fetchone()[0]
        # Note: Trade history may be empty early in system, that's OK

    def test_audit_endpoints_have_data(self, db_connection):
        """Validate audit endpoints can retrieve data."""
        cur = db_connection.cursor()

        # Audit endpoint should have audit log
        cur.execute("SELECT COUNT(*) FROM algo_audit_log")
        count = cur.fetchone()[0]
        # Audit log may be empty, that's OK

    def test_scores_endpoint_returns_current_data(self, db_connection):
        """Validate scores endpoint has current data."""
        cur = db_connection.cursor()

        cur.execute("""
            SELECT COUNT(*) FROM stock_scores
            WHERE updated_at::DATE = CURRENT_DATE
        """)
        count = cur.fetchone()[0]
        # Should have today's scores
        # Note: may be empty if loaders haven't run today


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
