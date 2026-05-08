# Complete Integration Plan — All 4 Critical Gaps
**Objective**: Seamlessly integrate data quality monitoring, signal performance tracking, execution visibility, and rejection explainability into your existing pipeline without disrupting current operations.

**Architecture Principle**: Extend, don't replace. Leverage your existing tables (algo_trades, algo_positions, algo_audit_log, data_loader_status) and add minimal new tables + middleware layers.

---

## Phase 1: Database Schema Extensions (2 hours)

### NEW Tables (4 additions to init_database.py)

#### 1. Loader Health SLA Tracking
```sql
CREATE TABLE IF NOT EXISTS loader_sla_status (
    id SERIAL PRIMARY KEY,
    loader_name VARCHAR(100) NOT NULL,
    table_name VARCHAR(80) NOT NULL,
    expected_frequency VARCHAR(20),           -- 'daily', 'weekly', etc.
    max_age_hours INT,                        -- SLA threshold (16h for prices, 24h for earnings)
    latest_data_date DATE,                    -- Max(date) in that table
    age_hours INT GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (NOW() - TO_TIMESTAMP(latest_data_date, 'YYYY-MM-DD'))) / 3600
    ) STORED,
    row_count_today BIGINT,                   -- How many rows loaded in last 24h
    status VARCHAR(20),                       -- 'OK', 'WARNING', 'CRITICAL'
    alert_sent_at TIMESTAMP,
    last_check_at TIMESTAMP DEFAULT NOW(),
    error_message TEXT,
    UNIQUE(loader_name, table_name)
);
```
**Purpose**: Per-loader SLA enforcement. Triggers alerts if data is stale or load count drops unexpectedly.
**Used by**: `DataQualityValidator` → called before algo_run_daily starts

---

#### 2. Signal Performance Attribution
```sql
CREATE TABLE IF NOT EXISTS signal_trade_performance (
    id SERIAL PRIMARY KEY,
    trade_id INT REFERENCES algo_trades(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    signal_date DATE NOT NULL,
    entry_price DECIMAL(12, 4),
    base_type VARCHAR(50),                    -- 'Cup', 'Flat Base', etc.
    sqs INT,                                  -- Signal Quality Score
    swing_score DECIMAL(8, 2),                -- Swing trader score
    swing_grade VARCHAR(5),                   -- 'A+', 'A', 'B', etc.
    trend_score INT,                          -- Minervini trend
    stage_at_entry VARCHAR(50),               -- 'Stage 2', etc.
    sector VARCHAR(100),
    rs_percentile INT,                        -- Relative strength 0-100
    market_exposure_at_entry DECIMAL(8, 2),
    
    -- Exit & Performance
    exit_price DECIMAL(12, 4),
    exit_date DATE,
    hold_days INT,
    realized_pnl DECIMAL(12, 2),
    realized_pnl_pct DECIMAL(8, 4),
    r_multiple DECIMAL(8, 2),                 -- (exit - entry) / (entry - stop)
    win BOOLEAN,                              -- true if pnl > 0
    
    -- Feedback
    target_1_hit BOOLEAN,
    target_2_hit BOOLEAN,
    target_3_hit BOOLEAN,
    exit_by_stop BOOLEAN,
    exit_by_time BOOLEAN,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_signal_perf_symbol_date ON signal_trade_performance(symbol, signal_date);
CREATE INDEX idx_signal_perf_base_type ON signal_trade_performance(base_type);
```
**Purpose**: Link every executed trade back to its signal + metadata. Enable win rate analysis by base type, SQS, stage, etc.
**Used by**: `TradePerformanceAuditor` → populate on trade exit

---

#### 3. Filter Rejection Tracking
```sql
CREATE TABLE IF NOT EXISTS filter_rejection_log (
    id SERIAL PRIMARY KEY,
    eval_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    entry_price DECIMAL(12, 4),
    rejected_at_tier INT,                    -- Which tier rejected it (1-5)
    rejection_reason VARCHAR(200),           -- "Distribution days 5 > 4"
    tier_1_pass BOOLEAN,
    tier_2_pass BOOLEAN,
    tier_2_reason VARCHAR(200),
    tier_3_pass BOOLEAN,
    tier_3_reason VARCHAR(200),
    tier_4_pass BOOLEAN,
    tier_4_reason VARCHAR(200),
    tier_5_pass BOOLEAN,
    tier_5_reason VARCHAR(200),
    advanced_checks_reason VARCHAR(200),
    swing_score_min_reason VARCHAR(200),
    base_type VARCHAR(50),
    sqs INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_rejection_eval_date ON filter_rejection_log(eval_date);
Create INDEX idx_rejection_tier ON filter_rejection_log(rejected_at_tier);
```
**Purpose**: Capture why each signal was rejected, in order. Enable rejection funnel analysis + explainability.
**Used by**: `FilterPipeline.evaluate_signals()` → log rejection before returning

