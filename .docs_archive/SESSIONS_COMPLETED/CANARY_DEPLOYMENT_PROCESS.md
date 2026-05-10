# Canary Deployment Process - Staged Rollout Guide

**Objective:** Deploy code changes safely by rolling them out gradually (1% → 10% → 50% → 100%) and monitoring for issues before full release.

**Status:** Ready to use with feature flags infrastructure.

**Key Principle:** Never deploy to 100% at once. Start small, measure, then expand.

---

## Why Canary Deployments?

### The Risk

```
Before Canary:
Release → Deploy to 100% → Issue discovered → Rollback (users affected)
Cost: Possible trader losses, hours of troubleshooting

After Canary:
Release → Deploy to 1% → Monitor → Expand to 10% → Issue discovered
Cost: 1% of trades affected, fast recovery, learning opportunity
```

### The Benefit

- **Early Detection:** Issues surface with 1% of traffic, not 100%
- **Fast Rollback:** Stop canary immediately, full system unaffected
- **Confidence:** You have data proving new code works before full release
- **Safety Net:** Feature flags let you pause/resume without re-deploying

---

## Canary Deployment Stages

### Stage 1: Canary (1% of Trades)

**Goal:** Verify basic functionality with minimal exposure.

**Timeline:** Run for 2-4 hours (at least 5-10 trades)

**Monitoring Checklist:**
- ✓ Lambda executes without errors (check CloudWatch logs)
- ✓ Signals are generated (not blocked by new code)
- ✓ Orders are placed and filled (no order placement issues)
- ✓ No new alerts triggered
- ✓ Execution quality (slippage) is normal

**Exit Criteria:**
- At least 5 trades completed without errors
- No CRITICAL or ERROR level logs
- Slippage within expected range
- All API endpoints responsive

**If Issue Found:**
```bash
# Immediately pause canary
python3 feature_flags.py --disable tier_5_enabled
# Or for specific feature:
python3 feature_flags.py --set rollout_new_filter_pct rollout 0

# Diagnose issue
aws logs tail /aws/lambda/algo-orchestrator --since 1h | grep ERROR

# Fix code, commit, and redeploy
git commit -am "fix: issue found in canary stage"
gh workflow run deploy-algo-orchestrator.yml

# Restart canary
python3 feature_flags.py --set rollout_new_filter_pct rollout 1
```

### Stage 2: Early Adopters (10% of Trades)

**Goal:** Expand to 10x the traffic, catch interaction issues.

**Timeline:** Run for 4-8 hours (at least 20-30 trades)

**Monitoring Checklist:**
- ✓ All Stage 1 checks pass
- ✓ Portfolio position tracking is accurate
- ✓ P&L calculations are correct
- ✓ No database query slowdowns
- ✓ Alert volume is normal (no spam)
- ✓ API latency doesn't increase
- ✓ Risk metrics (Sharpe, drawdown) are reasonable

**Exit Criteria:**
- At least 20 trades completed
- <1% error rate across all trades
- No degradation in performance
- No unexpected alerts
- All metrics within normal range

**If Issue Found:**
```bash
# Pause expansion
python3 feature_flags.py --set rollout_new_filter_pct rollout 1

# Investigate with more data
python3 audit_dashboard.py --symbol AAPL --days 1  # See all trades from past day
python3 slippage_tracker.py --date 2026-05-09

# Fix code
git commit -am "fix: issue in early adopter stage"
gh workflow run deploy-algo-orchestrator.yml

# Resume at 1% while you monitor next stage
python3 feature_flags.py --set rollout_new_filter_pct rollout 1
# Wait 2 hours for fixes to propagate
# Then expand to 10% again
```

### Stage 3: Broad Rollout (50% of Trades)

**Goal:** Run at half traffic, catch edge cases with larger dataset.

**Timeline:** Run for 8-16 hours (100+ trades)

**Monitoring Checklist:**
- ✓ All Stage 2 checks pass
- ✓ Portfolio diversification is maintained
- ✓ Sector/industry concentration limits are respected
- ✓ No systematic bias in selection (not all selecting same sectors)
- ✓ Trade frequency is reasonable (not over-trading)
- ✓ Stop loss levels are being respected
- ✓ Exit signals work correctly

**Exit Criteria:**
- At least 100 trades completed
- <0.5% error rate
- PnL is positive or neutral (not systematically losing)
- Metrics consistent with historical performance
- Team confidence is high

**If Issue Found:**
```bash
# Pause broader rollout
python3 feature_flags.py --set rollout_new_filter_pct rollout 10

# Analyze larger dataset
python3 audit_dashboard.py --signals --days 1
# Check for any systematic bias or risk

# Consider: Is this an issue or just variance?
# New filter might select different stocks (intentional)
# Check if results are acceptable

# If acceptable:
python3 feature_flags.py --set rollout_new_filter_pct rollout 50

# If not acceptable:
git commit -am "fix: systematic issue in broad rollout"
gh workflow run deploy-algo-orchestrator.yml
python3 feature_flags.py --set rollout_new_filter_pct rollout 1  # Back to canary
```

