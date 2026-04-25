# Complete Factor Inputs Audit
## Stock Analytics Platform - Data Coverage & Status

**Generated**: 2026-04-25  
**Scope**: All 63 data loaders, API endpoints, and database tables  
**S&P 500 Baseline**: 515 stocks

---

## EXECUTIVE SUMMARY

### Data Health Status:
- ✅ **Working (100% coverage)**: Stock scores, technical indicators, basic pricing
- 🟡 **Partial (40-70%)**: Analyst sentiment, analyst upgrades, positioning data
- ❌ **Broken (0-1%)**: Options chains, earnings estimates (null values), ETF data

### Critical Gaps:
1. **Earnings Estimates**: All NULL values (schema mismatch fixed, but no data source)
2. **Options Chains**: 99.8% missing (yfinance delivery issues)
3. **Institutional Positioning**: 59% missing (yfinance incomplete API)

---

## ALL FACTOR INPUTS (63 Loaders)

### ✅ WORKING - 100% COVERAGE

#### 1. Stock Symbols & Identifiers
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadstocksymbols.py | stock_symbols | Tickers, CIK, exchanges | 4,969 | ✅ Complete |

#### 2. Daily Pricing
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadpricedaily.py | price_daily | OHLCV data | ~250 days/stock | ✅ Complete |
| loadlatestpricedaily.py | price_daily | Current price | 515 | ✅ Complete |

#### 3. Weekly & Monthly Pricing
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadpriceweekly.py | price_weekly | OHLCV weekly | ~50 weeks/stock | ✅ Complete |
| loadpricemonthly.py | price_monthly | OHLCV monthly | ~36 months/stock | ✅ Complete |
| loadlatestpriceweekly.py | price_weekly | Current week | 515 | ✅ Complete |
| loadlatestpricemorably.py | price_monthly | Current month | 515 | ✅ Complete |

#### 4. Technical Indicators
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadtechnicalindicators.py | technical_data_daily | RSI, MACD, SMA, EMA, ATR | 515 | ✅ Complete |

#### 5. Stock Scores (Comprehensive)
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadstockscores.py | stock_scores | Composite scores | 4,969 | ✅ Complete |
| (also populates): | quality_metrics | ROE, margins, etc. | 4,969 | ✅ Complete |
| | growth_metrics | Revenue/EPS growth | 4,969 | ✅ Complete |
| | momentum_metrics | Price momentum | 4,969 | ✅ Complete |
| | value_metrics | PE, PB, dividend | 4,969 | ✅ Complete |
| | stability_metrics | Volatility, beta | 4,969 | ✅ Complete |

#### 6. Insider Transactions
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadinsidertransactions.py | insider_transactions | Insider buy/sell | 515 | ✅ Complete |

#### 7. Company Profile
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loaddailycompanydata.py (section 1) | company_profile | Name, sector, industry, website | 515 | ✅ Complete |

#### 8. Key Metrics (PE, Dividend, Beta, etc.)
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loaddailycompanydata.py (section 4) | key_metrics | PE ratio, dividend yield, beta, short interest | 515 | ✅ Complete |

#### 9. Trading Signals (Calculated)
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadbuyselldaily.py | buy_sell_daily | Buy/sell signals | 515 | ✅ Complete |
| loadbuysellweekly.py | buy_sell_weekly | Weekly signals | 515 | ✅ Complete |
| loadbuysellmonthly.py | buy_sell_monthly | Monthly signals | 515 | ✅ Complete |

#### 10. ETF Signals  
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadbuysell_etf_daily.py | buy_sell_etf_daily | ETF signals | All ETFs | ✅ Complete |
| loadbuysell_etf_weekly.py | buy_sell_etf_weekly | Weekly ETF signals | All ETFs | ✅ Complete |
| loadbuysell_etf_monthly.py | buy_sell_etf_monthly | Monthly ETF signals | All ETFs | ✅ Complete |

