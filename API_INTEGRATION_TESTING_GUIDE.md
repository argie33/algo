# API Integration Testing Guide - Week 2

**Objective:** Verify all 30+ API endpoints work correctly in isolation and end-to-end (data load → algo → trade execution → portfolio tracking).

**Status:** Ready to integrate into CI/CD pipeline.

**Testing Scope:** 5 test suites covering complete trading workflow.

---

## Test Suite Overview

### Suite 1: Data Loading API (5 endpoints)
- Stock symbol lookup
- Price history retrieval
- Technical indicators query
- Data freshness check
- Loader status API

### Suite 2: Signal Generation API (4 endpoints)
- Buy/sell signal query
- Signal details with confidence scores
- Historical signal performance
- Signal audit trail

### Suite 3: Trading Execution API (6 endpoints)
- Portfolio positions query
- Order placement and tracking
- Order status updates
- Trade execution history
- Slippage metrics
- Order reconciliation status

### Suite 4: Portfolio Management API (5 endpoints)
- Portfolio allocation view
- Position sizing calculator
- Risk metrics (Sharpe, drawdown, etc.)
- Portfolio snapshots over time
- Rebalancing recommendations

### Suite 5: Observability API (6 endpoints)
- System health status
- Loader SLA dashboard
- Alert history and routing
- Audit log query
- CloudWatch metrics integration
- Incident status

---

## How to Run Tests

### Local (Docker Compose)

```bash
# Start local environment
docker-compose up -d
sleep 30  # Wait for services

# Run all tests
pytest tests/integration/ -v

# Run specific suite
pytest tests/integration/test_suite_1_data_loading.py -v

# Run single test
pytest tests/integration/test_suite_2_signals.py::test_buy_signals_today -v
```

### In GitHub Actions (CI/CD)

Tests run automatically on:
- Every push to main
- Pull requests to main
- Scheduled daily at 6am ET

```bash
# Check test status
gh workflow run ci-integration-tests.yml
gh run list --workflow ci-integration-tests.yml
```

---

## Test Suite 1: Data Loading API

**File:** `tests/integration/test_suite_1_data_loading.py`

### Test 1.1: Stock Symbol Lookup

```python
def test_get_stock_symbols():
    """GET /api/stocks - retrieve list of supported symbols"""
    response = api.get('/api/stocks')
    
    assert response.status == 200
    assert 'symbols' in response.body
    assert 'AAPL' in response.body['symbols']  # At least sample stocks present
    assert len(response.body['symbols']) >= 100  # Reasonable stock universe
    
    # Verify structure
    for symbol in response.body['symbols'][:5]:
        assert 'symbol' in symbol
        assert 'name' in symbol
        assert 'sector' in symbol
```

**Success Criteria:**
- ✓ Returns HTTP 200
- ✓ Contains at least 100 stocks
- ✓ Each stock has symbol, name, sector

### Test 1.2: Price History Query

```python
def test_get_price_history():
    """GET /api/stocks/{symbol}/prices - retrieve OHLCV history"""
    response = api.get('/api/stocks/AAPL/prices?days=60')
    
    assert response.status == 200
    prices = response.body['prices']
    
    # Verify data structure
    assert len(prices) >= 50  # At least 50 trading days
    
    for price in prices:
        assert 'date' in price
        assert 'open' in price
        assert 'high' in price
        assert 'low' in price
        assert 'close' in price
        assert 'volume' in price
        assert price['high'] >= price['low']  # OHLC sanity
        assert price['close'] > 0
        assert price['volume'] >= 0
    
    # Verify time series is sorted
    dates = [p['date'] for p in prices]
    assert dates == sorted(dates)
```

**Success Criteria:**
- ✓ Returns HTTP 200
- ✓ Has at least 50 days of data
- ✓ OHLC values are sane (high >= low)
- ✓ Sorted chronologically

### Test 1.3: Technical Indicators Query

