# Correct Design Specification - Professional Swing Trading Algorithm
**Based on:** Minervini/Weinstein teachings, professional trading standards, and your existing code intent

---

## THE CORRECT ARCHITECTURE

### What Swing Trading Algorithm Should Do (Professional Standard)

#### Entry Rules (Minervini Template)
1. **Signal Generation** (Day 0): Detect oversold bounce (RSI < 30 + MACD crossover)
2. **Confirmation** (Day 1): Wait for next trading day
   - Check if daily trend template is still uptrending (Stage 2)
   - Verify stock is above 30-day MA
   - Check volume > average
3. **Entry** (Day 1 open/close): Enter only if:
   - Conditions from Day 0 still valid on Day 1
   - OR: Price and indicators still support entry
   - Use **market close price** on entry day (NOT theoretical "buylevel")
4. **Stop Loss**: Place below support (typically low of past 2 weeks)
5. **Targets**: 1.5R, 3R, 4R multiples from actual risk

#### Exit Rules (Minervini Discipline)
1. **First Check**: Day 2+ only (never same day as entry)
2. **Trend Break**: If price closes below key MA on volume
3. **Partial Exits**: Take profits at targets (50% at T1, 25% at T2, 25% at T3)
4. **Trailing Stop**: Adjust stop up after breaking support
5. **Time Stop**: Max hold 20-30 days unless strong conviction

---

## THE CORRECT FLOW (Multi-Day Lifecycle)

```
DAY 0 (Monday):
  - Generate signals: RSI < 30 + MACD > signal_line
  - Store: symbol, date, signal, close_price, rsi, macd, etc.
  - Do NOT create trades yet

DAY 1 (Tuesday):
  - Load Day 0 signals
  - For each signal:
    * Fetch Day 1 market data
    * Check: Is Stage 2 still valid? Is price > 30-day MA?
    * If YES: Create trade at Day 1 close price
    * If NO: Skip this signal
  - Create trades with:
    * entry_price = Day 1 close (actual market price)
    * entry_date = Day 1
    * signal_date = Day 0 (when signal was generated)

DAY 2+ (Wednesday+):
  - Monitor all open trades
  - Check daily for exit conditions:
    * "Closed below 30-day MA on volume" → EXIT
    * Hit stop loss → EXIT  
    * Hit profit target → PARTIAL or FULL EXIT
  - Exit when first condition triggers
  - Record: exit_date, exit_price, exit_reason, P&L

RESULT:
  - Multi-day holds (minimum 2 days, typical 5-20 days)
  - Realistic P&L (can be +/- based on market movement)
  - Professional risk management
```

---

## THE CORRECT DATA FLOW

### 1. Signal Generation (loadbuyselldaily.py)
```
Input:  price_daily (OHLCV history)
Process: Calculate RSI, MACD on price history
Output: buy_sell_daily with:
  - symbol, date, signal
  - close (market close price)
  - rsi, macd, signal_line
  - sma_50, sma_200, ema_21
  - DO NOT create entry_price - it's not known yet!

Entry_price field should be DELETED or left NULL
(It will be determined on Day 1 when trade actually enters)
```

### 2. Signal Evaluation & Entry Decision (algo_filter_pipeline.py)
```
Input: buy_sell_daily signals from Day 0
Process on Day 1:
  1. Fetch latest price_daily for signal symbols (Day 1 data)
  2. Check filter tiers:
     - T1: Data quality (>70% complete, price > $1)
     - T2: Market health (SPY Stage 2, VIX < 35)
     - T3: Stock stage (Weinstein Stage 2 - is it uptrending?)
     - T4: Signal quality (SQS score)
     - T5: Portfolio health (concentration, position limits)
  3. For survivors: Get Day 1 close price from price_daily
  4. Use Day 1 close as entry_price (NOT the old wrong buylevel)
  5. Return: Only Day 1 closes, no theoretical prices
```

### 3. Trade Execution (algo_trade_executor.py)
```
Input: Qualified trade with:
  - symbol, entry_price (Day 1 close), stop_loss, targets
  - signal_date (Day 0 - when signal appeared)
  - entry_date = TODAY (Day 1)

Action: Create trade via Alpaca
Store in algo_trades:
  - trade_id (unique)
  - symbol
  - signal_date (Day 0)
  - entry_date (Day 1 - DIFFERENT from signal_date!)
  - entry_price (Day 1 close from market)
  - status = 'open'
```

### 4. Exit Detection & Execution (algo_exit_engine.py)
```
Input: All open trades from previous days
For each open trade on Day 2+:
  1. Fetch latest price_daily for that symbol
  2. Check: Is today's close below 30-day MA on volume?
  3. If YES: Execute exit at today's close
  4. Update algo_trades:
     - exit_date = today
     - exit_price = today's close
     - exit_reason = "Minervini: closed below MA"
     - status = 'closed'
     - pnl = (exit_price - entry_price) / entry_price * 100
```

