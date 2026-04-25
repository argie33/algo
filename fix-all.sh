#!/bin/bash
echo "FIXING ALL DATA GAPS..."
echo "======================================"

# Kill any existing loaders
pkill -f "python load" 2>/dev/null
pkill -f "python populate" 2>/dev/null

# Start all critical loaders in background
echo "Starting all loaders..."

# Weekly/Monthly prices
timeout 600 python loadpriceweekly.py > /tmp/price-weekly.log 2>&1 &
echo "  - loadpriceweekly.py"

timeout 600 python loadpricemonthly.py > /tmp/price-monthly.log 2>&1 &
echo "  - loadpricemonthly.py"

# ETF prices
timeout 600 python loadetfpricedaily.py > /tmp/etf-daily.log 2>&1 &
echo "  - loadetfpricedaily.py"

timeout 600 python loadetfpriceweekly.py > /tmp/etf-weekly.log 2>&1 &
echo "  - loadetfpriceweekly.py"

timeout 600 python loadetfpricemonthly.py > /tmp/etf-monthly.log 2>&1 &
echo "  - loadetfpricemonthly.py"

# Weekly/Monthly buy/sell signals
timeout 600 python loadbuysellweekly.py > /tmp/buysell-weekly.log 2>&1 &
echo "  - loadbuysellweekly.py"

timeout 600 python loadbuysellmonthly.py > /tmp/buysell-monthly.log 2>&1 &
echo "  - loadbuysellmonthly.py"

# Metrics
timeout 600 python loadfactormetrics.py > /tmp/factor-metrics.log 2>&1 &
echo "  - loadfactormetrics.py"

# Sectors and industries
timeout 600 python loadsectorranking.py > /tmp/sector-ranking.log 2>&1 &
echo "  - loadsectorranking.py"

timeout 600 python loadindustryranking.py > /tmp/industry-ranking.log 2>&1 &
echo "  - loadindustryranking.py"

# Annual balance sheet
timeout 600 python loadannualbalancesheet.py > /tmp/annual-balance.log 2>&1 &
echo "  - loadannualbalancesheet.py"

# Quarterly balance sheet (may already be loaded but make sure)
timeout 600 python loadquarterlybalancesheet.py > /tmp/quarterly-balance.log 2>&1 &
echo "  - loadquarterlybalancesheet.py"

# Company data
timeout 600 python loaddailycompanydata.py > /tmp/company-data.log 2>&1 &
echo "  - loaddailycompanydata.py"

echo ""
echo "All loaders started. Monitoring progress..."
echo "This will take ~10-30 minutes depending on API limits"
echo ""

# Wait for all background jobs
wait

echo ""
echo "Loaders complete!"
