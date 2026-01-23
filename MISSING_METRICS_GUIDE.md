# MISSING METRICS GUIDE - Why Data Is Missing

**Purpose:** Help troubleshoot why certain metrics show as NULL/missing in scores

---

## ✅ METRICS WITH FULL DATA (95%+)

These are safe to use - gaps are rare:
- Current Ratio: 91.4%
- Quick Ratio: 91.3%
- ROE: 90.9%
- ROA: 95.5%
- Price/Book: 99.0%
- EPS Trailing: 98.1%
- Institutional Ownership: 98.5%
- Insider Ownership: 95.2%

**For missing values here:** Data just hasn't been loaded for this stock yet

---

## 🟡 METRICS WITH GOOD DATA (80-95%)

These are usable but have intentional gaps:

### **Debt/Equity: 95.7%** (235 missing)
**Missing because:**
- Companies with zero equity (unprofitable)
- Private companies without balance sheet data

**Indicator:** `debt_to_equity IS NULL` → Stock may be unprofitable

---

### **Forward P/E: 88.9%** (602 missing)
**Missing because:**
- Unprofitable companies can't have forward earnings
- New IPOs without analyst coverage
- Small caps without estimates

**Indicator:** `forward_pe IS NULL` → Check if unprofitable or new IPO

---

### **PEG Ratio: 66.5%** (1,861 missing)
**Missing because:**
- Requires earnings growth rate (not all stocks have it)
- IPOs without historical growth
- Unprofitable companies

**Indicator:** `peg_ratio IS NULL` → Check earnings_growth_pct for stock

---

### **Dividend Yield: 35.5%** (3,488 missing)
**Missing because:**
- **INTENTIONAL** - Growth stocks don't pay dividends
- Unprofitable companies can't pay dividends
- Tech/startup companies prioritize growth over dividends

**Indicator:** `dividend_yield IS NULL` → Stock likely growth-focused (CORRECT)

---

### **Revenue Growth: 89.4%** (1,683 missing)
**Missing because:**
- New IPOs without prior year data
- Pre-IPO companies
- Recently acquired/merged companies

**Indicator:** `revenue_growth_pct IS NULL` → Stock may be new/startup

---

### **Quarterly Growth Momentum: 91.7%** (1,315 missing)
**Missing because:**
- New IPOs with only 1 quarter of history
- Recently listed stocks
- Some micro-caps

**Indicator:** `quarterly_growth_momentum IS NULL` → Stock likely very new

---

## 🔴 METRICS WITH CORRECT GAPS (< 80%)

These gaps are **BUSINESS FACTS, NOT DATA ERRORS**:

### **Trailing P/E: 53.8%** (2,499 missing)
**Missing because:** ✓ CORRECT
- 1,800+ stocks are UNPROFITABLE (negative earnings)
- P/E = Price ÷ Earnings
- Can't divide by negative number (undefined mathematically)

**Action:** Use P/B or EV/EBITDA for unprofitable companies

**Indicator:** `trailing_pe IS NULL` → **Check if net_income < 0**

---

### **EPS CAGR (3Y): 83.7%** (2,589 missing)
**Missing because:** ✓ CORRECT
- Limited historical data in database
- IPOs with < 3 years of history
- Unprofitable companies

**Action:** Use revenue growth as alternative for young companies

**Indicator:** `eps_growth_3y_cagr IS NULL` → Stock may be young

---

### **Earnings Growth Rate: 44.5%** (3,003 missing)
**Missing because:** ✓ CORRECT
- Unprofitable companies have no earnings growth (they're losing money)
- IPOs with no prior year comparisons

**Indicator:** `earnings_growth_pct IS NULL` → **Check if unprofitable**

---

### **Earnings Estimates: 85.0%** (947 missing)
**Missing because:**
- Small-cap stocks not covered by analysts
- Recent IPOs without consensus estimates
- Foreign companies with limited US coverage

**Action:** Would need external analyst API (Bloomberg, Yahoo Finance)

**Indicator:** `analyst_target_price IS NULL` → Stock likely small-cap/new

---

## 📋 TROUBLESHOOTING FLOWCHART

```
Metric is NULL/Missing?

├─ Is it Dividend Yield?
│  └─ YES → Normal! Growth stocks don't pay dividends (CORRECT)
│
├─ Is it Trailing P/E?
│  └─ YES → Check net_income
│     ├─ Negative? → CORRECT (unprofitable)
│     └─ Positive? → Missing analyst data
│
├─ Is it Earnings Growth or EPS CAGR?
│  └─ YES → Check if unprofitable or new stock
│
├─ Is it Forward P/E, Analyst Est?
│  └─ YES → Check if small-cap or new IPO
│
├─ All other metrics NULL?
│  └─ YES → Data loading issue, contact support
│
└─ Just 1-2 metrics missing?
   └─ YES → Normal, some data providers don't cover all stocks
```

---

## 🎯 HOW TO ADD INDICATORS TO API RESPONSES

**Suggested enhancement:**

Instead of just `metric: null`, return:

```json
{
  "ticker": "STOCK",
  "trailing_pe": null,
  "trailing_pe_reason": "unprofitable",  // ← NEW
  "trailing_pe_note": "Stock has negative earnings"  // ← NEW
}
```

**Possible reason values:**
- `"unprofitable"` - Stock has negative earnings
- `"new_ipo"` - Stock recently went public
- `"no_data"` - Data not loaded yet
- `"no_historical"` - Not enough historical data
- `"intentional_null"` - Growth stock (dividend) or other business fact
- `"external_needed"` - Requires external data source

---

## 💡 KEY INSIGHT

**Not all NULL values are errors!**

Some are features:
- Unprofitable stocks SHOULD have NULL P/E
- Growth stocks SHOULD have NULL dividend yield
- New IPOs SHOULD have NULL 3Y growth

**This is correct data, not missing data.**

