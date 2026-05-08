# Monday 2026-05-04 — Operations Runbook

**Goal**: see the algo run end-to-end against the live Alpaca paper account on
Monday's market open, with full data refresh and audit trail.

---

## Pre-market (before 9:30 EDT)

### 1. Verify broken positions queued to close
```bash
python3 /tmp/positions_audit2.py
# Should show 3 open SELL orders: NFLX, AVGO, NVDA (queued Sunday)
```

These are paper-account legacy positions with stops set far above current
price (NFLX stop $1085 vs px $92). They've been queued via market sell so
they fire at the 9:30 open, freeing the risk budget the algo needs.

### 2. Refresh data (if EOD didn't auto-run Friday)

The pipeline is `bash run_eod_loaders.sh` but for testing each step
individually:

```bash
# A. Source env (loaders need this)
set -a; source .env.local; set +a

# B. Refresh price data (yfinance throttles after ~150 symbols/run, may need
#    a few passes — re-run until watermark says all caught up)
python3 loadpricedaily.py --parallelism 4

# C. Recompute trend / SQS / Mansfield-RS via SQL window functions (fast)
#    See /tmp/quick_recompute2.py for the canonical SQL path
python3 algo_market_exposure.py
python3 loadswingscores.py
```

### 3. Verify pipeline health
```bash
python3 algo_data_patrol.py --quick
# Should report DONE with no CRITICAL findings
```

---

## At market open (9:30 EDT)

### 4. Confirm broken positions filled
```bash
python3 -c "
import os, requests
from dotenv import load_dotenv; load_dotenv('.env.local')
H = {'APCA-API-KEY-ID': os.getenv('APCA_API_KEY_ID'),
     'APCA-API-SECRET-KEY': os.getenv('APCA_API_SECRET_KEY')}
r = requests.get('https://paper-api.alpaca.markets/v2/positions', headers=H)
print(f'Remaining positions: {len(r.json())}')
for p in r.json(): print(f'  {p[\"symbol\"]}: qty={p[\"qty\"]}')
"
```

Expected: 4 positions remaining (AAPL, BRK.B, CL, NVR). Total open risk
should drop below 4% (was 8.58% with the 3 broken).

### 5. Run the orchestrator

**Dry run first** (always):
```bash
python3 algo_orchestrator.py --dry-run
```

Watch for:
- ✅ Phase 1 freshness check passes (data should be fresh from step 2)
- ✅ Phase 2 circuit breakers: total risk < 4%
- ✅ Phase 3 position monitor: 4 positions reviewed
- ✅ Phase 3b exposure policy: regime + tier
- ✅ Phase 4 exit execution: planned exits
- ✅ Phase 5 signal generation: candidate count
- ✅ Phase 6 entry execution: dry-run trades
- ✅ Phase 7 reconciliation

**If dry-run looks good, live run**:
```bash
python3 algo_orchestrator.py
# Reads execution_mode from algo_config — defaults to 'paper'
```

---

## What to expect

Based on Sunday's data state:

- **Candidate quality**: top swing scores max at ~57 (C grade). The
  research-weighted gate is min_swing_score=60 in healthy regime, 75 in
  caution. So the algo will likely **NOT** place new entries Monday — that's
  correct behavior, not a bug.

- **Position management**: phase 3 will trail stops upward on AAPL (+59%)
  and BRK.B (+16%) — those are working positions.

- **The "showing it works" payoff**: even with no new entries, you'll see
  the full audit trail — every decision, every gate evaluated, every reason.
  That's what tomorrow demonstrates. The day with strong A+/A setups, the
  algo will fire.

---

## After-market (4:00 EDT close)

### 6. EOD pipeline
```bash
bash run_eod_loaders.sh
```

This runs:
1. Pre-load patrol
2. Loaders in dependency order (price → technicals → buy/sell → metrics →
   sector/industry → market_exposure → swing_scores)
3. Post-load patrol
4. Auto-remediation
5. Orchestrator run for Tuesday's plan

### 7. Review the audit trail

```bash
python3 -c "
import psycopg2, os
from dotenv import load_dotenv; load_dotenv('.env.local')
conn = psycopg2.connect(host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'),
                         password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'))
cur = conn.cursor()
cur.execute('SELECT timestamp, run_id, phase, action, message FROM algo_audit_log ORDER BY timestamp DESC LIMIT 30')
for r in cur.fetchall(): print(' ', r)
"
```

Or visit `/api/algo/audit-log` (auth required for mutating endpoints).

---

## Known gaps for follow-up

1. `loadpricedaily.py` rate-limits silently after ~150 symbols (yfinance).
   Need pagination/throttle/retry per symbol.
2. EOD pipeline isn't yet on cron / EventBridge — must be triggered manually.
3. Patrol doesn't auto-run on a schedule.
4. 4 of the 7 legacy positions remain (AAPL/BRK.B/CL/NVR) — they have
   reasonable stops, will be trailed by the algo. Don't need to close them.

---

## Emergency overrides

- **Halt trading immediately**: set `execution_mode = 'manual'` in
  `algo_config` (orchestrator phase 6 will skip).
- **Skip freshness gate** (testing only): `python3 algo_orchestrator.py
  --skip-freshness` — but never for live trading.
- **Cancel all orders**: `for o in $(curl -H "key" GET /v2/orders?status=open
  | jq -r '.[].id'); do curl -X DELETE /v2/orders/$o; done`
