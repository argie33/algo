# Positioning Metrics - Coverage Improvement Roadmap

**Current Coverage:** 58.9% (2,806/4,761 stocks)  
**Breakdow:**
- Institutional: 53.6% (2,552 stocks from yfinance)
- Short Interest: 0% (FINRA offline)
- Insider: 0% (Form 4/5 not implemented)

---

## Implementation Tasks (Priority Order)

### Task 1: Short Interest - MarketWatch Web Scraper (2-3 hours, +10% potential)
**Status:** Not started  
**Priority:** HIGH (highest ROI)  
**Effort:** 2-3 hours

**What to do:**
```
1. Create utils/marketwatch_short_interest.py scraper
   - Fetch AAPL page: https://www.marketwatch.com/investing/stock/AAPL
   - Parse short interest % from page HTML
   - Handle rate limiting with delays

2. Update loaders/load_short_interest_finra.py
   - If FINRA unavailable → fallback to MarketWatch scraper (MARKED as source)
   - Log source in data_source field

3. Test: Run loader, verify short interest coverage increases
```

**Risks:**
- MarketWatch may change HTML structure (fragile)
- Rate limiting if too fast
- MarketWatch may block scrapers

**Expected result:** +10-15% coverage (500-750 stocks)

---

### Task 2: Institutional Holdings - Form 13F Aggregator (4-8 hours, +5-10% potential)
**Status:** Not started  
**Priority:** MEDIUM (complex but real SEC data)  
**Effort:** 4-8 hours

**What to do:**
```
1. Create utils/sec_form13f_aggregator.py
   - Use SecEdgarClient.get_submissions(cik) to list Form 13F filings
   - For each 13F filing:
     - Extract holdings data
     - Aggregate by symbol
     - Calculate % of shares outstanding

2. Update loaders/load_institutional_holdings_13f.py
   - Call aggregator before falling back to yfinance
   - Mark source as "sec_form13f"

3. Test: Run on sample symbols (AAPL, MSFT, TSLA)
   - Verify coverage and accuracy
```

**Risks:**
- Form 13F parsing complexity (various formats)
- SEC rate limiting (need parallelism tuning)
- Coverage won't reach 100% (not all companies in 13F database)

**Expected result:** +5-10% coverage (350-700 stocks)

---

### Task 3: Insider Holdings - Form 4/5 Parser (8-16 hours, +5-10% potential)
**Status:** Not started  
**Priority:** LOW (complex, lower ROI)  
**Effort:** 8-16 hours

**What to do:**
```
1. Create utils/sec_form4_parser.py
   - Use SecEdgarClient.get_filings_plaintext() for Form 4 files
   - Parse: number of insiders, recent buy/sell, net change
   - Extract insider ownership % from calculations

2. Update loaders/load_insider_holdings_sec.py
   - Call parser instead of just marking unavailable
   - Handle parsing errors gracefully

3. Test & iterate on sample filings
```

**Risks:**
- Plain-text parsing is fragile (many format variations)
- Takes significant effort
- Coverage may be limited for small companies

**Expected result:** +5-10% coverage (250-500 stocks)

---

## Implementation Sequence Recommendation

### Phase 1: Quick Win (2-4 hours)
**Start:** MarketWatch scraper (Task 1)
- Highest ROI (2-3 hours → +10-15% coverage)
- Lowest complexity
- Can be done this week

### Phase 2: Real SEC Data (4-8 hours)
**Start:** Form 13F aggregator (Task 2) - IF MarketWatch succeeds
- Medium complexity
- Real SEC source (replaces yfinance for institutional)
- Can start next week

### Phase 3: Comprehensive (8-16 hours)
**Start:** Form 4/5 parser (Task 3) - IF business value justifies
- Highest complexity
- Lower ROI compared to effort
- Can defer to following week/month

---

## How to Implement Each Task

