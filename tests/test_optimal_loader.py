"""
Unit and integration tests for OptimalLoader base class.

Run locally:
  pytest tests/test_optimal_loader.py -v

Requires:
  - PostgreSQL running (via docker-compose up)
  - Database schema initialized
  - Credentials configured (.env.local or AWS Secrets)
"""

import pytest
from datetime import date, timedelta
from typing import List, Optional
from optimal_loader import OptimalLoader


class TestLoaderSubclass(OptimalLoader):
    """Minimal test loader subclass."""

    table_name = "price_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def __init__(self):
        super().__init__()
        self.fetch_calls = []

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        """Return test data."""
        self.fetch_calls.append({"symbol": symbol, "since": since})
        if symbol == "AAPL":
            return [
                {"symbol": "AAPL", "date": date(2024, 5, 1), "open": 150.0, "close": 151.0, "volume": 1000000},
                {"symbol": "AAPL", "date": date(2024, 5, 2), "open": 151.0, "close": 152.0, "volume": 1100000},
            ]
        elif symbol == "MSFT":
            return [
                {"symbol": "MSFT", "date": date(2024, 5, 1), "open": 300.0, "close": 301.0, "volume": 500000},
            ]
        else:
            return None


class TestOptimalLoaderBasics:
    """Test basic OptimalLoader functionality."""

    def test_loader_name(self):
        loader = TestLoaderSubclass()
        assert loader.loader_name == "TestLoaderSubclass"

    def test_table_name(self):
        loader = TestLoaderSubclass()
        assert loader.table_name == "price_daily"

    def test_primary_key(self):
        loader = TestLoaderSubclass()
        assert loader.primary_key == ("symbol", "date")

    def test_parse_watermark_date(self):
        assert OptimalLoader._parse_watermark_date(None) is None
        assert OptimalLoader._parse_watermark_date(date(2024, 5, 1)) == date(2024, 5, 1)
        assert OptimalLoader._parse_watermark_date("2024-05-01") == date(2024, 5, 1)
        assert OptimalLoader._parse_watermark_date("2024-05-01T10:30:00") == date(2024, 5, 1)

    def test_validate_row(self):
        loader = TestLoaderSubclass()
        valid_row = {"symbol": "AAPL", "date": date(2024, 5, 1), "open": 150.0}
        assert loader._validate_row(valid_row) is True
        invalid_row = {"date": date(2024, 5, 1), "open": 150.0}
        assert loader._validate_row(invalid_row) is False


class TestWatermarkFromRows:
    """Test watermark derivation from rows."""

    def test_watermark_from_rows_empty(self):
        loader = TestLoaderSubclass()
        result = loader.watermark_from_rows([])
        assert result is None

    def test_watermark_from_rows_single(self):
        loader = TestLoaderSubclass()
        rows = [{"symbol": "AAPL", "date": date(2024, 5, 1)}]
        result = loader.watermark_from_rows(rows)
        assert result == date(2024, 5, 1)

    def test_watermark_from_rows_multiple(self):
        loader = TestLoaderSubclass()
        rows = [
            {"symbol": "AAPL", "date": date(2024, 5, 1)},
            {"symbol": "AAPL", "date": date(2024, 5, 3)},
            {"symbol": "AAPL", "date": date(2024, 5, 2)},
        ]
        result = loader.watermark_from_rows(rows)
        assert result == date(2024, 5, 3)


class TestFetchIncremental:
    """Test fetch_incremental contract."""

    def test_fetch_incremental_aapl(self):
        loader = TestLoaderSubclass()
        result = loader.fetch_incremental("AAPL", None)
        assert result is not None
        assert len(result) == 2

    def test_fetch_incremental_unknown_symbol(self):
        loader = TestLoaderSubclass()
        result = loader.fetch_incremental("UNKNOWN", None)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