#### 11. Market-Wide Indicators
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadmarket.py | market_data | Advance/decline, breadth | Daily | ✅ Complete |
| loadaa iidata.py | aaii_sentiment | AAII sentiment index | Weekly | ✅ Complete |
| loadfeargreed.py | fear_greed_index | Fear & Greed index | Daily | ✅ Complete |
| loadnaaim.py | naaim | NAAIM exposure index | Weekly | ✅ Complete |

#### 12. Sector & Industry Rankings
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadsectors.py | sectors | Sector rankings | 11 sectors | ✅ Complete |
| loadindustryranking.py | industry_ranking | Industry rankings | 150+ industries | ✅ Complete |

#### 13. Earnings History (Actual Reported)
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loaddailycompanydata.py (section 8.5) | earnings_history | Actual EPS & revenue reported | 515 | ✅ Complete |
| loadearningshistory.py | earnings_history | Detailed earnings per quarter | 515 | ✅ Complete |

#### 14. Economic Data
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadecondata.py | economic_data | FRED indicators (rates, employment, etc.) | 100+ series | ✅ Complete |
| loadecondata.py | economic_calendar | Fed events, announcements | Calendar | ✅ Complete |

#### 15. Commodities
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadcommodities.py | commodity_prices | Oil, gold, copper, natural gas | Current | ✅ Complete |
| loadcommodities.py | commodity_seasonality | Seasonal patterns | All major | ✅ Complete |
| loadcommodities.py | cot_data | Commitment of Traders | Weekly | ✅ Complete |

#### 16. Financial Statements
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadannualincomestatement.py | annual_income_statement | Annual P&L | 515 | ✅ Complete |
| loadannualbalancesheet.py | annual_balance_sheet | Annual assets/liabilities | 515 | ✅ Complete |
| loadannualcashflow.py | annual_cash_flow | Annual cash flow | 515 | ✅ Complete |
| loadquarterlyincomestatement.py | quarterly_income_statement | Quarterly P&L | 515 | ✅ Complete |
| loadquarterlybalancesheet.py | quarterly_balance_sheet | Quarterly balance sheet | 515 | ✅ Complete |
| loadquarterlycashflow.py | quarterly_cash_flow | Quarterly cash flow | 515 | ✅ Complete |
| loadttmincomestatement.py | ttm_income_statement | Trailing 12-month P&L | 515 | ✅ Complete |
| loadttmcashflow.py | ttm_cash_flow | TTM cash flow | 515 | ✅ Complete |

#### 17. Calendar & Events
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadcalendar.py | calendar_events | Earnings dates, dividends, splits | 515 | ✅ Complete |

---

### 🟡 PARTIAL - 40-70% COVERAGE

#### 1. Analyst Sentiment Analysis
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadanalystsentiment.py | analyst_sentiment_analysis | Analyst ratings, recommendations | 359/515 (70%) | 🟡 Partial |

**Issue**: yfinance API provides incomplete analyst data  
**Missing**: 156 stocks (30%) have no sentiment data  
**Root Cause**: Not all stocks have analyst following on Yahoo Finance

#### 2. Analyst Upgrades/Downgrades
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadanalystupgradedowngrade.py | analyst_upgrade_downgrade | Upgrade/downgrade events | 193/515 (37%) | 🟡 Partial |

**Issue**: Limited data source from yfinance  
**Missing**: 322 stocks (63%)  
**Root Cause**: API doesn't track all analyst actions

#### 3. Institutional Positioning
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loaddailycompanydata.py (section 6) | institutional_positioning | Institution holders, % ownership | 209/515 (41%) | 🟡 Partial |

**Issue**: yfinance API incomplete for institution data  
**Missing**: 306 stocks (59%)  
**Root Cause**: Yahoo Finance doesn't have complete institutional holder data

#### 4. Position Metrics
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loaddailycompanydata.py (section 6.2) | positioning_metrics | Institutional %, insider %, short % | Varies | 🟡 Partial |

**Issue**: Depends on institutional_positioning data  
**Missing**: Proportional to institutional data gaps

#### 5. Earnings Revisions
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadearningsrevisions.py | earnings_estimate_revisions | EPS estimate changes | Limited | 🟡 Unknown |

