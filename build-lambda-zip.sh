#!/bin/bash
# Build Lambda ZIP files for local testing and deployment

set -e
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="/tmp/lambda-build"

echo "Building Lambda ZIP files..."

# ============================================================
# 1. API Lambda
# ============================================================
echo ""
echo "1️⃣  Building API Lambda..."
rm -rf "$BUILD_DIR" && mkdir -p "$BUILD_DIR/api"

cp -r "$PROJECT_ROOT/lambda/api"/* "$BUILD_DIR/api/"
cd "$BUILD_DIR/api"

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt -t . --no-cache-dir --quiet
fi

rm -f "$PROJECT_ROOT/terraform/lambda_api.zip"
zip -r "$PROJECT_ROOT/terraform/lambda_api.zip" . -q -x "*.pyc" "__pycache__/*" "*.dist-info/*"
echo "✅ API Lambda: $(du -sh $PROJECT_ROOT/terraform/lambda_api.zip | cut -f1)"
unzip -l "$PROJECT_ROOT/terraform/lambda_api.zip" | head -10

# ============================================================
# 2. Data Freshness Monitor Lambda
# ============================================================
echo ""
echo "2️⃣  Building Data Freshness Monitor Lambda..."
rm -rf "$BUILD_DIR/monitor" && mkdir -p "$BUILD_DIR/monitor"

cp "$PROJECT_ROOT/lambda/data-freshness-monitor/lambda_function.py" "$BUILD_DIR/monitor/"
cd "$BUILD_DIR/monitor"

pip install -r "$PROJECT_ROOT/lambda/data-freshness-monitor/requirements.txt" -t . --no-cache-dir --quiet

mkdir -p "$PROJECT_ROOT/terraform/lambda/data-freshness-monitor"
rm -f "$PROJECT_ROOT/terraform/lambda/data-freshness-monitor/lambda_function.zip"
zip -r "$PROJECT_ROOT/terraform/lambda/data-freshness-monitor/lambda_function.zip" . -q -x "*.pyc" "__pycache__/*" "*.dist-info/*"
echo "✅ Data Freshness Monitor: $(du -sh $PROJECT_ROOT/terraform/lambda/data-freshness-monitor/lambda_function.zip | cut -f1)"
unzip -l "$PROJECT_ROOT/terraform/lambda/data-freshness-monitor/lambda_function.zip" | head -10

echo ""
echo "✨ All Lambda ZIPs built successfully!"
echo "Location: $PROJECT_ROOT/terraform/"