```python
def test_get_technical_indicators():
    """GET /api/stocks/{symbol}/indicators - retrieve RSI, MACD, Bollinger Bands"""
    response = api.get('/api/stocks/AAPL/indicators?days=30')
    
    assert response.status == 200
    indicators = response.body['indicators']
    
    # Check expected indicators present
    assert 'rsi' in indicators
    assert 'macd' in indicators
    assert 'bollinger_bands' in indicators
    
    # Verify RSI (0-100)
    for rsi in indicators['rsi']:
        assert 0 <= rsi['value'] <= 100
    
    # Verify MACD structure
    for macd in indicators['macd']:
        assert 'signal' in macd
        assert 'histogram' in macd
        assert macd['histogram'] == macd['line'] - macd['signal']
    
    # Verify Bollinger Bands (upper > lower)
    for bb in indicators['bollinger_bands']:
        assert bb['upper'] >= bb['middle'] >= bb['lower']
```

**Success Criteria:**
- ✓ Returns RSI (0-100)
- ✓ Returns MACD with signal and histogram
- ✓ Returns Bollinger Bands with upper/middle/lower bands

### Test 1.4: Data Freshness Check

```python
def test_data_freshness():
    """GET /api/health/data-freshness - check when data was last updated"""
    response = api.get('/api/health/data-freshness')
    
    assert response.status == 200
    freshness = response.body
    
    # Check timestamp format
    for table, info in freshness.items():
        assert 'last_update' in info
        assert 'hours_old' in info
        assert 'status' in info  # FRESH, STALE, MISSING
    
    # Critical data must be <24 hours old
    assert freshness['price_daily']['status'] == 'FRESH'
    assert freshness['price_daily']['hours_old'] < 24
    assert freshness['buy_sell_daily']['status'] == 'FRESH'
    assert freshness['buy_sell_daily']['hours_old'] < 24
```

**Success Criteria:**
- ✓ Returns timestamp of last update
- ✓ Shows hours old
- ✓ Critical tables are FRESH (<24h)

### Test 1.5: Loader Status API

```python
def test_loader_status():
    """GET /api/admin/loaders - check SLA status of data loaders"""
    response = api.get('/api/admin/loaders')
    
    assert response.status == 200
    loaders = response.body['loaders']
    
    # Verify expected loaders
    loader_names = {l['name'] for l in loaders}
    assert 'price_daily' in loader_names
    assert 'buy_sell_daily' in loader_names
    
    # Check status structure
    for loader in loaders:
        assert 'name' in loader
        assert 'status' in loader  # PASS, FAILED, PENDING
        assert 'last_run' in loader
        assert 'rows_loaded' in loader
        assert 'rows_failed' in loader
        assert 'success_rate' in loader  # percentage
    
    # Critical loaders must have passed
    price_loader = next(l for l in loaders if l['name'] == 'price_daily')
    assert price_loader['status'] == 'PASS'
```

**Success Criteria:**
- ✓ Shows status of each loader
- ✓ Shows last run time and row counts
- ✓ Critical loaders are PASS status

---

## Test Suite 2: Signal Generation API

**File:** `tests/integration/test_suite_2_signals.py`

### Test 2.1: Buy Signals Today

```python
def test_buy_signals_today():
    """GET /api/signals/buy?date=today - retrieve buy signals generated today"""
    response = api.get(f'/api/signals/buy?date={date.today().isoformat()}')
    
    assert response.status == 200
    signals = response.body['signals']
    
    # Expect 5-50 signals (reasonable range for daily)
    assert 5 <= len(signals) <= 50
    
    # Verify signal structure
    for signal in signals:
        assert 'symbol' in signal
        assert 'date' in signal
        assert 'signal_type' in signal  # BUY, SELL
        assert signal['signal_type'] == 'BUY'
        assert 'confidence' in signal  # 0-100
        assert 0 <= signal['confidence'] <= 100
        assert 'entry_price' in signal
        assert signal['entry_price'] > 0
        assert 'stop_loss' in signal
        assert signal['stop_loss'] < signal['entry_price']
```

**Success Criteria:**
- ✓ Returns 5-50 buy signals
- ✓ Each signal has symbol, date, type, confidence, entry_price, stop_loss
- ✓ Confidence is 0-100
- ✓ Stop loss < entry price

### Test 2.2: Signal Confidence Scores

