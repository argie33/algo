#!/bin/bash
# Auto-trigger loaders once infrastructure deployment completes

echo "=========================================="
echo "INFRASTRUCTURE DEPLOYMENT COMPLETE!"
echo "=========================================="
echo ""
echo "✅ VPC created"
echo "✅ ECS cluster deployed"
echo "✅ RDS database ready"
echo "✅ Docker image in ECR"
echo "✅ Lambda functions deployed"
echo ""
echo "Now triggering data loaders..."
echo ""

# Trigger the loader workflow
echo "⏳ Starting loader execution (Tier: all)"
gh workflow run manual-trigger-loaders.yml -f tier=all --repo argie33/algo

echo ""
echo "📊 Loader workflow triggered!"
echo "Monitor execution:"
echo "  GitHub Actions: https://github.com/argie33/algo/actions"
echo "  CloudWatch Logs: aws logs tail /ecs/algo-stock_symbols-loader --follow --region us-east-1"
echo ""
echo "Expected timeline:"
echo "  - Tier 0 (symbols):   5 minutes"
echo "  - Tier 1 (prices):    15 minutes"
echo "  - Tier 2 (reference): 30 minutes"
echo "  - Tier 3 (metrics):   30 minutes"
echo "  - TOTAL:             ~80 minutes"
echo ""
echo "After loaders complete, data will be available for testing!"
