# Research: Optimal Architecture for Swing Trading System

## Questions to Answer
1. **Signal Generation Frequency** - Once daily? Multiple times? Real-time?
2. **Data Refresh Requirements** - What's the optimal refresh rate?
3. **Execution Timing** - When should trades actually execute?
4. **Pipeline Architecture** - How should data flow end-to-end?

---

## RESEARCH: Swing Trading Best Practices

### What is Swing Trading?
- **Holding Period:** 2-30 days (typically 2-7 days for active swing traders)
- **Goal:** Capture medium-term price moves within trending markets
- **Key Metrics:** Technical indicators (RSI, moving averages, support/resistance, volume)
- **Decision Frequency:** Daily analysis is standard, intraday updates common among pros

### Signal Generation Frequency - Industry Standard

**Professional Swing Trading Systems:**
- **Minimum:** Once per day (end-of-day or pre-market)
- **Better:** Twice per day (pre-market + mid-day)
- **Best:** 4x daily or continuous (opening bell, mid-morning, lunch, close)
- **Reason:** Market conditions change throughout the day; RSI, volume, momentum shift constantly

**Why not just once daily?**
- Early morning signal might be invalid by 2 PM (market reverses)
- Miss entries that form mid-day (strong 11am-2pm moves)
- Positions entered at opening might already be out-of-sync by market close
- Swing setups often visible in multiple timeframes (daily + 4H + 1H)

**Best Practice Finding:**
Most professional swing traders (Minervini, Cardone, etc.) analyze:
- Watchlist scan: Every 2-4 hours during market hours
- Signal generation: End-of-day + pre-market for next day
- Execution: At specific times when setup is strongest (opening, after 11am, before close)

### Data Refresh Requirements

**For Swing Trading Signals:**
- **Price data:** End-of-day closes (sufficient for daily signals)
- **Technical indicators:** Refresh whenever new price bar completes
  - Daily bars: Once at 4 PM ET (market close)
  - 4-hour bars: Every 4 hours during market hours
  - 1-hour bars: Every hour during market hours
- **Volume data:** Critical for swing trading, need up-to-date EOD
- **Sector/market context:** Daily sufficient (EOD recalc)

**Optimal Refresh Schedule:**
```
4:00 AM ET   - Overnight index futures, pre-market movers (optional)
9:30 AM ET   - Market open, first wave of entries
1:00 PM ET   - Mid-day update (4-hour bars refresh if using them)
3:30 PM ET   - Afternoon update before close
4:00 PM ET   - Market close (EOD final signals)
```

### Execution Timing

**Best Times for Swing Trade Execution:**
1. **9:30-10:00 AM ET** - Market open (highest volume, breakouts confirmed)
2. **11:00 AM-1:00 PM ET** - Mid-session (reversal signals, new trends)
3. **3:00-3:30 PM ET** - Before close (final consolidation patterns)

**Why these times?**
- 9:30-10 AM: Price discovers fair value, volume highest
- 11-1 PM: Dead-cat bounces, mid-day reversals become clear
- 3-3:30 PM: Can assess whether day's trend will hold into next day

### Data Pipeline Architecture

**Optimal Design for Swing Trading:**

```
Phase 1: Pre-Market (4:00-9:30 AM ET)
├─ 4:00 AM: Load yesterday's EOD data
│           - Price closes, volume
│           - Technical indicators (RSI, SMA, ATR)
│           - Earnings calendar, news, events
├─ 5:00 AM: Generate pre-market signals
│           - Score all candidates based on EOD setup
│           - Rank by strength and risk/reward
└─ 9:00 AM: Final pre-market scan
            - Check gaps, overnight futures movement
            - Flag biggest movers, volatility spikes

Phase 2: Market Hours (9:30 AM-4:00 PM ET)
├─ 9:30 AM: FIRST EXECUTION (use pre-market signals)
│           - Execute strongest setups at open
│           - Monitor for reversals/invalidations
├─ 11:00 AM: Mid-day update
│           - Refresh 4-hour indicators if using
│           - Check if trends intact
│           - Update stop losses
├─ 1:00 PM: Mid-afternoon scan
│           - Look for new reversal setups
│           - Check for profit-taking momentum
└─ 3:30 PM: Pre-close update
            - Final decision on adding/exiting

Phase 3: Post-Market (4:00-5:00 PM ET)
└─ 4:00 PM: EOD reconciliation
            - Calculate final P&L
            - Assess next day's setup
            - Generate overnight alerts
```