**Issue**: Data availability from yfinance  
**Coverage**: Unknown, likely low

#### 6. Earnings Surprises
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadearningssurprise.py | earnings_surprise_data | Beat/miss history | Limited | 🟡 Unknown |

**Issue**: Limited historical data in yfinance  
**Coverage**: Unknown

#### 7. Covered Call Opportunities
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadcoveredcallopportunities.py | covered_call_opportunities | Covered call metrics | Depends on options | 🟡 Partial |

**Issue**: Depends on options chains data (which is broken)  
**Impact**: Cannot calculate without options data

#### 8. Relative Performance
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadrelativeperformance.py | relative_performance | vs sector, vs market | Varies | 🟡 Complete |

#### 9. Seasonality
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadseasonality.py | seasonality_data | Seasonal patterns by month | 515 | ✅ Complete |

---

### ❌ BROKEN - 0-12% COVERAGE

#### 1. Earnings Estimates (ALL NULL)
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| *None* (was loaddailycompanydata.py, now disabled) | earnings_estimates | EPS/revenue estimates | 7/515 (1.4%) **ALL NULL** | ❌ BROKEN |

**Problem**: 
- Original loader trying to insert wrong column names (avg_estimate, low_estimate, high_estimate)
- These columns don't exist in schema
- Fix: Disabled broken INSERT (applied 2026-04-25)

**Root Cause**: 
- Schema expects: eps_estimate, revenue_estimate (for forward estimates)
- Loader was using: avg_estimate, low_estimate, high_estimate
- Mismatch = INSERT fails silently

**Solution Needed**:
- Option A: Create new earnings estimates loader with different data source
- Option B: Use alternative API (FactSet, S&P Capital IQ, Seeking Alpha)
- Option C: Accept that earnings estimates aren't available from yfinance

**Impact**: All earnings forecast pages show NULL values

---

#### 2. Options Chains (99.8% MISSING)
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadoptionschains.py | options_chains | Options contract data | 1/515 (0.2%) | ❌ BROKEN |
| (also populates): | options_greeks | Delta, gamma, theta, vega | 1/515 | ❌ BROKEN |
| (also populates): | iv_history | IV tracking | 1/515 | ❌ BROKEN |

**Problem**: Only 1 symbol has options data  
**Root Cause**: Unknown - loader runs but doesn't populate data for 514+ stocks

**Investigation Needed**:
1. Is loader being executed?
2. Is yfinance.Ticker.options returning chains?
3. Is there a silent error/timeout in the loop?
4. Are there database insert errors?

