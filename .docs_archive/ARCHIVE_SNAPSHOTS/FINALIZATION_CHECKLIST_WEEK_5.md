# Week 5: Finalization Checklist

**Objective:** Polish existing systems (Weeks 1-4) to production-grade quality. Handle edge cases, improve error messages, add defensive coding.

**Status:** Checklist for systematic completion.

---

## Week 1 Finalization: Credential Security

### ✅ Credential Manager Polish

- [ ] Add credential rotation support
  ```python
  # credential_manager.py
  def rotate_credential(self, secret_name, new_value):
      """Rotate credential in Secrets Manager"""
      self._get_secret(secret_name, update=new_value)
      self._cache.pop(secret_name, None)  # Invalidate cache
      logger.info("Credential rotated", extra={"secret": secret_name})
  ```

- [ ] Add credential validation on every access (not just startup)
  ```python
  def validate_on_access(self, credential_type):
      """Validate credential is still usable (before each use)"""
      cred = self.get_db_credentials()
      if not cred or not cred.get('password'):
          raise CredentialError("DB password invalid or missing")
      # Similar checks for Alpaca, SMTP
  ```

- [ ] Add credential expiration warnings
  ```python
  # Alert 7 days before credential expires (if using Secrets Manager rotation)
  if days_until_rotation < 7:
      logger.warning("Credential expiring soon", extra={
          "secret": secret_name,
          "days_left": days_until_rotation
      })
  ```

### ✅ Error Handling Improvements

- [ ] Replace generic exceptions with specific types
  ```python
  class CredentialError(Exception): pass
  class CredentialExpiredError(CredentialError): pass
  class CredentialMissingError(CredentialError): pass
  class CredentialValidationError(CredentialError): pass
  ```

- [ ] Add helpful error messages
  ```python
  # Before
  raise Exception("DB connection failed")
  
  # After
  raise CredentialError(
      "DB password invalid or missing. "
      "Set DB_PASSWORD env var or add to AWS Secrets Manager. "
      "Run: python3 credential_validator.py --validate"
  )
  ```

- [ ] Add credential validator improvements
  ```bash
  # Should show:
  # - Which credentials are missing
  # - Where to set them (env var vs Secrets Manager)
  # - How to test them
  python3 credential_validator.py --validate
  # Output:
  # ✓ DB_PASSWORD found in Secrets Manager
  # ✗ ALPACA_API_KEY missing (set in .env or Secrets Manager)
  # ✓ SMTP password found
  # ✓ Twilio SID found
  ```

---

## Week 3 Finalization: Data Loading Reliability

### ✅ Data Quality Gate Polish

- [ ] Add configurable validation thresholds
  ```python
  DATA_QUALITY_CONFIG = {
      'min_volume': 100000,  # Minimum daily volume
      'max_price_jump_pct': 50,  # Alert if price jumps >50% in a day
      'max_data_age_days': 2555,  # 7 years max (older data likely irrelevant)
      'zero_volume_action': 'WARN',  # Or 'REJECT'
  }
  ```

- [ ] Add data quality report
  ```bash
  python3 data_quality_gate.py --report --date 2026-05-09
  # Shows:
  # Validation Results by Symbol:
  #   AAPL: ✓ 100% pass (passed 100 rows, rejected 0)
  #   MSFT: ⚠ 95% pass (99 rows, 1 zero-volume rejected)
  #   GOOGL: ✗ 80% pass (80 rows, 20 bad price data rejected)
  ```

- [ ] Add automatic repair for common issues
  ```python
  # If volume is zero but price is good, keep it (don't reject)
  # If price jump is >50%, flag but keep (don't auto-reject)
  # If price is negative, REJECT (actual data error)
  ```

### ✅ Loader SLA Tracker Polish

- [ ] Add SLA trend reporting
  ```bash
  python3 loader_sla_tracker.py --trends --days 30
  # Shows:
  # price_daily: 100% success (last 30 days)
  # buy_sell_daily: 98% success (1 failed run 5 days ago)
  # Trend: ↓ (was 100% last week)
  ```

- [ ] Add automatic SLA escalation
  ```python
  # If success rate drops below 95%, page operator
  # If below 90%, trigger runbook (automated recovery)
  if success_rate < 90:
      logger.critical("SLA threshold breached", extra={
          "loader": loader_name,
          "success_rate": success_rate,
          "action": "Activate runbook"
      })
  ```

