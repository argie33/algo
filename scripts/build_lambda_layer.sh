#!/bin/bash
# Build and publish Lambda layer with all required dependencies
# This layer will be used by algo-orchestrator and api Lambda functions

set -e

LAYER_NAME="algo-orchestrator-layer"
REQUIREMENTS_FILE="terraform/lambda-layer-requirements.txt"
BUILD_DIR="lambda_layer_build"
AWS_REGION=${AWS_REGION:-us-east-1}

echo "=== Building Lambda Layer: $LAYER_NAME ==="
echo "Region: $AWS_REGION"
echo ""

# Clean up
rm -rf "$BUILD_DIR" layer.zip

# Create layer structure
mkdir -p "$BUILD_DIR/python"
cd "$BUILD_DIR"

# Install dependencies into python directory
echo "Installing dependencies from $REQUIREMENTS_FILE..."
pip install \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python 3.11 \
  --only-binary=:all: \
  --upgrade \
  --target ./python \
  -r "../$REQUIREMENTS_FILE"

echo "Dependencies installed:"
ls -la ./python/ | head -20

# Create layer zip
cd ..
echo ""
echo "Creating layer.zip..."
cd "$BUILD_DIR"
zip -r ../layer.zip python/
cd ..

echo "Layer size: $(du -h layer.zip | cut -f1)"
echo ""

# Publish to AWS Lambda
echo "Publishing layer to AWS Lambda..."
LAYER_ARN=$(aws lambda publish-layer-version \
  --layer-name "$LAYER_NAME" \
  --zip-file fileb://layer.zip \
  --compatible-runtimes python3.11 \
  --region "$AWS_REGION" \
  --query 'LayerVersionArn' \
  --output text)

echo "✅ Layer published: $LAYER_ARN"
echo ""

# Update Terraform variable (if needed)
echo "To use this layer in Terraform, set:"
echo "  lambda_layer_name = \"$LAYER_NAME\""
echo ""

# Cleanup
rm -rf "$BUILD_DIR" layer.zip

echo "Done!"