---

#### 4. Order Audit Trail
```sql
CREATE TABLE IF NOT EXISTS order_execution_log (
    id SERIAL PRIMARY KEY,
    trade_id INT REFERENCES algo_trades(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    order_sequence_num INT,                  -- 1st attempt, 2nd retry, etc.
    order_timestamp TIMESTAMP,
    order_type VARCHAR(20),                  -- 'entry', 'exit_t1', 'exit_t2', 'exit_t3'
    side VARCHAR(10),                        -- 'BUY' or 'SELL'
    requested_shares INT,
    requested_price DECIMAL(12, 4),
    order_status VARCHAR(50),                -- 'pending', 'filled', 'partial', 'rejected', 'cancelled'
    filled_shares INT,
    filled_price DECIMAL(12, 4),
    fill_rate_pct DECIMAL(6, 2),
    slippage_bps DECIMAL(10, 2),             -- Basis points
    alpaca_order_id VARCHAR(100),
    rejection_reason VARCHAR(200),
    execution_latency_ms INT,
    retry_count INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_order_trade_id ON order_execution_log(trade_id);
Create INDEX idx_order_status ON order_execution_log(order_status);
```
**Purpose**: Per-order audit trail. Track every attempt, fill, rejection, slippage.
**Used by**: `TradeExecutor.execute_trade()` → log after each Alpaca API call

---

### Schema Update Script (add to init_database.py)
```python
# In the SCHEMA string, add these 4 CREATE TABLE statements
# Then run:
# python3 init_database.py
```

---

## Phase 2: Middleware Layers (4 new modules, 3-4 hours each)

### Layer 1: Data Quality Validator
**File**: `data_quality_validator.py` (NEW)

```python
#!/usr/bin/env python3
"""
Data Quality SLA Enforcement

Validates:
- Loader freshness (price data ≤ 16h old, earnings ≤ 24h old)
- Load volume (minimum rows loaded per run)
- Data completeness (% of symbols loaded vs. expected)
- Fallback detection (did a loader use fallback source?)

Blocks algo_run_daily if any SLA is violated.
"""

class DataQualityValidator:
    def __init__(self, config):
        self.config = config
        self.conn = None
        self.failures = []
    
    def validate_all(self, eval_date=None):
        """Run all SLA checks. Return (all_pass: bool, failures: list)"""
        self.connect()
        
        # Check each critical loader
        critical_loaders = [
            ('price_daily', 16, 4000),           # 16h old, ≥4000 symbols
            ('market_health_daily', 24, 1),      # 24h old, ≥1 row
            ('trend_template_data', 24, 3000),   # 24h old, ≥3000 symbols
            ('buy_sell_daily', 24, 1000),        # 24h old, ≥1000 signals
            ('technical_data_daily', 24, 3000),
        ]
        
        for table, max_age_h, min_rows in critical_loaders:
            passed = self._check_loader(table, max_age_h, min_rows)
            if not passed:
                self.failures.append(f"{table}: SLA violated")
        
        self.disconnect()
        return len(self.failures) == 0, self.failures
    
    def _check_loader(self, table, max_age_hours, min_expected_rows):
        """Check if loader meets SLA."""
        self.cur.execute(f"""
            SELECT 
                MAX(date) as latest_date,
                COUNT(*) as total_rows,
                COUNT(DISTINCT symbol) as symbol_count
            FROM {table}
            WHERE date >= NOW()::DATE - INTERVAL '1 day'
        """)
        row = self.cur.fetchone()
        if not row or not row[0]:
            self.failures.append(f"{table}: No recent data")
            return False
        
        latest_date, total_rows, symbol_count = row
        age_hours = (datetime.now().date() - latest_date).total_seconds() / 3600
        
        if age_hours > max_age_hours:
            msg = f"{table}: Data {age_hours:.1f}h old > {max_age_hours}h SLA"
            self._alert(msg, 'CRITICAL')
            return False
        
        if symbol_count < min_expected_rows * 0.8:  # Allow 20% variance
            msg = f"{table}: Only {symbol_count}/{min_expected_rows} symbols loaded"
            self._alert(msg, 'WARNING')
        
        # Update loader_sla_status table
        self.cur.execute("""
            INSERT INTO loader_sla_status 
            (loader_name, table_name, latest_data_date, row_count_today, status, last_check_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (loader_name, table_name) DO UPDATE SET
                latest_data_date = EXCLUDED.latest_data_date,
                row_count_today = EXCLUDED.row_count_today,
                status = EXCLUDED.status,
                last_check_at = NOW()
        """, (table.replace('_', ' ').title(), table, latest_date, total_rows, 'OK'))
        self.conn.commit()
        
        return True
    
    def _alert(self, message, level):
        """Send alert to monitoring system (Slack/email)."""
        # TODO: Implement SNS → Slack integration
        print(f"[{level}] {message}")
```

