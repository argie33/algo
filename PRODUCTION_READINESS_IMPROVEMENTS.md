# Production Readiness Improvements — Real Money Trading Audit

## Summary

This document tracks the improvements made to ensure the swing trading algo is production-ready for real money deployment.

**Status**: 🟡 **In Progress** — Infrastructure complete, integration pending

---

## Improvements Implemented

### 1. ✅ Enhanced Audit Logging System (`algo/algo_trade_audit_logger.py`)

**Purpose**: Log every trade decision with complete reasoning for audit trail.

**What's logged**:
- **Position Sizing Audit**: Why each position was sized as it was
  - Base risk calculation
  - Cascade multipliers (drawdown, exposure tier, VIX, phase)
  - Final position size as % of portfolio
  - All multipliers and their reasons

- **Stop Loss Audit**: Why each stop was chosen
  - Candidates considered (SMA-50, swing low 10d, 2×ATR)
  - Which candidate was chosen and why
  - Distance from entry (%)
  - Fallback vs base-type stop

- **Exit Rules Distribution**: Which exits fire most
  - Rule name (STOP, T1, T2, TIME, MINERVINI_BREAK, etc.)
  - P&L outcome
  - R-multiple achieved
  - Win rate by exit rule

**API Methods**:
```python
audit = TradeAuditLogger()
audit.log_position_sizing_audit(
    symbol, signal_date, entry, stop_loss,
    base_shares, final_shares, position_pct,
    multipliers_dict, reasons_dict
)
audit.log_stop_loss_calculation(
    symbol, signal_date, entry, stop_loss,
    method, reasoning, candidates_dict
)
audit.log_exit_execution(
    symbol, position_id, exit_reason, exit_rule,
    entry, exit_price, pnl_dollars, pnl_pct, r_multiple
)
```

---

### 2. ✅ Database Schema Extensions (`terraform/modules/database/init.sql`)

Added 3 new audit tables for production visibility:

**`algo_position_sizing_audit`**
- Tracks every position sizing decision
- Fields: symbol, signal_date, entry_price, stop_loss_price, base_shares, final_shares, position_size_pct, cascade_multiplier, multipliers_json, reasons_json
- Indexes: (symbol, signal_date), (created_at DESC)
- **Diagnostic**: Why were some positions sized much smaller than expected?

**`algo_stop_loss_audit`**
- Tracks every stop loss calculation
- Fields: symbol, signal_date, entry_price, stop_loss_price, distance_pct, stop_method, stop_reasoning, candidates_json
- Indexes: (symbol, signal_date), (created_at DESC)
- **Diagnostic**: Are stops being chosen correctly? Are swing lows too tight?

**`algo_exit_rules_distribution`**
- Tracks which exit rules fire and how profitable each is
- Fields: symbol, position_id, exit_rule, exit_reason, entry_price, exit_price, pnl_dollars, pnl_pct, r_multiple
- Indexes: (created_at DESC), (exit_rule, created_at DESC)
- **Diagnostic**: Which exit rule drives most wins? Are we exiting too early?

---

### 3. ✅ Frontend Risk Display API (`lambda/api/routes/risk_dashboard.py`)

New API endpoints for real-time risk visibility:

**`/api/algo/risk-dashboard`** — Comprehensive view
```json
{
  "timestamp": "2026-05-25T14:30:00",
  "drawdown": {
    "current_drawdown_pct": 3.5,
    "peak_portfolio_value": 100000,
    "current_portfolio_value": 96500,
    "status": "NORMAL",
    "thresholds": {...},
    "risk_multipliers": {...}
  },
  "exposure_tier": {
    "current_tier": "CAUTION",
    "exposure_pct": 75,
    "rationale": "Drawdown at -5% to -10%",
    "position_size_multiplier": 0.75
  },
  "vix_metrics": {
    "vix_level": 28.5,
    "caution_threshold": 25.0,
    "halt_threshold": 35.0,
    "risk_reduction_multiplier": 0.75
  },
  "position_sizing_stats": {
    "trades_30d": 12,
    "avg_cascade_multiplier": 0.85,
    "avg_position_size_pct": 3.2
  },
  "exit_rules_distribution": {
    "T1": 4,
    "STOP": 3,
    "T2": 2
  }
}
```

**`/api/algo/risk-dashboard/drawdown`** — Drawdown details
**`/api/algo/risk-dashboard/exposure-tier`** — Current tier and multiplier
**`/api/algo/risk-dashboard/position-sizing-audit?days=30`** — Why trades were sized
**`/api/algo/risk-dashboard/stop-loss-audit?days=30`** — Why stops were chosen
**`/api/algo/risk-dashboard/exit-rules?days=30`** — Exit rule performance

