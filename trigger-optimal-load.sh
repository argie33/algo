#!/bin/bash

# Optimal Data Loading Trigger Script
# Usage: ./trigger-optimal-load.sh [api-token]

API_TOKEN="${1:-}"
REPO="argie33/algo"
WORKFLOW="deploy-app-stocks.yml"

if [[ -z "$API_TOKEN" ]]; then
  echo "ERROR: GitHub API token required"
  echo "Usage: ./trigger-optimal-load.sh <github-pat-token>"
  echo ""
  echo "Get token from: https://github.com/settings/tokens"
  echo "Need scopes: repo, workflow"
  exit 1
fi

# Optimal batch sequence
declare -a BATCHES=(
  "stocksymbols"
  "pricedaily,priceweekly,pricemonthly"
  "dailycompanydata"
  "buyselldaily,buysellweekly,buysellmonthly"
  "annualbalancesheet,annualincomestatement,annualcashflow"
  "quarterlybalancesheet,quarterlyincomestatement,quarterlycashflow"
  "earningshistory,earningsestimate,factormetrics"
  "stockscores"
  "etfpricedaily,etfpriceweekly,etfpricemonthly"
  "buysell_etf_daily,buysell_etf_weekly,buysell_etf_monthly"
  "analystsentiment,earningsrevisions,sectors,benchmark"
  "econdata,naaim,feargreed,aaiidata"
)

echo "🚀 OPTIMAL DATA LOADING - FULL SEQUENCE"
echo "========================================"
echo "Starting optimal batch execution..."
echo ""

batch_num=1
for batch in "${BATCHES[@]}"; do
  echo "[Batch $batch_num] Triggering: $batch"
  
  # Trigger workflow via GitHub API
  curl -X POST \
    -H "Authorization: token $API_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/dispatches" \
    -d "{
      \"ref\": \"main\",
      \"inputs\": {
        \"loaders\": \"$batch\",
        \"environment\": \"prod\"
      }
    }" \
    -s | jq . > /dev/null
  
  if [[ $? -eq 0 ]]; then
    echo "✅ Batch $batch_num triggered - Monitor at: https://github.com/$REPO/actions"
    echo ""
    
    # Wait time between batches (allow previous to progress)
    if [[ $batch_num -lt ${#BATCHES[@]} ]]; then
      echo "⏳ Waiting 60 seconds before next batch..."
      echo ""
      sleep 60
    fi
  else
    echo "❌ Failed to trigger batch $batch_num"
    exit 1
  fi
  
  ((batch_num++))
done

echo ""
echo "✅ ALL BATCHES QUEUED FOR EXECUTION"
echo "📊 Monitor progress at: https://github.com/$REPO/actions"
echo ""
echo "Expected timeline:"
echo "  - Batch 1-3: ~30 min (symbols + prices)"
echo "  - Batch 4-6: ~45 min (signals + financials)"
echo "  - Batch 7-8: ~20 min (earnings + scores)"
echo "  - Batch 9-12: ~30 min (ETF + advanced)"
echo "  TOTAL: ~90-120 minutes"
echo ""
echo "Check data when complete: curl http://localhost:5174/api/diagnostics"

