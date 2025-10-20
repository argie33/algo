# Stock Scoring Analysis - Documentation Index

## Overview
Comprehensive analysis of the stock scoring and ranking logic in the codebase. Three complementary documents provide different perspectives on the same system.

---

## Documents

### 1. **STOCK_SCORING_ANALYSIS.md** (520 lines)
**Comprehensive Technical Deep Dive**

Complete analysis of the scoring system covering all aspects:
- Core scoring architecture (9 score types)
- Detailed methodology for each of 7 factors
- Normalization and inversion techniques
- Data flow and dependencies
- Score storage and retrieval
- Edge cases and fallbacks
- Implementation details and considerations

**Best for**: Understanding the full system, research, documentation

**Contents**:
- Section 1: Core Architecture
- Section 2: Detailed Scoring Methodology (Factors 1-7)
- Section 3: Composite Score Calculation
- Section 4: Normalization & Inversion Details
- Section 5: Data Flow & Dependencies
- Section 6: Score Storage & Retrieval
- Section 7: Key Metrics Definitions
- Section 8: Implementation Details
- Section 9: Files & Code Locations
- Section 10: Testing & Validation

---

### 2. **SCORING_QUICK_REFERENCE.md** (295 lines)
**Quick Lookup and Implementation Guide**

Fast reference guide for developers and analysts:
- Weight distribution at a glance
- Factor calculations summary
- Normalization methods overview
- Inversion pattern summary
- Composite score formulas
- Data dependencies diagram
- Score interpretation guide
- Calculation flow diagram
- Key files table
- Working example (AAPL)

**Best for**: Quick lookups, implementation reference, presentations

**Contents**:
- Weight distribution
- 7 Factor calculations (1-line summaries)
- Normalization methods
- Inversion patterns
- Score formulas (full and fallback)
- Data dependencies
- Interpretation guide
- Calculation flow
- Key files reference
- Real example walkthrough

---

### 3. **SCORING_CODE_LOCATIONS.md** (324 lines)
**Code Navigation and Modification Guide**

Detailed code location reference with line numbers:
- Python implementation locations
- JavaScript implementation locations
- Frontend component locations
- Data input sources and preprocessing
- Test file coverage
- Database schema
- API response structures
- Key calculation paths
- Modification hotspots with priority levels

**Best for**: Code navigation, modifications, debugging, maintenance

**Contents**:
- Primary Python implementation (with line numbers)
- Secondary JavaScript implementation
- Frontend display components
- Data input sources (5 files)
- Test files coverage
- Database schema (stock_scores + supporting tables)
- API response structures
- Calculation paths (momentum, composite)
- Modification hotspots (high/medium/low priority)

---

## Quick Navigation

### To Understand System Architecture
1. Start: **STOCK_SCORING_ANALYSIS.md** Section 1
2. Reference: **SCORING_QUICK_REFERENCE.md** Weight Distribution

### To Implement Changes
1. Find code: **SCORING_CODE_LOCATIONS.md** Line numbers
2. Understand logic: **STOCK_SCORING_ANALYSIS.md** Relevant section
3. Verify impact: **SCORING_QUICK_REFERENCE.md** Example

### To Add a New Metric
1. Identify component: **SCORING_QUICK_REFERENCE.md** Factor table
2. Locate code: **SCORING_CODE_LOCATIONS.md** Component section
3. Study current: **STOCK_SCORING_ANALYSIS.md** Factor section
4. Test impact: **SCORING_CODE_LOCATIONS.md** Test files

### To Debug a Score
1. Understand factor: **SCORING_QUICK_REFERENCE.md** Factor detail
2. Find calculation: **SCORING_CODE_LOCATIONS.md** Line numbers
3. Study methodology: **STOCK_SCORING_ANALYSIS.md** Factor section
4. Check data: **STOCK_SCORING_ANALYSIS.md** Data dependencies

---

## Key Information Locations

### Factor Weights
**File**: SCORING_QUICK_REFERENCE.md
**Section**: Weight Distribution (top)

### Factor Calculation Details
**File**: STOCK_SCORING_ANALYSIS.md
**Sections**: 2.1-2.7 (Factors 1-7)

### Code to Modify
**File**: SCORING_CODE_LOCATIONS.md
**Section**: Primary Python Implementation

### Data Sources
**File**: STOCK_SCORING_ANALYSIS.md
**Section**: 5. Data Flow & Dependencies

### Normalization Methods
**File**: STOCK_SCORING_ANALYSIS.md OR SCORING_QUICK_REFERENCE.md
**Sections**: Section 4 (Analysis) or Normalization Methods (Quick Ref)

### Inversion Logic
**File**: SCORING_QUICK_REFERENCE.md
**Section**: Inversion Pattern Summary

### Line Numbers for Exact Changes
**File**: SCORING_CODE_LOCATIONS.md
**Sections**: Key Calculation Paths, Important Line Numbers

### Example Score Walkthrough
**File**: SCORING_QUICK_REFERENCE.md
**Section**: Example: How a Stock Gets Scored (AAPL)

### Test Coverage
**File**: SCORING_CODE_LOCATIONS.md
**Section**: Test Files