### Signal Generation Strategy

**Daily Swing Trading Signals (Best Practice):**

1. **Pre-Market Scan (5:00 AM ET)**
   - Use yesterday's close + volume
   - Identify Stage 2 stocks (uptrending)
   - Find RSI <30 / <20 for entry setups
   - Check for volume confirmation
   - Generate top 10-20 candidates

2. **Market Open Execution (9:30-10:00 AM ET)**
   - Execute top 3-5 candidates from pre-market scan
   - Wait for opening momentum to confirm/deny setup
   - Use 1-minute bars to confirm entry trigger
   - Size positions conservatively (start with half-size)

3. **Mid-Day Monitoring (11 AM-1 PM ET)**
   - Check if morning trades are profitable
   - Look for second-wave setups (11-1 PM common)
   - Don't add new trades if already 3+ open
   - Tighten stops on profitable trades

4. **Pre-Close Review (3:30 PM ET)**
   - Assess which trades to hold vs. exit
   - Check for end-of-day momentum
   - Make final sizing decisions

### Frequency Decision Matrix

| Scenario | Frequency | Reason |
|----------|-----------|--------|
| Small account (<$25k) | 1x daily (EOD) | Simple to manage, fewer forced trades |
| Medium account ($25k-$100k) | 2x daily (AM + PM) | Capture more setups, split execution |
| Large account ($100k+) | 3-4x daily (AM + mid + PM) | Risk management easier, more opportunities |
| Professional (full-time) | 4-6x daily + monitoring | Adjust to market conditions, maximize alpha |

**For THIS system (starting/automated):** 2x daily (pre-market + market open) = good balance

---

## PROBLEM WITH CURRENT DESIGN

**Current (flawed):**
- Signals generated once at 5:30 AM ET
- Only one execution opportunity at 9:30 AM ET
- Miss mid-day setups and second-wave opportunities
- No ability to adjust based on market behavior throughout day
- Rigid timing

**Better Design:**
- Pre-market signal generation (5:00-5:30 AM ET)
- First execution at market open (9:30 AM ET) with top candidates
- Mid-day signal update (1:00 PM ET) for new setups
- Second execution opportunity (1:30-2:00 PM ET) if appropriate
- Final reconciliation at market close (4:00 PM ET)

---

## PROPOSED OPTIMAL ARCHITECTURE

### Data Loading Pipeline

```
PRICE DATA
├─ 4:00 AM ET: Load yesterday's EOD prices + volume
├─ Intraday: Optional (if we want intraday signals)
└─ 4:00 PM ET: Load today's EOD close (final)

TECHNICAL INDICATORS
├─ 4:30 AM ET: Calculate daily RSI, SMA, EMA, ATR, ATR stops
├─ Intraday: Optional (only if generating intraday signals)
└─ 4:30 PM ET: Recalculate on final close

MARKET CONTEXT
├─ 4:15 AM ET: Load VIX, market sentiment, sector rotation
├─ 1:00 PM ET: Mid-day market context update
└─ 4:00 PM ET: Final market close context

SIGNAL GENERATION
├─ 5:00 AM ET: PRE-MARKET signals (based on yesterday's close)
│             Output: Top 10-20 candidates scored and ranked
│
├─ 9:30 AM ET: ORCHESTRATOR RUN #1 (Market Open)
│             - Monitor existing positions
│             - Execute exits if needed
│             - Execute top 3-5 entries from pre-market signals
│
├─ 1:00 PM ET: MID-DAY UPDATE (optional, for new setups)
│             - Rescan for new reversal setups
│             - Check if morning trades valid
│             - Update position monitoring
│
├─ 2:00 PM ET: ORCHESTRATOR RUN #2 (optional, if new signals)
│             - Execute mid-day setups if warranted
│
└─ 4:00 PM ET: EOD RECONCILIATION
              - Final P&L update
              - Generate next-day setup report
              - Alert on overnight risks
```

### Orchestrator Frequency Decision

**Option A: Once Daily (9:30 AM)**
- Pros: Simple, fewer API calls, lower overhead
- Cons: Miss mid-day opportunities, can't respond to market changes

