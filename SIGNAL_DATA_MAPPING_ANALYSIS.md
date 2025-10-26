# Trading Signals Data Field Mapping Investigation Report

## Executive Summary

The Trading Signals display is showing all zeros for **Technical Indicators**, **Moving Averages**, and **Volume Analysis** sections because:

1. **Database Schema Mismatch**: These columns (`rsi`, `adx`, `atr`, `pct_from_ema_21`, `pct_from_sma_50`, `pct_from_sma_200`, `volume_ratio`) are defined in the enhancement schema but NOT populated in the actual `buy_sell_*` tables
2. **API Returns Hardcoded Zeros**: The backend API in `signals.js` explicitly sets these fields to `0` rather than fetching real data
3. **Missing Data Calculations**: Technical indicators should be calculated from `technical_data_daily` table but aren't being joined
4. **Data Source Disconnection**: The component expects calculated metrics that exist in the database schema but are never loaded into the signals tables

---

## Part 1: What Fields the API is Actually Returning

### Backend API: `/home/stocks/algo/webapp/lambda/routes/signals.js`

#### Lines 225-241: Actual Columns Being Queried
```javascript
const actualColumns = `
  bsd.id, bsd.symbol, bsd.timeframe, bsd.date,
  bsd.open, bsd.high, bsd.low, bsd.close, bsd.volume,
  bsd.signal, bsd.buylevel, bsd.stoplevel, bsd.inposition,
  bsd.strength, bsd.signal_type, bsd.pivot_price,
  bsd.buy_zone_start, bsd.buy_zone_end,
  bsd.exit_trigger_1_price, bsd.exit_trigger_2_price,
  bsd.exit_trigger_3_condition, bsd.exit_trigger_3_price,
  bsd.exit_trigger_4_condition, bsd.exit_trigger_4_price,
  bsd.initial_stop, bsd.trailing_stop,
  bsd.base_type, bsd.base_length_days,
  bsd.avg_volume_50d, bsd.volume_surge_pct,
  bsd.rs_rating, bsd.breakout_quality,
  bsd.risk_reward_ratio, bsd.current_gain_pct, bsd.days_in_position
`;
```

#### Lines 314-468: Fields Being Returned in Response
The API response maps database fields and fills missing ones with zeros:

**REAL DATA** (from database):
- `symbol`, `signal`, `date`, `timeframe`
- `open`, `high`, `low`, `close`, `volume`
- `buylevel`, `stoplevel`, `inposition`
- `strength`, `signal_type`, `pivot_price`
- `buy_zone_start`, `buy_zone_end`
- `exit_trigger_1_price` through `exit_trigger_4_price`
- `initial_stop`, `trailing_stop`
- `base_type`, `base_length_days`
- `avg_volume_50d`, `volume_surge_pct`
- `rs_rating`, `breakout_quality`
- `risk_reward_ratio`, `current_gain_pct`, `days_in_position`

**HARDCODED ZEROS** (NOT in database):
```javascript
// Line 386-392
pct_from_ema_21: 0,
pct_from_sma_50: 0,
pct_from_sma_200: 0,
rsi: 0,
adx: 0,
atr: 0,
daily_range_pct: 0,
```

**HARDCODED ZEROS** (with comments explaining why):
```javascript
// Line 378-383
volume_ratio: 0,
volume_analysis: null,
// ... avg_volume_50d comes from database but others don't
volume_percentile: 0,
volume_surge_on_breakout: false,

// Line 395
entry_quality_score: 0, // Column doesn't exist

// Line 402
current_gain_loss_pct: parseFloat(row.current_gain_pct || 0),
```

---

## Part 2: What SignalCardAccordion.jsx is Expecting

### Frontend Component: `/home/stocks/algo/webapp/frontend/src/components/SignalCardAccordion.jsx`

The component attempts to display these fields in the following sections:

#### TECHNICAL INDICATORS (Lines 261-273)
```javascript
<DataField label="RSI" value={signal.rsi} format="number" />
<DataField label="ADX" value={signal.adx} format="number" />
<DataField label="ATR" value={signal.atr} format="number" />
<DataField label="RS Rating" value={signal.rs_rating} format="number" />
<DataField label="Pivot Price" value={signal.pivot_price} format="currency" />
```

Expected fields:
- `rsi` - Relative Strength Index (0-100)
- `adx` - Average Directional Index (0-100)
- `atr` - Average True Range (price units)
- `rs_rating` - Relative Strength Rating (0-100) **[EXISTS IN DB]**
- `pivot_price` - Pivot point **[EXISTS IN DB]**

#### MOVING AVERAGES (Lines 275-286)
```javascript
<DataField label="% from EMA21" value={signal.pct_from_ema_21} format="percent" />
<DataField label="% from SMA50" value={signal.pct_from_sma_50} format="percent" />
<DataField label="% from SMA200" value={signal.pct_from_sma_200} format="percent" />
<DataField label="Daily Range %" value={signal.daily_range_pct} format="percent" />
```

