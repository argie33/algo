#!/bin/bash
# LOAD ALL DATA - Sequential execution of ALL real production loaders
# This uses the ACTUAL loaders you'll use in AWS
# Total time: ~10-15 hours (can run overnight)
# No alternatives, no _fast versions - just the real thing

set -e  # Exit on error

LOG_DIR="$(pwd)/loader_logs"
mkdir -p "$LOG_DIR"

log_stage() {
    echo ""
    echo "========================================================================"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
    echo "========================================================================"
    echo ""
}

run_loader() {
    local script=$1
    local stage=$2
    local log_file="$LOG_DIR/${stage}_$(basename $script .py).log"

    log_stage "$stage: Running $script"

    if python3 "$script" 2>&1 | tee "$log_file"; then
        echo "[OK] $script completed successfully"
    else
        echo "[ERROR] $script FAILED - check $log_file"
        exit 1
    fi
}

# ========================================================================
# PHASE 1: LOAD PRICE HISTORY (1 hour)
# ========================================================================
log_stage "PHASE 1: Price Data - Daily/Weekly/Monthly"
run_loader "loadpricedaily.py" "01-prices-daily"
run_loader "loadpriceweekly.py" "02-prices-weekly"
run_loader "loadpricemonthly.py" "03-prices-monthly"

# ========================================================================
# PHASE 2: COMPANY DATA (45 minutes)
# ========================================================================
log_stage "PHASE 2: Company Fundamentals (key_metrics)"
run_loader "loaddailycompanydata.py" "04-company-data"

# ========================================================================
# PHASE 3: FINANCIAL STATEMENTS (2-3 hours parallel)
# ========================================================================
log_stage "PHASE 3: Financial Statements (Annual + Quarterly)"
echo "Running 6 financial loaders in parallel..."

python3 loadannualincomestatement.py > "$LOG_DIR/05a_annual_income.log" 2>&1 &
pid1=$!
python3 loadannualbalancesheet.py > "$LOG_DIR/05b_annual_bs.log" 2>&1 &
pid2=$!
python3 loadannualcashflow.py > "$LOG_DIR/05c_annual_cf.log" 2>&1 &
pid3=$!
python3 loadquarterlyincomestatement.py > "$LOG_DIR/05d_qtr_income.log" 2>&1 &
pid4=$!
python3 loadquarterlybalancesheet.py > "$LOG_DIR/05e_qtr_bs.log" 2>&1 &
pid5=$!
python3 loadquarterlycashflow.py > "$LOG_DIR/05f_qtr_cf.log" 2>&1 &
pid6=$!

wait $pid1 $pid2 $pid3 $pid4 $pid5 $pid6 || {
    echo "[ERROR] One or more financial loaders failed"
    exit 1
}
echo "[OK] All financial statements loaded"

# ========================================================================
# PHASE 4: FACTOR METRICS (1-2 hours)
# ========================================================================
log_stage "PHASE 4: Factor Metrics (Quality/Growth/Value/Stability)"
run_loader "loadfactormetrics.py" "06-factor-metrics"

# ========================================================================
# PHASE 5: STOCK SCORES (30 minutes)
# ========================================================================
log_stage "PHASE 5: Stock Scores (Composite Ranking)"
run_loader "loadstockscores.py" "07-stock-scores"

# ========================================================================
# PHASE 6: TRADING SIGNALS (4-6 hours parallel)
# ========================================================================
log_stage "PHASE 6: Trading Signals (Daily/Weekly/Monthly)"
echo "Running buy/sell loaders in parallel..."

python3 loadbuyselldaily.py > "$LOG_DIR/08a_signals_daily.log" 2>&1 &
pid1=$!
python3 loadbuysellweekly.py > "$LOG_DIR/08b_signals_weekly.log" 2>&1 &
pid2=$!
python3 loadbuysellmonthly.py > "$LOG_DIR/08c_signals_monthly.log" 2>&1 &
pid3=$!

wait $pid1 $pid2 $pid3 || {
    echo "[ERROR] One or more signal loaders failed"
    exit 1
}
echo "[OK] All trading signals generated"

# ========================================================================
# PHASE 7: MARKET CONTEXT (1-2 hours parallel)
# ========================================================================
log_stage "PHASE 7: Market Context & Analysis Data"
echo "Running market/sector/analyst loaders in parallel..."

python3 loadsectorranking.py > "$LOG_DIR/09a_sector_ranking.log" 2>&1 &
pid1=$!
python3 loadindustryranking.py > "$LOG_DIR/09b_industry_ranking.log" 2>&1 &
pid2=$!
python3 loadanalystupgradedowngrade.py > "$LOG_DIR/09c_analyst_upgrades.log" 2>&1 &
pid3=$!
python3 loadecondata.py > "$LOG_DIR/09d_econ_data.log" 2>&1 &
pid4=$!

wait $pid1 $pid2 $pid3 $pid4 || {
    echo "[ERROR] One or more context loaders failed"
    exit 1
}
echo "[OK] All market context data loaded"

# ========================================================================
# DONE
# ========================================================================
log_stage "COMPLETE: All data loaded successfully!"
echo ""
echo "Logs saved in: $LOG_DIR"
echo ""
echo "To verify data:"
echo "  python3 -c \"import psycopg2, os; conn = psycopg2.connect(host='localhost', database='stocks', user='stocks', password=os.getenv('DB_PASSWORD')); cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM price_daily'); print(f'Price records: {cur.fetchone()[0]:,}'); conn.close()\""
echo ""
