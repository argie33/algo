#!/usr/bin/env python3
"""Analyze all loaders and their data coverage."""

import os
import re
from pathlib import Path
from collections import defaultdict

# Find all loader scripts
loaders_dir = Path("loaders")
loader_files = sorted(loaders_dir.glob("load_*.py"))

print("=" * 100)
print("DATA LOADER ANALYSIS")
print("=" * 100)

# Categorize loaders
categories = defaultdict(list)

for loader_file in loader_files:
    content = loader_file.read_text(encoding='utf-8', errors='ignore')

    # Extract docstring to understand purpose
    docstring_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
    docstring = docstring_match.group(1).strip() if docstring_match else "No description"
    first_line = docstring.split('\n')[0]

    # Try to categorize
    name = loader_file.stem

    if 'price' in name:
        category = 'PRICES'
    elif 'technical' in name:
        category = 'TECHNICALS'
    elif 'trend' in name:
        category = 'TREND'
    elif 'market' in name or 'health' in name:
        category = 'MARKET_HEALTH'
    elif 'signal' in name:
        category = 'SIGNALS'
    elif 'economic' in name or 'fred' in name:
        category = 'ECONOMIC'
    elif 'sentiment' in name or 'analyst' in name:
        category = 'SENTIMENT'
    elif 'earnings' in name:
        category = 'EARNINGS'
    elif 'metric' in name or 'growth' in name or 'value' in name or 'quality' in name or 'stability' in name or 'positioning' in name:
        category = 'FUNDAMENTAL_METRICS'
    elif 'ranking' in name:
        category = 'RANKINGS'
    elif 'cash_flow' in name or 'balance' in name or 'income' in name:
        category = 'FINANCIALS'
    elif 'weight' in name or 'optimization' in name:
        category = 'OPTIMIZATION'
    elif 'score' in name:
        category = 'SCORING'
    else:
        category = 'OTHER'

    categories[category].append({
        'file': loader_file.name,
        'description': first_line,
        'name': name
    })

# Print organized by category
for category in sorted(categories.keys()):
    loaders = categories[category]
    print(f"\n{category} ({len(loaders)} loaders)")
    print("-" * 100)
    for loader in loaders:
        print(f"  • {loader['name']:<40} — {loader['description'][:60]}")

print("\n" + "=" * 100)
print(f"TOTAL LOADERS: {len(loader_files)}")
print("=" * 100)

# Analyze for potential gaps
print("\n" + "=" * 100)
print("POTENTIAL DATA COVERAGE GAPS")
print("=" * 100)

gaps = []

# Check for critical data
critical_data = {
    'PRICES': 'stock_prices_daily',
    'TECHNICALS': 'technical_data_daily',
    'MARKET_HEALTH': 'market_health_daily',
    'TREND': 'trend template data',
    'ECONOMIC': 'FRED economic data',
}

for category, description in critical_data.items():
    has_loader = len(categories.get(category, [])) > 0
    if not has_loader:
        gaps.append(f"⚠️  Missing loader for: {description}")

# Check for loaders that might have dependencies
dependencies = {
    'SIGNALS': 'TECHNICALS (signals require technical indicators)',
    'RANKING': 'FUNDAMENTAL_METRICS (rankings require fundamentals)',
    'OPTIMIZATION': 'SIGNALS (optimization requires signals)',
}

for dependent, dependency in dependencies.items():
    has_dependent = len(categories.get(dependent, [])) > 0
    has_dependency = len(categories.get(dependency.split()[0], [])) > 0
    if has_dependent and not has_dependency:
        gaps.append(f"⚠️  {dependent} loaders exist but {dependency}")

if gaps:
    for gap in gaps:
        print(gap)
else:
    print("[OK] No obvious gaps detected in loader categories")

print("\n" + "=" * 100)
print("RECOMMENDED IMPROVEMENTS")
print("=" * 100)

recommendations = [
    "1. Verify all 30 loaders execute successfully daily",
    "2. Check ECS task definitions are correctly configured",
    "3. Ensure error handling and logging captures failures",
    "4. Implement health checks for each loader category",
    "5. Add watermarking for incremental updates",
    "6. Monitor data freshness for critical tables",
    "7. Set up alerting for failed loaders",
    "8. Document data quality thresholds",
]

for rec in recommendations:
    print(f"  {rec}")

print("\n" + "=" * 100)
