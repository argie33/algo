# Phase 2 Monitoring: Form 4 Parsing Failure Detection

**Session:** 251  
**Goal:** Add CloudWatch monitoring and alerting for Form 4 parsing failures to detect Phase 2 data quality issues before they impact insider holdings data.

## Overview

Phase 2 of the yfinance optimization relies on SEC Form 4 plain-text parsing to extract insider transaction data. The parsing is complex (HTML preprocessing, regex-based extraction) and can fail for various reasons:

- **HTML Stripping Failures** — SEC files contain embedded HTML markup
- **Insider Name Extraction Failures** — Parser cannot extract insider name from Form 4
- **Shares Owned Extraction Failures** — Cannot extract current holdings
- **Ownership % Extraction Failures** — Cannot extract ownership percentage
- **Transaction Extraction Failures** — Cannot extract buy/sell activity

This monitoring system tracks these failures in production to ensure data quality is maintained.

## Architecture

### 1. Metrics Emission (`utils/monitoring/form4_parsing_metrics.py`)

Centralized metrics instrumentation for Form 4 parsing:

- **`put_form4_parsing_metric()`** — Emit raw CloudWatch metric
- **`track_form4_parsing_error()`** — Track parsing failures by error type
- **`track_form4_parsing_success()`** — Track successful parses

#### Modes

- **LOCAL_MODE** (`LOCAL_MODE=1`): Metrics logged to stderr (no AWS calls)
- **AWS_MODE** (default): Metrics sent to CloudWatch for production visibility

### 2. Parser Instrumentation (`utils/external/form4_plaintext_parser.py`)

Form 4 parser calls metrics tracking at critical failure points:

```python
# Failure paths:
track_form4_parsing_error(symbol, "invalid_content", "non_string_or_empty")
track_form4_parsing_error(symbol, "insider_name_extraction_failed")
track_form4_parsing_error(symbol, "shares_owned_extraction_failed")
track_form4_parsing_error(symbol, "ownership_pct_extraction_failed")

# Success path:
track_form4_parsing_success(symbol)
```

### 3. CloudWatch Metrics

Metrics sent to namespace: `Algo/Form4Parsing`

#### Metrics

| Metric | Dimensions | Unit | Purpose |
|--------|-----------|------|---------|
| `ParsingFailure` | Symbol, FailureReason, FilingFormat | Count | Track individual parsing failures |
| `ParsingSuccess` | Symbol, FilingFormat | Count | Track successful parses (data quality baseline) |

#### Dimensions

- **Symbol** — Stock ticker (max 10 chars, truncated)
- **FailureReason** — Error classification (max 60 chars):
  - `invalid_content`: Content validation failed
  - `insider_name_extraction_failed`: Name extraction failed
  - `shares_owned_extraction_failed`: Holdings extraction failed
  - `ownership_pct_extraction_failed`: Ownership % extraction failed
  - `html_stripping_failed`: HTML preprocessing failed
  - `parsing_returned_none`: Parser returned None
- **FilingFormat** — `plaintext` or `xbrl`

### 4. CloudWatch Alarms (Terraform)

File: `terraform/modules/monitoring/phase2-form4-monitoring.tf`

#### Alarms

1. **Form 4 Parsing Failures High** — Alert when ≥10 failures in 1 hour
   - Threshold: 10 failures/hour
   - Action: SNS notification to ops team
   - Severity: Warning

2. **Form 4 Parsing Success Rate Low** — Alert when <5 successes in 1 hour
   - Threshold: <5 successes/hour
   - Action: SNS notification
   - Severity: Warning (data coverage degraded)

### 5. CloudWatch Dashboard (`terraform/modules/monitoring/phase2-form4-monitoring.tf`)

Dashboard name: `{project}-form4-parsing-health-{environment}`

#### Widgets

1. **Success/Failure Rate** (5-min windows)
   - Line chart of `ParsingSuccess` and `ParsingFailure`
   - Trend identification

2. **Failure Breakdown by Type**
   - Stacked bars: Name extraction, shares extraction, ownership extraction
   - Identify most common failure modes

3. **Most Common Parsing Failures**
   - Top 10 failure reasons with counts (24h window)
   - Helps prioritize parser improvements

4. **Top 20 Symbols: Successful Parsing**
   - Which stocks parse successfully most often
   - Baseline for comparison

## Testing

### Unit Tests

File: `tests/unit/monitoring/test_form4_parsing_metrics.py`

