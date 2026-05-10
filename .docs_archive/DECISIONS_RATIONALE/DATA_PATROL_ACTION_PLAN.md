# Data Patrol Implementation - Detailed Action Plan

## Overview
This document provides step-by-step implementation plan to close critical data monitoring gaps identified in DATA_PATROL_AUDIT.md.

**Timeline:** 4 weeks  
**Priority:** P12, P13, P14, P15 (Tier 1 patrols must deploy before production)  
**Effort:** ~80 hours  

---

## PHASE 1: ADD CRITICAL PATROLS (Week 1-2)

### 1.1: Add P12 - Earnings Data Validation

**Goal:** Ensure earnings data is always fresh and complete before positions are evaluated

**Code Changes:** In `algo_data_patrol.py`

```python
def check_earnings_data(self):
    """P12. Earnings data freshness and completeness.
    
    Earnings drive position stop decisions and exit rules. Must be current.
    - earnings_estimates: latest price target revisions
    - earnings_estimate_revisions: daily estimate changes
    - earnings_history: past earnings dates (for forward projection)
    """
    try:
        # Check staleness: estimates should be updated within 7 days
        sources = [
            ('earnings_estimates', 'date_recorded', 'daily', 7, WARN),
            ('earnings_estimate_revisions', 'date_recorded', 'daily', 14, WARN),
            ('earnings_history', 'quarter', 'quarterly', 120, WARN),
        ]
        today = _date.today()
        for tbl, col, freq, max_days, sev in sources:
            try:
                self.cur.execute(f"SELECT MAX({col}::date), COUNT(*) FROM {tbl}")
                latest, count = self.cur.fetchone()
                if not latest:
                    self.log('earnings_staleness', ERROR, tbl, 
                             f'EMPTY table {tbl}', {'count': count})
                    continue
                age = (today - latest).days
                if age > max_days:
                    self.log('earnings_staleness', sev, tbl,
                             f'{tbl} stale: {age}d > {max_days}d threshold',
                             {'latest': str(latest), 'age_days': age})
                else:
                    self.log('earnings_staleness', INFO, tbl,
                             f'{tbl} fresh ({age}d old)', 
                             {'latest': str(latest)})
            except Exception as e:
                self.log('earnings_staleness', ERROR, tbl, f'Check failed: {e}', None)
        
        # Check coverage: earnings_estimates should cover major % of universe
        try:
            self.cur.execute("""
                SELECT
                    COUNT(DISTINCT symbol) as est_symbols,
                    (SELECT COUNT(DISTINCT symbol) FROM price_daily 
                     WHERE date >= CURRENT_DATE - INTERVAL '7 days') as price_symbols
                FROM earnings_estimates
                WHERE date_recorded >= CURRENT_DATE - INTERVAL '7 days'
            """)
            est_syms, price_syms = self.cur.fetchone()
            est_syms = int(est_syms or 0)
            price_syms = int(price_syms or 1)
            coverage_pct = (est_syms / price_syms * 100) if price_syms else 0
            
            if coverage_pct < 80:
                self.log('earnings_coverage', WARN, 'earnings_estimates',
                         f'Only {coverage_pct:.1f}% of symbols have recent estimates',
                         {'symbols_with_est': est_syms, 
                          'symbols_in_universe': price_syms,
                          'coverage_pct': round(coverage_pct, 1)})
            else:
                self.log('earnings_coverage', INFO, 'earnings_estimates',
                         f'{coverage_pct:.1f}% coverage', None)
        except Exception as e:
            self.log('earnings_coverage', ERROR, 'earnings_estimates', 
                     f'Check failed: {e}', None)
    
    except Exception as e:
        self.log('earnings_data', ERROR, 'earnings', f'Check failed: {e}', None)
```

**Add to loader_contracts in check_loader_contracts():**
```python
contracts = [
    # ... existing contracts ...
    ('earnings_estimates', '1=1', 2000, WARN,
     'Earnings estimates: should cover 2000+ symbols'),
    ('earnings_estimate_revisions', 
     "date_recorded >= CURRENT_DATE - INTERVAL '7 days'",
     500, WARN,
     'Earnings revisions: daily activity indicator'),
]
```

