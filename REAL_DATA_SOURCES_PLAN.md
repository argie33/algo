# Real Data Sources Integration Plan

## Overview
Replace all fake/hardcoded data with real data from legitimate sources.

---

## 1. SENTIMENT DATA - Google Trends & Reddit

### Google Trends (FREE - No API Key Required)
**Library**: `pytrends` (already partially implemented)
**Data**: Search volume index (0-100 relative to peak), search trends

**What We Get**:
- Stock symbol search volume
- 7-day trend (% change from 7 days ago)
- 30-day trend (% change from 30 days ago)

**Implementation Status**: Partially done, needs:
- Install `pytrends` package
- Fix fallback logic to use real data instead of random
- Add proper error handling

**Code Location**: `loadsentiment.py` lines 276-331

---

### Reddit Sentiment (FREE - Requires Setup)
**Library**: `PRAW` (Python Reddit API Wrapper)
**Data**: Mention counts, user engagement, sentiment from discussions

**Setup Required**:
1. Go to https://www.reddit.com/prefs/apps
2. Create "script" app
3. Get credentials: Client ID, Client Secret
4. Store in AWS Secrets Manager

**What We Get**:
- Mention count in r/stocks, r/wallstreetbets, r/investing
- Comment sentiment analysis (positive/negative/neutral)
- Trend direction (rising/falling mentions)

**Implementation Status**: Needs creation
- Create new PRAW client initialization
- Define subreddit search terms
- Implement sentiment analysis using TextBlob

**Code Location**: `loadsentiment.py` lines 240-274

---

## 2. CORRELATION MATRICES - Real Historical Price Data

### Economic Correlations (FRED API)
**Already Available**: FRED_API_KEY environment variable is configured
**Data**: Historical economic series (GDP, inflation, unemployment, etc.)

**Implementation**:
```python
# Calculate Pearson correlation from economic_data table
from scipy.stats import pearsonr

def calculate_economic_correlations():
    # Get overlapping date ranges for series1 and series2
    # Calculate correlation coefficient
    corr, p_value = pearsonr(series1_values, series2_values)
    return corr  # Returns -1.0 to 1.0
```

**Code Location**: `webapp/lambda/routes/economic.js` lines 808-820

---

### Market Correlations (Price Daily Data)
**Data Already Available**: `price_daily` table has historical prices
**Calculation**: Pearson correlation of daily returns

**Implementation**:
```python
# Calculate returns: (close[t] - close[t-1]) / close[t-1]
# Then calculate correlation of returns vectors
def calculate_market_correlations(symbol1, symbol2):
    returns1 = calculate_daily_returns(prices1)
    returns2 = calculate_daily_returns(prices2)
    corr, _ = pearsonr(returns1, returns2)
    return corr  # Returns -1.0 to 1.0
```

**Code Location**: `webapp/lambda/routes/market.js` lines 5000-5043

---

## 3. PRICING DATA - yfinance (Already Working)
**Status**: Already implemented in multiple loaders
**Source**: Yahoo Finance via `yfinance` library
**Data**: OHLCV (Open, High, Low, Close, Volume)

**Used By**:
- `loadpricedaily.py` - Historical daily prices
- `loadtechnicalsdaily.py` - Technical indicators
- All charting endpoints

**No Changes Needed** - This is working well

---

## 4. ANALYST SENTIMENT - yfinance
**Status**: Partially implemented
**Source**: Yahoo Finance analyst recommendations

**Used By**:
- `loadsanalystsentiment.py` - Analyst ratings and targets
- Market overview analyst consensus

**Enhancements**:
- Use analyst upgrade/downgrade history
- Weight by analyst reputation/tier

---

## Implementation Roadmap

### Phase 1: CRITICAL (This Week)
- [ ] Fix correlation matrices (economic + market)
  - Implement Pearson correlation calculation
  - Remove hardcoded values
  - Test with sample data

### Phase 2: HIGH (Next Week)
- [ ] Setup Reddit API credentials
  - Register app on reddit.com
  - Store credentials in Secrets Manager
  - Implement PRAW integration