Expected fields:
- `pct_from_ema_21` - % distance from 21-day EMA (not in DB)
- `pct_from_sma_50` - % distance from 50-day SMA (not in DB)
- `pct_from_sma_200` - % distance from 200-day SMA (not in DB)
- `daily_range_pct` - Daily high-low range as % (not in DB)

#### VOLUME ANALYSIS (Lines 288-300)
```javascript
<DataField label="Current Volume" value={signal.volume} ... />
<DataField label="Avg 50d" value={signal.avg_volume_50d} ... /> // ✓ EXISTS
<DataField label="Volume Surge %" value={signal.volume_surge_pct} ... /> // ✓ EXISTS
<DataField label="Volume Ratio" value={signal.volume_ratio} format="number" />
<DataField label="Vol Percentile" value={signal.volume_percentile} format="percent" />
```

Expected fields:
- `volume` - Current day volume **[EXISTS IN DB]**
- `avg_volume_50d` - 50-day average volume **[EXISTS IN DB]**
- `volume_surge_pct` - Surge as % **[EXISTS IN DB]**
- `volume_ratio` - Current vs average ratio (not in DB)
- `volume_percentile` - Percentile ranking (not in DB)

---

## Part 3: Specific Mismatches Found

### Summary Table

| Section | Field | Frontend Expects | API Returns | Database Has | Status |
|---------|-------|------------------|-------------|--------------|--------|
| **Technical Indicators** | RSI | number | 0 | NO | MISSING |
| | ADX | number | 0 | NO | MISSING |
| | ATR | number | 0 | NO | MISSING |
| | RS Rating | number | rs_rating | YES | OK |
| | Pivot Price | currency | pivot_price | YES | OK |
| **Moving Averages** | % from EMA21 | percent | 0 | NO | MISSING |
| | % from SMA50 | percent | 0 | NO | MISSING |
| | % from SMA200 | percent | 0 | NO | MISSING |
| | Daily Range % | percent | 0 | NO | MISSING |
| **Volume Analysis** | Current Volume | int | volume | YES | OK |
| | Avg 50d | int | avg_volume_50d | YES | OK |
| | Volume Surge % | percent | volume_surge_pct | YES | OK |
| | Volume Ratio | number | 0 | NO | MISSING |
| | Vol Percentile | percent | 0 | NO | MISSING |

### Root Causes

#### 1. **Technical Indicators Missing (Lines 386-392 in signals.js)**
```javascript
// Technical indicators - NOT IN buy_sell tables, would require separate calculation
pct_from_ema_21: 0,
pct_from_sma_50: 0,
pct_from_sma_200: 0,
rsi: 0,
adx: 0,
atr: 0,
daily_range_pct: 0,
```

**Issue**: These should come from `technical_data_daily` table but:
- No JOIN to `technical_data_daily` in the query
- Fields not being calculated
- Hardcoded to 0

#### 2. **Volume Metrics Partial (Lines 378-383)**
```javascript
// Volume analysis - REAL DATA
volume_ratio: 0,              // ← NOT CALCULATED
volume_analysis: null,
avg_volume_50d: row.avg_volume_50d || 0,  // ✓ REAL
volume_surge_pct: parseFloat(row.volume_surge_pct || 0), // ✓ REAL
volume_percentile: 0,         // ← NOT CALCULATED
```

**Issue**: 
- `volume_ratio` = current volume / avg volume - NOT CALCULATED
- `volume_percentile` = ranking percentile - NOT CALCULATED
- Only some volume fields populated

#### 3. **Missing JOIN to technical_data_daily**

The API query (lines 243-269) joins:
- `buy_sell_daily` as primary table (bsd)
- `company_profile` for company names
- `stock_symbols` for security names
- `earnings_history` for earnings dates

**NOT JOINING**:
- `technical_data_daily` (which has RSI, MACD, SMA, EMA, ADX, ATR, etc.)

---

## Part 4: Database Schema Analysis

### What SHOULD Exist (from enhance_buyselldaily_schema.sql)

The database schema file (lines 9-30) shows these columns should exist:

```sql
ALTER TABLE buy_sell_daily
ADD COLUMN IF NOT EXISTS pct_from_ema_21 NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS pct_from_sma_50 NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS pct_from_sma_200 NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS rsi NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS adx NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS atr NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS daily_range_pct NUMERIC(6,2);
```

**BUT**: These columns may exist in the schema definition but are never populated with actual data.

### What ACTUALLY EXISTS in buy_sell_daily

Based on the API query selecting columns that work without errors:
- `id`, `symbol`, `timeframe`, `date`
- `open`, `high`, `low`, `close`, `volume`
- `signal`, `buylevel`, `stoplevel`, `inposition`
- `strength`, `signal_type`, `pivot_price`
- `buy_zone_start`, `buy_zone_end`
- `exit_trigger_*_*` fields
- `initial_stop`, `trailing_stop`
- `base_type`, `base_length_days`
- `avg_volume_50d`, `volume_surge_pct`
- `rs_rating`, `breakout_quality`
- `risk_reward_ratio`, `current_gain_pct`, `days_in_position`

