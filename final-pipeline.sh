#!/bin/bash

export $(cat /c/Users/arger/code/algo/.env.local | grep -v '^#' | xargs)
cd /c/Users/arger/code/algo

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║ CORRECT SEQUENTIAL PIPELINE                                    ║"
echo "║ 1. PRICES → 2. TECHNICALS → 3. BUY/SELL                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# PHASE 1: WAIT FOR HISTORICAL PRICES TO COMPLETE
# ============================================================================
echo "⏳ PHASE 1: HISTORICAL PRICES (batch 994/994)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Waiting for all 5000+ symbols to load from yfinance..."
echo ""

for i in {1..7200}; do
  BATCH=$(grep -oP "batch \K[0-9]+(?=/)" /tmp/historical_prices.log 2>/dev/null | tail -1)
  
  if [ -z "$BATCH" ]; then
    echo "Waiting for price loader to start..."
    sleep 30
    continue
  fi
  
  PCT=$((BATCH * 100 / 994))
  
  # Show progress every 30 seconds
  if [ $((i % 3)) -eq 0 ]; then
    BAR=$(printf '█%.0s' $(seq 1 $((PCT / 5))))
    EMPTY=$(printf '░%.0s' $(seq 1 $((20 - PCT / 5))))
    echo -ne "Progress: [$BAR$EMPTY] $BATCH/994 ($PCT%)\r"
  fi
  
  # Check if complete
  if [ "$BATCH" -eq 994 ]; then
    echo ""
    echo "✅ PHASE 1 COMPLETE!"
    break
  fi
  
  sleep 10
done

echo ""
echo "Verifying price data..."
PRICE_COUNT=$(node << 'NODEEOF' 2>/dev/null
const { Pool } = require('pg');
const pool = new Pool({
  host: 'localhost', port: 5432, user: 'stocks',
  password: 'bed0elAn', database: 'stocks'
});
pool.query('SELECT COUNT(*) as c FROM price_daily').then(r => {
  console.log(r.rows[0].c);
  pool.end();
}).catch(() => { console.log('?'); process.exit(1); });
NODEEOF
)
echo "Total price records: $PRICE_COUNT"
echo ""

# ============================================================================
# PHASE 2: CALCULATE TECHNICAL INDICATORS
# ============================================================================
echo "🔧 PHASE 2: CALCULATE TECHNICAL INDICATORS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Calculating RSI, MACD, SMA, EMA, ATR for all prices..."
echo ""

python3 populate-technical-data.py 2>&1 | while read line; do
  if echo "$line" | grep -q "Progress:"; then
    echo "$line"
  elif echo "$line" | grep -q "Complete!"; then
    echo "$line"
  fi
done

echo ""
echo "Verifying technical data..."
TECH_COUNT=$(node << 'NODEEOF' 2>/dev/null
const { Pool } = require('pg');
const pool = new Pool({
  host: 'localhost', port: 5432, user: 'stocks',
  password: 'bed0elAn', database: 'stocks'
});
pool.query('SELECT COUNT(*) as c FROM technical_data_daily WHERE rsi IS NOT NULL').then(r => {
  console.log(r.rows[0].c);
  pool.end();
}).catch(() => { console.log('?'); process.exit(1); });
NODEEOF
)
echo "Technical records calculated: $TECH_COUNT"
echo ""

# ============================================================================
# PHASE 3: REGENERATE PRICE AGGREGATIONS
# ============================================================================
echo "📊 PHASE 3: REGENERATE WEEKLY/MONTHLY PRICES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Aggregating daily → weekly..."
python3 loadpriceweekly.py 2>&1 | grep -E "inserted|error|ERROR" | tail -5

echo ""
echo "Aggregating daily → monthly..."
python3 loadpricemonthly.py 2>&1 | grep -E "inserted|error|ERROR" | tail -5

echo ""
echo "✅ PHASE 3 COMPLETE"
echo ""

# ============================================================================
# PHASE 4: GENERATE BUY/SELL SIGNALS
# ============================================================================
echo "🎯 PHASE 4: GENERATE BUY/SELL SIGNALS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Generating daily signals..."
python3 loadbuyselldaily.py 2>&1 | grep -E "inserted|signal|error|ERROR" | tail -5

echo ""
echo "Generating weekly signals..."
python3 loadbuysellweekly.py 2>&1 | grep -E "inserted|signal|error|ERROR" | tail -5

echo ""
echo "Generating monthly signals..."
python3 loadbuysellmonthly.py 2>&1 | grep -E "inserted|signal|error|ERROR" | tail -5

echo ""
echo "✅ PHASE 4 COMPLETE"
echo ""

# ============================================================================
# FINAL VERIFICATION
# ============================================================================
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║ FINAL DATA VERIFICATION                                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

node << 'NODEEOF'
const { Pool } = require('pg');
const pool = new Pool({
  host: 'localhost', port: 5432, user: 'stocks',
  password: 'bed0elAn', database: 'stocks'
});

async function verify() {
  try {
    const tables = [
      { name: 'price_daily', query: 'SELECT COUNT(*) as c FROM price_daily' },
      { name: 'price_weekly', query: 'SELECT COUNT(*) as c FROM price_weekly' },
      { name: 'price_monthly', query: 'SELECT COUNT(*) as c FROM price_monthly' },
      { name: 'technical_data_daily', query: 'SELECT COUNT(*) as c FROM technical_data_daily' },
      { name: 'buy_sell_daily', query: 'SELECT COUNT(*) as c FROM buy_sell_daily WHERE signal IN (\'Buy\', \'Sell\')' },
      { name: 'buy_sell_weekly', query: 'SELECT COUNT(*) as c FROM buy_sell_weekly WHERE signal IN (\'Buy\', \'Sell\')' },
      { name: 'buy_sell_monthly', query: 'SELECT COUNT(*) as c FROM buy_sell_monthly WHERE signal IN (\'Buy\', \'Sell\')' }
    ];

    console.log('Final Data State:\n');
    for (const table of tables) {
      const result = await pool.query(table.query);
      const count = result.rows[0].c;
      const status = count > 0 ? '✅' : '❌';
      console.log(`${status} ${table.name.padEnd(25)} ${count.toString().padStart(10)} records`);
    }

    await pool.end();
  } catch (e) {
    console.error('Error:', e.message);
    process.exit(1);
  }
}

verify();
NODEEOF

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║ ✅ PIPELINE COMPLETE - ALL DATA LOADED                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