---

### 4. 🟡 Filter Pipeline Integration (Partial)

**Modified**: `algo/algo_filter_pipeline.py`
- Updated `_compute_stop_loss()` to return full dict with method, reasoning, candidates
- Added audit logging call after stop loss calculation
- Stop loss decision now fully traceable

**Still needed**:
- Integration into position sizer (log multiplier cascade)
- Integration into exit engine (log which exit rule fires)

---

## What This Enables

### For You (Trading Perspective)
✅ **Complete audit trail**: Every position shows exactly why it was sized as it was
✅ **Risk visibility**: Dashboard shows current drawdown, exposure tier, VIX risk reduction
✅ **Exit diagnostics**: See which exit rules actually work (win rate by rule)
✅ **Stop validation**: Verify stops are reasonable and not too tight
✅ **Cascade transparency**: Understand how multipliers cascade (1.0 → 0.75 × 0.5 × 0.75 = 0.28x)

### For Real Money Deployment
✅ **Compliance ready**: Complete audit trail of all decisions
✅ **Performance tracking**: Exit rule distribution shows which strategies work
✅ **Risk management**: Visual dashboard of drawdown, exposure, VIX
✅ **Debugging**: Answer "why was this trade sized so small?" in seconds
✅ **Learning**: Identify patterns (e.g., "time-based exits have worse win rate than target exits")

---

## Remaining Integration Tasks

### Priority 1: Position Sizer Integration
**File**: `algo/algo_position_sizer.py`

Add audit logging after calculating final shares:

```python
from algo.algo_trade_audit_logger import TradeAuditLogger

# After calculate_position_size() returns shares
final_shares = sizer.calculate_position_size(...)
audit = TradeAuditLogger()
audit.log_position_sizing_audit(
    symbol=symbol,
    signal_date=signal_date,
    entry_price=entry_price,
    stop_loss_price=stop_loss_price,
    base_shares=shares_before_multipliers,
    final_shares=final_shares['shares'],
    position_size_pct=...,
    multipliers={
        'base_risk_pct': 0.0075,
        'drawdown_adjustment': dd_multiplier,
        'exposure_tier_multiplier': exposure_mult,
        'vix_caution_multiplier': vix_mult,
        'phase_multiplier': phase_mult,
    },
    reasons={
        'drawdown_adjustment': f'At {drawdown_pct:.1f}% drawdown',
        'exposure_tier_multiplier': f'{exposure_tier} tier',
        'vix_caution_multiplier': f'VIX {vix_level:.1f}',
        'phase_multiplier': f'{phase} phase',
    },
)
```

**Impact**: Positions dashboard can show "Position sized at X% because: drawdown -10% (0.5x), VIX 28 (0.75x), CAUTION tier (0.75x) = 28% of intended size"

---

### Priority 2: Exit Engine Integration
**File**: `algo/algo_exit_engine.py`

Add audit logging when exits execute:

```python
from algo.algo_trade_audit_logger import TradeAuditLogger

# When exit_rule fires:
audit = TradeAuditLogger()
audit.log_exit_execution(
    symbol=symbol,
    position_id=position_id,
    exit_reason=f'Price crossed T1 target at ${t1_price:.2f}',
    exit_rule='T1',
    entry_price=entry_price,
    exit_price=exit_price,
    pnl_dollars=pnl_dollars,
    pnl_pct=pnl_pct,
    r_multiple=r_multiple,
)
```

**Impact**: Exit rules dashboard shows "T1 (4 exits): avg P&L +1.8%, win rate 75%" helping you identify which rules work best.

---

### Priority 3: Frontend Display Component
**File**: `webapp/frontend/src/pages/AlgoTradingDashboard.jsx`

Add new "Risk Metrics" tab using risk-dashboard API:

```jsx
const { data: riskMetrics } = useApiQuery(['algo','risk'], 
  () => api.get('/api/algo/risk-dashboard'), 
  { refetchInterval: 30000 }
);

return (
  <Tab label="Risk Metrics">
    <RiskMetricsDisplay data={riskMetrics} />
  </Tab>
);
```

Components needed:
- DrawdownIndicator: Shows current drawdown % with thresholds
- ExposureTierBadge: Shows NORMAL/CAUTION/PRESSURE tier
- VIXIndicator: Shows current VIX with caution/halt zones
- PositionSizingAudit: Expandable list of why each trade was sized
- StopLossAudit: Expandable list of why stops were chosen
- ExitRulesChart: Bar chart of exit rule frequency and win rate

---

## Database Migration

To apply schema changes:

```bash
# Option 1: Via Terraform (automatic on next deploy)
cd terraform
terraform apply

# Option 2: Direct SQL (for quick testing)
psql -U $DB_USER -h $DB_HOST -d $DB_NAME -f terraform/modules/database/init.sql
```

---

## Testing Checklist Before Live Trading

- [ ] Run 1 week of paper trading
- [ ] Verify position sizing audit shows cascade multipliers
- [ ] Verify stop loss audit shows reasonable stops (not < 1% below entry)
- [ ] Check exit rules distribution (should see mix of exits, not all one rule)
- [ ] Verify drawdown dashboard updates correctly after first losing trade
- [ ] Test exposure tier changes (manually trigger -5% drawdown in test)
- [ ] Confirm frontend displays all risk metrics without errors

---

## Config Validation for Real Money

**Critical Config Parameters** (verify before deploying):

```python
# In algo/algo_config.py or database config table:

# Risk Management
'base_risk_pct': 0.75                    # 0.75% per trade
'max_positions': 3                       # Start with 3 max
'max_position_size_pct': 8.0            # 8% max per position

# Stop Loss
'max_stop_distance_pct': 8.0            # 8% max distance from entry
't1_target_r_multiple': 1.5             # 1.5R for first target
't2_target_r_multiple': 3.0             # 3R for second target
't3_target_r_multiple': 4.0             # 4R for third target

# Drawdown Defense
'halt_drawdown_pct': 20.0               # Halt at -20%
'risk_reduction_at_minus_15': 0.25      # 25% of position size at -15%
'risk_reduction_at_minus_10': 0.5       # 50% of position size at -10%
'risk_reduction_at_minus_5': 0.75       # 75% of position size at -5%

# Circuit Breakers
'max_daily_loss_pct': 2.0               # Halt if -2% in one session
'max_consecutive_losses': 3             # Halt after 3 losing trades
'vix_max_threshold': 35.0               # Halt if VIX > 35
'vix_caution_threshold': 25.0           # 25% risk reduction if VIX 25-35

# Entry Quality
'min_trend_template_score': 6           # Minervini score >= 6/8
'min_swing_score': 55                   # Swing trader score >= 55
'max_percent_from_52w_high': 25.0       # Can't be > 25% from highs
'min_percent_from_52w_low': 25.0        # Must be > 25% from lows

# Exit Timing
'max_hold_days': 20                     # Max 20 days in position
'min_hold_days': 1                      # Min 1 day (don't exit same day)
```

---

## Deployment Checklist

- [ ] Database migrations applied (audit tables created)
- [ ] `algo_trade_audit_logger.py` deployed to Lambda
- [ ] API routes updated (`api_router.py` imports risk_dashboard)
- [ ] Risk dashboard endpoints active at `/api/algo/risk-dashboard/*`
- [ ] Position sizer integrated with TradeAuditLogger
- [ ] Exit engine integrated with TradeAuditLogger
- [ ] Frontend Risk Metrics tab added and operational
- [ ] Paper trading validates all audit logging works
- [ ] Config values validated for account size
- [ ] All circuit breakers tested (manually trigger at least 2)
- [ ] Alerts configured (Slack/email for drawdown thresholds)

---

## Next Steps (Recommended Order)

1. **This session**:
   - ✅ Audit logger infrastructure
   - ✅ Database schema
   - ✅ API endpoints
   - ⏳ Remaining: Position sizer & exit engine integration

2. **After deployment**:
   - Paper trade for 1 week
   - Review audit logs daily
   - Verify exit rule distribution
   - Check cascade multipliers are working

3. **Before live money**:
   - Document your comfort level with multiplier cascade (is 0.28x acceptable?)
   - Verify stops are hitting as expected
   - Confirm exit rules match your intended strategy
   - Set up alert thresholds

---

## References

- Audit Logger: `algo/algo_trade_audit_logger.py`
- API Endpoints: `lambda/api/routes/risk_dashboard.py`
- Database Schema: `terraform/modules/database/init.sql` (new audit tables)
- Filter Pipeline: `algo/algo_filter_pipeline.py` (updated _compute_stop_loss)

---

## Key Insight for Real Money Trading

**The cascade multiplier effect is the key risk control.**

Example: After a -7% drawdown, market in PRESSURE exposure tier, VIX at 28:
```
Position size = base_shares × 0.75 (drawdown) × 0.5 (PRESSURE) × 0.75 (VIX) × 0.5 (phase)
             = base_shares × 0.14 (14% of intended size)
```

This is **intentional protection**, not a bug. The audit trail shows exactly why. Before deploying real money, ensure you're comfortable with positions being 14-28% of intended size during drawdown—this is conservative and appropriate.

