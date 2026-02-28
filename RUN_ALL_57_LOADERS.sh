#!/bin/bash
# COMPLETE DATA LOAD - ALL 57 LOADERS IN PARALLEL

set -a
export AWS_REGION=us-east-1
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks
export PGPASSWORD=bed0elAn
export FRED_API_KEY=0a4d65c73e9e97a0c3ca65ac73e9e97a5e82
set +a

mkdir -p /home/arger/algo/loader_logs

echo "════════════════════════════════════════════════════════════════"
echo "🚀 LAUNCH ALL 57 DATA LOADERS"
echo "════════════════════════════════════════════════════════════════"
echo "Started: $(date)"
echo ""

# List of ALL loaders
LOADERS=(
    "loadstockscores"
    "loadpricedaily"
    "loadpriceweekly"
    "loadpricemonthly"
    "loadfactormetrics"
    "loadbuysell_etf_daily"
    "loadbuysell_etf_weekly"
    "loadbuysell_etf_monthly"
    "loadbuyselldaily"
    "loadbuysellweekly"
    "loadbuysellmonthly"
    "loadannualincomestatement"
    "loadannualbalancesheet"
    "loadannualcashflow"
    "loadquarterlyincomestatement"
    "loadquarterlybalancesheet"
    "loadquarterlycashflow"
    "loadearningshistory"
    "loadearningsmetrics"
    "loadearningsrevisions"
    "loadanalystsentiment"
    "loadanalystupgradedowngrade"
    "loadmarket"
    "loadmarketindices"
    "loadbenchmark"
    "loadsectorranking"
    "loadsectors"
    "loadindustryranking"
    "loaddailycompanydata"
    "loadfeargreed"
    "loadecondata"
    "loadnews"
    "loadsecfilings"
    "loadaaiidata"
    "loadnaaim"
    "loadcalendar"
    "loadtechnicalindicators"
    "loadetfpricedaily"
    "loadetfpriceweekly"
    "loadetfpricemonthly"
    "loadetfsignals"
    "loadlatestpricedaily"
    "loadlatestpriceweekly"
    "loadlatestpricemonthly"
    "loadseasonality"
    "loadrelativeperformance"
    "loadstocksymbols"
    "loadsentiment"
    "loadttmincomestatement"
    "loadttmcashflow"
    "loadcommodities"
    "loadinsidertransactions"
    "loadoptionschains"
    "loadcoveredcallopportunities"
    "loadguidance"
    "loadalpacaportfolio"
    "loadearningssurprise"
)

echo "Total loaders to launch: ${#LOADERS[@]}"
echo ""

STARTED=0
for loader in "${LOADERS[@]}"; do
    if [ -f "/home/arger/algo/${loader}.py" ]; then
        timeout 1200 python3 "/home/arger/algo/${loader}.py" > "/home/arger/algo/loader_logs/${loader}.log" 2>&1 &
        STARTED=$((STARTED + 1))
        echo "[$(printf '%3d' $STARTED)/$((${#LOADERS[@]})] Starting: $loader"
    else
        echo "[SKIP] $loader - file not found"
    fi

    # Stagger startup to avoid overwhelming the system
    sleep 0.2
done

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Launched $STARTED loaders"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Waiting for completion... This may take several minutes."
echo "Monitor with: tail -f /home/arger/algo/loader_logs/*.log"
echo ""

# Wait for all background jobs
wait

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ ALL LOADERS FINISHED - $(date)"
echo "════════════════════════════════════════════════════════════════"
