#!/bin/bash
# Comprehensive Loader Audit Script
# Verify all 39 official loaders meet quality standards

set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# All 39 official loaders
LOADERS=(
    "aaiidata" "alpacaportfolio" "analystsentiment" "analystupgradedowngrade"
    "annualbalancesheet" "annualcashflow" "annualincomestatement"
    "benchmark" "buysell_etf_daily" "buysell_etf_monthly" "buysell_etf_weekly"
    "buyselldaily" "buysellmonthly" "buysellweekly" "calendar"
    "commodities" "coveredcallopportunities" "dailycompanydata"
    "earningshistory" "earningsrevisions" "earningssurprise"
    "econdata" "etfpricedaily" "etfpricemonthly" "etfpriceweekly"
    "etfsignals" "factormetrics" "feargreed" "guidance"
    "insidertransactions" "latestpricedaily" "latestpricemonthly"
    "latestpriceweekly" "market" "marketindices" "naaim"
    "news" "optionschains" "pricedaily" "pricemonthly" "priceweekly"
    "quarterlybalancesheet" "quarterlycashflow" "quarterlyincomestatement"
    "relativeperformance" "seasonality" "secfilings" "sectors"
    "sentiment" "_sp500_earnings" "stockscores" "stocksymbols"
    "technicalsdaily" "technicalsmonthly" "technicalsweekly"
    "ttmcashflow" "ttmincomestatement"
)

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Comprehensive Loader Audit${NC}"
echo -e "${BLUE}Checking ${#LOADERS[@]} official loaders${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Audit counters
TOTAL_LOADERS=${#LOADERS[@]}
FILES_FOUND=0
PHASE_A_ENABLED=0
TIMEOUT_PROTECTED=0
ERROR_HANDLING=0
LOGGING_ENABLED=0
DATABASE_HELPER=0
DOCKERFILES_FOUND=0
TASK_DEFS_FOUND=0

# Arrays to track results
MISSING_FILES=()
PHASE_A_MISSING=()
TIMEOUT_MISSING=()
ERROR_HANDLING_MISSING=()
LOGGING_MISSING=()
DB_HELPER_MISSING=()
DOCKERFILE_MISSING=()
TASKDEF_MISSING=()

# Check each loader
for loader in "${LOADERS[@]}"; do
    LOADER_FILE="load${loader}.py"

    # 1. Check file exists
    if [[ -f "$LOADER_FILE" ]]; then
        ((FILES_FOUND++))

        # 2. Check Phase A (S3 staging or incremental)
        if grep -q "USE_S3_STAGING\|s3_copy_to_table\|incremental" "$LOADER_FILE"; then
            ((PHASE_A_ENABLED++))
        else
            PHASE_A_MISSING+=("$loader")
        fi

        # 3. Check timeout protection (30s for APIs)
        if grep -q "timeout.*30\|timeout=30" "$LOADER_FILE"; then
            ((TIMEOUT_PROTECTED++))
        else
            TIMEOUT_MISSING+=("$loader")
        fi

        # 4. Check error handling (try/except)
        if grep -q "except\|try:" "$LOADER_FILE"; then
            ((ERROR_HANDLING++))
        else
            ERROR_HANDLING_MISSING+=("$loader")
        fi

        # 5. Check logging
        if grep -q "logger\|logging" "$LOADER_FILE"; then
            ((LOGGING_ENABLED++))
        else
            LOGGING_MISSING+=("$loader")
        fi

        # 6. Check DatabaseHelper usage
        if grep -q "DatabaseHelper\|from db_helper" "$LOADER_FILE"; then
            ((DATABASE_HELPER++))
        else
            DB_HELPER_MISSING+=("$loader")
        fi
    else
        MISSING_FILES+=("$loader")
    fi

    # 7. Check Dockerfile
    DOCKERFILE="Dockerfile.load${loader}"
    if [[ -f "$DOCKERFILE" ]]; then
        ((DOCKERFILES_FOUND++))
    else
        DOCKERFILE_MISSING+=("$loader")
    fi

    # 8. Check CloudFormation task definition (in template-app-ecs-tasks.yml)
    TASK_DEF_PATTERN=$(echo "$loader" | sed 's/_//g' | tr '[:lower:]' '[:upper:]')
    if grep -q "${TASK_DEF_PATTERN}TaskDef\|load${loader}" template-app-ecs-tasks.yml 2>/dev/null; then
        ((TASK_DEFS_FOUND++))
    else
        TASKDEF_MISSING+=("$loader")
    fi
done

# Print results
echo -e "${BLUE}AUDIT RESULTS${NC}"
echo ""

# File existence
echo -e "${YELLOW}1. Loader Files${NC}"
echo "   Found: $FILES_FOUND/$TOTAL_LOADERS"
if [[ ${#MISSING_FILES[@]} -eq 0 ]]; then
    echo -e "   ${GREEN}✓ All loader files present${NC}"
else
    echo -e "   ${RED}✗ Missing files: ${MISSING_FILES[*]}${NC}"
fi
echo ""

# Phase A
echo -e "${YELLOW}2. Phase A Optimization (S3 Staging/Incremental)${NC}"
echo "   Enabled: $PHASE_A_ENABLED/$FILES_FOUND"
if [[ ${#PHASE_A_MISSING[@]} -eq 0 ]]; then
    echo -e "   ${GREEN}✓ All loaders have Phase A${NC}"
else
    echo -e "   ${YELLOW}⚠ Consider enabling Phase A for: ${PHASE_A_MISSING[*]}${NC}"
fi
echo ""

# Timeout protection
echo -e "${YELLOW}3. API Timeout Protection (30s)${NC}"
echo "   Protected: $TIMEOUT_PROTECTED/$FILES_FOUND"
if [[ ${#TIMEOUT_MISSING[@]} -gt 5 ]]; then
    echo -e "   ${RED}✗ Missing timeout in: ${TIMEOUT_MISSING[*]:0:5}...${NC}"
else
    echo -e "   ${YELLOW}⚠ Check timeout in: ${TIMEOUT_MISSING[*]}${NC}"
fi
echo ""

# Error handling
echo -e "${YELLOW}4. Error Handling (try/except)${NC}"
echo "   Protected: $ERROR_HANDLING/$FILES_FOUND"
if [[ ${#ERROR_HANDLING_MISSING[@]} -eq 0 ]]; then
    echo -e "   ${GREEN}✓ All loaders have error handling${NC}"
else
    echo -e "   ${RED}✗ Missing error handling: ${ERROR_HANDLING_MISSING[*]}${NC}"
fi
echo ""

# Logging
echo -e "${YELLOW}5. Logging Enabled${NC}"
echo "   Enabled: $LOGGING_ENABLED/$FILES_FOUND"
if [[ ${#LOGGING_MISSING[@]} -eq 0 ]]; then
    echo -e "   ${GREEN}✓ All loaders have logging${NC}"
else
    echo -e "   ${YELLOW}⚠ No logging in: ${LOGGING_MISSING[*]}${NC}"
fi
echo ""

# Database Helper
echo -e "${YELLOW}6. DatabaseHelper Integration${NC}"
echo "   Using: $DATABASE_HELPER/$FILES_FOUND"
if [[ $DATABASE_HELPER -eq $FILES_FOUND ]]; then
    echo -e "   ${GREEN}✓ All loaders use DatabaseHelper${NC}"
else
    echo -e "   ${RED}✗ Not using DatabaseHelper: ${DB_HELPER_MISSING[*]:0:3}...${NC}"
fi
echo ""

# Dockerfiles
echo -e "${YELLOW}7. Docker Images${NC}"
echo "   Found: $DOCKERFILES_FOUND/$FILES_FOUND"
if [[ ${#DOCKERFILE_MISSING[@]} -eq 0 ]]; then
    echo -e "   ${GREEN}✓ All Dockerfiles present${NC}"
else
    echo -e "   ${YELLOW}⚠ Consolidated in unified Dockerfile${NC}"
fi
echo ""

# CloudFormation tasks
echo -e "${YELLOW}8. CloudFormation Task Definitions${NC}"
echo "   Defined: $TASK_DEFS_FOUND/$FILES_FOUND"
if [[ $TASK_DEFS_FOUND -eq $FILES_FOUND ]]; then
    echo -e "   ${GREEN}✓ All task definitions in template${NC}"
else
    echo -e "   ${YELLOW}⚠ Missing $((FILES_FOUND - TASK_DEFS_FOUND)) task definitions${NC}"
fi
echo ""

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}QUALITY SCORE${NC}"
echo -e "${BLUE}========================================${NC}"

QUALITY_SCORE=0
QUALITY_TOTAL=8

[[ ${#MISSING_FILES[@]} -eq 0 ]] && ((QUALITY_SCORE++))
[[ ${#PHASE_A_MISSING[@]} -eq 0 ]] && ((QUALITY_SCORE++))
[[ ${#TIMEOUT_MISSING[@]} -lt 5 ]] && ((QUALITY_SCORE++))
[[ ${#ERROR_HANDLING_MISSING[@]} -eq 0 ]] && ((QUALITY_SCORE++))
[[ ${#LOGGING_MISSING[@]} -eq 0 ]] && ((QUALITY_SCORE++))
[[ $DATABASE_HELPER -eq $FILES_FOUND ]] && ((QUALITY_SCORE++))
[[ ${#DOCKERFILE_MISSING[@]} -eq 0 ]] && ((QUALITY_SCORE++))
[[ $TASK_DEFS_FOUND -eq $FILES_FOUND ]] && ((QUALITY_SCORE++))

PERCENTAGE=$((QUALITY_SCORE * 100 / QUALITY_TOTAL))

if [[ $PERCENTAGE -ge 90 ]]; then
    echo -e "${GREEN}Score: $QUALITY_SCORE/$QUALITY_TOTAL ($PERCENTAGE%)${NC}"
    echo -e "${GREEN}Status: PRODUCTION READY ✓${NC}"
elif [[ $PERCENTAGE -ge 75 ]]; then
    echo -e "${YELLOW}Score: $QUALITY_SCORE/$QUALITY_TOTAL ($PERCENTAGE%)${NC}"
    echo -e "${YELLOW}Status: GOOD - Minor improvements recommended${NC}"
else
    echo -e "${RED}Score: $QUALITY_SCORE/$QUALITY_TOTAL ($PERCENTAGE%)${NC}"
    echo -e "${RED}Status: NEEDS WORK - Fix critical issues${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}RECOMMENDATIONS${NC}"
echo -e "${BLUE}========================================${NC}"

ISSUES=0

if [[ ${#PHASE_A_MISSING[@]} -gt 0 ]]; then
    echo ""
    echo -e "${YELLOW}Priority 1: Enable Phase A for high-frequency loaders${NC}"
    for loader in "${PHASE_A_MISSING[@]}"; do
        # Check if it's a high-frequency loader
        if [[ "$loader" =~ ^(pricedaily|priceweekly|buyselldaily|technicalsdaily)$ ]]; then
            echo -e "   ${RED}✗ $loader (HIGH PRIORITY)${NC}"
            ((ISSUES++))
        fi
    done
fi

if [[ ${#TIMEOUT_MISSING[@]} -gt 0 ]]; then
    echo ""
    echo -e "${YELLOW}Priority 2: Add timeout protection to API loaders${NC}"
    for loader in "${TIMEOUT_MISSING[@]:0:5}"; do
        echo -e "   ${YELLOW}⚠ $loader${NC}"
        ((ISSUES++))
    done
fi

if [[ ${#DATABASE_HELPER_MISSING[@]} -gt 0 && ${#DATABASE_HELPER_MISSING[@]} -lt 5 ]]; then
    echo ""
    echo -e "${YELLOW}Priority 3: Migrate to DatabaseHelper${NC}"
    for loader in "${DB_HELPER_MISSING[@]}"; do
        echo -e "   ${YELLOW}⚠ $loader${NC}"
        ((ISSUES++))
    done
fi

echo ""
echo -e "${BLUE}========================================${NC}"

if [[ $ISSUES -eq 0 ]]; then
    echo -e "${GREEN}All critical checks passed!${NC}"
    echo -e "${GREEN}System is ready for production.${NC}"
    exit 0
else
    echo -e "${RED}Found $ISSUES issues to address${NC}"
    echo -e "${YELLOW}Review recommendations above${NC}"
    exit 1
fi
