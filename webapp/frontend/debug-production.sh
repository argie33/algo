#!/bin/bash

echo "🌐 PRODUCTION DEBUGGING SUITE"
echo "============================="
echo ""

# Get production URL from user
if [ -z "$1" ]; then
    echo "❓ Please provide your production site URL"
    echo "Usage: ./debug-production.sh https://your-site.com"
    echo ""
    echo "For local testing use: ./debug-production.sh http://localhost:8080"
    exit 1
fi

PRODUCTION_URL=$1
echo "🎯 Target URL: $PRODUCTION_URL"
echo ""

# Check if required tools are installed
echo "🔍 Checking required dependencies..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found - please install Node.js first"
    exit 1
fi

if ! npm list puppeteer &> /dev/null; then
    echo "❌ Puppeteer not installed - installing now..."
    npm install puppeteer
fi

if ! npm list playwright &> /dev/null; then
    echo "❌ Playwright not installed - installing now..."
    npm install playwright
fi

echo "✅ All dependencies ready"
echo ""

# Menu for debugging options
echo "🛠️  DEBUGGING OPTIONS:"
echo "1) Local site debugging (uses Puppeteer with DevTools)"
echo "2) Live production site debugging (uses Playwright)"
echo "3) Quick error capture (headless mode)"
echo "4) Network analysis only"
echo ""

read -p "Choose option (1-4): " option

case $option in
    1)
        echo "🔍 Starting local site debugging..."
        node remote-debug.js $PRODUCTION_URL
        ;;
    2)
        echo "🌐 Starting live production site debugging..."
        node live-site-debugger.js $PRODUCTION_URL
        ;;
    3)
        echo "⚡ Quick error capture..."
        node test_error.js
        ;;
    4)
        echo "🌐 Network analysis only..."
        python3 debug_network.py
        ;;
    *)
        echo "❌ Invalid option"
        exit 1
        ;;
esac

echo ""
echo "📊 Debugging session completed!"
echo "Check the generated report files for detailed analysis."