**Add to run() method:**
```python
def run(self, quick=False, validate_alpaca=False):
    # ... existing checks ...
    if not quick:
        self.check_earnings_data()  # NEW
        # ... other checks ...
```

---

### 1.2: Add P13 - ETF Data Validation

**Goal:** Ensure ETF prices and signals are complete and fresh

**Code Changes:** In `algo_data_patrol.py`

```python
def check_etf_data(self):
    """P13. ETF price and signal data validation.
    
    Covers: etf_price_daily, buy_sell_daily_etf, buy_sell_weekly_etf
    """
    try:
        # Check ETF price staleness
        self.cur.execute("""
            SELECT MAX(date), COUNT(DISTINCT symbol) 
            FROM etf_price_daily
        """)
        latest_date, etf_count = self.cur.fetchone()
        
        if not latest_date:
            self.log('etf_prices', CRIT, 'etf_price_daily', 
                     'EMPTY table etf_price_daily', {})
        else:
            today = _date.today()
            age = (today - latest_date).days
            if age > 3:
                self.log('etf_prices', ERROR, 'etf_price_daily',
                         f'ETF prices stale: {age}d old',
                         {'latest': str(latest_date), 'etf_count': etf_count})
            else:
                self.log('etf_prices', INFO, 'etf_price_daily',
                         f'ETF prices fresh ({age}d old, {etf_count} ETFs)', None)
        
        # Check ETF signal staleness
        for tbl, max_age in [
            ('buy_sell_daily_etf', 1),
            ('buy_sell_weekly_etf', 7),
            ('buy_sell_monthly_etf', 30)
        ]:
            try:
                self.cur.execute(f"""
                    SELECT MAX(date), COUNT(*) FROM {tbl}
                    WHERE date >= CURRENT_DATE - INTERVAL '{max_age + 1} days'
                """)
                latest, count = self.cur.fetchone()
                if not latest or count == 0:
                    self.log('etf_signals', WARN, tbl,
                             f'{tbl} has no recent signals',
                             {'days_back': max_age + 1})
                else:
                    age = (today - latest).days
                    if age > max_age:
                        self.log('etf_signals', WARN, tbl,
                                 f'{tbl} stale: {age}d old',
                                 {'latest': str(latest)})
                    else:
                        self.log('etf_signals', INFO, tbl,
                                 f'{tbl} fresh ({age}d old)',
                                 {'signal_count': count})
            except Exception as e:
                self.log('etf_signals', WARN, tbl, f'Check failed: {e}', None)
        
        # Check ETF coverage: price_daily should have ETF prices
        try:
            self.cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM price_daily
                WHERE symbol IN (SELECT symbol FROM etf_symbols)
                  AND date = (SELECT MAX(date) FROM price_daily)
            """)
            etf_in_price = int(self.cur.fetchone()[0] or 0)
            self.log('etf_coverage', INFO, 'etf_symbols',
                     f'{etf_in_price} ETFs in price_daily', None)
        except Exception as e:
            self.log('etf_coverage', INFO, 'etf_symbols', 
                     f'Coverage check: {e}', None)
    
    except Exception as e:
        self.log('etf_data', ERROR, 'etf', f'Check failed: {e}', None)
```

**Add to loader_contracts:**
```python
contracts = [
    # ... existing ...
    ('etf_price_daily',
     "date >= CURRENT_DATE - INTERVAL '3 days'",
     30, WARN,
     'ETF prices: minimum 30 ETFs should be updated'),
    ('buy_sell_daily_etf',
     "date >= CURRENT_DATE - INTERVAL '1 days'",
     5, WARN,
     'ETF signals daily: at least 5 signals per day'),
    ('buy_sell_weekly_etf',
     "date >= CURRENT_DATE - INTERVAL '7 days'",
     2, INFO,
     'ETF signals weekly: some signals'),
]
```

**Add to run() method:**
```python
if not quick:
    self.check_etf_data()  # NEW
```

---

### 1.3: Add P14 - Cross-Table Alignment

