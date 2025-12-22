# Statement Loaders - Quick Start

## The Problem
Running all 9 statement loaders simultaneously → **yfinance API rate limits** → data gaps and failures

## The Solution
**Sequential execution** with 15-35 second delays between loaders + monitoring

---

## Run It

```bash
# Standard execution (recommended)
python3 orchestrate_statement_loaders.py --mode sequential

# See plan without running
python3 orchestrate_statement_loaders.py --dry-run

# Extra safety mode (for aggressive rate limiting)
python3 orchestrate_statement_loaders.py --mode careful

# Run only annual statements
python3 orchestrate_statement_loaders.py --group annual

# Resume from failure
python3 orchestrate_statement_loaders.py --resume 4
```

---

## What Runs

| # | Loader | Group | Delay After |
|---|--------|-------|---|
| 1 | Annual Balance Sheet | annual | 15s |
| 2 | Quarterly Balance Sheet | quarterly | 15s |
| 3 | Annual Income Statement | annual | 15s |
| 4 | Quarterly Income Statement | quarterly | 15s |
| 5 | Annual Cash Flow | annual | 15s |
| 6 | Quarterly Cash Flow | quarterly | 15s |
| 7 | TTM Income Statement | ttm | 15s |
| 8 | TTM Cash Flow | ttm | 15s |
| 9 | Earnings History | earnings | - |

**Total time:** 45-90 minutes (depending on stock count and network)

---

## Output Example

```
✅ PASS | Annual Balance Sheet       | 245.3s
✅ PASS | Quarterly Balance Sheet    | 198.7s
✅ PASS | Annual Income Statement    | 221.4s
❌ FAIL | Quarterly Income Statement | 156.2s
✅ PASS | Annual Cash Flow           | 203.5s
✅ PASS | Quarterly Cash Flow        | 189.3s
✅ PASS | TTM Income Statement       | 167.8s
✅ PASS | TTM Cash Flow              | 172.1s
✅ PASS | Earnings History           | 234.6s

Success Rate: 88.9% (8/9 passed)
Total Time:  1847.5s (30.8m)
```

---

## Troubleshooting

### Rate Limit Errors
Use careful mode with longer delays:
```bash
python3 orchestrate_statement_loaders.py --mode careful
```

### Failed Loader
Re-run individually:
```bash
python3 loadquarterlyincomestatement.py
```

### Resume from Failure
Find the failed loader number and continue:
```bash
python3 orchestrate_statement_loaders.py --resume 4
```

---

## How It Fixes Your Issue

| Issue | Solution |
|-------|----------|
| API rate limits | 15s delays between loaders |
| Simultaneous requests | Sequential execution |
| Data gaps | Monitoring shows which loaders failed |
| No visibility | Detailed logging and reporting |
| Can't resume | `--resume` flag to continue from failure |

---

## Next Steps

After running successfully:

```bash
# Calculate financial scores using loaded statement data
python3 calculate_scores.py
```

---

## Files Created

- `orchestrate_statement_loaders.py` - Main orchestrator script
- `STATEMENT_LOADERS_GUIDE.txt` - Detailed guide (read for full documentation)
- `STATEMENT_LOADERS_QUICK_START.md` - This file