- [ ] Add SLA forecasting
  ```python
  # Predict: "Based on current trend, this loader will fail in 2 days"
  def predict_failure_date(self, loader_name, days_ahead=7):
      # Simple linear regression on success rate
      # Return: (predicted_failure_date, confidence)
  ```

### ✅ Database Table Improvements

- [ ] Add SLA summary view
  ```sql
  CREATE VIEW v_loader_sla_summary AS
  SELECT 
      loader_name,
      COUNT(*) as total_runs,
      SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) as passed_runs,
      ROUND(100.0 * SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_pct,
      MAX(completed_at) as last_run,
      AVG(rows_succeeded) as avg_rows_loaded
  FROM loader_execution_history
  WHERE execution_date >= CURRENT_DATE - INTERVAL '30 days'
  GROUP BY loader_name;
  ```

---

## Week 4 Finalization: Observability Phase 1

### ✅ Structured Logging Polish

- [ ] Add context propagation
  ```python
  # Every log should inherit trace_id from parent context
  def log_with_context(self, level, message, **extra):
      """Automatically add trace_id and caller context"""
      extra.setdefault('trace_id', get_trace_id())
      extra.setdefault('caller', f"{caller_file}:{caller_line}")
      extra.setdefault('version', VERSION)  # App version
      self._log(level, message, extra)
  ```

- [ ] Add sampling for high-volume logs
  ```python
  # Don't log every single tick, sample intelligently
  @log_with_sampling(rate=0.1)  # Log 1 in 10 ticks
  def log_price_update(self, symbol, price):
      logger.info(f"Price update: {symbol} @ {price}")
  ```

- [ ] Add performance timings
  ```python
  # Automatically measure and log execution time
  @measure_duration(threshold_ms=100)  # Only log if >100ms
  def phase_4_signal_quality(self):
      # Logs: "Phase 4 completed in 234ms"
  ```

### ✅ Alert Router Polish

- [ ] Add alert deduplication
  ```python
  # Don't send 10 identical alerts in a row
  class AlertRouter:
      def __init__(self):
          self.last_alert_by_signature = {}  # Track recent alerts
      
      def route_alert(self, severity, title, message):
          signature = f"{severity}:{title}"
          if self.is_duplicate(signature, minutes=30):
              logger.debug("Alert deduplicated", extra={"signature": signature})
              return
          # Send alert...
  ```

- [ ] Add alert escalation
  ```python
  # If operator doesn't acknowledge CRITICAL alert in 5 min, escalate
  def check_unacked_alerts(self):
      critical_unacked = self.get_alerts(severity='CRITICAL', acked=False, older_than_minutes=5)
      if critical_unacked:
          self.escalate_to_oncall(critical_unacked)
          logger.warning(f"Alert escalated: {len(critical_unacked)} critical unacked")
  ```

- [ ] Add alert routing tests
  ```python
  def test_alert_reaches_correct_channel():
      # CRITICAL → SMS + Email + Slack
      assert alert_reaches_sms()
      assert alert_reaches_email()
      assert alert_reaches_slack()
  ```

### ✅ Audit Dashboard Polish

- [ ] Add dashboard caching
  ```python
  # Cache expensive queries for 5 minutes
  @cache(ttl_minutes=5)
  def get_portfolio_history(self, days=30):
      # Only recalculate if cache expired
  ```

- [ ] Add export functionality
  ```bash
  python3 audit_dashboard.py --export-csv --symbol AAPL --days 30
  # Exports: audit_AAPL_2026-05-09.csv
  ```

- [ ] Add alerting on anomalies
  ```python
  # Detect: "Unusual trading pattern detected"
  def detect_anomalies(self):
      trades_today = self.get_trades_today()
      if len(trades_today) > 10 * self.avg_daily_trades:
          logger.warning("Unusual trading volume", extra={
              "normal": self.avg_daily_trades,
              "today": len(trades_today)
          })
  ```

---

## Week 6 Finalization: Feature Flags

### ✅ Feature Flags Polish

- [ ] Add flag versioning (track history)
  ```python
  def get_flag_history(self, flag_name, days=7):
      """Get all changes to this flag in past N days"""
      # Returns: [(timestamp, value, changed_by, reason), ...]
  ```

- [ ] Add flag dependency management
  ```python
  # Flag A depends on Flag B being enabled
  FLAG_DEPENDENCIES = {
      'signal_tier_5_enabled': ['signal_tier_4_enabled'],  # Can't enable T5 if T4 disabled
      'ab_test_tier5': ['signal_tier_5_enabled'],
  }
  ```