**Goal:** Verify that all dependent tables have complete coverage of the symbol universe

**Code Changes:** In `algo_data_patrol.py`

```python
def check_cross_table_alignment(self):
    """P14. Cross-table coverage alignment.
    
    Validates that dependent tables cover the same symbol universe.
    A loader regression often shows up as sudden coverage drop.
    """
    try:
        today = _date.today()
        
        # Get baseline: symbols in today's price_daily
        self.cur.execute("""
            SELECT COUNT(DISTINCT symbol) FROM price_daily
            WHERE date = (SELECT MAX(date) FROM price_daily)
        """)
        price_baseline = int(self.cur.fetchone()[0] or 1)
        
        # Check each table's coverage vs baseline
        checks = [
            ('technical_data_daily', 
             'WHERE date = (SELECT MAX(date) FROM price_daily)',
             0.95, ERROR),
            ('buy_sell_daily',
             'WHERE date = (SELECT MAX(date) FROM buy_sell_daily)',
             0.90, ERROR),
            ('trend_template_data',
             'WHERE date = (SELECT MAX(date) FROM trend_template_data)',
             0.95, WARN),
            ('signal_quality_scores',
             'WHERE date = (SELECT MAX(date) FROM signal_quality_scores)',
             0.95, WARN),
            ('stock_scores',
             'WHERE 1=1',  # stock_scores is a snapshot
             0.95, WARN),
        ]
        
        for tbl, where_clause, min_ratio, severity in checks:
            try:
                self.cur.execute(f"""
                    SELECT COUNT(DISTINCT symbol) FROM {tbl}
                    {where_clause}
                """)
                tbl_count = int(self.cur.fetchone()[0] or 0)
                ratio = tbl_count / price_baseline if price_baseline else 0
                
                if ratio < min_ratio:
                    self.log('cross_align', severity, tbl,
                             f'{tbl} coverage {ratio*100:.1f}% < {min_ratio*100:.0f}% '
                             f'({tbl_count} vs {price_baseline} symbols)',
                             {'table': tbl, 'coverage_pct': round(ratio*100, 1),
                              'count': tbl_count, 'baseline': price_baseline})
                else:
                    self.log('cross_align', INFO, tbl,
                             f'{tbl} alignment OK ({ratio*100:.1f}%)', None)
            except Exception as e:
                self.log('cross_align', WARN, tbl, f'Check failed: {e}', None)
        
        # Special check: buy_sell_daily vs technical_data_daily on same date
        try:
            self.cur.execute("""
                SELECT
                    MAX(date) FILTER (WHERE table_name = 'buy_sell_daily'),
                    MAX(date) FILTER (WHERE table_name = 'technical_data_daily')
                FROM (
                    SELECT 'buy_sell_daily' as table_name, MAX(date) as date 
                    FROM buy_sell_daily
                    UNION ALL
                    SELECT 'technical_data_daily', MAX(date) FROM technical_data_daily
                ) t
            """)
            row = self.cur.fetchone()
            if row and row[0] and row[1]:
                if abs((row[0] - row[1]).days) > 1:
                    self.log('cross_align', WARN, 'buy_sell_daily/technical_data_daily',
                             f'Signal and technical data on different dates: '
                             f'{row[0]} vs {row[1]}',
                             {'signal_date': str(row[0]), 
                              'technical_date': str(row[1])})
        except Exception as e:
            self.log('cross_align', INFO, 'date_alignment', 
                     f'Check skipped: {e}', None)
    
    except Exception as e:
        self.log('cross_align', ERROR, 'all', f'Check failed: {e}', None)
```

**Add to run() method:**
```python
if not quick:
    self.check_cross_table_alignment()  # NEW
```

---

### 1.4: Add P15 - Financial Statement Freshness

**Goal:** Ensure fundamental data is recent enough for scoring

**Code Changes:** In `algo_data_patrol.py`

