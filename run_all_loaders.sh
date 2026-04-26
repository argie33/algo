#!/bin/bash
set +e
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks

LOGFILE="/tmp/full_load_$(date +%Y%m%d_%H%M%S).log"
echo "Loading ALL data - logging to $LOGFILE"

LOADERS=(
    "loadstocksymbols"
    "loadpricedaily" "loadpriceweekly" "loadpricemonthly"
    "loadetfpricedaily" "loadetfpriceweekly" "loadetfpricemonthly"
    "loadtechnicalindicators" "loadstockscores" "load_real_scores"
    "loadbuyselldaily" "loadbuysellweekly" "loadbuysellmonthly"
    "loadbuysell_etf_daily" "loadbuysell_etf_weekly" "loadbuysell_etf_monthly"
    "loadannualincomestatement" "loadquarterlyincomestatement"
    "loadannualbalancesheet" "loadquarterlybalancesheet"
    "loadannualcashflow" "loadquarterlycashflow"
    "loadttmincomestatement" "loadttmcashflow"
    "loadearningshistory" "loadearningsrevisions" "loadearningscalendar"
    "loadgrowthmetrics" "loadvaluemetrics" "loadqualitymetrics" "loadmomentummetrics" "loadstabilitymetrics"
    "loaddailycompanydata" "loadcompanyprofile"
    "loadfeargreed" "loadnaaim" "loadinsider" "loadindustryranking" "loadsectorranking"
    "loadfactormetrics" "loadrelativeperformance" "loadbenchmark"
    "loadanalystsentiment" "loadanalystupgradedowngrade"
    "loadcalendar" "loadecondata" "loadcommodities"
    "loadcoveredcallopportunities" "loadoptionschains" "loadoptionsgreeks"
    "loadalpacaportfolio" "loadpositioningmetrics"
    "loadetfsignals" "loadlatestpricedaily" "loadlatestpricemonthly"
    "loadaaiidata"
)

SUCCESS=0
FAILED=0

for loader in "${LOADERS[@]}"; do
    echo "[$(date +%H:%M:%S)] Running $loader..."
    timeout 900 python3 "${loader}.py" >> "$LOGFILE" 2>&1
    if [ $? -eq 0 ]; then
        SUCCESS=$((SUCCESS + 1))
        echo "   OK"
    else
        FAILED=$((FAILED + 1))
        echo "   FAILED (see log)"
    fi
done

echo ""
echo "=========================================="
echo "LOAD COMPLETE"
echo "Success: $SUCCESS | Failed: $FAILED"
echo "Log: $LOGFILE"
echo "=========================================="