**Integration Point**: Call at start of `algo_run_daily.py`:
```python
def run_algo_workflow(eval_date=None):
    # === NEW: Data quality gate ===
    validator = DataQualityValidator(config)
    all_pass, failures = validator.validate_all(eval_date)
    if not all_pass:
        print(f"DATA QUALITY SLA VIOLATED:\n{failures}")
        return {'status': 'data_sla_blocked', 'failures': failures}
    # === END: Data quality gate ===
    
    # ... rest of algo_run_daily ...
```

---

### Layer 2: Trade Performance Auditor
**File**: `trade_performance_auditor.py` (NEW)

```python
#!/usr/bin/env python3
"""
Trade Performance Attribution & Win Rate Analysis

On trade exit:
1. Populate signal_trade_performance table
2. Link trade → signal metadata (base_type, SQS, trend_score, stage, etc.)
3. Calculate realized P&L, R-multiple, hold duration
4. Record which targets were hit

Enable queries like:
- Win rate by base type: Cups 85%, Flat 70%, Double 60%
- Avg R by swing score: SQS 80+ avg 1.5R, SQS 60-79 avg 0.8R
- Best sector: Tech 80% win rate
"""

class TradePerformanceAuditor:
    def __init__(self, config):
        self.config = config
        self.conn = None
    
    def audit_exit(self, trade_id):
        """Called when a position exits. Populate signal_trade_performance."""
        self.connect()
        
        # Fetch trade record
        self.cur.execute("""
            SELECT id, symbol, signal_date, entry_price, entry_quantity,
                   stop_loss_price, exit_date, exit_price,
                   profit_loss_dollars, profit_loss_pct
            FROM algo_trades WHERE id = %s
        """, (trade_id,))
        trade = self.cur.fetchone()
        if not trade:
            return
        
        tid, symbol, sig_date, entry, qty, stop, exit_date, exit_price, pnl, pnl_pct = trade
        
        # Fetch signal metadata (from buy_sell_daily, signal_quality_scores, etc.)
        self.cur.execute("""
            SELECT 
                bsd.base_type, bsd.entry_price,
                sqs.composite_sqs,
                sts.score, sts.components->>'grade' as grade,
                tmt.minervini_trend_score, tmt.weinstein_stage,
                ss.sector,
                st.relative_strength_group, st.correlation_to_spy
            FROM buy_sell_daily bsd
            LEFT JOIN signal_quality_scores sqs ON bsd.symbol = sqs.symbol AND bsd.date = sqs.date
            LEFT JOIN swing_trader_scores sts ON bsd.symbol = sts.symbol AND bsd.date = sts.date
            LEFT JOIN trend_template_data tmt ON bsd.symbol = tmt.symbol AND bsd.date = tmt.date
            LEFT JOIN stock_symbols ss ON bsd.symbol = ss.symbol
            LEFT JOIN signal_themes st ON bsd.symbol = st.symbol AND bsd.date = st.date
            WHERE bsd.symbol = %s AND bsd.date = %s AND bsd.signal = 'BUY'
            LIMIT 1
        """, (symbol, sig_date))
        sig_meta = self.cur.fetchone()
        
        if not sig_meta:
            return  # No signal metadata
        
        base_type, entry_sig, sqs, swing, grade, trend, stage, sector, rs_group, corr_spy = sig_meta
        
        # Compute R-multiple
        if stop and entry and exit_price:
            risk = entry - stop
            realized = exit_price - entry
            r_mult = realized / risk if risk > 0 else 0
        else:
            r_mult = 0
        
        # Determine which targets were hit
        self.cur.execute("""
            SELECT target_1_price, target_2_price, target_3_price
            FROM algo_trades WHERE id = %s
        """, (trade_id,))
        targets = self.cur.fetchone()
        t1, t2, t3 = targets if targets else (None, None, None)
        
        target_1_hit = exit_price >= t1 if t1 else False
        target_2_hit = exit_price >= t2 if t2 else False
        target_3_hit = exit_price >= t3 if t3 else False
        
        # Compute hold duration
        hold_days = (exit_date - sig_date).days if exit_date and sig_date else 0
        
        # Insert signal_trade_performance
        self.cur.execute("""
            INSERT INTO signal_trade_performance
            (trade_id, symbol, signal_date, entry_price, base_type, sqs, swing_score,
             swing_grade, trend_score, stage_at_entry, sector, rs_percentile,
             exit_price, exit_date, hold_days, realized_pnl, realized_pnl_pct,
             r_multiple, win, target_1_hit, target_2_hit, target_3_hit)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (trade_id) DO UPDATE SET
                exit_price = EXCLUDED.exit_price,
                realized_pnl = EXCLUDED.realized_pnl,
                realized_pnl_pct = EXCLUDED.realized_pnl_pct,
                r_multiple = EXCLUDED.r_multiple,
                win = EXCLUDED.win,
                updated_at = NOW()
        """, (trade_id, symbol, sig_date, entry, base_type, sqs, swing, grade, trend,
              stage, sector, rs_group, exit_price, exit_date, hold_days, pnl, pnl_pct,
              r_mult, pnl > 0, target_1_hit, target_2_hit, target_3_hit))
        
        self.conn.commit()
        self.disconnect()
```