```python
def check_fundamental_data(self):
    """P15. Financial statement and fundamental data freshness.
    
    Annual/quarterly fundamentals have longer update cycles but must be
    tracked to catch loader failures.
    """
    try:
        today = _date.today()
        
        # Quarterly statements: max 45 days old
        quarterly_tables = [
            ('quarterly_income_statement', 'date_reported', 45, WARN),
            ('quarterly_balance_sheet', 'date_reported', 45, WARN),
            ('quarterly_cash_flow', 'date_reported', 45, WARN),
        ]
        
        # Annual statements: max 120 days old
        annual_tables = [
            ('annual_income_statement', 'date_reported', 120, WARN),
            ('annual_balance_sheet', 'date_reported', 120, WARN),
            ('annual_cash_flow', 'date_reported', 120, WARN),
        ]
        
        # Key metrics: max 14 days old
        metrics_tables = [
            ('key_metrics', 'date_recorded', 14, WARN),
            ('earnings_metrics', 'date_recorded', 7, WARN),
        ]
        
        all_checks = quarterly_tables + annual_tables + metrics_tables
        
        for tbl, col, max_days, severity in all_checks:
            try:
                self.cur.execute(f"""
                    SELECT MAX({col}::date), COUNT(*),
                           COUNT(DISTINCT symbol)
                    FROM {tbl}
                """)
                latest, total_rows, unique_syms = self.cur.fetchone()
                
                if not latest:
                    self.log('fundamental_data', WARN, tbl,
                             f'{tbl} is empty', {})
                    continue
                
                age = (today - latest).days
                if age > max_days:
                    self.log('fundamental_data', severity, tbl,
                             f'{tbl} stale: {age}d > {max_days}d',
                             {'latest': str(latest), 'age_days': age,
                              'symbols': unique_syms, 'rows': total_rows})
                else:
                    self.log('fundamental_data', INFO, tbl,
                             f'{tbl} fresh ({age}d old, {unique_syms} symbols)',
                             None)
            except Exception as e:
                self.log('fundamental_data', WARN, tbl, 
                         f'Check failed: {e}', None)
        
        # Check coverage: fundamentals should cover major % of universe
        try:
            self.cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM price_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            """)
            price_syms = int(self.cur.fetchone()[0] or 1)
            
            self.cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM key_metrics
                WHERE date_recorded >= CURRENT_DATE - INTERVAL '14 days'
            """)
            metrics_syms = int(self.cur.fetchone()[0] or 0)
            coverage = (metrics_syms / price_syms * 100) if price_syms else 0
            
            if coverage < 80:
                self.log('fundamental_coverage', WARN, 'key_metrics',
                         f'Only {coverage:.1f}% of symbols have recent metrics',
                         {'symbols_with_metrics': metrics_syms,
                          'price_symbols': price_syms})
        except Exception as e:
            self.log('fundamental_coverage', INFO, 'key_metrics', 
                     f'Coverage check: {e}', None)
    
    except Exception as e:
        self.log('fundamental_data', ERROR, 'fundamentals', 
                 f'Check failed: {e}', None)
```

**Add to loader_contracts:**
```python
contracts = [
    # ... existing ...
    ('quarterly_income_statement', '1=1', 100, WARN,
     'Quarterly statements: should have 100+ records'),
    ('key_metrics', 
     "date_recorded >= CURRENT_DATE - INTERVAL '14 days'",
     500, WARN,
     'Key metrics: 500+ symbols recent'),
    ('earnings_metrics',
     "date_recorded >= CURRENT_DATE - INTERVAL '7 days'",
     1000, WARN,
     'Earnings metrics: 1000+ symbols recent'),
]
```

**Add to run() method:**
```python
if not quick:
    self.check_fundamental_data()  # NEW
```

---

## PHASE 2: AWS CloudWatch Integration (Week 2-3)

### 2.1: Create CloudWatch Metrics Lambda

**File:** `aws/lambdas/export_patrol_to_cloudwatch.py`