- [ ] Fix Google Trends loader
  - Install `pytrends` package
  - Remove random fallback
  - Implement proper error handling

- [ ] Create real sentiment calculation
  - Use TextBlob for sentiment analysis
  - Combine Reddit + Google Trends
  - Store in database

### Phase 3: ENHANCEMENT (Later)
- [ ] Implement holder quality scoring
- [ ] Enhance confidence calculations
- [ ] Add more sentiment sources (Twitter alternative, etc.)

---

## Data Source Dependencies

| Data | Source | Status | API Key Required | Library |
|------|--------|--------|------------------|---------|
| Prices (OHLCV) | yfinance | ✓ Working | No | yfinance |
| Analyst Sentiment | yfinance | ✓ Working | No | yfinance |
| Economic Data | FRED | ✓ Configured | Yes (have it) | pandas-datareader |
| Google Trends | Google | 🔴 Fake Data | No | pytrends |
| Reddit Sentiment | Reddit | 🔴 Fake Data | Yes (need setup) | praw |
| Correlation | Database | 🔴 Hardcoded | No | scipy |

---

## Required Python Packages

### Already Have (in requirements files):
- yfinance
- pandas
- numpy
- requests
- boto3
- psycopg2
- pandas-datareader (for FRED)

### Need to Add:
```
pytrends==4.9.2      # Google Trends (no API key)
praw==7.7.0          # Reddit API wrapper
textblob==0.17.1     # Sentiment analysis
scipy==1.11.4        # Statistical functions
```

### Optional:
```
nltk>=3.8.1          # Natural Language Processing
```

---

## Secrets Manager Setup

### Current (Database):
```
DB_SECRET_ARN = "arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-fl3BxQ"
```

### Need to Add (Reddit):
```json
{
  "reddit_client_id": "your_client_id",
  "reddit_client_secret": "your_client_secret",
  "reddit_user_agent": "StocksApp/1.0",
  "reddit_username": "optional_username",
  "reddit_password": "optional_password"
}
```

---

## Testing Strategy

### 1. Google Trends
```python
from pytrends.request import TrendReq

pytrends = TrendReq(hl='en-US', tz=360)
pytrends.build_payload(['AAPL'], cat=0, timeframe='today 1-m')
data = pytrends.interest_over_time()
print(data)  # Should show real AAPL search volume
```

### 2. Reddit
```python
import praw

reddit = praw.Reddit(client_id='...', client_secret='...', user_agent='...')
results = reddit.subreddit('stocks').search('AAPL')
# Process mentions and sentiment
```

### 3. Correlations
```python
from scipy.stats import pearsonr

corr, p_value = pearsonr(series1, series2)
print(f"Correlation: {corr:.3f}")  # Should be between -1.0 and 1.0
```

---

## Migration Path (Zero Downtime)

1. **Deploy new code** with both old (hardcoded) and new (real) implementations
2. **Use feature flag** to switch between real and fake data
3. **Test with real data** in staging environment
4. **Gradually enable** for small percentage of users
5. **Monitor for issues** (missing data, API failures)
6. **Fully switch** once stable
7. **Remove** old hardcoded code

---

## Success Criteria

✅ All sentiment data comes from Google Trends or Reddit
✅ All correlations calculated from real price/economic data
✅ No hardcoded values in production code
✅ Graceful fallback to NULL if APIs unavailable
✅ Database stores only real data (clear old fake data)
✅ Unit tests verify real data format

---

## Risk Mitigation

**Risk**: API failures cause "N/A" data
**Mitigation**: Graceful fallback, cached recent data

**Risk**: Rate limits on APIs
**Mitigation**: Implement caching, batch requests, stagger loads

**Risk**: Data quality issues
**Mitigation**: Validation checks, data quality metrics

---

## Next Steps

1. **Assign**: Who sets up Reddit API credentials?
2. **Install**: Add packages to requirements files
3. **Implement**: Phase 1 (correlations) - This week
4. **Test**: Create test suite for real data
5. **Deploy**: Follow zero-downtime migration