**Integration Point**: Call in `algo_exit_engine.py` after exiting a position:
```python
def check_and_execute_exits(self, eval_date):
    # ... existing exit logic ...
    
    # === NEW: Audit trade performance ===
    auditor = TradePerformanceAuditor(self.config)
    for exit_result in exited_trades:
        if exit_result['success']:
            auditor.audit_exit(exit_result['trade_id'])
    # === END: Audit performance ===
```

---

### Layer 3: Filter Rejection Tracker
**File**: `filter_rejection_tracker.py` (NEW)

```python
#!/usr/bin/env python3
"""
Filter Pipeline Rejection Tracking

Logs every signal through all 5 tiers + advanced filters.
Captures rejection reason at each tier for explainability.

Enables:
- Rejection funnel analysis
- Per-gate rejection counts
- Time-based rejection patterns
- Tuning feedback (if we loosen Tier 2, how many extra signals?)
"""

class RejectionTracker:
    def __init__(self):
        self.conn = None
    
    def log_rejection(self, eval_date, symbol, entry_price,
                      tier_results, advanced_results=None):
        """
        Log signal rejection with reason at each tier.
        
        Args:
            tier_results: dict {
                1: {'pass': bool, 'reason': '...'},
                2: {'pass': bool, 'reason': '...'},
                ...
            }
        """
        self.connect()
        
        # Find which tier rejected it
        rejected_tier = None
        for tier in [1, 2, 3, 4, 5]:
            if not tier_results.get(tier, {}).get('pass', False):
                rejected_tier = tier
                break
        
        # Build rejection log entry
        self.cur.execute("""
            INSERT INTO filter_rejection_log
            (eval_date, symbol, entry_price, rejected_at_tier,
             rejection_reason, tier_1_pass, tier_2_pass, tier_2_reason,
             tier_3_pass, tier_3_reason, tier_4_pass, tier_4_reason,
             tier_5_pass, tier_5_reason, advanced_checks_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            eval_date, symbol, entry_price, rejected_tier,
            tier_results.get(rejected_tier, {}).get('reason', 'Unknown'),
            tier_results.get(1, {}).get('pass', False),
            tier_results.get(2, {}).get('pass', False),
            tier_results.get(2, {}).get('reason', ''),
            tier_results.get(3, {}).get('pass', False),
            tier_results.get(3, {}).get('reason', ''),
            tier_results.get(4, {}).get('pass', False),
            tier_results.get(4, {}).get('reason', ''),
            tier_results.get(5, {}).get('pass', False),
            tier_results.get(5, {}).get('reason', ''),
            advanced_results.get('reason', '') if advanced_results else ''
        ))
        
        self.conn.commit()
        self.disconnect()
    
    def get_rejection_funnel(self, eval_date):
        """
        Get rejection counts by tier for funnel chart.
        
        Returns:
        {
            'total_signals': 150,
            'tier_1': {'pass': 100, 'reject': 50},
            'tier_2': {'pass': 80, 'reject': 20},
            ...
        }
        """
        self.connect()
        
        self.cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN tier_1_pass THEN 1 ELSE 0 END) as t1_pass,
                SUM(CASE WHEN tier_2_pass THEN 1 ELSE 0 END) as t2_pass,
                SUM(CASE WHEN tier_3_pass THEN 1 ELSE 0 END) as t3_pass,
                SUM(CASE WHEN tier_4_pass THEN 1 ELSE 0 END) as t4_pass,
                SUM(CASE WHEN tier_5_pass THEN 1 ELSE 0 END) as t5_pass
            FROM filter_rejection_log
            WHERE eval_date = %s
        """, (eval_date,))
        
        row = self.cur.fetchone()
        total, t1, t2, t3, t4, t5 = row
        
        result = {
            'total_signals': total,
            'tier_1': {'pass': t1 or 0, 'reject': (total - (t1 or 0))},
            'tier_2': {'pass': t2 or 0, 'reject': ((t1 or 0) - (t2 or 0))},
            'tier_3': {'pass': t3 or 0, 'reject': ((t2 or 0) - (t3 or 0))},
            'tier_4': {'pass': t4 or 0, 'reject': ((t3 or 0) - (t4 or 0))},
            'tier_5': {'pass': t5 or 0, 'reject': ((t4 or 0) - (t5 or 0))},
        }
        
        self.disconnect()
        return result
```

