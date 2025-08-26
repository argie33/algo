#!/bin/bash
# Systematic Dependency Update Strategy
# Replaces manual "super random" approach with automated workflow

echo "🔄 Starting systematic dependency update..."

# 1. Python Dependencies
echo "📊 Phase 1: Python dependency analysis..."
cd /home/stocks/algo
pip-review --local || echo "pip-review not installed, install with: pip install pip-review"

# 2. Node.js Dependencies  
echo "📦 Phase 2: Node.js dependency analysis..."
cd webapp/frontend
npx npm-check-updates --format group
echo "Run 'npx npm-check-updates -u' to update package.json"

# 3. Security Audits
echo "🔒 Phase 3: Security audit..."
npm audit --audit-level=high

# 4. Docker Base Image Updates
echo "🐳 Phase 4: Docker base image check..."
echo "Current Python versions in Dockerfiles:"
grep -r "FROM python:" . --include="Dockerfile*" | grep -v node_modules | sort | uniq -c

echo "✅ Dependency analysis complete"
echo "💡 Review output and run specific update commands as needed"
