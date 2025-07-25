#!/bin/bash

# Stock Symbols Database Setup Runner
# This script sets up the stock_symbols table and sample data

echo "🏗️ Stock Database Setup Script"
echo "================================"

# Check if we're in the lambda directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: Run this script from the lambda directory"
    echo "   cd /home/stocks/algo/webapp/lambda && scripts/run-stocks-setup.sh"
    exit 1
fi

# Check if database utilities exist
if [ ! -f "utils/database.js" ]; then
    echo "❌ Error: Database utilities not found"
    echo "   Expected: utils/database.js"
    exit 1
fi

# Check if setup script exists
if [ ! -f "scripts/setup-stocks-database.js" ]; then
    echo "❌ Error: Setup script not found"
    echo "   Expected: scripts/setup-stocks-database.js"
    exit 1
fi

echo "📋 Environment Check:"
echo "   NODE_ENV: ${NODE_ENV:-development}"
echo "   DB_ENDPOINT: ${DB_ENDPOINT:-not set}"
echo "   DB_SECRET_ARN: ${DB_SECRET_ARN:-not set}"
echo "   USE_AWS_SECRETS: ${USE_AWS_SECRETS:-false}"

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "📁 Loading environment from .env file..."
    set -a
    source .env
    set +a
    echo "✅ Environment loaded"
else
    echo "⚠️  No .env file found - using system environment variables"
fi

echo ""
echo "🚀 Running stock database setup..."
echo ""

# Run the setup script
node scripts/setup-stocks-database.js

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Setup completed successfully!"
    echo ""
    echo "🧪 Test the stocks API:"
    echo "   curl \"https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/stocks/sectors\""
    echo ""
    echo "📱 Test the frontend:"
    echo "   Navigate to the stocks page in your app"
    echo ""
else
    echo ""
    echo "❌ Setup failed!"
    echo ""
    echo "🔧 Common issues:"
    echo "   1. Database connection problems"
    echo "   2. Missing environment variables"
    echo "   3. Insufficient database permissions"
    echo "   4. Network connectivity issues"
    echo ""
    echo "💡 Check the error messages above for specific guidance"
    exit 1
fi