```python
import json
import boto3
import psycopg2
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

cloudwatch = boto3.client('cloudwatch')

def lambda_handler(event, context):
    """Export data patrol results to CloudWatch metrics."""
    
    # Get latest patrol results from database
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )
    cur = conn.cursor()
    
    try:
        # Get patrol summary
        cur.execute("""
            SELECT severity, COUNT(*) as count
            FROM data_patrol_log
            WHERE patrol_run_id = (SELECT patrol_run_id FROM data_patrol_log ORDER BY created_at DESC LIMIT 1)
            GROUP BY severity
        """)
        
        findings = {row[0]: row[1] for row in cur.fetchall()}
        
        # Publish metrics
        cloudwatch.put_metric_data(
            Namespace='StockAlgo/DataQuality',
            MetricData=[
                {'MetricName': 'CriticalFindings', 'Value': findings.get('critical', 0), 
                 'Unit': 'Count', 'Timestamp': datetime.utcnow()},
                {'MetricName': 'ErrorFindings', 'Value': findings.get('error', 0),
                 'Unit': 'Count', 'Timestamp': datetime.utcnow()},
                {'MetricName': 'WarningFindings', 'Value': findings.get('warn', 0),
                 'Unit': 'Count', 'Timestamp': datetime.utcnow()},
            ]
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({'findings': findings})
        }
    
    finally:
        conn.close()
```

### 2.2: Update Patrol Script to Publish Metrics

**In algo_data_patrol.py summarize() method:**

```python
def summarize(self):
    counts = {INFO: 0, WARN: 0, ERROR: 0, CRIT: 0}
    for r in self.results:
        counts[r['severity']] = counts.get(r['severity'], 0) + 1
    
    # ... existing summary print ...
    
    # NEW: Publish to CloudWatch if running in Lambda
    try:
        import boto3
        cw = boto3.client('cloudwatch')
        cw.put_metric_data(
            Namespace='StockAlgo/DataQuality',
            MetricData=[
                {'MetricName': 'PatrolCritical', 'Value': counts.get(CRIT, 0)},
                {'MetricName': 'PatrolError', 'Value': counts.get(ERROR, 0)},
                {'MetricName': 'PatrolWarning', 'Value': counts.get(WARN, 0)},
            ]
        )
    except ImportError:
        pass  # Not running in AWS
    
    return {
        'run_id': self._run_id,
        'counts': counts,
        'ready': ready,
        'flagged': flagged,
        'all_results': self.results,
    }
```

### 2.3: Create SNS Alert Lambda

**File:** `aws/lambdas/patrol_alerts.py`

```python
import json
import boto3

sns = boto3.client('sns')

def lambda_handler(event, context):
    """Trigger SNS alerts on critical patrol findings."""
    
    message = event.get('body', {})
    counts = message.get('counts', {})
    
    if counts.get('critical', 0) > 0 or counts.get('error', 0) > 5:
        sns.publish(
            TopicArn=os.getenv('ALERT_TOPIC_ARN'),
            Subject='🚨 CRITICAL: Data Quality Issues Detected',
            Message=f"""
Patrol Run: {message.get('run_id')}

CRITICAL: {counts.get('critical', 0)}
ERROR: {counts.get('error', 0)}
WARNING: {counts.get('warn', 0)}

Immediate investigation required.

Dashboard: https://console.aws.amazon.com/cloudwatch/
Database: Review data_patrol_log for details
            """
        )
    
    return {'statusCode': 200}
```

### 2.4: EventBridge Schedule

**In CloudFormation:**

```yaml
PatrolScheduleRule:
  Type: AWS::Events::Rule
  Properties:
    ScheduleExpression: 'cron(0 8 * * ? *)'  # 8am ET daily
    State: ENABLED
    Targets:
      - Arn: !GetAtt PatrolLambda.Arn
        RoleArn: !GetAtt EventBridgeRole.Arn

PatrolLambdaPermission:
  Type: AWS::Lambda::Permission
  Properties:
    FunctionName: !Ref PatrolLambda
    Action: lambda:InvokeFunction
    Principal: events.amazonaws.com
    SourceArn: !GetAtt PatrolScheduleRule.Arn
```

---

## PHASE 3: Monitoring & Alerts (Week 3)

### 3.1: CloudWatch Alarms

**Create alarm for CRITICAL findings:**