**Integration Point**: In `algo_filter_pipeline.py.evaluate_signals()`:
```python
def evaluate_signals(self, eval_date=None):
    # ... existing evaluation loop ...
    
    tracker = RejectionTracker()
    for symbol, signal_date, _signal, entry_price in signals:
        # ... tier evaluation ...
        
        # === NEW: Track rejection ===
        tracker.log_rejection(eval_date, symbol, entry_price, tier_results)
        # === END: Track rejection ===
```

---

### Layer 4: Order Execution Tracker
**File**: `order_execution_tracker.py` (NEW)

```python
#!/usr/bin/env python3
"""
Order Execution Audit Trail

Tracks every order attempt:
- Pre-execution: What are we about to trade?
- Execution: Did the order fill?
- Post-execution: What was the slippage?

Enables:
- Pre-execution dashboard (approve before submitting)
- Order audit trail (why did this order reject?)
- Fill quality analysis (avg slippage, fill rate)
"""

class OrderExecutionTracker:
    def __init__(self, config):
        self.config = config
        self.conn = None
    
    def log_order_attempt(self, trade_id, symbol, order_type, side,
                          requested_shares, requested_price, alpaca_order_id):
        """Log a new order being sent to Alpaca."""
        self.connect()
        
        self.cur.execute("""
            SELECT COUNT(*) FROM order_execution_log
            WHERE trade_id = %s AND order_type = %s
        """, (trade_id, order_type))
        attempt_num = self.cur.fetchone()[0] + 1
        
        self.cur.execute("""
            INSERT INTO order_execution_log
            (trade_id, symbol, order_sequence_num, order_timestamp, order_type,
             side, requested_shares, requested_price, order_status, alpaca_order_id)
            VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, 'pending', %s)
        """, (trade_id, symbol, attempt_num, order_type, side, requested_shares,
              requested_price, alpaca_order_id))
        
        self.conn.commit()
        self.disconnect()
    
    def log_order_fill(self, alpaca_order_id, filled_shares, filled_price, status):
        """Log order result (filled, partial, rejected, etc.)."""
        self.connect()
        
        # Fetch original request
        self.cur.execute("""
            SELECT id, requested_price, requested_shares, side
            FROM order_execution_log
            WHERE alpaca_order_id = %s
            ORDER BY id DESC LIMIT 1
        """, (alpaca_order_id,))
        
        order = self.cur.fetchone()
        if not order:
            return
        
        order_id, req_price, req_shares, side = order
        
        # Calculate metrics
        fill_rate = (filled_shares / req_shares * 100) if req_shares > 0 else 0
        if side == 'BUY':
            slippage_bps = (filled_price - req_price) / req_price * 10000
        else:
            slippage_bps = (req_price - filled_price) / req_price * 10000
        
        # Update order log
        self.cur.execute("""
            UPDATE order_execution_log SET
                order_status = %s,
                filled_shares = %s,
                filled_price = %s,
                fill_rate_pct = %s,
                slippage_bps = %s
            WHERE alpaca_order_id = %s
        """, (status, filled_shares, filled_price, fill_rate, slippage_bps, alpaca_order_id))
        
        self.conn.commit()
        
        # Alert if slippage excessive
        if abs(slippage_bps) > 300:  # 3% is bad
            print(f"[ALERT] High slippage on {alpaca_order_id}: {slippage_bps:.0f}bps")
        
        self.disconnect()
    
    def get_pending_orders(self):
        """Fetch all pending/submitted orders (for pre-execution review)."""
        self.connect()
        
        self.cur.execute("""
            SELECT id, trade_id, symbol, order_type, side, requested_shares,
                   requested_price, order_timestamp
            FROM order_execution_log
            WHERE order_status IN ('pending', 'submitted')
            ORDER BY order_timestamp DESC
        """)
        
        orders = self.cur.fetchall()
        self.disconnect()
        return orders
    
    def get_execution_quality_metrics(self, days=30):
        """Summary: fill rate, avg slippage, rejection count."""
        self.connect()
        
        self.cur.execute("""
            SELECT
                COUNT(*) as total_orders,
                SUM(CASE WHEN order_status = 'filled' THEN 1 ELSE 0 END) as filled,
                SUM(CASE WHEN order_status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                AVG(fill_rate_pct) as avg_fill_rate,
                AVG(ABS(slippage_bps)) as avg_slippage_bps
            FROM order_execution_log
            WHERE order_timestamp >= NOW() - INTERVAL %s
        """, (f'{days} days',))
        
        row = self.cur.fetchone()
        self.disconnect()
        
        return {
            'total_orders': row[0],
            'filled': row[1],
            'rejected': row[2],
            'fill_rate_pct': row[3],
            'avg_slippage_bps': row[4],
        }
```