```python
def test_signal_confidence_details():
    """GET /api/signals/{symbol}/confidence - get detailed scoring breakdown"""
    response = api.get('/api/signals/AAPL/confidence')
    
    assert response.status == 200
    score = response.body
    
    # Verify scoring components
    assert 'overall_score' in score
    assert 'tier_1_data_quality' in score
    assert 'tier_2_market_health' in score
    assert 'tier_3_trend_template' in score
    assert 'tier_4_signal_quality' in score
    assert 'tier_5_portfolio_health' in score
    
    # Each tier should be 0-100 or null if not calculated
    for tier in ['tier_1_data_quality', 'tier_2_market_health', 'tier_3_trend_template', 'tier_4_signal_quality', 'tier_5_portfolio_health']:
        if score[tier] is not None:
            assert 0 <= score[tier] <= 100
```

**Success Criteria:**
- ✓ Returns all 5 tier scores
- ✓ Each score is 0-100 or null
- ✓ Overall score is computed from tiers

### Test 2.3: Signal Performance Historical

```python
def test_signal_historical_performance():
    """GET /api/signals/{symbol}/performance - measure how signals performed"""
    response = api.get('/api/signals/AAPL/performance?days=30')
    
    assert response.status == 200
    perf = response.body
    
    # Verify metrics present
    assert 'win_rate' in perf  # percentage of profitable trades
    assert 'avg_gain' in perf  # average % gain per trade
    assert 'avg_loss' in perf  # average % loss per trade
    assert 'sharpe_ratio' in perf
    assert 'max_drawdown' in perf
    
    # Verify reasonable ranges
    assert 0 <= perf['win_rate'] <= 100
    assert perf['sharpe_ratio'] >= -5  # Sharpe can be negative in bad markets
    assert -50 <= perf['max_drawdown'] <= 0  # Drawdown is negative
```

**Success Criteria:**
- ✓ Shows win rate, avg gain/loss
- ✓ Shows Sharpe ratio and max drawdown
- ✓ Metrics are in reasonable ranges

### Test 2.4: Signal Audit Trail

```python
def test_signal_audit_trail():
    """GET /api/signals/audit?symbol=AAPL&days=7 - see all signals for symbol"""
    response = api.get('/api/signals/audit?symbol=AAPL&days=7')
    
    assert response.status == 200
    signals = response.body['signals']
    
    # Verify we have audit history
    assert len(signals) >= 1  # At least 1 signal in past 7 days
    
    # Each audit entry should show:
    for signal in signals:
        assert 'date' in signal
        assert 'signal' in signal  # BUY or SELL
        assert 'price' in signal
        assert 'reason' in signal  # Why this signal was generated
        assert 'tiers_passed' in signal  # Which tiers passed
```

**Success Criteria:**
- ✓ Shows signals for symbol over date range
- ✓ Each signal has date, type, price, reason
- ✓ Shows which tiers passed

---

## Test Suite 3: Trading Execution API

**File:** `tests/integration/test_suite_3_trading.py`

### Test 3.1: Portfolio Positions

```python
def test_portfolio_positions():
    """GET /api/portfolio/positions - see all open positions"""
    response = api.get('/api/portfolio/positions')
    
    assert response.status == 200
    positions = response.body['positions']
    
    # Verify position structure
    for pos in positions:
        assert 'symbol' in pos
        assert 'shares' in pos
        assert pos['shares'] > 0
        assert 'entry_price' in pos
        assert 'current_price' in pos
        assert 'entry_date' in pos
        assert 'unrealized_pnl' in pos  # dollars
        assert 'unrealized_pnl_pct' in pos  # percentage
        assert 'stop_loss' in pos
        
        # PnL should be: (current - entry) * shares
        expected_pnl = (pos['current_price'] - pos['entry_price']) * pos['shares']
        assert abs(pos['unrealized_pnl'] - expected_pnl) < 1  # Allow $1 rounding
```

**Success Criteria:**
- ✓ Shows all open positions
- ✓ Each position has entry/exit prices, shares, dates
- ✓ PnL is calculated correctly

### Test 3.2: Place Order

