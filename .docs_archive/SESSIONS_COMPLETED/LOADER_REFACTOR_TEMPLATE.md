# Loader Refactoring Template

Use this as the template for refactoring all 18 loaders to use `OptimalLoader`.

## Pattern: From Old to New

### OLD PATTERN (200-400 lines)
```python
#!/usr/bin/env python3
import logging
import psycopg2
from datetime import date

def loadpricedaily():
    """Load daily prices - OLD PATTERN"""
    conn = psycopg2.connect(...)
    cur = conn.cursor()
    
    symbols = get_active_symbols()
    for symbol in symbols:
        try:
            # Fetch
            df = yfinance.download(symbol, start='2020-01-01')
            
            # Transform
            for _, row in df.iterrows():
                # Clean, validate
                data = {
                    'symbol': symbol,
                    'date': row.name.date(),
                    'open': row['Open'],
                    'close': row['Close'],
                }
            
            # Insert (slow: 1 row at a time)
            for data in transformed:
                cur.execute("""
                    INSERT INTO price_daily (symbol, date, open, close)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (data['symbol'], data['date'], data['open'], data['close']))
            
            conn.commit()
        except Exception as e:
            print(f"Failed: {symbol}: {e}")
            conn.rollback()
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    loadpricedaily()
```

### NEW PATTERN (30-50 lines)
```python
#!/usr/bin/env python3
from optimal_loader import OptimalLoader
from datetime import date
from typing import Optional, List

class PriceDailyLoader(OptimalLoader):
    """Load daily prices - NEW PATTERN with watermarking and bulk inserts."""
    
    table_name = "price_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch OHLCV for symbol since last load."""
        end = date.today()
        if since is None:
            start = date(2020, 1, 1)
        else:
            start = since + timedelta(days=1)
        
        # Use router for multi-source fallback
        return self.router.fetch_ohlcv(symbol, start=start, end=end)
    
    def transform(self, rows: List[dict]) -> List[dict]:
        """Custom validation/cleaning (optional)."""
        # Most loaders need no custom transform
        # Override only if you need domain-specific logic
        return rows

if __name__ == "__main__":
    PriceDailyLoader().run(get_active_symbols(), parallelism=8)
```

---

## The 18 Loaders To Refactor

In priority order (core first):

### TIER 1: Core Prices (3 loaders)
These are the most critical. Do these first.

#### 1. **loadpricedaily.py** (ALREADY DONE)
- Inherit from OptimalLoader
- Set table_name = "price_daily"
- Implement fetch_incremental() using router.fetch_ohlcv()
- No transform() needed

#### 2. **loadpriceweekly.py**
```python
class PriceWeeklyLoader(OptimalLoader):
    table_name = "price_weekly"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_ohlcv(symbol, start=since, end=date.today(), granularity='weekly')
```

#### 3. **loadpricemonthly.py**
```python
class PriceMonthlyLoader(OptimalLoader):
    table_name = "price_monthly"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_ohlcv(symbol, start=since, end=date.today(), granularity='monthly')
```

### TIER 2: Signals & Scores (5 loaders)
These depend on prices being fresh.

#### 4. **loadstockscores.py**
```python
class StockScoresLoader(OptimalLoader):
    table_name = "stock_scores"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        # Fetch technical indicators (RSI, MACD, etc.)
        return self.router.fetch_indicators(symbol, since=since)
```

#### 5. **loadbuyselldaily.py**
```python
class SignalsDailyLoader(OptimalLoader):
    table_name = "buy_sell_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_signals(symbol, since=since, granularity='daily')
```

#### 6. **loadbuysellweekly.py**
```python
class SignalsWeeklyLoader(OptimalLoader):
    table_name = "buy_sell_weekly"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_signals(symbol, since=since, granularity='weekly')
```

#### 7. **loadbuysellmonthly.py**
```python
class SignalsMonthlyLoader(OptimalLoader):
    table_name = "buy_sell_monthly"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_signals(symbol, since=since, granularity='monthly')
```

#### 8. **loadstocksymbols.py** (Universe)
```python
class SymbolUniverseLoader(OptimalLoader):
    table_name = "stock_symbols"
    primary_key = ("symbol",)  # Unique only by symbol
    watermark_field = "updated_at"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        # This is special: fetch ALL symbols (not per-symbol)
        # Override run() to handle differently
        return self.router.fetch_all_symbols()
    
    def run(self, symbols=None, **kwargs):
        # Universe loader doesn't use per-symbol watermark
        rows = self.fetch_incremental(None, None)
        rows = self.transform(rows)
        rows = [r for r in rows if self._validate_row(r)]
        self._bulk_insert(rows)
        return self._stats
```

### TIER 3: Fundamentals (3 loaders)
These update less frequently (earnings reports, etc.)

#### 9. **loadearningsrevisions.py**
```python
class EarningsRevisionsLoader(OptimalLoader):
    table_name = "earnings_revisions"
    primary_key = ("symbol", "period_date")
    watermark_field = "period_date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_earnings_revisions(symbol, since=since)
```

#### 10. **loadestimatedeps.py**
```python
class EstimatedEPSLoader(OptimalLoader):
    table_name = "estimated_eps"
    primary_key = ("symbol", "period_date")
    watermark_field = "period_date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_estimated_eps(symbol, since=since)
```

