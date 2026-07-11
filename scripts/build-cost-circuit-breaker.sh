#!/bin/bash
set -e

# Build Cost Circuit Breaker Lambda ZIP
# This script creates a deployment package for the cost monitoring Lambda function

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
SOURCE_LAMBDA="$PROJECT_ROOT/lambda/cost-circuit-breaker"
TERRAFORM_LAMBDA="$PROJECT_ROOT/terraform/lambda"
PKG_DIR="/tmp/cost-circuit-breaker-pkg"

echo "=== Building Cost Circuit Breaker Lambda ==="
echo "Source: $SOURCE_LAMBDA"
echo "Output: $TERRAFORM_LAMBDA/cost_circuit_breaker.zip"
echo ""

# Create package directory
mkdir -p "$PKG_DIR" "$TERRAFORM_LAMBDA"
rm -rf "$PKG_DIR"/*

# Copy Lambda function handler
echo "[1/3] Copying Lambda handler..."
cp "$SOURCE_LAMBDA/index.py" "$PKG_DIR/index.py"

# Copy requirements and install dependencies
echo "[2/3] Installing dependencies..."
if [ -f "$SOURCE_LAMBDA/requirements.txt" ]; then
    python3 -m pip install -r "$SOURCE_LAMBDA/requirements.txt" \
        -t "$PKG_DIR/" \
        --no-cache-dir --quiet 2>/dev/null || true
fi

# Create ZIP
echo "[3/3] Creating deployment package..."
rm -f "$TERRAFORM_LAMBDA/cost_circuit_breaker.zip"
cd "$PKG_DIR"
zip -r "$TERRAFORM_LAMBDA/cost_circuit_breaker.zip" . -q -x "*.pyc" "__pycache__/*" "*.dist-info/*" "requirements.txt"
cd "$PROJECT_ROOT"

# Verify
ZIP_SIZE=$(du -sh "$TERRAFORM_LAMBDA/cost_circuit_breaker.zip" | cut -f1)
echo ""
echo "✓ Build complete!"
echo "  File: $TERRAFORM_LAMBDA/cost_circuit_breaker.zip"
echo "  Size: $ZIP_SIZE"
echo ""
echo "Next steps:"
echo "  cd terraform"
echo "  terraform plan"
echo "  terraform apply"