### MarketWatch Scraper Template
```python
# utils/marketwatch_short_interest.py
import requests
from bs4 import BeautifulSoup
import time

class MarketWatchShortInterestFetcher:
    """Scrape short interest % from MarketWatch."""
    
    def fetch_short_interest(self, symbol: str) -> float | None:
        """Fetch short interest % for symbol.
        
        Returns: Short interest as percentage (0-100), or None if unavailable
        """
        try:
            url = f"https://www.marketwatch.com/investing/stock/{symbol.upper()}"
            response = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            }, timeout=10)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for "Short Interest %" in page
            # Pattern: look for text containing "Short" then find nearby percentage
            # This is example - actual pattern will vary
            for elem in soup.find_all(string=lambda text: text and 'short' in text.lower()):
                # Try to extract percentage from nearby elements
                pass
            
            time.sleep(0.5)  # Rate limit
            return None  # Placeholder
            
        except Exception as e:
            return None
```

### Form 13F Aggregator Template
```python
# utils/sec_form13f_aggregator.py
from utils.external.sec_edgar_client import SecEdgarClient

class Form13FAggregator:
    """Aggregate Form 13F filings to get institutional ownership %."""
    
    def get_institutional_ownership_pct(self, symbol: str, cik: str) -> float | None:
        """Calculate institutional ownership % by aggregating Form 13F filings.
        
        Returns: Institutional ownership as percentage (0-100), or None if unavailable
        """
        client = SecEdgarClient()
        
        try:
            submissions = client.get_submissions(cik)
            recent = submissions['filings']['recent']
            
            # Find all 13F filings
            total_shares = None
            institutional_shares = 0
            
            for i, form in enumerate(recent['form']):
                if form == '13F-HR':
                    accession = recent['accessionNumber'][i]
                    filing_date = recent['filingDate'][i]
                    
                    # Parse 13F filing
                    # Extract holdings and aggregate by symbol
                    pass
            
            if total_shares and total_shares > 0:
                return (institutional_shares / total_shares) * 100
            
            return None
            
        except Exception as e:
            return None
```

---

## Testing Strategy

### For MarketWatch Scraper
```
1. Test symbols: AAPL, MSFT, TSLA, AMZN, GOOGL
   - Verify short interest % is reasonable (0-100%)
   - Compare against other sources if available
   - Check HTML doesn't change between runs

2. Run loader: python3 loaders/load_short_interest_finra.py
   - Check database for short_interest_finra records
   - Verify source shows "marketwatch" or similar
   - Confirm coverage increases from 0%
```

### For Form 13F Aggregator
```
1. Test on 10 random symbols
   - Verify parsing doesn't crash
   - Compare coverage vs expected (~50-70% of companies)
   - Check calculated % is reasonable (0-100%)

2. Run loader: python3 loaders/load_institutional_holdings_13f.py
   - Check database for new sec_form13f records
   - Verify source shows "sec_form13f"
   - Confirm coverage increases from 8.7%
```

---

## Success Criteria

### If All Implemented
- Short interest: 0% → 10-15%
- Institutional holdings: 8.7% → 15-20%
- Insider holdings: 0% → 5-10%
- **Overall positioning coverage: 58.9% → 75-85%**
- **Stock scores tradeable: 53.4% → 65-75%**

### Realistic Target (Scraper + Form 13F)
- Overall positioning: 58.9% → 70-75%
- Stock scores: 53.4% → 60-65%

---

## Current Status
- ✅ Task 1 design: Ready to implement
- ✅ Task 2 design: Ready to implement
- ✅ Task 3 design: Ready to implement
- ⏳ Implementation: Not started (ready for next session)

---

## Notes for Implementation
- All source data must be marked in database (source_tracking, data_source)
- All parsing failures must mark data_unavailable=TRUE (fail-fast)
- Rate limiting required for web scraping and SEC APIs
- Error handling must log clearly for operator visibility
- Test coverage should verify both success and failure paths

