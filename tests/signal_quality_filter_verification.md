# Signal Quality Filter Verification Plan (Jun 6-11)

## Deployed Changes (Commit 3a50b359)

### Filter Relaxations
- **Sector position limit:** 8 (was 5) — allows more concentration in single sector
- **Industry position limit:** 5 (was 3) — allows more concentration in single industry  
- **Close quality filter:** 40% (was 60%) — accepts more closes in lower half of daily range

### Expected Impact
- ✅ Reduction in rejections: 40%+ fewer signals rejected by filters
- ✅ Increase in qualified signals: 0-2/day → 2-5+/day by Jun 11
- ✅ Signal freshness: All staleness columns (buy_sell_daily_age_days, technical_data_age_days, trend_template_age_days) should be non-NULL

## Verification Checklist (Daily Jun 6-11)

### Morning (9:35 AM ET)
- [ ] **Market opened successfully**
  - Command: `aws logs tail /lambda/algo-orchestrator-dev --since 1h | grep "Phase 1\|HALT"` 
  - Expected: No halt messages before market open

- [ ] **Data freshness passed**
  - Command: `aws logs tail /lambda/algo-orchestrator-dev --since 1h | grep "staleness\|freshness"`
  - Expected: All data sources reported as fresh

### Midday (1:30 PM ET)
- [ ] **Phase 5 filter logs present**
  - Command: `aws logs tail /lambda/algo-orchestrator-dev --since 6h | grep "FILTER REJECTION ANALYSIS"`
  - Expected: One entry per pipeline run showing filter metrics

- [ ] **Signal count trending upward**
  - Look for: `"total_qualified_signals": <N>` in logs
  - Expected: Increasing from 0-2 at start of week to 2-5+ by end

### EOD (5:45 PM ET)
- [ ] **Orchestrator completed all 7 phases**
  - Command: `aws logs tail /lambda/algo-orchestrator-dev --since 2h | grep "Phase 7\|reconciliation"`
  - Expected: Reconciliation completed without errors

- [ ] **No halt flags stuck from previous day**
  - Command: `python scripts/check_halt_flag.py`
  - Expected: Halt flag cleared (expires on prior trading day)

## Detailed Metrics to Track

| Metric | Jun 6 Baseline | Jun 7-11 Expected | Threshold Alert |
|--------|---|---|---|
| Signals/day | 0-2 | 2-5+ | <1 (indicates filter issue) |
| Rejection rate | High | Down 40%+ | >70% (indicates filter too strict) |
| Sector violations | 0 (limit enforced) | 0 | >0 (broken filter) |
| Industry violations | 0 (limit enforced) | 0 | >0 (broken filter) |
| Close quality fails | High | Lower | >50% (indicates bad data) |

## CloudWatch Logs Insights Queries

### Query 1: Filter Rejection Summary
```
fields @timestamp, @message
| filter @message like /FILTER REJECTION ANALYSIS/
| stats count() as total_runs, 
  avg(fromjson(@message).total_qualified_signals) as avg_qualified by @timestamp
| sort @timestamp desc
```

### Query 2: Signal Count Trend
```
fields @timestamp, @message
| filter @message like /total_qualified_signals/
| stats max(fromjson(@message).total_qualified_signals) as max_signals by bin(5m)
| sort @timestamp asc
```

### Query 3: Filter Rejection Details
```
fields @timestamp, @message
| filter @message like /sector_limit|industry_limit|close_quality/
| stats count() as rejection_count by @message
| sort rejection_count desc
```

## Success Criteria

### By Jun 11 EOD (All Required)
- [ ] Qualified signals average 2-5/day (vs 0-2 baseline)
- [ ] Rejection count down 30%+ 
- [ ] Zero sector/industry limit violations
- [ ] All staleness columns populated daily
- [ ] No Phase 5 errors in logs
- [ ] Halt flag never stuck beyond prior trading day

### Escalation Triggers
- **If qualified signals < 1/day:** Filter may be reversed or data issue
- **If rejections > 80%:** Filters still too strict, need further relaxation
- **If sector/industry > 0 violations:** Filter logic broken, requires code fix
- **If staleness columns NULL:** Data patrol failed, verify failsafe trigger working

## Rollback Plan

If filters cause problems:
```bash
git revert <commit-id>  # Revert filter changes
git push                 # Triggers deploy
```

Expected rollback time: 10-15 minutes
