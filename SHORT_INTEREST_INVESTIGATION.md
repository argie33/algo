# Short Interest Data Source Investigation

**Goal:** Find working short interest data source to replace broken FINRA  
**Status:** In Progress

---

## Current Problem

- **FINRA CSV endpoints:** All 404 (broken)
- **Current coverage:** 0%
- **Potential impact if fixed:** +10-15% positioning metrics coverage

---

## Alternative Data Sources to Investigate

### 1. FINRA Official Site (Status: Research needed)
- Main page: https://www.finra.org/filing-and/short-sale-volume-data → 404
- Try direct archive: https://www.finra.org/research/data
- Try new FINRA API: https://api.finra.org/data/
- **Next step:** Check if FINRA has new API documentation or data portal

### 2. SEC EDGAR (Direct Form SHO-13)
- SEC publishes Form SHO-13 (Reg SHO short sale volume)
- Available via: https://www.sec.gov/cgi-bin/viewer
- **Challenge:** Would need to parse per-filing, slower than CSV
- **Advantage:** Official source, no third-party dependency
- **Next step:** Check if SEC EDGAR API has structured endpoint

### 3. Free/Open Sources
- **MarketWatch:** Publishes short interest (could scrape or use API)
- **Yahoo Finance:** Has shortPercentOfFloat (but rate-limited)
- **Finviz:** Publishes short interest (may require API key)
- **Alternative Finance APIs:** 
  - Alpha Vantage (might have short interest)
  - IEX Cloud (check if available)
  - Polygon.io (may have short data)

### 4. Paid/Premium Sources (Not suitable)
- Bloomberg Terminal
- FactSet
- Refinitiv

---

## Recommended Investigation Order

1. **FINRA Current Status** (5 min)
   - Check if FINRA has new data portal
   - Look for API documentation
   - Search GitHub for working FINRA fetchers

2. **SEC EDGAR SHO-13 Option** (10 min)
   - Check SEC API for Form SHO-13
   - Assess parsing complexity

3. **Free API Options** (10 min)
   - Try Alpha Vantage, IEX Cloud, Polygon.io
   - Check coverage and rate limits

4. **Web Scraping Option** (20 min)
   - MarketWatch or Finviz
   - Assess stability and legal implications

---

## Success Criteria

✅ **Minimal success:** Find any working source with 50%+ coverage  
✅ **Good success:** Find source with 70%+ coverage  
✅ **Excellent success:** Find official source (FINRA or SEC) with 80%+ coverage

---

## Next Steps

1. Research current FINRA availability
2. Test alternative sources
3. Implement best option in load_short_interest_finra.py
4. Update loaders to use new source