**Integration Point 1**: Before executing, show pre-execution review:
```python
def execute_trade(self, symbol, entry_price, shares, ...):
    tracker = OrderExecutionTracker(self.config)
    
    # === NEW: Pre-execution review ===
    print("About to submit orders:")
    for trade in trades_to_enter:  # Show next 3 trades
        print(f"  {trade['symbol']} {trade['shares']}sh @ ${trade['entry_price']}")
    # === END: Pre-execution review ===
    
    # ... actual execution ...
    
    # === NEW: Log order attempt ===
    tracker.log_order_attempt(trade_id, symbol, 'entry', 'BUY', shares, entry_price, alpaca_order_id)
    # === END: Log attempt ===
```

**Integration Point 2**: After Alpaca fills the order:
```python
# In _verify_order_status() or after order fill confirmation
tracker.log_order_fill(alpaca_order_id, filled_shares, fill_price, 'filled')
```

---

## Phase 3: API Endpoints for UI (2-3 hours)

### New API Routes (add to webapp/lambda/routes/)

#### GET /api/algo/data-quality
```javascript
// Returns SLA status per loader
{
  "status": "ok|warning|critical",
  "checks": [
    {
      "loader": "price_daily",
      "table": "price_daily",
      "latest_date": "2026-05-05",
      "age_hours": 8,
      "max_age_hours": 16,
      "status": "OK",
      "row_count": 4965
    },
    {
      "loader": "market_health_daily",
      "status": "CRITICAL",
      "latest_date": "2026-05-03",
      "age_hours": 48,
      "max_age_hours": 24,
      "reason": "Market health loader failed 3 days ago"
    }
  ]
}
```

#### GET /api/algo/rejection-funnel?date=2026-05-06
```javascript
// Rejection funnel visualization
{
  "date": "2026-05-06",
  "total_signals": 150,
  "tiers": [
    { "tier": 1, "name": "Data Quality", "pass": 100, "reject": 50 },
    { "tier": 2, "name": "Market Health", "pass": 80, "reject": 20 },
    { "tier": 3, "name": "Trend Confirmation", "pass": 40, "reject": 40 },
    { "tier": 4, "name": "Signal Quality", "pass": 15, "reject": 25 },
    { "tier": 5, "name": "Portfolio Health", "pass": 10, "reject": 5 }
  ]
}
```

