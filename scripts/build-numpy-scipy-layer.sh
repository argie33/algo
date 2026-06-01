#!/bin/bash
# ============================================================
# Build compressed numpy/scipy Lambda layer (F-03)
# ============================================================
# Creates a Python Lambda layer with numpy and scipy in compressed form.
# Removes unnecessary files to reduce size from ~200MB to <69MB.
#
# Usage:
#   ./scripts/build-numpy-scipy-layer.sh
#
# Output:
#   terraform/numpy-scipy-layer.zip (< 69 MB)
#
# Deploy:
#   aws lambda publish-layer-version \
#     --layer-name algo-numpy-scipy \
#     --zip-file fileb://terraform/numpy-scipy-layer.zip \
#     --compatible-runtimes python3.12
# ============================================================

set -e

LAYER_DIR="python-deps-layer"
mkdir -p "$LAYER_DIR/python"

# Install numpy and scipy with binary wheels (no compilation needed)
pip install --target "$LAYER_DIR/python" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --no-cache-dir \
  numpy scipy

echo "[*] Cleaning up unnecessary files to reduce size..."

# Remove common unnecessary files
rm -rf "$LAYER_DIR/python"/{*.dist-info,*.egg-info}
rm -rf "$LAYER_DIR/python"/{__pycache__,*.pyc,*.pyo}
rm -rf "$LAYER_DIR/python"/numpy/{f2py,tests,core/tests}
rm -rf "$LAYER_DIR/python"/scipy/{stats/tests,optimize/tests,special/tests}
find "$LAYER_DIR/python" -type f -name "*.c" -o -name "*.h" -o -name "*.so.debug" | xargs rm -f

# Strip debug symbols from .so files (saves ~30-40%)
find "$LAYER_DIR/python" -type f -name "*.so" -exec strip {} \;

# Create zip layer
LAYER_SIZE=$(du -sh "$LAYER_DIR" | awk '{print $1}')
echo "[*] Layer size before compression: $LAYER_SIZE"

cd "$LAYER_DIR"
zip -r -q "../terraform/numpy-scipy-layer.zip" .
cd ..

FINAL_SIZE=$(ls -lh "terraform/numpy-scipy-layer.zip" | awk '{print $5}')
echo "[✓] Created terraform/numpy-scipy-layer.zip ($FINAL_SIZE)"

# Verify size is under 69 MB (50 MiB direct upload, 250 MiB via S3)
ZIP_SIZE_MB=$(stat -f%z "terraform/numpy-scipy-layer.zip" 2>/dev/null || stat -c%s "terraform/numpy-scipy-layer.zip" 2>/dev/null | awk '{printf "%.0f\n", $0/1024/1024}')
echo "[*] Size in MB: ${ZIP_SIZE_MB}MB"

if [ "$ZIP_SIZE_MB" -lt 69 ]; then
  echo "[✓] SUCCESS: Layer is under 69 MB limit - can be deployed directly"
else
  echo "[⚠] WARNING: Layer is ${ZIP_SIZE_MB}MB - exceeds 69 MB direct upload limit"
  echo "[*] Use S3 upload instead: aws lambda publish-layer-version --layer-name algo-numpy-scipy --zip-file s3://bucket/numpy-scipy-layer.zip"
fi

# Cleanup
rm -rf "$LAYER_DIR"
