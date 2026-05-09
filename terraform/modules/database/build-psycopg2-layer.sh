#!/bin/bash
# Build psycopg2 Lambda layer for RDS rotation Lambda function
# This script creates a zip file that can be uploaded to AWS Lambda

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAYER_DIR="${SCRIPT_DIR}/.psycopg2-layer"
OUTPUT_ZIP="${SCRIPT_DIR}/python-psycopg2-layer.zip"

echo "Building psycopg2 Lambda layer..."
echo "Output: ${OUTPUT_ZIP}"

# Clean old layer
rm -rf "${LAYER_DIR}" "${OUTPUT_ZIP}"
mkdir -p "${LAYER_DIR}/python/lib/python3.11/site-packages"

# Option 1: Use psycopg[binary] (recommended - single binary)
echo "Installing psycopg[binary]..."
pip install -t "${LAYER_DIR}/python/lib/python3.11/site-packages" psycopg[binary] --no-cache-dir

# Remove unnecessary files to reduce size
find "${LAYER_DIR}" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find "${LAYER_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${LAYER_DIR}" -type f -name "*.pyc" -delete
find "${LAYER_DIR}" -type f -name "*.dist-info" -delete 2>/dev/null || true

# Strip debug symbols from .so files
find "${LAYER_DIR}" -type f -name "*.so" -exec strip {} \; 2>/dev/null || true

# Create zip file
cd "${LAYER_DIR}"
zip -r "${OUTPUT_ZIP}" . -q

# Report size
SIZE_MB=$(du -h "${OUTPUT_ZIP}" | cut -f1)
echo ""
echo "✓ Layer created successfully: ${OUTPUT_ZIP}"
echo "  Size: ${SIZE_MB}"
echo ""
echo "Next steps:"
echo "1. Verify layer size is < 50MB (current: ${SIZE_MB})"
echo "2. Run: terraform apply"
echo "3. Confirm Lambda function has access to psycopg module"
echo ""
echo "To test the layer:"
echo "  aws lambda invoke --function-name <project>-rds-rotation-<env> \\"
echo "    --payload '{\"Step\": \"create\"}' response.json"
echo "  cat response.json"