#### GET /api/algo/signal-performance?days=90&base_type=Cup
```javascript
// Trade performance by signal attributes
{
  "period": "last 90 days",
  "filters": { "base_type": "Cup" },
  "trades": [
    {
      "trade_id": 123,
      "symbol": "AAPL",
      "signal_date": "2026-04-15",
      "base_type": "Cup",
      "sqs": 85,
      "swing_grade": "A+",
      "entry_price": 150.00,
      "exit_price": 157.50,
      "realized_pnl": 750,
      "r_multiple": 1.67,
      "win": true,
      "target_1_hit": true,
      "target_2_hit": false
    }
  ],
  "summary": {
    "total_trades": 12,
    "wins": 10,
    "losses": 2,
    "win_rate_pct": 83.3,
    "avg_r_multiple": 1.4,
    "best_signal": "Cup w/ Handle (3/3 wins, avg 2.1R)"
  }
}
```

#### GET /api/algo/orders/pending
```javascript
// Pre-execution order review
{
  "pending_orders": [
    {
      "symbol": "AAPL",
      "order_type": "entry",
      "side": "BUY",
      "requested_shares": 100,
      "requested_price": 150.00,
      "order_timestamp": "2026-05-06T09:30:00Z",
      "trade_id": 123,
      "sqs": 85,
      "base_type": "Cup"
    }
  ],
  "total_pending_value": 15000,
  "approval_required": true
}
```

#### GET /api/algo/execution-quality
```javascript
// Execution metrics (fill rate, slippage, etc.)
{
  "period": "last 30 days",
  "total_orders": 45,
  "filled": 44,
  "rejected": 1,
  "fill_rate_pct": 97.8,
  "avg_slippage_bps": 12.5,
  "slippage_alert": false
}
```

---

## Phase 4: Frontend Integration (3-4 hours)

### New Dashboard Pages/Sections

#### 1. Data Quality Monitor (Top-level alert)
```jsx
// DashboardDataQuality.jsx
- Alert banner if any SLA violated
- Per-loader status table
- Last load timestamp + age indicator
- Auto-refresh every 5 minutes
```

#### 2. Rejection Funnel Chart
```jsx
// RejectionFunnel.jsx
- Horizontal bar chart: Tier 1 → Tier 2 → ... → Qualified
- Color-coded by rejection rate
- Hover: see rejection reasons (e.g., "Distribution days 5 > 4")
- Key metric: "150 signals → 8 qualified (5.3%)"
```

#### 3. Signal Performance Analytics
```jsx
// SignalPerformanceAnalytics.jsx (new page)
- Table: All closed trades with P&L, R-multiple, base type, SQS
- Filters: Base type, SQS range, Win/Loss, Sector
- Graphs:
  - Win rate by base type (bar chart)
  - Avg R by swing score (scatter)
  - Best performing sector (pie)
  - Distribution of hold days (histogram)
- CSV export
```

#### 4. Order Execution Dashboard
```jsx
// OrderExecutionDashboard.jsx (new panel)
- Pending orders (if any) with "APPROVE" button
- Recent order audit trail (filled, rejected, partial)
- Execution quality metrics (fill rate, slippage)
- Alert: If slippage > 100bps on any recent order
```

#### 5. Enhance TradingSignals.jsx
```jsx
// Add to existing page:
- "P&L Performance" tab showing historical returns
- "Data Quality" banner at top
- Link to rejection funnel ("See why 90% were filtered")
```

---

## Phase 5: Integration Points (Modify Existing Files)

### algo_run_daily.py
```python
def run_algo_workflow(eval_date=None):
    """Run complete daily algo workflow."""
    
    # ===== PHASE 1: Data Quality Gate (NEW) =====
    print(f"\n{'='*70}")
    print("PHASE 0: DATA QUALITY VALIDATION")
    print(f"{'='*70}\n")
    
    validator = DataQualityValidator(config)
    all_pass, failures = validator.validate_all(eval_date)
    if not all_pass:
        print(f"❌ DATA SLA VIOLATIONS:\n  {chr(10).join(failures)}")
        alert_manager.alert('CRITICAL', f'Data SLA violated: {failures[0]}')
        return {'status': 'data_sla_blocked', 'failures': failures}
    # ===== END: Data Quality Gate =====
    
    # ... existing workflow ...
```

