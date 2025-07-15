#!/bin/bash

# Trigger Auto-Sync Documentation Routine
# Simple script to manually trigger the document sync process

echo "🔄 Triggering Auto-Sync Documentation Routine..."

# Check if we're in the right directory
if [ ! -f "CLAUDE.md" ]; then
  echo "❌ Error: CLAUDE.md not found. Please run from project root directory."
  exit 1
fi

# Run the auto-sync routine
echo "📖 Reading operational guidelines..."
echo "📊 Analyzing 3 content documents..."
echo "🔍 Identifying gaps and inconsistencies..."
echo "📝 Preparing document updates..."

# Execute the sync routine
node auto-sync-docs.js

# Check if it succeeded
if [ $? -eq 0 ]; then
  echo "✅ Auto-Sync completed successfully!"
  echo ""
  echo "📋 Next steps:"
  echo "1. Review auto-sync-report.json for detailed analysis"
  echo "2. Check claude-todo.md for updated priorities"
  echo "3. Start working on high-priority items"
  echo "4. Run this script again after significant changes"
  echo ""
  
  # Show next actions if report exists
  if [ -f "auto-sync-report.json" ]; then
    echo "🎯 Next Actions:"
    node -e "
      const report = require('./auto-sync-report.json');
      report.nextActions.forEach((action, i) => {
        console.log(\`\${i+1}. \${action.content}\`);
      });
    "
  fi
else
  echo "❌ Auto-Sync failed. Check the error messages above."
  exit 1
fi