- [ ] Add flag impact analysis
  ```python
  def analyze_impact(self, flag_name):
      """What happens if we flip this flag?"""
      # Show: which code paths affected, which other flags depend on it
  ```

- [ ] Add flag validation rules
  ```python
  # Prevent invalid flag values
  FLAG_VALIDATION = {
      'rollout_tier6_pct': {
          'min': 0,
          'max': 100,
          'allowed_values': None,  # Any 0-100
      },
      'ab_test_tier5_variant': {
          'allowed_values': ['control', 'A', 'B'],
      },
  }
  ```

### ✅ Feature Flag Monitoring

- [ ] Add dashboard showing active flags
  ```bash
  python3 feature_flags.py --dashboard
  # Shows:
  # Signal Tier Disables:
  #   signal_tier_2_enabled: FALSE (disabled 2 hours ago by operator)
  #   signal_tier_4_enabled: TRUE
  #
  # A/B Tests:
  #   ab_test_tier5_variant: A (variant A active)
  #
  # Rollouts:
  #   rollout_tier6_pct: 50 (50% gradual rollout)
  ```

---

## Week 7 Finalization: Order Reconciliation

### ✅ Order Reconciler Polish

- [ ] Add reconciliation scheduling
  ```python
  # Run reconciliation every 5 minutes during market hours
  @schedule(every_minutes=5, during='market_hours')
  def reconcile_orders(self):
      # Automatic continuous sync with Alpaca
  ```

- [ ] Add dry-run mode (diagnose without fixing)
  ```bash
  python3 order_reconciler.py --check --dry-run
  # Shows: "If we ran recovery, 3 orders would be updated"
  # But doesn't actually update anything
  ```

- [ ] Add batch recovery
  ```bash
  # Fix multiple stuck orders at once
  python3 order_reconciler.py --cancel-orders-older-than 30min
  # Cancels all orders pending >30 minutes
  ```

### ✅ Slippage Tracker Polish

- [ ] Add slippage alerts
  ```python
  # Alert if slippage exceeds threshold
  if avg_slippage_pct > 0.5:
      logger.warning("Slippage exceeds threshold", extra={
          "avg_pct": avg_slippage_pct,
          "threshold": 0.5
      })
  ```

- [ ] Add slippage by time-of-day analysis
  ```python
  # Show: "Morning trades have 0.1% slippage, afternoon 0.3%"
  def analyze_slippage_by_time(self):
      return {
          '09:30-11:30': 0.05,  # AM lowest slippage
          '11:30-13:30': 0.15,  # Lunch slight increase
          '13:30-15:59': 0.25,  # Afternoon higher slippage
      }
  ```

- [ ] Add market impact analysis
  ```python
  # Show: "Our trades had -0.2% market impact (moved market against us)"
  def estimate_market_impact(self):
      return {
          'impact_basis_points': -20,  # Moved market -0.2%
          'estimated_lost_value': 1250,  # $ cost
      }
  ```

---

## Cross-System Finalization

### ✅ Error Handling Uniformity

- [ ] Standardize error response format across all systems
  ```python
  # All APIs return consistent error format
  {
      "error": {
          "code": "CREDENTIAL_MISSING",
          "message": "DB password invalid or missing",
          "details": "Set DB_PASSWORD or add to Secrets Manager",
          "action": "Run: python3 credential_validator.py",
          "trace_id": "RUN-2026-05-09-143045-abc"
      }
  }
  ```

- [ ] Add retry logic with exponential backoff
  ```python
  @retry(max_attempts=3, backoff=1.5)  # Try 3x with 1.5s, 2.25s, 3.37s delays
  def query_database(self):
      # Automatically retry on transient failures
  ```

- [ ] Add timeout handling
  ```python
  @timeout(seconds=10)
  def get_alpaca_orders(self):
      # Fail fast if Alpaca API doesn't respond within 10s
  ```

### ✅ Documentation Polish

- [ ] Add runbook quick-reference card (laminate!)
  ```
  ┌─────────────────────────────────────────┐
  │ QUICK REFERENCE - INCIDENT RESPONSE      │
  ├─────────────────────────────────────────┤
  │ Data Load Fails:                         │
  │ 1. python3 audit_dashboard.py --loaders │
  │ 2. Check: python3 loadpricedaily.py ... │
  │ 3. If stuck: Disable flag, restart ECS  │
  │                                         │
  │ Order Stuck:                            │
  │ 1. python3 order_reconciler.py --check  │
  │ 2. Cancel: --cancel-order AAPL order-id│
  │ 3. Or force-sell: --force-sell AAPL 100│
  │                                         │
  │ Lambda Timeout:                         │
  │ 1. Check CloudWatch: aws logs tail ...  │
  │ 2. Increase memory: 1024→2048 MB        │
  │ 3. Deploy: gh workflow run ...          │
  └─────────────────────────────────────────┘
  ```