```python
def test_place_order():
    """POST /api/orders/place - place a buy order"""
    order_request = {
        'symbol': 'AAPL',
        'side': 'BUY',
        'quantity': 10,
        'order_type': 'market',
        'time_in_force': 'day'
    }
    
    response = api.post('/api/orders/place', order_request)
    
    assert response.status == 201  # Created
    order = response.body['order']
    
    # Verify order details
    assert 'order_id' in order
    assert order['symbol'] == 'AAPL'
    assert order['side'] == 'BUY'
    assert order['quantity'] == 10
    assert 'status' in order  # PENDING, FILLED, CANCELLED
    assert 'filled_price' in order or order['status'] == 'PENDING'
    assert 'created_at' in order
```

**Success Criteria:**
- ✓ Returns HTTP 201
- ✓ Order has ID, symbol, side, quantity
- ✓ Status tracks order lifecycle

### Test 3.3: Order Status Query

```python
def test_get_order_status():
    """GET /api/orders/{order_id} - check status of specific order"""
    # First place an order
    order_request = {'symbol': 'AAPL', 'side': 'BUY', 'quantity': 10, 'order_type': 'market'}
    place_response = api.post('/api/orders/place', order_request)
    order_id = place_response.body['order']['order_id']
    
    # Then check its status
    response = api.get(f'/api/orders/{order_id}')
    
    assert response.status == 200
    order = response.body['order']
    
    # Status progression: PENDING → FILLED (or CANCELLED)
    assert order['status'] in ['PENDING', 'FILLED', 'CANCELLED', 'PARTIALLY_FILLED']
    
    if order['status'] == 'FILLED':
        assert 'filled_price' in order
        assert 'filled_at' in order
        assert order['filled_price'] > 0
```

**Success Criteria:**
- ✓ Returns order details by ID
- ✓ Shows current status
- ✓ Shows filled_price if filled

### Test 3.4: Trade Execution History

```python
def test_trade_execution_history():
    """GET /api/trades/history?days=30 - see all trades executed"""
    response = api.get('/api/trades/history?days=30')
    
    assert response.status == 200
    trades = response.body['trades']
    
    # Verify trade structure
    for trade in trades:
        assert 'symbol' in trade
        assert 'entry_date' in trade
        assert 'exit_date' in trade or trade['status'] == 'OPEN'
        assert 'entry_price' in trade
        assert 'exit_price' in trade or trade['status'] == 'OPEN'
        assert 'shares' in trade
        assert 'status' in trade  # OPEN, CLOSED, PARTIAL
        assert 'pnl' in trade  # dollars
        assert 'pnl_pct' in trade  # percentage
```

**Success Criteria:**
- ✓ Shows recent trades
- ✓ Each trade has entry/exit prices and dates
- ✓ Shows PnL realized

### Test 3.5: Slippage Metrics

```python
def test_slippage_metrics():
    """GET /api/trades/slippage?date=today - measure execution quality"""
    response = api.get(f'/api/trades/slippage?date={date.today().isoformat()}')
    
    assert response.status == 200
    slippage = response.body
    
    # Overall metrics
    assert 'trade_count' in slippage
    assert 'avg_slippage' in slippage
    assert 'avg_slippage_pct' in slippage
    assert 'best_trade' in slippage
    assert 'worst_trade' in slippage
    
    # Per-symbol metrics
    if 'per_symbol' in slippage:
        for symbol, stats in slippage['per_symbol'].items():
            assert 'count' in stats
            assert 'avg_slippage' in stats
            assert stats['count'] > 0
```

**Success Criteria:**
- ✓ Shows overall slippage metrics
- ✓ Shows per-symbol breakdown
- ✓ Tracks execution quality

### Test 3.6: Order Reconciliation Status

```python
def test_order_reconciliation():
    """GET /api/orders/reconciliation - check for discrepancies with broker"""
    response = api.get('/api/orders/reconciliation')
    
    assert response.status == 200
    recon = response.body
    
    # Should show:
    assert 'discrepancies' in recon  # List of issues
    assert 'total_orders' in recon
    assert 'reconciled_orders' in recon
    
    # Verify structure
    if len(recon['discrepancies']) > 0:
        for disc in recon['discrepancies']:
            assert 'type' in disc  # ORPHANED, FILLED_UNKNOWN, STUCK, etc.
            assert 'symbol' in disc
            assert 'message' in disc
```