### Stage 4: Full Release (100% of Trades)

**Goal:** Release new code to all trades. No more monitoring rollout, just normal operations.

**Timeline:** Indefinite (ongoing operations)

**Before Full Release:**
- [ ] Team reviewed all stage results
- [ ] No unresolved issues
- [ ] Metrics are positive
- [ ] Runbooks updated for any new failure modes
- [ ] Team trained on any new behavior

**Final Release Command:**
```bash
# Full release
python3 feature_flags.py --set rollout_new_filter_pct rollout 100

# Or remove the feature flag entirely if fully tested
# Edit code to remove flag check:
# - Remove: if flags.is_enabled(...):
# - Keep: just the new code

# Commit and deploy
git commit -am "feat: Full release of new filter (completed canary)"
gh workflow run deploy-algo-orchestrator.yml
```

**Post-Release Monitoring:**
- Monitor for 24 hours for any issues
- Have runbook ready for quick rollback (via feature flag)
- Celebrate with team! 🎉

---

## Canary Deployment Checklist

### Pre-Deployment (Before Starting Canary)

- [ ] Code changes reviewed and merged to main
- [ ] Tests pass: `pytest tests/integration/ -v`
- [ ] Feature flag already created: `python3 feature_flags.py --list`
- [ ] Runbook updated if new failure mode
- [ ] Team notified: "Canary deploy starting in 1 hour"
- [ ] On-call engineer assigned to monitor

### During Canary

- [ ] Start canary: `python3 feature_flags.py --set rollout_feature_pct rollout 1`
- [ ] Monitor CloudWatch logs: `aws logs tail /aws/lambda/algo-orchestrator --follow`
- [ ] Monitor audit dashboard: `python3 audit_dashboard.py --loaders` (every 15 min)
- [ ] Check alerts: Slack `#incidents` channel (no CRITICAL alerts expected)
- [ ] Wait for at least 5-10 trades (2-4 hours)
- [ ] Review results: No errors, normal execution

### During Early Adopters Stage

- [ ] Expand to 10%: `python3 feature_flags.py --set rollout_feature_pct rollout 10`
- [ ] Continue monitoring (every 15 min)
- [ ] Track key metrics:
  - Trade count (should be ~10x canary stage)
  - Error rate (should be <1%)
  - Slippage (should be normal)
  - API latency (should be <2s)
  - PnL (should be positive or neutral)
- [ ] Wait for 20-30 trades (4-8 hours)
- [ ] Review results

### During Broad Rollout Stage

- [ ] Expand to 50%: `python3 feature_flags.py --set rollout_feature_pct rollout 50`
- [ ] Continue monitoring (every 30 min now)
- [ ] Track additional metrics:
  - Portfolio concentration (not all in one sector)
  - Selection bias (new filter not systematically choosing same types)
  - Risk metrics (Sharpe ratio, drawdown)
  - Correlation to SPY (should be unchanged)
- [ ] Wait for 100+ trades (8-16 hours)
- [ ] Review results

### For Full Release

- [ ] Expand to 100%: `python3 feature_flags.py --set rollout_feature_pct rollout 100`
- [ ] Or remove feature flag check from code (full permanent release)
- [ ] Monitor for 24 hours
- [ ] If any issues, use feature flag to pause: `python3 feature_flags.py --set rollout_feature_pct rollout 0`

---

## Real-World Canary Example: New Signal Filter

### Timeline

**Monday 10am ET:** Canary starts (1% of trades)
```
signal_tier_6_enabled = false (disabled)
rollout_tier6_pct = 1 (only 1% of trades use new filter)

Results after 3 hours (5 trades):
✓ Tier 6 filter runs without errors
✓ No additional slippage
✓ Exit signals from Tier 6 work correctly
→ Decision: Proceed to Early Adopters
```

**Monday 2pm ET:** Early Adopters (10% of trades)
```
rollout_tier6_pct = 10 (10% of trades use new filter)

Results after 5 hours (18 trades):
✓ All 5 trades still passing
✓ Performance metrics unchanged
✗ Alert: "Tier 6 selecting too many tech stocks" (concentration risk)
→ Decision: Investigate concentration, pause for now
```

**Monday 4pm ET:** Investigate & Fix
```
Analysis shows:
- New Tier 6 filter is legitimately selecting tech stocks
- This is correct behavior (tech stocks were in uptrend)
- Not a bug, just different selection criteria
- Concentration is within risk limits

Conclusion:
- New filter works correctly
- Different selection is intentional (better signals from tech)
- Resume rollout

Deployment:
git commit -am "docs: Tier 6 filter intentionally selects tech sector"
rollout_tier6_pct = 1 (back to canary while fix propagates)
# Wait 1 hour for code to propagate
rollout_tier6_pct = 50 (expand to broad rollout)
```

**Monday 10pm ET:** Broad Rollout (50% of trades)
```
rollout_tier6_pct = 50 (50% of trades use new filter)

Results after 8 hours (92 trades):
✓ Tech concentration is expected and acceptable
✓ Sharpe ratio: 0.82 (vs. control 0.75 - IMPROVED!)
✓ Win rate: 52% (vs. control 50% - IMPROVED!)
✓ Slippage: 0.07% (vs. control 0.06% - acceptable)
→ Decision: Full release is safe
```

