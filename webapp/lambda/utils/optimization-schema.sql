-- Portfolio Optimization History & Tracking Schema

-- Store optimization analysis runs
CREATE TABLE IF NOT EXISTS optimization_runs (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(255) NOT NULL,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  -- Portfolio State at Analysis Time
  total_value DECIMAL(15, 2),
  holdings_count INT,

  -- Metrics
  beta DECIMAL(5, 2),
  alpha DECIMAL(8, 4),
  sharpe_ratio DECIMAL(5, 2),
  sortino_ratio DECIMAL(5, 2),
  volatility DECIMAL(6, 4),
  concentration DECIMAL(5, 3),
  avg_quality DECIMAL(5, 1),

  -- Issues Summary
  issues_count INT,
  issues_json JSONB,

  -- Recommendations Generated
  recommendations_count INT,
  recommendations_json JSONB,

  -- Expected Improvements
  improvements_json JSONB,

  -- Execution Status
  status VARCHAR(50) DEFAULT 'generated', -- generated, partially_executed, fully_executed
  executed_at TIMESTAMP,
  executed_count INT DEFAULT 0,

  -- Raw Response (for full context)
  full_analysis JSONB,

  -- Metadata
  notes TEXT,
  CREATED_BY VARCHAR(50) DEFAULT 'system',

  INDEX idx_user_timestamp (user_id, timestamp DESC),
  INDEX idx_status (status),
  INDEX idx_created (created_at)
);

-- Track individual trade executions from recommendations
CREATE TABLE IF NOT EXISTS optimization_trades (
  id SERIAL PRIMARY KEY,
  optimization_run_id INT NOT NULL REFERENCES optimization_runs(id) ON DELETE CASCADE,

  -- Recommendation Details
  recommendation_id INT,
  action VARCHAR(10), -- BUY, SELL
  symbol VARCHAR(10),
  reason TEXT,
  priority VARCHAR(20),
  target_weight DECIMAL(5, 3),
  quantity INT,

  -- Execution Details
  order_id VARCHAR(255),
  alpaca_status VARCHAR(50), -- pending, filled, partial, rejected
  executed_at TIMESTAMP,
  executed_price DECIMAL(10, 2),
  executed_quantity INT,
  filled_percentage DECIMAL(5, 2),

  -- Outcome
  order_cost DECIMAL(15, 2), -- actual cost of execution
  slippage DECIMAL(8, 4), -- difference from recommended price
  notes TEXT,

  -- Tracking
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  INDEX idx_optimization_run (optimization_run_id),
  INDEX idx_symbol (symbol),
  INDEX idx_alpaca_status (alpaca_status)
);

-- Track metric changes over time
CREATE TABLE IF NOT EXISTS optimization_metrics_history (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(255) NOT NULL,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  beta DECIMAL(5, 2),
  alpha DECIMAL(8, 4),
  sharpe_ratio DECIMAL(5, 2),
  sortino_ratio DECIMAL(5, 2),
  volatility DECIMAL(6, 4),
  concentration DECIMAL(5, 3),
  total_value DECIMAL(15, 2),
  holdings_count INT,

  INDEX idx_user_timestamp (user_id, timestamp DESC)
);

-- Track recommendation outcomes
CREATE TABLE IF NOT EXISTS recommendation_outcomes (
  id SERIAL PRIMARY KEY,
  optimization_run_id INT NOT NULL REFERENCES optimization_runs(id) ON DELETE CASCADE,
  trade_id INT REFERENCES optimization_trades(id),

  symbol VARCHAR(10),
  recommended_action VARCHAR(10),
  recommended_price DECIMAL(10, 2),

  -- Actual Results
  actual_price_today DECIMAL(10, 2),
  price_change_pct DECIMAL(6, 2),

  -- Recommendation Quality
  was_correct BOOLEAN, -- Did recommendation improve portfolio metrics?
  actual_outcome_score DECIMAL(5, 2),

  -- Analysis
  holding_current_price DECIMAL(10, 2),
  holding_quantity INT,
  position_value DECIMAL(15, 2),
  unrealized_gain DECIMAL(15, 2),
  unrealized_gain_pct DECIMAL(6, 2),

  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  INDEX idx_optimization_run (optimization_run_id),
  INDEX idx_symbol (symbol),
  INDEX idx_created (created_at)
);