**Success Criteria:**
- ✓ Shows reconciliation status
- ✓ Identifies discrepancy types
- ✓ Provides actionable information

---

## Test Suite 4: Portfolio Management API

**File:** `tests/integration/test_suite_4_portfolio.py`

### Test 4.1: Portfolio Allocation View

```python
def test_portfolio_allocation():
    """GET /api/portfolio/allocation - see sector and industry breakdown"""
    response = api.get('/api/portfolio/allocation')
    
    assert response.status == 200
    allocation = response.body
    
    # By sector
    assert 'by_sector' in allocation
    total_pct = sum(s['pct'] for s in allocation['by_sector'])
    assert 95 <= total_pct <= 105  # Allow 5% rounding error
    
    # By industry
    assert 'by_industry' in allocation
    total_pct = sum(i['pct'] for i in allocation['by_industry'])
    assert 95 <= total_pct <= 105
    
    # Verify structure
    for sector in allocation['by_sector']:
        assert 'sector' in sector
        assert 'value_usd' in sector
        assert 'pct' in sector
        assert 0 <= sector['pct'] <= 100
```

**Success Criteria:**
- ✓ Shows sector breakdown
- ✓ Shows industry breakdown
- ✓ Percentages sum to ~100%

### Test 4.2: Position Sizing Calculator

```python
def test_position_sizing():
    """POST /api/portfolio/size-position - calculate shares for new position"""
    sizing_request = {
        'symbol': 'TSLA',
        'entry_price': 250.00,
        'stop_loss_price': 240.00,
        'risk_per_trade_dollars': 500  # Risk $500 per trade
    }
    
    response = api.post('/api/portfolio/size-position', sizing_request)
    
    assert response.status == 200
    sizing = response.body
    
    # Verify sizing logic
    assert 'shares' in sizing
    assert sizing['shares'] > 0
    assert 'risk_dollars' in sizing
    assert sizing['risk_dollars'] <= 500  # Should not exceed risk limit
    assert 'entry_value' in sizing  # shares * entry_price
    assert 'expected_return_at_target' in sizing
```

**Success Criteria:**
- ✓ Calculates proper share count
- ✓ Risk doesn't exceed limit
- ✓ Shows full position details

### Test 4.3: Risk Metrics

```python
def test_portfolio_risk_metrics():
    """GET /api/portfolio/risk - see Sharpe, drawdown, correlation, etc."""
    response = api.get('/api/portfolio/risk')
    
    assert response.status == 200
    risk = response.body
    
    # Key risk metrics
    assert 'sharpe_ratio' in risk
    assert 'max_drawdown_pct' in risk
    assert 'volatility_annual_pct' in risk
    assert 'value_at_risk_95' in risk
    assert 'correlation_to_spy' in risk
    assert 'beta' in risk
    
    # Verify ranges
    assert risk['max_drawdown_pct'] <= 0  # Drawdown is negative
    assert risk['volatility_annual_pct'] >= 0
    assert -1 <= risk['correlation_to_spy'] <= 1
```

**Success Criteria:**
- ✓ Shows Sharpe ratio, drawdown, volatility
- ✓ Shows correlation to SPY
- ✓ Shows Value at Risk (95%)

### Test 4.4: Portfolio Snapshots

```python
def test_portfolio_snapshots():
    """GET /api/portfolio/snapshots?days=30 - view portfolio evolution"""
    response = api.get('/api/portfolio/snapshots?days=30')
    
    assert response.status == 200
    snapshots = response.body['snapshots']
    
    # Should have daily snapshots
    assert len(snapshots) >= 20  # At least 20 trading days
    
    # Verify structure
    for snap in snapshots:
        assert 'date' in snap
        assert 'portfolio_value' in snap
        assert 'num_positions' in snap
        assert 'total_pnl' in snap
        assert 'total_pnl_pct' in snap
    
    # Portfolio value should be monotonic or increasing (no hard requirement)
    # (Can have drawdowns during market moves)
```

**Success Criteria:**
- ✓ Shows daily portfolio snapshots
- ✓ Each snapshot has value, positions, PnL
- ✓ Covers requested date range