**Tuesday 9am ET:** Full Release (100% of trades)
```
rollout_tier6_pct = 100 (all trades use new filter)

OR

Remove feature flag from code:
git commit -am "feat: Full release Tier 6 filter (canary complete)"

Post-release monitoring (24 hours):
✓ No issues
✓ Metrics match canary expectations
✓ Team confident

Result: Tier 6 filter successfully deployed!
```

---

## Metrics to Track During Canary

### Trading Metrics

| Metric | Baseline | Stage 1 | Stage 2 | Stage 3 | Target |
|--------|----------|---------|---------|---------|--------|
| Trade Count | 5-20/day | 1-2 | 5-10 | 20-50 | 50-100 |
| Error Rate | 0.5% | <0.5% | <1% | <0.5% | <0.5% |
| Win Rate | 50% | 48-52% | 48-52% | 48-52% | 50%+ |
| Avg Slippage | 0.06% | 0.04-0.08% | 0.04-0.08% | 0.04-0.08% | <0.1% |
| Sharpe Ratio | 0.80 | 0.75-0.85 | 0.75-0.85 | 0.75-0.85 | 0.80+ |
| Max Drawdown | -12% | -15% to -10% | -15% to -10% | -15% to -10% | -12% |

### System Metrics

| Metric | Stage 1 | Stage 2 | Stage 3 | Target |
|--------|---------|---------|---------|--------|
| Lambda Duration | <10s | <12s | <15s | <20s |
| Lambda Errors | 0 | 0 | <1% | 0 |
| API Latency | <1s | <1.5s | <2s | <2s |
| DB Query Time | <100ms | <150ms | <200ms | <200ms |
| Alert Volume | 0 | 0-1 | 0-2 | 0-1/hour |

---

## Rollback Procedure (If Issues Arise)

### Immediate Rollback (Via Feature Flag)

```bash
# Stop new code immediately (no re-deploy needed)
python3 feature_flags.py --disable signal_tier_6_enabled
# OR
python3 feature_flags.py --set rollout_tier6_pct rollout 0

# Instant effect: next algo run uses old code
# No Lambda re-deployment required
# No risk of broken code being deployed again
```

### Full Rollback (If Feature Flag Not Possible)

```bash
# Revert last commit
git revert HEAD

# Deploy reverted code
gh workflow run deploy-algo-orchestrator.yml

# Wait for Lambda to update (~3 min)
# Then verify: aws lambda get-function-configuration --function-name algo-orchestrator
```

### Post-Rollback Procedure

1. **Document what went wrong:**
   ```bash
   echo "Rollback reason: Issue with Tier 6 filter
   Error: [copy from CloudWatch logs]
   First noticed at: [timestamp]
   Rollback time: [timestamp]
   Affected trades: ~50 (4 hours at 10% rollout)
   " > /tmp/rollback_incident.md
   ```

2. **Create post-mortem (within 24 hours):**
   - Use INCIDENT_RESPONSE_PROCESS.md template
   - Analyze what went wrong
   - Fix root cause

3. **Re-attempt canary** (after fix):
   - Start back at 1% (canary stage)
   - Run full stages again
   - Gather confidence before expanding

---

## Decision Tree: Should We Proceed to Next Stage?

```
At Each Stage Boundary, Ask:
├─ Error Rate < Threshold? 
│  NO → Rollback and fix
│  YES → Continue
├─ Trading Metrics Match Expected?
│  NO (worse by >5%) → Investigate, possibly rollback
│  YES → Continue
├─ Any Unexpected Alerts?
│  YES → Investigate, decide if critical
│  NO → Continue
├─ Team Confidence High?
│  NO → Ask questions, resolve concerns, or rollback
│  YES → Continue
├─ Sample Size Large Enough?
│  NO → Wait longer (need 5+ trades for canary, 20+ for early adopters, 100+ for broad)
│  YES → Proceed to next stage

Result: PROCEED or ROLLBACK
```

---

## Canary Deployment Benefits Summary

✅ **Safety First:** Issues are caught early with minimal exposure
✅ **Data Driven:** You have metrics before deciding to expand
✅ **Fast Recovery:** Feature flags enable instant rollback (no redeploy)
✅ **Learning Opportunity:** Each stage teaches you about the change
✅ **Team Confidence:** Progressive validation builds trust
✅ **Zero Downtime:** Old code continues running during canary

---

## Feature Flags for Canary Support

Your feature flag system must support:

```python
# Emergency disable (kill-switch)
signal_tier_6_enabled = true/false  # Enable/disable entire feature

# Gradual rollout (canary stages)
rollout_tier6_pct = 1 / 10 / 50 / 100  # Percentage of trades

# A/B testing (if you want to test variants)
ab_test_tier6_variant = 'control' / 'new' / 'experimental'
```

All three patterns are supported by `feature_flags.py`. Use them!

---

**Canary deployments are the bridge between testing and production. They give you confidence without risk.**