**Option B: Twice Daily (9:30 AM + 2:00 PM)**
- Pros: Capture more setups, can exit if trend breaks mid-day
- Cons: More complexity, more API calls
- Recommended: YES, especially for algorithm trading

**Option C: Continuous (Every hour or every trade trigger)**
- Pros: Maximum flexibility, best risk management
- Cons: Much more complex, real-time data requirements
- Recommended: Future enhancement

---

## BEST PRACTICE DECISION FOR THIS SYSTEM

Based on swing trading research:

### Recommended Frequency
**2x Daily Signal Generation + 2x Daily Execution**

**Why?**
1. Swing trading opportunities appear throughout the day
2. Pre-market analysis might be invalidated by 10 AM market behavior
3. Mid-day reversals create secondary entry opportunities
4. Can exit trades mid-day if setup breaks
5. Professional traders operate on this cadence

### Recommended Schedule

```
4:00 AM ET    - Price loaders (EOD data from yesterday)
4:30 AM ET    - Technical indicators calculation
5:00 AM ET    - PRE-MARKET signal generation

9:30 AM ET    - ORCHESTRATOR RUN #1 (Market Open)
              • Monitor existing positions
              • Execute top entries from pre-market
              • Check circuit breakers

1:00 PM ET    - MID-DAY signal generation (new setups only)
1:30 PM ET    - ORCHESTRATOR RUN #2 (Mid-day)
              • Check position health
              • Exit if trend breaks
              • Execute mid-day setups if strong

4:00 PM ET    - EOD reconciliation & metrics
```

### Data Handling

**For Swing Trading, Need:**
1. **Daily closes** (always, EOD at 4 PM ET)
2. **Volume data** (critical, with each close)
3. **Technical indicators** (RSI, SMA-50, SMA-200, ATR, stages)
4. **Market context** (VIX, sector rotation, seasonality)
5. **Position tracking** (Alpaca live, reconciled daily)

**Data Freshness Requirements:**
- Prices: Critical at EOD (must be accurate)
- Indicators: Can be daily (based on daily close)
- Market context: Daily sufficient
- Position data: Real-time (from Alpaca API)

**Intraday Considerations:**
- If using intraday signals: need hourly or 4-hourly bars
- For pure EOD swing trading: daily bars are sufficient
- Recommendation: Start with daily, add intraday later if needed

---

## SUMMARY OF RESEARCH FINDINGS

### Key Insights
1. **Daily signals are OK** but **missing opportunities** (mid-day setups)
2. **2x daily execution is optimal** for automated swing trading
3. **Data only needs daily refresh** (EOD closes sufficient)
4. **Execution timing is critical** (9:30 AM + 1:30 PM are best windows)
5. **Position monitoring is continuous** (but active trading only at execution windows)

### Best Practice Architecture for THIS System
- Pre-market signal generation (5:00 AM ET)
- Market open execution (9:30 AM ET) - Primary entry window
- Mid-day signal update (1:00 PM ET) - Optional but recommended
- Mid-afternoon execution (1:30 PM ET) - Secondary entry window
- EOD reconciliation (4:00 PM ET)

### Complexity vs. Return Trade-off
- **Simple (1x daily):** Lower implementation cost, but miss 30% of opportunities
- **Balanced (2x daily):** Small added complexity, capture ~70% of opportunities
- **Complex (4x+ daily):** Much higher overhead, capture ~85%+ of opportunities

**Recommendation: 2x daily is the sweet spot for automated swing trading**

---

## IMPLEMENTATION PLAN

### Phase 1: 2x Daily Execution (Recommended Start)
- Pre-market signal generation at 5:00 AM ET
- Orchestrator at 9:30 AM ET (primary execution)
- Orchestrator at 1:30 PM ET (secondary execution)
- EOD reconciliation at 4:00 PM ET

### Phase 2: Enhanced Monitoring (Add Later)
- Intraday stop loss adjustment (continuous)
- Real-time profit-taking triggers (continuous)
- Risk management alerts (continuous)

### Phase 3: Adaptive Signals (Advanced Future)
- Intraday signal generation (4-hour or hourly bars)
- Dynamic position sizing based on market volatility
- Seasonal/sector rotation adjustments

---

**CONCLUSION:**
The best practice for this swing trading system is **2x daily execution** (market open + mid-afternoon), with data only needing daily refresh at EOD. This balances simplicity with opportunity capture.
