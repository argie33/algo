# Stock Scoring System Comparison

## Old Approach (`loadstockscores.py`) vs New Approach (`loadstockscores_sector_based.py`)

### Key Improvements in New System

#### 1. **Sector-Relative Scoring** ⭐

**Old:**
```python
# Compares ALL stocks together
pe_percentile = calculate_z_score_normalized(
    -float(trailing_pe),
    all_pe_values  # Tech, utilities, banks all mixed
)
```

**New:**
```python
# Compares stocks ONLY within their sector
for sector in sectors:
    stocks = fetch_sector_stocks(cursor, sector)
    # Z-scores calculated within this sector only
    z = calculate_sector_zscore(
        stock['trailing_pe'],
        sector_pe_values  # Only tech stocks if this is tech sector
    )
```

**Why Better:**
- Fairer comparison (tech vs tech, not tech vs utilities)
- Accounts for sector-specific norms (banks have low P/B, software has high P/S)
- More actionable stock picks

---

#### 2. **Winsorization for Outlier Handling** ⭐

**Old:**
```python
# No outlier handling before z-score
# PE=8249 corrupts mean and std
mean = np.mean(all_values)  # Inflated by outliers
std = np.std(all_values)    # Inflated by outliers
```

**New:**
```python
def winsorize(values, lower_percentile=1.0, upper_percentile=99.0):
    """Cap outliers at 1st and 99th percentile"""
    lower_bound = np.percentile(clean_values, lower_percentile)
    upper_bound = np.percentile(clean_values, upper_percentile)

    # Cap PE=8249 to 99th percentile value
    winsorized = [max(lower_bound, min(upper_bound, v)) for v in values]

# Then calculate z-score on clean data
z_scores = zscore(winsorized_values)
```

**Impact:**
- PE distribution: mean=19.6 (vs 43.5 corrupted), std=18 (vs 186 corrupted)
- Stocks with reasonable PE=20 now score correctly (around 50-60, not penalized)

---

#### 3. **Proper Metric Inversion**

**Old:**
```python
# Had inversion but only in some places
pe_percentile = calculate_z_score_normalized(-float(trailing_pe), ...)
```

**New:**
```python
# Systematic inversion for ALL "lower is better" metrics
INVERSE_METRICS = [
    'trailing_pe',      # Lower PE = cheaper = better
    'forward_pe',
    'price_to_book',    # Lower P/B = cheaper
    'price_to_sales_ttm',
    'peg_ratio',
    'ev_to_ebitda',
    'ev_to_revenue',
    'debt_to_equity',   # Lower debt = better
    'volatility_12m',   # Lower vol = more stable
]

# Automatically inverts during scoring
z = calculate_sector_zscore(stock[metric], values, invert=(metric in INVERSE_METRICS))
```

---

#### 4. **Simpler, More Interpretable Scoring**

**Old:**
```python
# Complex weighted system with nested normalization
normalized_score = 50 + (z_score * 15)  # Convert to 0-100
# Multiple weighting layers
profitability_score = (roic_pct * 14 + roe_pct * 10 + ...) / total_weight
quality_score = (profitability * 0.38 + strength * 0.28 + ...)
```

**New:**
```python
# Simple z-score averaging (like the script you shared)
quality_zscores = []
for metric in QUALITY_METRICS:
    z = calculate_sector_zscore(stock[metric], sector_values[metric])
    quality_zscores.append(z)

# Factor score = mean of z-scores
stock['quality_score'] = np.mean(quality_zscores)

# Composite = weighted average of factors
composite = (0.25*quality + 0.20*value + 0.20*growth +
             0.20*momentum + 0.15*stability)
```

**Benefits:**
- Raw z-scores are interpretable (0 = average, 1 = one std dev above)
- Can easily compare across factors
- Transparent weighting scheme

---

#### 5. **Better Data Coverage**

**Old:**
```sql
-- Only 16 stocks had scores
SELECT COUNT(*) FROM stock_scores;  -- 16
```

**New:**
```python
# Processes ALL sectors, ALL stocks
for sector in sectors:
    stocks = fetch_sector_stocks(cursor, sector)
    # Scores calculated for all stocks with sufficient data
```

---

### Score Interpretation

#### Old System (0-100 scale)
```
Score Range    Interpretation
-----------    --------------
90-100         Exceptional
80-89          Very Good
70-79          Good
60-69          Above Average
50-59          Average
40-49          Below Average
30-39          Poor
0-29           Very Poor
```

#### New System (Z-Score scale)
```
Z-Score    Percentile    Interpretation
-------    ----------    --------------
> 2.0      ~98th         Exceptional (top 2%)
1.5-2.0    93-98th       Very Good
1.0-1.5    84-93rd       Good
0.5-1.0    69-84th       Above Average
-0.5-0.5   31-69th       Average
-1.0--0.5  16-31st       Below Average
-1.5--1.0  7-16th        Poor
< -1.5     < 7th         Very Poor
```

---

### Example: How Scoring Changed for a Stock

**Stock: AAPL (Apple Inc.)**

**Metrics:**
- PE Ratio: 28.5
- P/B Ratio: 45.2
- Sector: Technology

#### Old Approach (Global Comparison)
```
Global PE Stats:
  Mean: 43.5 (inflated by outliers)
  Std:  186

AAPL PE Z-Score:
  z = (28.5 - 43.5) / 186 = -0.08
  Converted: 50 + (-0.08 * 15) = 48.8

Interpretation: Below average value ❌ (Wrong!)
```

#### New Approach (Sector-Relative + Winsorized)
```
Tech Sector PE Stats (winsorized):
  Mean: 24.2
  Std:  12.5

AAPL PE Z-Score:
  Inverted PE: -28.5
  Sector mean: -24.2
  z = (-28.5 - (-24.2)) / 12.5 = -0.34

Interpretation: Slightly expensive for tech sector ✓ (Correct!)
```

---

### Running the New System

```bash
# Run the new sector-based scoring
python3 loadstockscores_sector_based.py

# Output shows:
# - Scores for each sector separately
# - Top stocks in each factor by sector
# - Overall top 20 stocks across all sectors
```

### Migration Path

1. **Test the new system:**
   ```bash
   python3 loadstockscores_sector_based.py
   ```

2. **Compare results:**
   - Check if top stocks make more sense
   - Verify sector-relative rankings are fair
   - Review outlier handling effectiveness

3. **Once validated:**
   - Rename old script: `mv loadstockscores.py loadstockscores_old.py`
   - Rename new script: `mv loadstockscores_sector_based.py loadstockscores.py`
   - Update any calling scripts/workflows

### Key Metrics to Watch

After running the new system:

1. **Score Distribution:**
   ```sql
   SELECT
       AVG(quality_score) as avg_quality,
       STDDEV(quality_score) as std_quality,
       MIN(quality_score) as min_quality,
       MAX(quality_score) as max_quality
   FROM stock_scores;
   ```

2. **Sector Coverage:**
   ```sql
   SELECT sector, COUNT(*) as stock_count
   FROM stock_scores
   GROUP BY sector
   ORDER BY stock_count DESC;
   ```

3. **Top Stocks Make Sense:**
   - Do the top value stocks have low PE/PB ratios? ✓
   - Do the top quality stocks have high ROE/margins? ✓
   - Are tech stocks compared fairly vs utilities? ✓