- [ ] Add FAQ document
  ```markdown
  # Frequently Asked Questions
  
  Q: How do I disable a broken signal tier?
  A: python3 feature_flags.py --disable signal_tier_2_enabled
  
  Q: How do I know if data is fresh?
  A: python3 audit_dashboard.py --loaders
  
  Q: How do I check for stuck orders?
  A: python3 order_reconciler.py --check
  
  Q: How do I measure execution quality?
  A: python3 slippage_tracker.py --date 2026-05-09
  
  Q: How do I see what alerts have been sent?
  A: GET /api/admin/alerts (or check Slack history)
  ```

- [ ] Add troubleshooting decision tree
  ```
  START: "Something's wrong"
         ↓
  Q: Are signals still generating?
    YES → Q: Are orders placing?
           YES → Q: Are orders filling?
                  YES → System OK, monitor slippage
                  NO → Order reconciliation issue (see runbook)
           NO → Order placement issue (see runbook)
    NO → Q: Is data loading?
           YES → Signal generation issue (check tiers)
           NO → Data loading issue (see runbook)
  ```

### ✅ Performance Optimization

- [ ] Add performance baseline and monitoring
  ```python
  PERFORMANCE_BASELINES = {
      'phase_1_data_quality': {'max_ms': 100},
      'phase_2_market_health': {'max_ms': 50},
      'phase_3_trend': {'max_ms': 200},
      'phase_4_signal_quality': {'max_ms': 300},
      'phase_5_portfolio': {'max_ms': 100},
  }
  
  # Alert if phase exceeds baseline
  if duration > PERFORMANCE_BASELINES[phase]['max_ms']:
      logger.warning(f"{phase} slow", extra={
          "baseline_ms": PERFORMANCE_BASELINES[phase]['max_ms'],
          "actual_ms": duration
      })
  ```

- [ ] Add caching where appropriate
  ```python
  # Cache market health data (doesn't change during day)
  @cache(ttl_hours=4)
  def get_market_health(self, date):
      # Only fetch once per 4 hours
  ```

- [ ] Add index recommendations
  ```bash
  python3 database_optimizer.py --recommend-indexes
  # Output:
  # Index on algo_trades(symbol, created_at) would speed up queries by 40%
  # Index on price_daily(symbol, date) is unused (safe to drop)
  ```

---

## Finalization Verification Checklist

### ✅ Code Quality
- [ ] All error messages are helpful (include fix suggestion)
- [ ] All timeouts are reasonable (not too short, not too long)
- [ ] All retries have exponential backoff
- [ ] No hardcoded credentials or sensitive data
- [ ] All external API calls have timeout and retry logic
- [ ] All database queries have timeout and result limits

### ✅ Observability
- [ ] All errors are logged with trace_id
- [ ] All long operations log start/end with duration
- [ ] All alerts can be deduplicated
- [ ] All failures are auditable (traced)
- [ ] All success/failure paths are visible in logs

### ✅ Safety
- [ ] All data mutations are transactional
- [ ] All dangerous operations require explicit confirmation
- [ ] All rollbacks are tested
- [ ] All edge cases are handled
- [ ] All limits are enforced (position size, risk, etc.)

### ✅ Operations
- [ ] All common failures have documented recovery
- [ ] All recovery procedures are tested
- [ ] All manual operations log who did what and when
- [ ] All critical systems have fallback mechanisms
- [ ] All on-call procedures are documented

---

## How to Verify Finalization

```bash
# 1. Run full test suite
pytest tests/integration/ -v

# 2. Check error messages are helpful
python3 credential_validator.py  # Should guide missing creds
python3 feature_flags.py --set bad_flag bad_type bad_value  # Should explain requirement

# 3. Verify logging is structured
tail -f /tmp/algo.log | jq '.'  # Should be valid JSON

# 4. Verify alerting works
# Trigger a test CRITICAL alert (check if SMS received in 30s)

# 5. Run disaster recovery scenarios
# Simulate: RDS down, loader failure, stuck order
# Verify: runbook can fix each scenario

# 6. Performance baseline check
python3 performance_analyzer.py --baseline
# Should show: all phases within expected duration
```

---

**Week 5 Finalization enables confident production deployment. Polish is not luxury — it's risk reduction.**
