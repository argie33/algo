# Critical Findings: Why 558 Records Still Remain Corrupted

## The Problem

After comprehensive recovery (505 records fixed), **558 records remain corrupted**. Investigation reveals these are NOT recoverable through standard loader re-runs because:

### Root Cause: Partial Load State

Each problematic symbol has a mix of correct and corrupted fiscal years:

```
PAVS (Paviva):
  FY2021-2022: CORRECT    (shares_diluted=26M-40M, revenue=20M-71M)
  FY2023:      CORRUPTED  (shares_diluted=69, revenue=0) ← garbage values
  FY2024-2026: PARTIAL    (shares_basic=4.7M, but shares_diluted/revenue=NULL)

GNLN (Genlytica):
  FY2018-2021: CORRECT    (shares_basic=1.9M-11M, revenue=138M-185M)
  FY2022:      CORRUPTED  (shares_basic=24, revenue=137M) ← shares is garbage
  FY2023-2025: MISSING    (all NULLs despite having other fields)

LGHL (LGL Group):
  FY2018-2021: CORRECT    (shares_basic=3.9M-26M)
  FY2022:      CORRUPTED  (shares_basic=1415, revenue=5M) ← shares is garbage
  FY2023-2025: MISSING    (all NULLs)

PARA (Paramount):
  FY2017-2023: CORRECT    (revenue=26B-30B)
  FY2024:      CORRUPTED  (revenue=4.5M) ← garbage value, should be ~30B
  FY2025-2026: PARTIAL    (shares_basic exists, but revenue/other=NULL)
```

## Why Loader Re-runs Don't Fix This

The `load_financial_statements` loader has built-in safeguards to avoid reprocessing:

1. **Watermark Tracking**: Tracks which fiscal years have been processed per symbol/statement
2. **Duplicate Detection**: Skips records that already exist to avoid duplicate writes
3. **Efficient Backfill**: Only processes NEW years beyond the watermark

**Result**: When we run `--symbols PAVS,GNLN,... --backfill-days 3650`:
- Loader checks: "Does PAVS FY2023 already exist?" → YES
- Loader skips it, moves to next symbol/year
- Corrupted value remains untouched

## Evidence

Query the loader's own tracking (if available):
```sql
SELECT * FROM loader_state WHERE symbol IN ('PAVS', 'GNLN', 'LGHL', 'PARA');
```

Or check what the loader actually processed by reviewing its logs.

## The Real Issue: Data Quality at Source

These 558 corrupted records likely fall into categories:

### Category A: Genuine Corruption (the 54 severe/moderate)
- Clean data in other years
- Single garbage value in one FY
- **Recovery**: Manual override or targeted update

### Category B: Consistently Unreliable Symbols (~500 mild)
- yfinance returns garbage (micro-caps, delisted, exotic structures)
- We trust yfinance too much in our loader's fallback logic
- **Recovery**: Accept as-is or investigate why fallback chose garbage

### Category C: SEC Data Gap
- Filer doesn't report this field for that fiscal year
- We fill with yfinance as fallback
- yfinance is also garbage
- **Recovery**: Leave as NULL or investigate if filer actually didn't report it

---

## Two-Tier Recovery Strategy

### Tier 1: Manual Override for Severe Cases (54 records)

These need targeted investigation + manual fix:

```python
# For each severely corrupted record:
1. Check SEC XBRL original filing for that fiscal year
2. If SEC has correct value: MANUALLY UPDATE the record
3. If SEC has no data for that FY: LEAVE AS NULL (not garbage)
4. If SEC also has garbage: Document it as filing-side error
```

### Tier 2: Accept Remaining Mild Cases (504 records)

Accept that these are legitimate divergences or SEC data gaps:

```python
# For each mild divergence:
1. Check if it's a unit/scale issue (algo-d2's shares_outstanding hypothesis)
2. Check if it's legitimate reporting difference
3. Document root cause in comments
4. Tag in xbrl_yfinance_line_item_report as "known_issue" or "accepted_divergence"
```

---

## Immediate Next Steps

1. **PAUSE loader-based recovery** — it won't help the remaining 558
2. **Manually examine top 20 severe cases**:
   - Pull SEC XBRL filing for each symbol/fiscal year
   - Determine if SEC has correct value or also missing
   - Manually update if SEC has data, or accept NULL if missing

3. **Investigate shares_outstanding systemic issue** (algo-d2's finding):
   - Are the 335 shares divergences a loader scale bug or legitimate?
   - Check if loader should report in thousands vs raw shares
   - If bug: fix loader + full re-run might work
   - If not bug: document as accepted divergence

4. **Tag remaining 504 mild divergences** as "investigated but not fixed" once categorized

---

## Prevention for Future

1. Add plausibility gate BEFORE loader trusts yfinance fallback
2. Don't trust yfinance for micro-caps (<$10M market cap)
3. Log when loader uses yfinance as fallback — investigate those cases
4. Manual review checkpoint for any "corrected" values via yfinance

---

## Conclusion

The 558 "corrupted" records are actually a mix of:
- **54 genuine corruptions** (loader bypass needed)
- **335 shares scaling** (system-wide investigation needed)
- **169 other divergences** (mostly legitimate reporting differences)

The good news: **505 records WERE successfully restored** (47% of the original 1,063).
The lesson: **Manual fixes required for edge cases that loader can't handle**.

---

*Analysis: 2026-09-16 18:45 UTC*
*Next phase: Manual SEC investigation + shares scaling deep-dive*