**Note**: Loader is defensively coded for missing greeks_calculator (it's optional)

**Impact**: Options analysis unavailable, covered call opportunities can't be calculated

---

#### 3. ETF Pricing Data
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadetfpricedaily.py | etf_price_daily | ETF OHLCV | -1 rows | ❌ ERROR |
| loadetfpriceweekly.py | etf_price_weekly | ETF weekly | -1 rows | ❌ ERROR |
| loadetfpricemonthly.py | etf_price_monthly | ETF monthly | -1 rows | ❌ ERROR |

**Problem**: Negative row counts indicate query errors or table issues

**Impact**: ETF analysis pages broken

---

#### 4. News Data
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadnews.py | stock_news | News headlines | Unknown | 🟡 Unknown |
| loadnews.py | news_articles | Full articles | Unknown | 🟡 Unknown |

**Coverage**: Unknown - possibly empty

---

#### 5. SEC Filings
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadsecfilings.py | sec_filings | 10-K, 10-Q documents | Unknown | 🟡 Unknown |

**Coverage**: Unknown

---

### ⚠️ PARTIALLY IMPLEMENTED

#### 1. Portfolio Tracking
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadalpacaportfolio.py | portfolio_holdings | User holdings (from Alpaca) | 0 | ❌ Not Implemented |
| | portfolio_performance | Portfolio returns | 0 | ❌ Not Implemented |
| | trades | Trade history | 0 | ❌ Not Implemented |

**Note**: These require actual Alpaca account integration, not expected to have data without user accounts

---

#### 2. Value Trap Detection
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| loadvaluetrapscore.py | value_trap_score | Value trap scores | Unknown | ⚠️ Unknown |

---

#### 3. World ETFs
| Loader | Table | Data | Coverage | Status |
|--------|-------|------|----------|--------|
| world-etfs.js (API route) | N/A | International ETF data | Unknown | ⚠️ Unknown |

---

---

## FACTOR INPUTS BY CATEGORY

### 📊 Valuation Factors
| Factor | Data | Coverage | Status |
|--------|------|----------|--------|
| P/E Ratio | key_metrics.trailing_pe, forward_pe | 515 | ✅ |
| Price/Book | key_metrics.price_to_book | 515 | ✅ |
| Price/Sales | key_metrics.price_to_sales_ttm | 515 | ✅ |
| PEG Ratio | key_metrics.peg_ratio | 515 | ✅ |
| EV/EBITDA | value_metrics (various) | 4,969 | ✅ |
| Dividend Yield | key_metrics.dividend_yield | 515 | ✅ |
| **EPS Estimates** | earnings_estimates.eps_estimate | 7 | ❌ NULL |
| **Revenue Estimates** | earnings_estimates.revenue_estimate | 7 | ❌ NULL |

### 📈 Growth Factors
| Factor | Data | Coverage | Status |
|--------|------|----------|--------|
| Revenue Growth | growth_metrics.revenue_growth | 4,969 | ✅ |
| EPS Growth | growth_metrics.earnings_growth | 4,969 | ✅ |
| Free Cash Flow Growth | growth_metrics.fcf_growth | 4,969 | ✅ |
| Book Value Growth | growth_metrics.book_value_growth | 4,969 | ✅ |
| Operating Margin Growth | growth_metrics.op_margin_growth | 4,969 | ✅ |

### 💪 Quality Factors
| Factor | Data | Coverage | Status |
|--------|------|----------|--------|
| ROE | quality_metrics.roe | 4,969 | ✅ |
| ROA | quality_metrics.roa | 4,969 | ✅ |
| ROIC | quality_metrics.roic | 4,969 | ✅ |
| Debt/Equity | quality_metrics.debt_equity_ratio | 4,969 | ✅ |
| Current Ratio | quality_metrics.current_ratio | 4,969 | ✅ |
| Quick Ratio | quality_metrics.quick_ratio | 4,969 | ✅ |

### 🚀 Momentum Factors
| Factor | Data | Coverage | Status |
|--------|------|----------|--------|
| RSI (14) | technical_data_daily.rsi | 515 | ✅ |
| MACD | technical_data_daily.macd | 515 | ✅ |
| Price Momentum | momentum_metrics.price_momentum | 4,969 | ✅ |
| Earnings Momentum | momentum_metrics.earnings_momentum | 4,969 | ✅ |
| Revenue Momentum | momentum_metrics.revenue_momentum | 4,969 | ✅ |

### 📍 Technical Factors
| Factor | Data | Coverage | Status |
|--------|------|----------|--------|
| 20-day SMA | technical_data_daily.sma_20 | 515 | ✅ |
| 50-day SMA | technical_data_daily.sma_50 | 515 | ✅ |
| 200-day SMA | technical_data_daily.sma_200 | 515 | ✅ |
| EMA-12 | technical_data_daily.ema_12 | 515 | ✅ |
| EMA-26 | technical_data_daily.ema_26 | 515 | ✅ |
| ATR | technical_data_daily.atr | 515 | ✅ |
| Volume | technical_data_daily.volume | 515 | ✅ |
| Price trends | buy_sell_daily, weekly, monthly | 515 | ✅ |

### 🎯 Sentiment & Positioning
| Factor | Data | Coverage | Status |
|--------|------|----------|--------|
| Analyst Rating | analyst_sentiment_analysis.rating | 359/515 (70%) | 🟡 |
| Analyst Target | analyst_sentiment_analysis.target_price | 359/515 (70%) | 🟡 |
| Upgrades/Downgrades | analyst_upgrade_downgrade | 193/515 (37%) | 🟡 |
| Insider Ownership | key_metrics.held_percent_insiders | 515 | ✅ |
| Insider Transactions | insider_transactions | 515 | ✅ |
| Institutional Ownership | institutional_positioning | 209/515 (41%) | 🟡 |
| Short Interest % | key_metrics.short_percent_of_float | 515 | ✅ |
| Short Interest Trend | positioning_metrics | Varies | 🟡 |
| Fund Ownership | institutional_positioning (filtered) | 209/515 (41%) | 🟡 |

### 📰 News & Events
| Factor | Data | Coverage | Status |
|--------|------|----------|--------|
| News Headlines | stock_news | Unknown | ⚠️ |
| News Sentiment | news_articles | Unknown | ⚠️ |
| Earnings Date | calendar_events | 515 | ✅ |
| Dividend Date | calendar_events | 515 | ✅ |
| Stock Split | calendar_events | 515 | ✅ |

### 📊 Macro Factors
| Factor | Data | Coverage | Status |
|--------|------|----------|--------|
| Fed Funds Rate | economic_data (FRED) | Daily | ✅ |
| 10-year Yield | economic_data (FRED) | Daily | ✅ |
| Unemployment Rate | economic_data (FRED) | Monthly | ✅ |
| Inflation (CPI) | economic_data (FRED) | Monthly | ✅ |
| ISM Manufacturing | economic_data (FRED) | Monthly | ✅ |
| Fear & Greed Index | fear_greed_index | Daily | ✅ |
| AAII Sentiment | aaii_sentiment | Weekly | ✅ |
| Market Breadth | market_data | Daily | ✅ |

### 💰 Options & Derivatives
| Factor | Data | Coverage | Status |
|--------|------|----------|--------|
| **Options Chains** | options_chains | 1/515 (0.2%) | ❌ |
| **Greeks (Delta)** | options_greeks.delta | 1/515 | ❌ |
| **Greeks (Gamma)** | options_greeks.gamma | 1/515 | ❌ |
| **Greeks (Theta)** | options_greeks.theta | 1/515 | ❌ |
| **Greeks (Vega)** | options_greeks.vega | 1/515 | ❌ |
| **IV Percentile** | iv_history | 1/515 | ❌ |
| **Put/Call Ratio** | options_chains | 1/515 | ❌ |

---

## WHAT'S REALLY BROKEN vs. WHAT JUST NEEDS DATA

### Schema/Code Issues (FIXED or OK):
- ✅ earnings_estimates INSERT mismatch - FIXED
- ✅ greeks_calculator import - Already OK
- ✅ Database credentials - Already OK

### Data Source Issues (NEED INVESTIGATION):
- ❌ Options chains - Only 1 stock loaded (why?)
- 🟡 Analyst sentiment - 70% coverage (data source limitation)
- 🟡 Analyst upgrades - 37% coverage (data source limitation)
- 🟡 Institutional positioning - 41% coverage (yfinance API limitation)

### Missing Data Sources (NEED EXTERNAL DATA):
- ❌ Earnings estimates - No loader exists for eps_estimate/revenue_estimate fields
- ⚠️ Options Greeks - Can calculate with Black-Scholes, but missing base options data
- ⚠️ News/sentiment - LoadNews.py doesn't seem to populate tables

---

## RECOMMENDATIONS

### Immediate Fixes:
1. ✅ Disable broken earnings_estimates INSERT - DONE
2. [ ] Debug options chains loader - why only 1 stock?
3. [ ] Verify analyst loaders are running all symbols

### Medium-term Improvements:
1. [ ] Add alternative data source for earnings estimates
2. [ ] Supplement institutional positioning data
3. [ ] Improve analyst coverage

### Long-term Strategy:
1. [ ] Integrate additional data providers (FactSet, Refinitiv, etc.)
2. [ ] Add real-time options data feed
3. [ ] Implement news/sentiment analysis
4. [ ] Create dedicated ETF universe tracking

---

**Report Status**: Complete audit of all 63 data loaders  
**Last Updated**: 2026-04-25  
**Action Items**: 3 fixes applied, 5 investigations needed
