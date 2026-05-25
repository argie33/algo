#!/bin/bash
# Quick fix for API Lambda 500 errors
# Run this script with AWS credentials configured
# Usage: bash QUICK_FIX_API_LAMBDA.sh

set -e

AWS_REGION=${AWS_REGION:-us-east-1}
FUNC_NAME="algo-api-dev"
LAYER_NAME="algo-api-layer"

echo "=== Quick Fix: API Lambda Layer Deployment ==="
echo ""

# Step 1: Check current Lambda status
echo "Step 1: Checking Lambda configuration..."
aws lambda get-function-configuration \
  --function-name "$FUNC_NAME" \
  --region "$AWS_REGION" \
  --query 'Layers' \
  --output text

if [ $? -eq 0 ]; then
  LAYERS=$(aws lambda get-function-configuration \
    --function-name "$FUNC_NAME" \
    --region "$AWS_REGION" \
    --query 'Layers' \
    --output json)

  if [ "$LAYERS" = "[]" ] || [ -z "$LAYERS" ]; then
    echo "  No layers attached - needs fix"
  else
    echo "  Layers already attached: $LAYERS"
    exit 0
  fi
else
  echo "  ERROR: Could not access Lambda function"
  exit 1
fi

echo ""
echo "Step 2: Publishing API Lambda layer..."

# Build the layer locally if needed
if [ ! -f "terraform/api_layer.zip" ]; then
  echo "  Creating api_layer.zip..."
  python3 << 'PYTHON_SCRIPT'
import zipfile
import subprocess
from pathlib import Path
import shutil
import sys

temp_dir = Path("./.layer_build")
if temp_dir.exists():
    shutil.rmtree(temp_dir)
temp_dir.mkdir()

python_dir = temp_dir / "python"
python_dir.mkdir()

subprocess.run([
    sys.executable, "-m", "pip", "install",
    "-r", "lambda/api/requirements.txt",
    "-t", str(python_dir),
    "-q"
], check=True)

layer_zip = Path("terraform/api_layer.zip")
if layer_zip.exists():
    layer_zip.unlink()

with zipfile.ZipFile(layer_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
    for file_path in python_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(temp_dir)
            zf.write(str(file_path), str(rel_path))

shutil.rmtree(temp_dir)
print(f"Created: {layer_zip.stat().st_size / (1024*1024):.1f} MB")
PYTHON_SCRIPT
fi

# Publish the layer
LAYER_ARN=$(aws lambda publish-layer-version \
  --layer-name "$LAYER_NAME" \
  --zip-file fileb://terraform/api_layer.zip \
  --compatible-runtimes python3.12 \
  --region "$AWS_REGION" \
  --query 'LayerVersionArn' \
  --output text)

echo "  Layer published: $LAYER_ARN"

echo ""
echo "Step 3: Attaching layer to Lambda..."

# Update Lambda to use the layer
aws lambda update-function-configuration \
  --function-name "$FUNC_NAME" \
  --layers "$LAYER_ARN" \
  --region "$AWS_REGION" \
  --query 'Layers' \
  --output json

echo "  Layer attached successfully"

echo ""
echo "Step 4: Verifying fix..."

# Test the /health endpoint
sleep 2
API_ENDPOINT=$(aws apigatewayv2 get-apis \
  --region "$AWS_REGION" \
  --query "Items[0].ApiEndpoint" \
  --output text 2>/dev/null || echo "")

if [ -n "$API_ENDPOINT" ] && [ "$API_ENDPOINT" != "None" ]; then
  echo "  Testing API at: $API_ENDPOINT/api/health"

  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_ENDPOINT/api/health" 2>/dev/null || echo "000")

  if [ "$HTTP_CODE" = "200" ]; then
    echo "  SUCCESS - API returned 200!"
  else
    echo "  HTTP Status: $HTTP_CODE (may still be deploying)"
  fi
else
  echo "  API Gateway endpoint not found - check AWS console"
fi

echo ""
echo "=== Fix Complete ==="
echo "The API Lambda layer has been attached."
echo "It may take 1-2 minutes for changes to propagate."
echo "Test the API with: curl https://YOUR_API_GATEWAY/api/health"