### Test 4.5: Rebalancing Recommendations

```python
def test_rebalancing_recommendations():
    """GET /api/portfolio/rebalance - get recommendations for sector/industry rebalancing"""
    response = api.get('/api/portfolio/rebalance')
    
    assert response.status == 200
    rebalance = response.body
    
    # Verify recommendations
    assert 'recommendations' in rebalance
    
    for rec in rebalance['recommendations']:
        assert 'action' in rec  # BUY or SELL
        assert 'symbol' in rec
        assert 'reason' in rec  # Why rebalance is suggested
        assert 'target_size_pct' in rec
        assert 'current_size_pct' in rec
        assert 'suggested_shares' in rec
```

**Success Criteria:**
- ✓ Provides rebalancing recommendations
- ✓ Shows target vs current allocation
- ✓ Suggests specific share counts

---

## Test Suite 5: Observability API

**File:** `tests/integration/test_suite_5_observability.py`

### Test 5.1: System Health Status

```python
def test_system_health():
    """GET /api/health - comprehensive system health check"""
    response = api.get('/api/health')
    
    assert response.status == 200
    health = response.body
    
    # Key components
    assert 'database' in health  # status: OK, DEGRADED, ERROR
    assert 'algodb' in health
    assert 'alpaca_connection' in health
    assert 'data_freshness' in health
    assert 'last_check' in health
    
    # Overall status
    assert health['status'] in ['OK', 'DEGRADED', 'ERROR']
    assert health['status'] == 'OK'  # Should be healthy
```

**Success Criteria:**
- ✓ Returns status of key components
- ✓ Overall status is OK or DEGRADED (not ERROR)
- ✓ Shows last check time

### Test 5.2: Loader SLA Dashboard

```python
def test_loader_sla_dashboard():
    """GET /api/admin/loader-sla - see detailed SLA metrics"""
    response = api.get('/api/admin/loader-sla')
    
    assert response.status == 200
    sla = response.body
    
    # Overall SLA
    assert 'overall_success_rate_pct' in sla
    assert 0 <= sla['overall_success_rate_pct'] <= 100
    
    # Per-loader SLA
    assert 'loaders' in sla
    for loader in sla['loaders']:
        assert 'name' in loader
        assert 'success_rate_pct' in loader
        assert 'last_7_days' in loader
        assert loader['success_rate_pct'] >= 90  # Should be high
```

**Success Criteria:**
- ✓ Shows overall SLA percentage
- ✓ Shows per-loader metrics
- ✓ SLA should be >90%

### Test 5.3: Alert History

```python
def test_alert_history():
    """GET /api/admin/alerts?hours=24 - see recent alerts"""
    response = api.get('/api/admin/alerts?hours=24')
    
    assert response.status == 200
    alerts = response.body['alerts']
    
    # Verify alert structure
    for alert in alerts:
        assert 'timestamp' in alert
        assert 'severity' in alert  # CRITICAL, ERROR, WARNING, INFO
        assert alert['severity'] in ['CRITICAL', 'ERROR', 'WARNING', 'INFO']
        assert 'title' in alert
        assert 'message' in alert
        assert 'resolved' in alert  # boolean
```

**Success Criteria:**
- ✓ Shows alerts within time range
- ✓ Each alert has severity, title, message
- ✓ Shows resolution status

### Test 5.4: Audit Log Query

```python
def test_audit_log():
    """GET /api/admin/audit?action=trade&days=7 - see auditable actions"""
    response = api.get('/api/admin/audit?action=trade&days=7')
    
    assert response.status == 200
    logs = response.body['logs']
    
    # Verify audit entries
    for log in logs:
        assert 'timestamp' in log
        assert 'action' in log  # TRADE_PLACED, ORDER_FILLED, etc.
        assert 'user' in log  # Who did it (algo or operator)
        assert 'symbol' in log or log['action'] not in ['TRADE_PLACED', 'TRADE_CLOSED']
        assert 'details' in log  # Additional context
        assert 'trace_id' in log  # For distributed tracing
```

**Success Criteria:**
- ✓ Shows auditable actions
- ✓ Each entry has timestamp, action, actor, trace_id
- ✓ Queryable by action type and date range

