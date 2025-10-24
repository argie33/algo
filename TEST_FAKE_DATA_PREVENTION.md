# Fake Data Prevention Test Suite

Comprehensive tests to prevent regression of hardcoded/fake data in sentiment and correlation analysis.

## Overview

This test suite validates that the system returns **real data or NULL**, never fake/hardcoded values.

## Python Tests: Sentiment Data Validation

**File:** `test_sentiment_real_data.py`

### Test Cases

#### 1. Reddit Sentiment Without API
```python
test_reddit_sentiment_without_client_returns_null()
```
- Validates that missing Reddit API returns NULL, not fake data
- Ensures no hardcoded fallback values when API unavailable

#### 2. Google Trends Data Validation
```python
test_google_trends_returns_real_data_or_null()
```
- Checks that Google Trends returns:
  - Real search volume index (0-100) OR NULL
  - Real trend calculations OR NULL
  - Never hardcoded defaults

#### 3. No Hardcoded Sentiment Defaults
```python
test_no_hardcoded_sentiment_defaults()
```
- Rejects hardcoded 0.5 values (neutral default)
- Validates sentiment scores are real (-1 to 1) or NULL
- Prevents masking missing data with fake defaults

#### 4. No Random Data Generation
```python
test_no_numpy_random_in_sentiment()
```
- Verifies sentiment collection is deterministic
- Running same function twice returns same results (no np.random)
- No fake data injection through randomization

#### 5. Sentiment Score Determinism
```python
test_sentiment_score_calculation_deterministic()
```
- TextBlob sentiment analysis returns same score for same text
- Not influenced by random number generation
- Repeatable and verifiable

#### 6. Confidence Score Completeness-Based
```python
test_confidence_based_on_data_completeness()
```
- Confidence varies based on data availability:
  - 0% data → NULL
  - 50% data → ~0.70 confidence
  - 100% data → ~0.95 confidence
- NOT hardcoded 90% for all cases

#### 7. Missing API Handling
```python
test_missing_reddit_api_returns_null()
```
- When Reddit API not configured, returns NULL for all sentiment fields
- Prevents silent failures with fake data

#### 8. Data Pattern Validation
```python
test_reject_hardcoded_patterns()
```
- Rejects known hardcoded values: 0.5, 0.0, 1.0, -1.0
- Ensures data comes from real sources or is NULL

### Running Python Tests

```bash
cd /home/stocks/algo
python3 -m pytest test_sentiment_real_data.py -v
# Or:
python3 test_sentiment_real_data.py
```

## JavaScript Tests: Correlation Data Validation

**File:** `test_correlation_real_data.js`

### Test Cases

#### 1. Pearson Correlation Calculation
```javascript
test_pearson_correlation_calculation()
```
- Validates mathematical correctness of Pearson coefficient
- Test cases:
  - Identical returns: correlation = 1.0 ✓
  - Insufficient data: returns NULL ✓
  - Realistic mixed returns: varies based on data ✓
  - Negatively correlated: correlation < -0.9 ✓

#### 2. No Hardcoded Tech-Tech Correlation (0.6)
```javascript
test_should_not_have_hardcoded_tech_tech_correlation()
```
- Previously all tech stocks had hardcoded 0.6 correlation
- Now: Calculate from real price data
- Real SPY-QQQ correlation is ~0.85, not always 0.6

#### 3. No Hardcoded ETF-ETF Correlation (0.7)
```javascript
test_should_not_have_hardcoded_etf_etf_correlation()
```
- Previously all ETF pairs had hardcoded 0.7
- Now: Calculated from actual price movements
- Varies based on real data (e.g., SPY-IWM ~0.75)

#### 4. No Hardcoded Pattern Values
```javascript
test_should_not_return_hardcoded_pattern_values()
```
- Rejects hardcoded values: 0.1, 0.4, 0.6, 0.7
- These should only appear if they're actual correlation results
- Not from if-then pattern matching logic

#### 5. NULL When Data Insufficient
```javascript
test_should_return_null_when_data_insufficient()
```
- Missing price data returns NULL, not 0.5
- Prevents false correlations with insufficient evidence

#### 6. Matrix Properties
```javascript
test_diagonal_should_be_1_0()
test_matrix_should_be_symmetric()
test_correlations_should_be_bounded()
```
- Diagonal: Symbol with itself = 1.0
- Symmetry: correlation(A,B) = correlation(B,A)
- Range: All values in [-1, 1]

### Running JavaScript Tests

```bash
cd /home/stocks/algo
npm test -- test_correlation_real_data.js
# Or with jest:
jest test_correlation_real_data.js --verbose
```

## Data Cleanup Script

**File:** `cleanup_sentiment_data.py`

Removes or updates fake/hardcoded data from database:
- Replaces hardcoded 0.5 values with NULL
- Removes suspiciously small/random sentiment values
- Reports data quality statistics

```bash
python3 cleanup_sentiment_data.py
```

## Test Results Interpretation

### ✅ PASS - All Checks
System is returning real data:
- Sentiment: Real Google Trends data, real Reddit sentiment, real news sentiment
- Correlations: Calculated from actual price movements
- Confidence: Based on data completeness

### ❌ FAIL - Fake Data Detected
Look for:
- Hardcoded sentiment values (0.5, 0.0)
- Hardcoded correlation values (0.6, 0.7, 0.4, 0.1)
- Random number patterns in sentiment scores
- Constant confidence scores (all 90%)

## Running Full Test Suite

```bash
# Python tests
python3 -m pytest test_sentiment_real_data.py -v

# JavaScript tests  
npm test -- test_correlation_real_data.js --verbose

# Database cleanup
python3 cleanup_sentiment_data.py
```

## Continuous Integration

Add to CI/CD pipeline:

```yaml
# .github/workflows/test.yml
- name: Run fake data prevention tests
  run: |
    python3 -m pytest test_sentiment_real_data.py -v
    npm test -- test_correlation_real_data.js
```

## What's Being Tested

### Removed Fake Data

| Issue | Before | After | Test |
|-------|--------|-------|------|
| Reddit sentiment | np.random scores | Real API or NULL | `test_reddit_sentiment_without_client_returns_null` |
| Google Trends | None (now implemented) | Real search data | `test_google_trends_returns_real_data_or_null` |
| Tech correlations | Hardcoded 0.6 | Calculated from returns | `test_should_not_have_hardcoded_tech_tech_correlation` |
| ETF correlations | Hardcoded 0.7 | Calculated from returns | `test_should_not_have_hardcoded_etf_etf_correlation` |
| Confidence scores | Hardcoded 90% | Data-based (50-95%) | `test_confidence_based_on_data_completeness` |
| News sentiment | Hardcoded 0.5 | Real analysis or NULL | `test_no_hardcoded_sentiment_defaults` |

## Related Documentation

- `HARDCODED_DATA_FIXES_SUMMARY.md` - Complete list of all fixes
- `loadsentiment.py` - Real sentiment data collection
- `webapp/lambda/routes/market.js` - Real correlation calculations