#### 11. **loadfactormetrics.py**
```python
class FactorMetricsLoader(OptimalLoader):
    table_name = "factor_metrics"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_factor_metrics(symbol, since=since)
```

### TIER 4: Alternative Data (3 loaders)
Sentiment, analyst upgrades, etc.

#### 12. **loadsentiment.py**
```python
class SentimentLoader(OptimalLoader):
    table_name = "sentiment"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_sentiment(symbol, since=since)
```

#### 13. **loadanalystupgradedowngrade.py**
```python
class AnalystUpgradesLoader(OptimalLoader):
    table_name = "analyst_upgrades"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_analyst_actions(symbol, since=since)
```

#### 14. **load_trend_template_data.py** (NEW)
```python
class TrendTemplateLoader(OptimalLoader):
    table_name = "trend_templates"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        # Custom implementation
        return self.router.fetch_trend_templates(symbol, since=since)
```

### TIER 5: Portfolio & Account (2 loaders)
Real-time account data.

#### 15. **loadalpacaportfolio.py**
```python
class AlpacaPortfolioLoader(OptimalLoader):
    table_name = "alpaca_positions"
    primary_key = ("symbol",)  # One row per position
    watermark_field = "updated_at"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        # Get ALL positions from Alpaca
        return self.router.fetch_alpaca_positions()
    
    def run(self, symbols=None, **kwargs):
        # Portfolio is not per-symbol
        rows = self.fetch_incremental(None, None)
        rows = self.transform(rows)
        rows = [r for r in rows if self._validate_row(r)]
        self._bulk_insert(rows)
        return self._stats
```

#### 16. **loadivrank.py**
```python
class IVRankLoader(OptimalLoader):
    table_name = "iv_rank"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_iv_rank(symbol, since=since)
```

### TIER 6: Extended Data (1 loader)
Fundamentals that update less frequently.

#### 17. **loadfundamentals.py**
```python
class FundamentalsLoader(OptimalLoader):
    table_name = "fundamentals"
    primary_key = ("symbol", "period_date")
    watermark_field = "period_date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_fundamentals(symbol, since=since)
```

#### 18. **loadtechnicalsdaily.py** (NEW)
```python
class TechnicalsLoader(OptimalLoader):
    table_name = "technical_indicators"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol: str, since: Optional[date]):
        return self.router.fetch_technical_indicators(symbol, since=since)
```

---

## Refactoring Checklist

For each loader:

- [ ] Rename class: `load*()` function → `*Loader` class
- [ ] Inherit from `OptimalLoader`
- [ ] Set: `table_name`, `primary_key`, `watermark_field`
- [ ] Implement: `fetch_incremental(symbol, since) -> List[dict]`
- [ ] Optional: `transform(rows) -> List[dict]` (only if custom logic needed)
- [ ] Update `__main__`: `ClassName().run(get_active_symbols())`
- [ ] Test locally: `python3 load*.py --test-mode` or unit test
- [ ] Verify: Same row count as old loader (sanity check)
- [ ] Commit: "refactor: migrate load* to OptimalLoader pattern"

---

## Testing Each Loader

```bash
# Test one loader locally
python3 -c "
from loadpricedaily import PriceDailyLoader
loader = PriceDailyLoader()
stats = loader.run(['AAPL', 'MSFT', 'NVDA'], parallelism=2)
print(stats)
"

# Run unit tests
pytest tests/test_optimal_loader.py -v

# Run integration tests (requires database)
pytest tests/ -v -m integration
```

---

## Commit Strategy

Commit in groups:

1. **Commit 1:** OptimalLoader base class + watermarks table
   ```
   git add optimal_loader.py init_db.sql tests/test_optimal_loader.py
   git commit -m "refactor: implement OptimalLoader base with watermarking"
   ```

2. **Commit 2:** TIER 1 loaders (prices)
   ```
   git add loadpricedaily.py loadpriceweekly.py loadpricemonthly.py
   git commit -m "refactor: migrate price loaders to OptimalLoader pattern"
   ```

3. **Commit 3:** TIER 2 loaders (signals)
   ```
   git add loadstockscores.py loadbuyselldaily.py loadbuysellweekly.py loadbuysellmonthly.py loadstocksymbols.py
   git commit -m "refactor: migrate signal loaders to OptimalLoader pattern"
   ```

4. **Commit 4:** TIER 3-6 loaders (rest)
   ```
   git add load*.py
   git commit -m "refactor: migrate remaining loaders to OptimalLoader pattern"
   ```

---

## Performance Impact

Expected improvements after full refactoring:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Code per loader | 200-400 lines | 30-50 lines | 80% reduction |
| Load time | 10-15 min | 3-5 min | 66% faster (due to batching + COPY) |
| API calls | 1 per symbol | 0.1 per symbol | 90% reduction (watermarks) |
| DB connections | 1 per loader | 1 per loader | Same (already pooled) |
| Memory usage | High (pandas) | Low (dict iteration) | ~40% reduction |

---

## Next Steps After Refactoring

1. Update Terraform to trigger all loaders daily at 4:00am ET
2. Add monitoring dashboard showing loader execution history
3. Add alerts for loader failures
4. Create performance baseline (query times, load times)
5. Add observability metrics (sources used, dedup rate, etc.)