```yaml
CriticalAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: DataQuality-CriticalFindings
    AlarmDescription: Data patrol critical findings
    MetricName: CriticalFindings
    Namespace: StockAlgo/DataQuality
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 1
    ComparisonOperator: GreaterThanOrEqualToThreshold
    AlarmActions:
      - !Ref AlertTopic
    TreatMissingData: notBreaching
```

### 3.2: SNS Topic

```yaml
AlertTopic:
  Type: AWS::SNS::Topic
  Properties:
    TopicName: algo-data-quality-alerts
    DisplayName: Data Quality Alerts
    Subscription:
      - Endpoint: ops-team@example.com
        Protocol: email
      - Endpoint: !Ref SlackWebhookURL
        Protocol: https
```

---

## PHASE 4: Testing & Validation (Week 4)

### 4.1: Test Checklist

- [ ] P12 catches stale earnings_estimates
- [ ] P13 catches missing ETF prices
- [ ] P14 detects coverage drops (simulate with UPDATE)
- [ ] P15 validates fundamental data freshness
- [ ] CloudWatch metrics publish correctly
- [ ] SNS alerts trigger on CRITICAL
- [ ] Patrol completes in <5min
- [ ] All 18 checks run successfully

### 4.2: Load Testing

```bash
# Run patrol against full database
time python3 algo_data_patrol.py

# Should complete in <5 minutes with all 139 tables available
# Expected: ~2000-3000 rows written to data_patrol_log
```

---

## ROLLOUT PLAN

### Week 1: Development
- Implement P12-P15 in dev branch
- Test locally against staging database
- Code review & QA

### Week 2: Pre-Production
- Deploy to staging
- Run daily for 5 consecutive days
- Verify alert routing
- Document any false positives

### Week 3: Production Preparation
- Set up CloudWatch dashboard
- Configure SNS alerting
- Prepare runbooks
- Train ops team

### Week 4: Production Rollout
- Deploy to production
- Monitor for first 5 runs
- Tune thresholds based on baseline
- Declare success criteria met

---

## Deployment Checklist

### Code Changes
- [ ] P12, P13, P14, P15 added to algo_data_patrol.py
- [ ] loader_contracts updated
- [ ] run() method includes new checks
- [ ] Code tested locally
- [ ] PR reviewed & merged

### Infrastructure
- [ ] CloudWatch namespace created
- [ ] Alarm templates deployed
- [ ] SNS topic created & subscribed
- [ ] EventBridge schedule created
- [ ] Lambda execution role configured
- [ ] Secrets Manager updated (if needed)

### Monitoring
- [ ] CloudWatch dashboard created
- [ ] Alert routing verified
- [ ] Logs aggregated
- [ ] Metrics visible in console

### Documentation
- [ ] Runbook updated
- [ ] Alert escalation procedures
- [ ] How to read patrol results
- [ ] How to investigate findings

---

## Success Metrics

✅ **Performance:**
- Patrol execution: <5min
- E2E alert latency: <30min
- False positive rate: <10%

✅ **Coverage:**
- 18 patrols running (P1-P18)
- All 139 tables monitored
- 100% of loaders tracked

✅ **Reliability:**
- 99.9% patrol success rate
- Zero data issues reach trading
- Ops response time <1 hour

---

## Maintenance

### Weekly Tasks
- Review patrol alerts
- Investigate any patterns
- Update thresholds if needed

### Monthly Tasks
- Review patrol effectiveness
- Check coverage metrics
- Update loader contracts as needed

### Quarterly Review
- Audit patrol accuracy
- Assess false positive rate
- Plan next improvements

---

## Questions & Troubleshooting

**Q: How long will patrol take?**  
A: ~3-5 minutes on full database. Can be parallelized for faster execution.

**Q: What if a loader fails?**  
A: P11 (loader_contracts) will catch if row count drops. P12-P15 will catch stale data.

**Q: Can we run patrol before market open?**  
A: Yes, schedule for 7:00am ET (1 hour before market open at 8:30am).

**Q: What's the retention policy?**  
A: data_patrol_log table should retain 2 years of audit trails (costs ~100MB/year).

---

**Status:** Ready for implementation  
**Owner:** Data Platform Team  
**Next Review:** After Week 1 implementation  
