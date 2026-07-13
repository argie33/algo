# Session 109: Critical Blocking Issues & Fixes

**Status:** 3 CRITICAL issues blocking live trading

## Issues Found

### ISSUE #1: SCHEMA TYPE MISMATCH ❌ → ✅ FIXED

**Status:** FIXED (Commit 0a35f8cc5)

**Problem:**
- algo_positions.id = INTEGER
- algo_trades.position_id = VARCHAR
- FK constraint failed on every trade creation attempt

**Solution Applied:**
1. Dropped FK constraint
2. Converted position_id VARCHAR → INTEGER
3. Recreated FK constraint with matching types

**Result:** Schema now valid, trades can be created without FK violations

---

### ISSUE #2: MISSING RISK_SCORE IN SIGNALS 🔴 BLOCKING

**Status:** NOT FIXED - Phase 8 rejects 100% of signals

**Problem:**
```
[PHASE 8] Persisted 9 signals to database
[PERSIST SIGNALS] Skipping CSWC: missing risk_score
[PERSIST SIGNALS] Skipping FCPT: missing risk_score
[PERSIST SIGNALS] Skipping EPRT: missing risk_score
...
[PHASE 8] Processing 9 qualified signals (cap: 5/day)
  → 0 trades executed (9/9 rejected)
```

**Root Cause:**
- Phase 7 generates signals without calculating risk_score
- Phase 8 requires risk_score for every signal
- Result: 0 trades created despite 9 signals qualified

**How to Fix:**
Find where Phase 7 creates signals and add risk_score calculation:

```python
# In algo/orchestrator/phase7_signal_generation.py or similar
signals = []
for symbol in qualified_symbols:
    signal = {
        'symbol': symbol,
        'signal_date': run_date,
        'entry_price': current_price,
        # ADD THIS:
        'risk_score': calculate_risk_score(symbol, current_price),  # Missing!
        'position_size_pct': 0.02,
        # ... other fields
    }
    signals.append(signal)
```

**Impact:** WITHOUT this, Phase 8 creates ZERO trades

---

### ISSUE #3: ALPACA CREDENTIALS NOT FOUND 🔴 BLOCKING

**Status:** NOT FIXED - Credentials ignored, trades can't execute

**Problem:**
```
[CREDENTIALS] Alpaca credentials NOT FOUND - trades cannot be executed!
[EXECUTOR] Running in paper trading mode without live Alpaca credentials
[EXECUTOR] mode=paper (sandbox) | key_set=True secret_set=True
```

Note the contradiction: key_set=True but credentials NOT FOUND

**Root Cause:**
- Code checks AWS Secrets Manager or env vars for credentials
- Code does NOT check algo_config table (where test credentials stored)
- For production this is correct, but for LOCAL DEV it fails

**Current Credential Locations:**
```sql
SELECT key, value FROM algo_config 
WHERE key IN ('alpaca_api_key', 'alpaca_api_secret');

Results:
  alpaca_api_key: 'PK0123456789ABCDEF' (DUMMY)
  alpaca_api_secret: 'test_secret_key_for_development' (DUMMY)
```

**How to Fix (LOCAL DEV):**

Option A: Use AWS Secrets Manager (production-like)
```bash
# Create secret in AWS Secrets Manager
aws secretsmanager create-secret --name algo/alpaca \
  --secret-string '{"APCA_API_KEY_ID":"YOUR_KEY","APCA_API_SECRET_KEY":"YOUR_SECRET"}'

# Or set environment variables
export APCA_API_KEY_ID="your_real_key"
export APCA_API_SECRET_KEY="your_real_secret"
```

Option B: Update orchestrator to check algo_config for LOCAL_MODE
```python
# In algo/orchestrator/orchestrator.py __init__
if os.getenv('LOCAL_MODE') == 'true':
    # For local dev, check algo_config table
    from utils.db import DatabaseContext
    with DatabaseContext('read') as cur:
        cur.execute('SELECT value FROM algo_config WHERE key = %s', ['alpaca_api_key'])
        key = cur.fetchone()[0] if cur.fetchone() else None
        # Set env var for rest of code
        if key:
            os.environ['APCA_API_KEY_ID'] = key
```

**Impact:** WITHOUT real credentials, market safety checks skip + no live execution

---

## Phase 8 Current Behavior

```
Signals Generated:     9 (from Phase 7)
Signals Persisted:     0 (all rejected - missing risk_score)
Trades Attempted:      0 (no signals to execute)
Trades Created:        0 (0% success rate)
```

## Fix Priority

1. **CRITICAL** - Fix missing risk_score (Phase 7)
   - Consequence: 0 trades created
   - Effort: 1-2 hours
   - Blocker for: Phase 8 entry execution

2. **CRITICAL** - Configure real Alpaca credentials
   - Consequence: Can't execute trades or verify market safety
   - Effort: 10 mins (if you have Alpaca key/secret)
   - Blocker for: Live trading, market safety

3. **HIGH** - Update orchestrator credential handling
   - Consequence: Local dev doesn't work without AWS setup
   - Effort: 30 mins
   - Blocker for: Local development workflow

## What Works Now

✅ Schema migration (trades can be created without FK errors)
✅ Data loading (prices, technical indicators fresh)
✅ Phase 1-7 execution (signals generating)
✅ Database integrity

## What's Broken

❌ Phase 8 trade creation (missing risk_score)
❌ Market safety verification (no credentials)
❌ Live trading (credentials + risk_score both needed)

## Next Session Tasks

- [ ] Find Phase 7 risk_score calculation and verify it's being used
- [ ] Add risk_score to signal output if missing
- [ ] Configure real Alpaca credentials (AWS or env var)
- [ ] Test Phase 8 creates trades successfully
- [ ] Verify live trading flow end-to-end