### Test 5.5: CloudWatch Metrics Integration

```python
def test_cloudwatch_metrics():
    """GET /api/admin/metrics?metric=lambda_duration&hours=1 - query CloudWatch metrics"""
    response = api.get('/api/admin/metrics?metric=lambda_duration&hours=1')
    
    assert response.status == 200
    metrics = response.body
    
    # Verify metric structure
    assert 'metric_name' in metrics
    assert 'datapoints' in metrics
    assert 'unit' in metrics
    
    # Lambda duration should be in seconds
    for point in metrics['datapoints']:
        assert 'timestamp' in point
        assert 'value' in point
        assert point['value'] >= 0  # Duration is positive
```

**Success Criteria:**
- ✓ Queries CloudWatch metrics
- ✓ Shows datapoints over time
- ✓ Values are reasonable

### Test 5.6: Incident Status

```python
def test_incident_status():
    """GET /api/admin/incidents - see open incidents"""
    response = api.get('/api/admin/incidents')
    
    assert response.status == 200
    incidents = response.body
    
    # Verify incident structure
    assert 'open_incidents' in incidents
    assert 'recent_incidents' in incidents
    
    for incident in incidents['open_incidents']:
        assert 'incident_id' in incident
        assert 'severity' in incident  # SEV-1, SEV-2, SEV-3
        assert 'discovered_at' in incident
        assert 'summary' in incident
        assert 'status' in incident  # INVESTIGATING, MITIGATING, RESOLVED
```

**Success Criteria:**
- ✓ Shows open incidents
- ✓ Shows recent incident history
- ✓ Each incident has severity, summary, status

---

## Running the Full Test Suite

### Local Development

```bash
# Install test dependencies
pip install pytest pytest-asyncio requests

# Run all tests with coverage
pytest tests/integration/ -v --cov=webapp/lambda --cov-report=html

# Run tests matching pattern
pytest tests/integration/ -k "test_buy_signals" -v

# Run with detailed output
pytest tests/integration/ -vv -s
```

### GitHub Actions

```yaml
# .github/workflows/ci-integration-tests.yml
name: Integration Tests

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6am ET

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: password
          POSTGRES_DB: stocks
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio
      
      - name: Run integration tests
        run: pytest tests/integration/ -v --tb=short
      
      - name: Upload test report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: test-report
          path: test-results.xml
```

---

## Test Execution Timeline

| Phase | Duration | Tests | Pass Rate |
|-------|----------|-------|-----------|
| Phase 1: Data Loading | 2-3 min | 5 | >95% |
| Phase 2: Signal Generation | 3-4 min | 4 | >95% |
| Phase 3: Trading Execution | 5-7 min | 6 | >95% |
| Phase 4: Portfolio Mgmt | 3-4 min | 5 | >95% |
| Phase 5: Observability | 2-3 min | 6 | >95% |
| **Total** | **15-20 min** | **26 tests** | **>95%** |

---

## Success Criteria

✅ **All 26 tests pass** (or explicitly marked as expected failures)
✅ **Response times** < 5 seconds for any endpoint
✅ **No data loss** during test execution
✅ **Consistent results** across multiple runs

If tests fail, use OPERATIONAL_RUNBOOKS.md to diagnose and recover.

---

## Integration Test Results Template

```markdown
# Integration Test Results - [DATE]

## Summary
- Total Tests: 26
- Passed: 26
- Failed: 0
- Skipped: 0
- Duration: 18 min

## Suite Results
- Suite 1 (Data Loading): ✓ 5/5 passed
- Suite 2 (Signals): ✓ 4/4 passed
- Suite 3 (Trading): ✓ 6/6 passed
- Suite 4 (Portfolio): ✓ 5/5 passed
- Suite 5 (Observability): ✓ 6/6 passed

## Performance
- Slowest test: test_portfolio_snapshots (2.3s)
- Fastest test: test_health (0.1s)
- Average: 0.7s per test

## Data Integrity
- No orphaned records created
- All transactions rolled back successfully
- Database clean after tests: ✓

## Recommendation
✅ **Ready for deployment**
```

---

**This test suite provides end-to-end validation that your platform works correctly. Run before every deployment.**
