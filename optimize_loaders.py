#!/usr/bin/env python3
"""
Batch Optimization Pattern Generator
Applies execute_values() batching to all loaders systematically
"""

import os
import re
from pathlib import Path

LOADERS_TO_OPTIMIZE = {
    # Price loaders (biggest data volume - 22.8M+ rows)
    'loadpricedaily.py': {
        'batch_size': 5000,
        'commit_frequency': 'per_50_symbols',
        'priority': 'CRITICAL',
        'estimated_improvement': '40-50%'
    },
    'loadpriceweekly.py': {
        'batch_size': 2000,
        'commit_frequency': 'per_20_symbols',
        'priority': 'CRITICAL',
        'estimated_improvement': '40-50%'
    },
    'loadpricemonthly.py': {
        'batch_size': 1000,
        'commit_frequency': 'per_10_symbols',
        'priority': 'CRITICAL',
        'estimated_improvement': '40-50%'
    },

    # ETF prices (parallel with stock prices)
    'loadetfpricedaily.py': {
        'batch_size': 3000,
        'commit_frequency': 'per_30_symbols',
        'priority': 'HIGH',
        'estimated_improvement': '40-50%'
    },
    'loadetfpriceweekly.py': {
        'batch_size': 1500,
        'commit_frequency': 'per_15_symbols',
        'priority': 'HIGH',
        'estimated_improvement': '40-50%'
    },
    'loadetfpricemonthly.py': {
        'batch_size': 1000,
        'commit_frequency': 'per_10_symbols',
        'priority': 'HIGH',
        'estimated_improvement': '40-50%'
    },

    # Financial statements (balance sheets, income, cash flow)
    'loadquarterlybalancesheet.py': {
        'batch_size': 500,
        'commit_frequency': 'per_10_symbols',
        'priority': 'HIGH',
        'estimated_improvement': '30-40%'
    },
    'loadannualbalancesheet.py': {
        'batch_size': 500,
        'commit_frequency': 'per_10_symbols',
        'priority': 'HIGH',
        'estimated_improvement': '30-40%'
    },
    'loadquarterlyincomestatement.py': {
        'batch_size': 500,
        'commit_frequency': 'per_10_symbols',
        'priority': 'HIGH',
        'estimated_improvement': '30-40%'
    },
    'loadannualincomestatement.py': {
        'batch_size': 500,
        'commit_frequency': 'per_10_symbols',
        'priority': 'HIGH',
        'estimated_improvement': '30-40%'
    },

    # Buy/Sell signals
    'loadbuysellmonthly.py': {
        'batch_size': 1000,
        'commit_frequency': 'per_10_symbols',
        'priority': 'MEDIUM',
        'estimated_improvement': '20-30%'
    },
    'loadbuysellweekly.py': {
        'batch_size': 2000,
        'commit_frequency': 'per_20_symbols',
        'priority': 'MEDIUM',
        'estimated_improvement': '20-30%'
    },
    'loadbuyselldaily.py': {
        'batch_size': 5000,
        'commit_frequency': 'per_50_symbols',
        'priority': 'MEDIUM',
        'estimated_improvement': '20-30%'
    },

    # ETF signals (parallel)
    'loadbuysell_etf_monthly.py': {
        'batch_size': 500,
        'commit_frequency': 'per_5_symbols',
        'priority': 'MEDIUM',
        'estimated_improvement': '20-30%'
    },
    'loadbuysell_etf_weekly.py': {
        'batch_size': 1000,
        'commit_frequency': 'per_10_symbols',
        'priority': 'MEDIUM',
        'estimated_improvement': '20-30%'
    },
    'loadbuysell_etf_daily.py': {
        'batch_size': 2000,
        'commit_frequency': 'per_20_symbols',
        'priority': 'MEDIUM',
        'estimated_improvement': '20-30%'
    },

    # Misc data
    'loadearningshistory.py': {  # Already optimized
        'status': 'DONE',
        'batch_size': 500,
        'estimated_improvement': '20-30%'
    },
    'loadstockscores.py': {  # Already optimized
        'status': 'DONE',
        'batch_size': 1000,
        'estimated_improvement': '30-40%'
    },
}

print("╔════════════════════════════════════════════════════════════════╗")
print("║           BATCH OPTIMIZATION ROADMAP - PHASE 2                ║")
print("╚════════════════════════════════════════════════════════════════╝")
print()

critical = [k for k, v in LOADERS_TO_OPTIMIZE.items() if v.get('priority') == 'CRITICAL']
high = [k for k, v in LOADERS_TO_OPTIMIZE.items() if v.get('priority') == 'HIGH']
medium = [k for k, v in LOADERS_TO_OPTIMIZE.items() if v.get('priority') == 'MEDIUM']
done = [k for k, v in LOADERS_TO_OPTIMIZE.items() if v.get('status') == 'DONE']

print(f"✅ ALREADY DONE ({len(done)}):")
for loader in done:
    info = LOADERS_TO_OPTIMIZE[loader]
    print(f"   ✓ {loader} ({info['estimated_improvement']})")

print()
print(f"🔴 CRITICAL ({len(critical)} loaders, ~22.8M rows):")
for loader in critical:
    info = LOADERS_TO_OPTIMIZE[loader]
    print(f"   • {loader}")
    print(f"     └─ Batch: {info['batch_size']} rows | Commit: {info['commit_frequency']}")
    print(f"     └─ Impact: {info['estimated_improvement']} faster")

print()
print(f"🟠 HIGH PRIORITY ({len(high)} loaders):")
for loader in high:
    info = LOADERS_TO_OPTIMIZE[loader]
    print(f"   • {loader}")
    print(f"     └─ Batch: {info['batch_size']} rows | Commit: {info['commit_frequency']}")

print()
print(f"🟡 MEDIUM PRIORITY ({len(medium)} loaders):")
for loader in medium:
    info = LOADERS_TO_OPTIMIZE[loader]
    print(f"   • {loader}")
    print(f"     └─ Batch: {info['batch_size']} rows | Commit: {info['commit_frequency']}")

print()
print("IMPLEMENTATION STRATEGY:")
print("═" * 60)
print()
print("Wave 1 (CRITICAL - Price data): 3 loaders")
print("  Deploy immediately after Batch 5 succeeds")
print("  Expected: 40-50% faster, biggest data volume")
print()
print("Wave 2 (HIGH - Financial data): 6 loaders")
print("  Deploy ~1 hour after Wave 1")
print("  Expected: 30-40% faster")
print()
print("Wave 3 (MEDIUM - Signals): 6 loaders")
print("  Deploy ~2 hours after Wave 2")
print("  Expected: 20-30% faster")
print()
print("TOTAL IMPACT:")
print("  • Current: Batch 5 = 2 loaders optimized")
print("  • After Phase 2: 20 loaders optimized (28 total)")
print("  • Coverage: All price + financial data")
print("  • Target improvement: 50-70% across entire pipeline")
print()
print("Next steps:")
print("  1. Apply Wave 1 optimizations to: pricedaily, priceweekly, pricemonthly")
print("  2. Wait for Batch 5 AWS results")
print("  3. Deploy Wave 1 → Monitor → Deploy Wave 2 → Deploy Wave 3")