---

## System Summary

### 7-Factor Weighted Model
- **Momentum** (18.95%): Technical momentum + RSI/MACD
- **Trend** (13.68%): Price trend + MA alignment  
- **Growth** (17.11%): Revenue/earnings growth
- **Value** (13.68%): Valuation ratios (PE, PB, PS, PEG)
- **Quality** (13.68%): Profitability + financial strength
- **Stability** (12.63%): Risk consistency (NEW)
- **Positioning** (10.26%): Institutional/insider ownership

### Normalization
- **Primary**: Percentile-based (relative to market)
- **Secondary**: Absolute ranges (predefined thresholds)
- **Fallback**: Sigmoid function

### Inversions Applied To
- P/E, P/B, P/S, PEG ratios
- Debt/Equity ratio
- Volatility
- Short interest

### Key Features
- All scores 0-100 scale
- Graceful fallbacks for missing data
- Automatic weight redistribution if positioning missing
- Daily recalculation (market-relative)
- 9 component scores + 1 composite

---

## File Locations (Absolute Paths)

### Documentation Files
```
/home/stocks/algo/STOCK_SCORING_ANALYSIS.md      (520 lines)
/home/stocks/algo/SCORING_QUICK_REFERENCE.md     (295 lines)
/home/stocks/algo/SCORING_CODE_LOCATIONS.md      (324 lines)
/home/stocks/algo/SCORING_INDEX.md               (This file)
```

### Implementation Files
```
/home/stocks/algo/loadstockscores.py             (Main Python engine)
/home/stocks/algo/webapp/lambda/routes/scores.js (API endpoint)
/home/stocks/algo/webapp/lambda/utils/factorScoring.js (JS fallback)
/home/stocks/algo/webapp/frontend/src/pages/ScoresDashboard.jsx (UI)
```

### Supporting Data Loaders
```
/home/stocks/algo/loadvaluemetrics.py            (Value percentiles)
/home/stocks/algo/loadqualitymetrics.py          (Quality percentiles)
/home/stocks/algo/loadgrowthmetrics.py           (Growth percentiles)
/home/stocks/algo/loadmomentummetrics.py         (Momentum metrics)
/home/stocks/algo/loadriskmetrics.py             (Risk metrics)
```

### Test Files
```
/home/stocks/algo/webapp/lambda/tests/unit/utils/factorScoring.test.js
/home/stocks/algo/webapp/lambda/tests/unit/routes/scores.test.js
/home/stocks/algo/webapp/lambda/tests/integration/routes/scores.integration.test.js
```

---

## Common Questions - Quick Answers

**Q: Where are the factor weights defined?**
A: `loadstockscores.py` lines 1601-1621

**Q: How is value_score calculated?**
A: From PE/PB/PS/PEG percentiles, weighted 35%/25%/20%/20%

**Q: What happens if positioning data is missing?**
A: Composite uses 6-factor model, positioning's 10.26% weight redistributed

**Q: How is sentiment currently used?**
A: Calculated (5%) but NOT included in composite score (weight redistributed)

**Q: Which metrics are inverted (lower is better)?**
A: P/E, P/B, P/S, PEG, Debt/Equity, Volatility, Short interest

**Q: How are percentiles calculated?**
A: Count of values < stock_value / total_values * 100

**Q: What's the score range?**
A: 0-100 scale, all scores clamped to this range

**Q: Where can I find exact line numbers for modifications?**
A: SCORING_CODE_LOCATIONS.md "Important Line Numbers for Modifications"

**Q: What's the data flow?**
A: 7 supporting tables → Python calculations → stock_scores table → API → Frontend

**Q: How are scores stored?**
A: PostgreSQL stock_scores table, daily refresh via loadstockscores.py

---

## Revision History

| Date | Version | Content |
|------|---------|---------|
| 2025-10-19 | 1.0 | Initial comprehensive analysis |
| - | - | Covers 7-factor scoring system |
| - | - | Python backend (loadstockscores.py) |
| - | - | JavaScript API and frontend |
| - | - | Normalized percentile-based scoring |
| - | - | Composite score with weight redistribution |

---

## Document Versions

These documents reflect the current state of the scoring system:
- **Primary Implementation**: `loadstockscores.py` (Python)
- **System Version**: 2.2+ (Enhanced, 7-factor model)
- **Last Updated**: 2025-10-16
- **Scoring Scale**: 0-100
- **Factor Count**: 7 (+ 2 additional: sentiment, stability)

---

## Related Resources

### In This Analysis
- STOCK_SCORING_ANALYSIS.md - Full technical details
- SCORING_QUICK_REFERENCE.md - Quick lookup guide
- SCORING_CODE_LOCATIONS.md - Code navigation

### In Repository
- /home/stocks/algo/loadstockscores.py - Main implementation
- /home/stocks/algo/webapp/lambda/routes/scores.js - API
- /home/stocks/algo/webapp/lambda/utils/factorScoring.js - JS engine

---

**Last Generated**: October 19, 2025
**Scope**: Stock Scoring & Ranking System
**Coverage**: Complete system analysis with code locations

