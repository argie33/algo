#!/bin/bash
# Build Lambda Layer for shared dependencies
# Run from terraform directory

set -e

LAYER_NAME="python-psycopg2-layer"
TEMP_DIR=$(mktemp -d)
PYTHON_DIR="$TEMP_DIR/python"

echo "Building Lambda Layer: $LAYER_NAME"
echo "Temp dir: $TEMP_DIR"

# Create python directory for layer
mkdir -p "$PYTHON_DIR"

# Install dependencies
echo "Installing dependencies..."
pip install -q -r lambda-layer-requirements.txt -t "$PYTHON_DIR" 2>&1 | grep -v "already satisfied" || true

# Create ZIP
echo "Creating ZIP..."
cd "$TEMP_DIR"
zip -r "$OLDPWD/$LAYER_NAME.zip" python > /dev/null
cd "$OLDPWD"

# Check size
SIZE=$(du -h "$LAYER_NAME.zip" | cut -f1)
echo "✅ Lambda Layer created: $LAYER_NAME.zip ($SIZE)"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "Next steps:"
echo "1. terraform plan  # Review changes"
echo "2. terraform apply # Deploy layer"
