# RDS Rotation Lambda Layer Setup

## Problem

The RDS rotation Lambda function requires the `psycopg2` PostgreSQL driver, which is not available in the standard Python runtime. You need to create a Lambda Layer to bundle it.

## Solution: Create Lambda Layer with psycopg2

### Option 1: Pre-built Layer (Recommended)

Use the AWS Lambda Python 3.11 base image to build a layer:

```bash
# Create layer directory
mkdir -p python_layer/python/lib/python3.11/site-packages
cd python_layer

# Install psycopg2-binary (compiled for Lambda)
pip install -t python/lib/python3.11/site-packages psycopg2-binary

# Create zip
zip -r ../psycopg2-layer.zip python/

# Upload to S3 (or use directly in Terraform)
aws s3 cp ../psycopg2-layer.zip s3://<bucket>/lambda-layers/

# Note the S3 URI for next step
```

### Option 2: Docker Build (For Lambda Container)

```bash
docker run --rm -v $(pwd):/var/task public.ecr.aws/lambda/python:3.11 \
  pip install -t /var/task/python psycopg2-binary

zip -r psycopg2-layer.zip python/
```

### Option 3: Use AWS Lambda Powertools (Includes psycopg2)

[Lambda Powertools](https://github.com/aws-lambda-powertools/python) includes common dependencies.

## Terraform Configuration

Add to `terraform/modules/database/main.tf`:

```hcl
# Upload layer zip to S3 first, or create from local path
data "archive_file" "psycopg2_layer" {
  type        = "zip"
  source_dir  = "${path.module}/.build/psycopg2-layer"
  output_path = "${path.module}/.terraform/psycopg2-layer.zip"
}

resource "aws_lambda_layer_version" "psycopg2" {
  filename                = data.archive_file.psycopg2_layer.output_path
  layer_name              = "${var.project_name}-psycopg2-layer"
  compatible_runtimes     = ["python3.11"]
  source_code_hash        = data.archive_file.psycopg2_layer.output_base64sha256
}

# Update Lambda function to use layer
resource "aws_lambda_function" "rds_rotation" {
  # ... existing config ...
  
  layers = [aws_lambda_layer_version.psycopg2.arn]
  
  # ... rest of config ...
}
```

## Alternative: Use psycopg3 Binary

Instead of compiling, use `psycopg[binary]` which includes pre-compiled bindings:

```bash
pip install -t python psycopg[binary]
```

Then update the Lambda function code to use `psycopg` instead of `psycopg2`:

```python
import psycopg

conn = psycopg.connect(
    host=...,
    user=...,
    password=...
)
```

## Verification

Test the layer before deploying:

```bash
# Create test function
zip test-lambda.zip index.py
aws lambda create-function \
  --function-name test-psycopg2 \
  --runtime python3.11 \
  --role <role-arn> \
  --handler index.handler \
  --zip-file fileb://test-lambda.zip \
  --layers <layer-arn>

# Invoke with test
aws lambda invoke \
  --function-name test-psycopg2 \
  --payload '{"test": true}' \
  response.json

# Check result
cat response.json
```

## Size Optimization

If the layer is too large (> 50MB):

1. Use `--no-deps` to skip dependencies
2. Use `strip` to remove debug symbols
3. Consider using Amazon RDS Proxy instead of direct connections (no driver needed)

```bash
find python -name "*.so" -exec strip {} \;
find python -name "tests" -type d -exec rm -rf {} +
find python -name "__pycache__" -type d -exec rm -rf {} +
```

## References

- AWS Docs: [Lambda Layers](https://docs.aws.amazon.com/lambda/latest/dg/invocation-layers.html)
- AWS Docs: [Using Python in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html)
- psycopg2 Docs: [Building from Source](https://www.psycopg.org/psycopg2/install.html)
