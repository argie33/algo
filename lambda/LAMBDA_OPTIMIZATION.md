# Lambda Cold-Start Optimization Guide

## Cold-Start Reduction Strategy

The `algo_orchestrator` Lambda function has been optimized for fast cold-start performance.

### Current Optimizations

1. **Lazy-Load AWS Clients**
   - boto3 clients (SNS, Secrets Manager, CloudWatch) only initialized on first use
   - Reduces module load time on cold start
   - Typical cold-start reduction: 300-500ms

2. **Pre-Warm Critical Imports**
   - Logging module pre-imported at top level
   - Python standard library imports cached
   - Subprocess module imported eagerly (used in hot path)

3. **Cold-Start Tracking**
   - Track initialization duration via `_init_start_time` global
   - Publish metric to CloudWatch on cold start
   - Monitor trends for performance regression

4. **Subprocess Optimization**
   - Set 900s timeout (15 min) — matches Lambda timeout
   - Use shell=True for single command (avoids fork overhead)
   - Capture output for logging, not streaming

### Target Metrics

- **Cold Start (first invocation):** < 2 seconds
- **Warm Start (subsequent invocations):** < 100ms
- **AWS Client First-Use Penalty:** < 500ms

### Production Deployment: Lambda Layers

Use Lambda layers to pre-package dependencies and reduce cold-start further:

```bash
# Create layer directory
mkdir -p python/lib/python3.11/site-packages

# Install dependencies into layer
pip install -r requirements.txt -t python/lib/python3.11/site-packages/

# Zip layer
zip -r lambda_layer.zip python

# Publish to Lambda
aws lambda publish-layer-version \
  --layer-name algo-dependencies \
  --zip-file fileb://lambda_layer.zip \
  --compatible-runtimes python3.11
```

Then attach layer to function:
```bash
aws lambda update-function-configuration \
  --function-name algo-orchestrator \
  --layers arn:aws:lambda:REGION:ACCOUNT:layer:algo-dependencies:1
```

### CloudWatch Monitoring

Monitor cold-start performance:

```
Namespace: AlgoTrading
Metric: LambdaColdStartDuration
Unit: Seconds
```

Set up alarm:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name algo-orchestrator-cold-start-warning \
  --metric-name LambdaColdStartDuration \
  --namespace AlgoTrading \
  --statistic Average \
  --period 3600 \
  --threshold 3.0 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT:AlertTopic
```

### Testing

Run unit tests to verify cold-start behavior:

```bash
pytest test_lambda_handler.py -v -k "cold_start"
```

Perform load test to measure real cold-start:
```bash
aws lambda invoke \
  --function-name algo-orchestrator \
  --payload '{}' \
  response.json

# Check CloudWatch logs for cold-start duration
aws logs tail /aws/lambda/algo-orchestrator --follow
```

### Benchmarks

Typical cold-start timeline (optimization complete):

| Phase | Duration | Notes |
|-------|----------|-------|
| Init Python runtime | 500-700ms | AWS Lambda managed |
| Import modules | 200-300ms | Pre-warmed logging, subprocess |
| AWS client lazy-load | 0ms | Not used until needed |
| Total cold-start | 700-1000ms | Target: < 2s |
| Warm-start overhead | 20-50ms | Subsequent invocations |

### Further Optimizations (Future)

1. **Lambda@Edge for pre-warming** - Invoke function periodically to keep warm
2. **Provisioned Concurrency** - Always keep 1-2 instances warm for zero cold-start
3. **In-process execution** - Move subprocess Python calls to in-process for < 50ms startup
4. **Memory optimization** - Increase Lambda memory to 3GB for faster CPU (faster initialization)

### Configuration

Update Lambda function settings in Terraform/CloudFormation:

```terraform
resource "aws_lambda_function" "algo_orchestrator" {
  function_name = "algo-orchestrator"
  runtime       = "python3.11"
  memory_size   = 3008  # Max 10240, higher = faster CPU for init
  timeout       = 900   # 15 minutes

  # Enable CloudWatch insights
  logging_config {
    log_group  = aws_cloudwatch_log_group.algo_orchestrator.name
    log_format = "JSON"
  }

  # Attach layer for dependencies
  layers = [aws_lambda_layer_version.algo_dependencies.arn]
}
```

### Troubleshooting

If cold-start exceeds 2 seconds:

1. Check CloudWatch metric `LambdaColdStartDuration`
2. Verify Lambda layer is attached (reduces Python module load)
3. Check for large dependencies in function code
4. Review subprocess spawning in hot path
5. Consider increasing memory size (larger memory = faster CPU for initialization)