Tests verify:
- ✅ LOCAL_MODE disables AWS calls
- ✅ AWS_MODE emits metrics to CloudWatch
- ✅ Failure tracking works correctly
- ✅ Success tracking works correctly
- ✅ Graceful handling of CloudWatch errors

All tests pass: `pytest tests/unit/monitoring/test_form4_parsing_metrics.py`

### Integration Tests

Form 4 parser tests verify metric instrumentation:
- ✅ `test_form4_plaintext_parser.py` (15 tests passing)
- All parsing failure paths tracked with metrics

## Deployment

### Local Development

```bash
# Metrics disabled in LOCAL_MODE
export LOCAL_MODE=1
python loaders/load_insider_holdings_sec.py
```

No AWS credentials required. Metrics logged to stderr.

### Production (AWS)

```bash
# Metrics enabled by default
python loaders/load_insider_holdings_sec.py
```

Requires AWS credentials with CloudWatch `put_metric_data` permission:

```json
{
  "Effect": "Allow",
  "Action": "cloudwatch:PutMetricData",
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "cloudwatch:namespace": "Algo/Form4Parsing"
    }
  }
}
```

### Terraform Deployment

Apply monitoring stack:

```bash
terraform apply -target=module.monitoring
# Creates: alarms, SNS topic, dashboard, log group
```

## Operational Use Cases

### Use Case 1: Investigate Form 4 Parsing Spike

**Scenario:** CloudWatch alarm "Form 4 Parsing Failures High" triggered

**Steps:**
1. Open CloudWatch Dashboard: `{project}-form4-parsing-health`
2. Check "Failure Breakdown by Type" — identify most common failure
3. Open CloudWatch Logs: `/algo/form4-parsing`
4. Filter by `FailureReason` to see affected symbols
5. Sample 2-3 failing Form 4s from SEC EDGAR to diagnose

**Example:** If "insider_name_extraction_failed" spike:
- Likely SEC changed Form 4 layout
- Update `Form4PlaintextParser._extract_insider_name()` patterns
- Add regression test with new format

### Use Case 2: Monitor Coverage Improvement

**Scenario:** Roll out parser improvement for HTML stripping

**Before/After:**
- Check "Success Rate" widget
- Compare to baseline (before deployment)
- Success count should increase

### Use Case 3: Alert on Data Quality Regression

**Scenario:** Success rate drops below 5/hour

**Investigation:**
1. Check "Most Common Failures" — what changed?
2. Review recent loader/parser code changes
3. Check SEC EDGAR for format changes
4. Validate sample Form 4 files manually

## Error Handling

### Graceful Degradation

Metric emission failures don't block parsing:

```python
try:
    cloudwatch.put_metric_data(...)
except Exception as e:
    logger.warning(f"Failed to emit metric: {e}")
    # Continue parsing — metrics are optional
```

### Missing AWS Credentials

- LOCAL_MODE: No credentials needed (stderr logging)
- AWS_MODE without credentials: Logs warning, continues parsing
- CI/CD without AWS: Set `LOCAL_MODE=1` in test env

## Future Enhancements

1. **Per-Symbol Failure Tracking**
   - Track which symbols consistently fail
   - Identify systemic parsing issues vs. rare edge cases

2. **Parsing Performance Metrics**
   - Track parsing duration per symbol
   - Alert if parsing takes >30s (timeout risk)

3. **Form 4 Format Versioning**
   - Track SEC layout changes
   - Automated regression test generation

4. **Insider Holdings Completeness**
   - Track % of symbols with successful Form 4 parse
   - Alert if coverage drops below 60%

5. **Alert Routing**
   - Route SEC format issues to data team
   - Route AWS issues to ops team

## References

- **Parser:** `utils/external/form4_plaintext_parser.py`
- **Metrics:** `utils/monitoring/form4_parsing_metrics.py`
- **Loader:** `loaders/load_insider_holdings_sec.py`
- **Terraform:** `terraform/modules/monitoring/phase2-form4-monitoring.tf`
- **Tests:** `tests/unit/monitoring/test_form4_parsing_metrics.py`

## Metrics Namespace

All Form 4 metrics use CloudWatch namespace: **`Algo/Form4Parsing`**

Query examples (CloudWatch Logs Insights):

```
# All failures in last hour
fields @timestamp, symbol, reason
| filter @message like /Form4.*extraction_failed/
| stats count() as failure_count by reason

# Success rate by hour
fields @timestamp
| filter @message like /parsing_succeeded/
| stats count() as success_count by bin(1h)

# Failures affecting specific symbol
fields @timestamp, reason
| filter symbol = "AAPL"
| stats count() as failures by reason
```
