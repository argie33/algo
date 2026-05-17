# Cleanup Checklist — Remove Incomplete Features

## Feature 1: analyst_sentiment_analysis

### Files to Delete/Modify
- [ ] Delete loader: `loaders/loadanalystsentiment.py`
- [ ] Delete loader: `loaders/loadanalystupgradedowngrade.py`  
- [ ] Remove from init_database.py: `analyst_sentiment_analysis` table creation
- [ ] Delete API route: `webapp/lambda/routes/analystSentiment.js`
- [ ] Delete API route: `webapp/lambda/routes/analystInsights.js`
- [ ] Remove from lambda_function.py: analyst_sentiment route handler
- [ ] Delete any frontend components referencing analyst data

### Verification
- [ ] Grep for analyst_sentiment_analysis in codebase (should find nothing)
- [ ] Grep for analyst insights API calls (should find nothing)

---

## Feature 2: mean_reversion_signals_daily

### Files to Delete/Modify
- [ ] Remove from init_database.py: `mean_reversion_signals_daily` table creation
- [ ] Delete API route: `webapp/lambda/routes/meanReversionSignals.js`
- [ ] Remove from lambda_function.py: mean_reversion route handler
- [ ] Delete any frontend components referencing mean reversion
- [ ] Remove any imports/references in orchestrator

### Verification
- [ ] Grep for mean_reversion_signals (should find nothing in code, only in git history)

---

## Feature 3: range_signals_daily_etf

### Files to Delete/Modify  
- [ ] Remove from init_database.py: `range_signals_daily_etf` table creation
- [ ] Delete API route: `webapp/lambda/routes/rangeSignals.js`
- [ ] Remove from lambda_function.py: range_signals route handler
- [ ] Delete any frontend components
- [ ] Remove any ETF-specific references

### Verification
- [ ] Grep for range_signals_daily_etf (should find nothing)

---

## After Cleanup

- [ ] Verify DATABASE schema by running: `python3 init_database.py --verify`
- [ ] Verify no orphaned loaders exist
- [ ] Verify no orphaned API routes exist
- [ ] Test all remaining 16 APIs
- [ ] Test all 19+ frontend pages
- [ ] Commit changes with message: "cleanup: Remove incomplete signal features (analyst_sentiment, mean_reversion, range_signals)"