### algo_filter_pipeline.py
```python
def evaluate_signals(self, eval_date=None):
    # ... existing code ...
    
    tracker = RejectionTracker()  # ===== NEW =====
    
    for symbol, signal_date, _signal, entry_price in signals:
        result = self.evaluate_signal(symbol, signal_date, float(entry_price))
        
        # ===== NEW: Log rejection =====
        if not result['passed_all_tiers']:
            tier_results = {i: result['tiers'][i] for i in range(1, 6)}
            tracker.log_rejection(eval_date, symbol, entry_price, tier_results)
        # ===== END: Log rejection =====
        
        # ... rest of eval ...
```

### algo_trade_executor.py
```python
def execute_trade(self, ...):
    # ===== NEW: Order tracking =====
    order_tracker = OrderExecutionTracker(self.config)
    # ===== END: Order tracking =====
    
    # ... validation ...
    
    # Before Alpaca order:
    order_tracker.log_order_attempt(trade_id, symbol, 'entry', 'BUY', shares, entry_price, order_id)
    
    # After Alpaca fill:
    order_tracker.log_order_fill(order_id, filled_shares, filled_price, 'filled')
    
    # ... rest of entry ...
```

### algo_exit_engine.py
```python
def check_and_execute_exits(self, eval_date):
    # ... existing code ...
    
    # ===== NEW: Performance audit =====
    auditor = TradePerformanceAuditor(self.config)
    # ===== END: Performance audit =====
    
    for exit_result in exited_trades:
        if exit_result['success']:
            auditor.audit_exit(exit_result['trade_id'])  # ===== NEW =====
```

---

## Implementation Schedule

| Phase | Task | Time | Start | End |
|-------|------|------|-------|-----|
| 1 | Add 4 new DB tables | 1h | Day 1 | Day 1 |
| 2a | DataQualityValidator module | 2h | Day 1 | Day 1 |
| 2b | TradePerformanceAuditor module | 3h | Day 1-2 | Day 2 |
| 2c | RejectionTracker module | 2h | Day 2 | Day 2 |
| 2d | OrderExecutionTracker module | 2h | Day 2-3 | Day 3 |
| 3 | API endpoints (5 new routes) | 2h | Day 3 | Day 3 |
| 4 | Frontend components (5 new) | 4h | Day 3-4 | Day 4 |
| 5 | Integration into existing code | 2h | Day 4 | Day 4 |
| **TOTAL** | | **18-20h** | | **4-5 Days** |

---

## Testing & Validation

### Unit Tests
```bash
pytest tests/unit/test_data_quality_validator.py
pytest tests/unit/test_trade_performance_auditor.py
pytest tests/unit/test_rejection_tracker.py
pytest tests/unit/test_order_execution_tracker.py
```

### Integration Tests
```bash
# Run full workflow on test data
python algo_run_daily.py --test-mode --eval-date 2026-04-01
# Verify: all 4 new tables populated
# Verify: no data quality blocks (prices recent)
# Verify: rejection log has 1000+ records
# Verify: signal_trade_performance populated for closed trades
```

### E2E Test (UI)
1. Open Dashboard → check "Data Quality" banner
2. Navigate to TradingSignals → click "Rejection Funnel"
3. Check Signal Performance Analytics (if trades exist)
4. Check Order Execution Dashboard (pending orders, exec metrics)

---

## Success Criteria

✅ Data quality SLA enforced before algo runs  
✅ Every trade linked back to its signal + metadata  
✅ Win rate calculable by base type, SQS, stage, sector  
✅ Every signal rejection logged with reason  
✅ Rejection funnel visualized in UI  
✅ Every order attempt audited (log, fill, slippage)  
✅ Pre-execution review dashboard functional  
✅ Execution quality metrics (fill rate, slippage) visible  
✅ All existing pipelines still work (backward compatible)  
✅ No disruption to paper trading schedule  

---

## Notes

- **Backward Compatibility**: All changes are additive. Existing code unaffected.
- **Performance**: New tables indexed. Queries <100ms.
- **Privacy**: Audit logs contain only signals/trades/orders (no PII).
- **Cost**: Negligible. 4 new tables ≈ <1GB storage over 12 months.
- **Maintenance**: Each module is self-contained. Easy to debug/extend.

---

**Status**: Ready to implement. Let's build this in phases.