---

## THE CORRECT PRICES TO USE

| Component | Price To Use | Where From | Why |
|-----------|-------------|-----------|-----|
| Signal Generation | N/A (just detect) | RSI/MACD calc | Generating signal, not executing |
| Trade Entry | **market close** | price_daily.close on entry_date | Actual executable price |
| Trade Exit | **market close** | price_daily.close on exit_date | Actual executable price |
| Position Monitoring | **close** or **high/low** | price_daily intraday | Monitor against targets/stops |
| Stop Loss Placement | **support level** | historical lows | Risk management |
| **NOT to use** | **buylevel** (theoretical) | buy_sell_daily.entry_price | This is wrong - it's a theoretical buy zone, not market price |

---

## THE CRITICAL DIFFERENCES FROM CURRENT (BROKEN) CODE

| Aspect | WRONG (Current) | RIGHT (Should Be) |
|--------|-----------------|-------------------|
| Entry price source | buy_sell_daily.entry_price | price_daily.close on entry_date |
| Entry timing | Same day as signal | Next day (Day 1) |
| Entry date | signal_date | Next trading day |
| Exit timing | Same day as entry! | Day 2 or later |
| Exit check | signal_date data | Current/latest market data |
| Trade lifecycle | 1 day (same day) | 5-20 days typical |
| P&L result | Always 0% (same price) | Realistic +/- based on market |

---

## KEY PROFESSIONAL PRINCIPLES

**1. Separation of Concerns**
- Signal generation ≠ Trade execution
- Generate signal Day 0
- Execute trade Day 1 (with fresh market data)
- Monitor exits Day 2+

**2. Use Only Market Data For Execution**
- Never use theoretical prices (buylevel, pivot, etc.)
- Always use price_daily.close for actual entry/exit
- Only use levels for analysis, not execution

**3. Multi-Day Trade Lifecycle**
- Signal generated on one day
- Entry on same/next day with market data
- Exit on day 2 or later
- Minimum holding period prevents same-day flip

**4. Validate Against Market Reality**
- Before entering: Confirm conditions still valid on entry_date
- Before exiting: Check actual market close, volume, MA position
- Don't trust old data - always verify with fresh market data

**5. Proper Date Handling**
- signal_date ≠ entry_date ≠ exit_date
- Each must be tracked separately
- Never confuse dates (currently broken - all same)

---

## WHAT NEEDS TO CHANGE

### Code Changes Required

1. **Delete/Fix buy_sell_daily.entry_price**
   - This field should NOT exist for trade execution
   - It's corrupting entry logic
   - Use price_daily.close instead

2. **Fix algo_filter_pipeline.py**
   - Don't pull entry_price from signals
   - On Day 1, fetch fresh price_daily.close
   - Use that for entry decision

3. **Fix algo_run_daily.py**
   - Entry should be Day 1 (not same day as signal)
   - Exit checking should be Day 2+ only
   - Use price_daily not buy_sell_daily for prices

4. **Fix algo_exit_engine.py**
   - Check should be on current market data
   - Not signal_date - that's old!
   - Enforce minimum holding period (>= 2 days)

5. **Fix algo_trade_executor.py**
   - entry_date and signal_date must be different
   - entry_price must come from market (price_daily)
   - Add validation: entry_date > signal_date

### Data Cleanup

1. Audit all 51 existing trades
   - Fix entry_date = signal_date (wrong!)
   - Recalculate entry_price if possible
   - Recalculate P&L with correct prices

2. Clean buy_sell_daily
   - Remove entry_price field (it's wrong)
   - Or if kept: use it only for analysis, not execution
   - Validate remaining data

---

## VERIFICATION CHECKLIST

After fixes, verify:
- [ ] No trade has entry_date == exit_date
- [ ] All trades have entry_date > signal_date (or entry_date == signal_date+1)
- [ ] entry_price matches price_daily.close on entry_date
- [ ] exit_price matches price_daily.close on exit_date
- [ ] At least 50% of trades have non-zero P&L
- [ ] Exit reasons mention "Day 2+", not same day
- [ ] Filter pipeline checks Day 1+ data, not Day 0

---

## PROFESSIONAL STANDARD COMPLIANCE

This design follows:
✅ Mark Minervini's trend template (Stage 2 confirmation)  
✅ Mark Weinstein's stage analysis (4-stage framework)  
✅ Professional trading industry standards (multi-day lifecycle)  
✅ Risk management best practices (targets, stops, trailing stops)  
✅ Data integrity principles (use market data, not theoretical)  
✅ Software engineering best practices (separation of concerns)