**NOT POPULATED**:
- `rsi`, `adx`, `atr` (should come from technical_data_daily)
- `pct_from_ema_21`, `pct_from_sma_50`, `pct_from_sma_200` (should be calculated)
- `daily_range_pct` (should be calculated from high/low)
- `volume_ratio` (should be calculated: volume / avg_volume_50d)
- `volume_percentile` (would need all symbol volumes for ranking)

---

## Part 5: Why the Mismatch Occurred

### Problem Chain

1. **Schema Definition vs Reality**
   - Enhancement schema file defines columns to add
   - But actual database may not have them populated
   - Or calculations never run to populate them

2. **API Hard-Coding Zeros**
   - Instead of querying missing fields
   - API explicitly sets them to 0 (line 386: `pct_from_ema_21: 0`)
   - Prevents errors but shows wrong data

3. **No JOIN to Technical Data**
   - `technical_data_daily` table exists and has RSI, ADX, ATR, SMA, EMA, etc.
   - But the signals API never joins to fetch these values
   - So they can't be returned

4. **Missing Calculations**
   - Moving average percentages should be calculated from OHLC data
   - Volume ratios should be calculated from volume / avg_volume
   - Daily range should be (high - low) / low * 100
   - But none of these are being computed in the API

5. **Frontend Still Expects Them**
   - Component was built expecting complete data
   - Displays zeros instead of "N/A" or hiding the section
   - Creates confusing UX with all-zero values

---

## Summary of Findings

### Fields by Status

#### Fully Working (5 fields)
- `volume` (current volume)
- `avg_volume_50d` (50-day average)
- `volume_surge_pct` (surge percentage)
- `rs_rating` (relative strength rating)
- `pivot_price` (pivot point)

#### Showing Zeros But Should Have Data (9 fields)
**Should come from `technical_data_daily`**:
- `rsi` - In technical_data_daily table
- `adx` - In technical_data_daily table
- `atr` - In technical_data_daily table

**Should be calculated from existing data**:
- `pct_from_ema_21` - Calculated from price vs EMA
- `pct_from_sma_50` - Calculated from price vs SMA50
- `pct_from_sma_200` - Calculated from price vs SMA200
- `daily_range_pct` - Calculated (high-low)/low
- `volume_ratio` - Calculated volume/avg_volume
- `volume_percentile` - Calculated from volume ranking

#### Undefined/Not Referenced (5 fields)
- `entry_quality_score` - Not in buy_sell tables
- `passes_minervini_template` - Not in buy_sell tables
- `market_stage` - Not in buy_sell tables
- `stage_confidence` - Not in buy_sell tables
- `stage_number` - Not in buy_sell tables

---

## Root Cause Files

### Key Files Involved

1. **Backend API** (hardcoding zeros)
   - `/home/stocks/algo/webapp/lambda/routes/signals.js`
   - Lines 225-241: Query definition (missing technical data join)
   - Lines 378-392: Response formatting (hardcoded zeros)

2. **Frontend Component** (expecting data)
   - `/home/stocks/algo/webapp/frontend/src/components/SignalCardAccordion.jsx`
   - Lines 261-273: Technical Indicators section
   - Lines 275-286: Moving Averages section
   - Lines 288-300: Volume Analysis section

3. **Database Schema** (column definitions)
   - `/home/stocks/algo/webapp/lambda/enhance_buyselldaily_schema.sql`
   - Lines 9-30: Column definitions (may not be populated)

4. **Missing Data Source**
   - `/home/stocks/algo/DATABASE_SCHEMA_VISUAL.md`
   - Shows `technical_data_daily` table exists with RSI, ADX, ATR, SMA, EMA

---

## Recommendations for Fix

### Priority 1: Add JOIN to technical_data_daily
The signals API should JOIN to `technical_data_daily` to fetch:
- RSI, ADX, ATR
- SMA20, SMA50, SMA150, SMA200
- EMA21

### Priority 2: Calculate Missing Fields in API
Calculate and return:
- `pct_from_ema_21` = (price - ema21) / ema21 * 100
- `pct_from_sma_50` = (price - sma50) / sma50 * 100
- `pct_from_sma_200` = (price - sma200) / sma200 * 100
- `daily_range_pct` = (high - low) / low * 100
- `volume_ratio` = volume / avg_volume_50d

### Priority 3: Populate buy_sell_daily Columns
Ensure these columns are populated with real data:
- Either from technical_data_daily join
- Or via calculated SQL UPDATE statements
- Not just schema definitions

### Priority 4: Update Frontend
Change display to show "N/A" or hide sections when data is 0/null
Instead of displaying misleading zeros

