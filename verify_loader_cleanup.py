#!/usr/bin/env python3
"""Comprehensive loader verification — find ALL remaining mess."""
import sys
import os
from pathlib import Path

sys.path.insert(0, '.')

issues = []
warnings = []
ok = []

# ============================================================
# 1. FILES ON DISK vs TERRAFORM
# ============================================================
loader_dir = Path('loaders')
actual_files = set(f.stem for f in loader_dir.glob('load_*.py'))

# Read terraform loader_file_map
with open('terraform/modules/loaders/main.tf') as f:
    content = f.read()
    # Extract all keys from loader_file_map
    import re
    matches = re.findall(r'"(\w+)"\s*=\s*"([^"]+\.py)"', content)
    terraform_keys = {key: file for key, file in matches}

print("=" * 80)
print("LOADER SYSTEM VERIFICATION")
print("=" * 80)

# Check 1: Are all terraform keys backed by real files?
print("\n[CHECK 1] Terraform references to actual files")
missing_files = []
for key, filename in terraform_keys.items():
    if filename == "loadpricedaily.py":
        # This is a special case - it's the wrapper reference
        if filename not in [f.name for f in loader_dir.glob('*.py')]:
            missing_files.append(f"{key} -> {filename} [MISSING]")
        else:
            ok.append(f"  {key} -> {filename} [OK]")
    elif filename.startswith("load_"):
        stem = filename.replace('.py', '')
        if stem not in actual_files:
            missing_files.append(f"{key} -> {filename} [MISSING]")
        else:
            ok.append(f"  {key} -> {filename} [OK]")

if missing_files:
    for m in missing_files:
        issues.append(f"Terraform references missing file: {m}")
else:
    ok.append("All terraform references point to real files")

# Check 2: Are there loader files not referenced in terraform?
print("\n[CHECK 2] Actual files -> terraform references")
referenced_files = set(f.split('.')[0] for f in terraform_keys.values())
orphaned = []
for f in actual_files:
    if f not in referenced_files and f != '__pycache__':
        orphaned.append(f)

if orphaned:
    for f in orphaned:
        warnings.append(f"Loader exists but NOT in terraform: load_{f}.py")
else:
    ok.append("All loader files are referenced in terraform")

# Check 3: Look for duplicates (different files with same purpose)
print("\n[CHECK 3] Duplicate/conflicting loaders")
purposes = {}
for f in actual_files:
    # Extract purpose (everything after load_)
    parts = f.split('_')
    # Group by purpose
    if f.startswith('load_stock_price'):
        purpose = 'price'
    elif f.startswith('load_growth_metric'):
        purpose = 'growth'
    elif f.startswith('load_signal'):
        purpose = 'signal'
    elif f.startswith('load_sentiment'):
        purpose = 'sentiment'
    elif f.startswith('load_analyst'):
        purpose = 'analyst'
    else:
        purpose = f

    if purpose not in purposes:
        purposes[purpose] = []
    purposes[purpose].append(f)

duplicates = {p: files for p, files in purposes.items() if len(files) > 1}
if duplicates:
    for purpose, files in sorted(duplicates.items()):
        issues.append(f"DUPLICATE PURPOSE '{purpose}': {', '.join(f'load_{f}.py' for f in files)}")
else:
    ok.append("No duplicate/conflicting loaders found")

# Check 4: Test imports - can each loader actually import?
print("\n[CHECK 4] Loader imports work")
import_issues = []
for f in sorted(actual_files):
    if f in ['__init__', '__pycache__', 'technical_indicators']:
        continue
    try:
        module_name = f'loaders.load_{f}'
        __import__(module_name)
        ok.append(f"  load_{f}.py imports OK")
    except Exception as e:
        import_issues.append(f"  load_{f}.py FAILS: {str(e)[:80]}")

if import_issues:
    for issue in import_issues:
        issues.append(issue)

# Check 5: Step Functions pipeline references
print("\n[CHECK 5] Step Functions pipeline loaders")
with open('terraform/modules/pipeline/main.tf') as f:
    pipeline_content = f.read()
    # Find all loader task definition references
    pipeline_refs = re.findall(r'var\.loader_task_definition_arns\["([^"]+)"\]', pipeline_content)

if pipeline_refs:
    ok.append(f"Step Functions uses {len(pipeline_refs)} loaders: {', '.join(sorted(set(pipeline_refs)))}")
    # Check each is in terraform
    for ref in set(pipeline_refs):
        if ref not in terraform_keys:
            issues.append(f"Step Functions references '{ref}' but NOT in terraform loader_file_map")
else:
    issues.append("Could not parse Step Functions loader references from terraform")

# Check 6: Look for old naming patterns (the "slop")
print("\n[CHECK 6] Look for 'AI slop' — old/weird naming patterns")
slop_patterns = [
    ('load_stock_prices_unified', 'unified (should be just load_stock_prices_daily)'),
    ('loadpricedaily', 'old naming convention (no load_ prefix) — wrapper OK but verify no others'),
    ('load_.*_v2', 'versioned files (should consolidate)'),
    ('load_.*_temp', 'temp files (should be deleted)'),
    ('load_.*_old', 'old files (should be deleted)'),
    ('load_.*_backup', 'backup files (should be deleted)'),
]

slop_found = []
for pattern, description in slop_patterns:
    matching = [f for f in actual_files if re.match(pattern, f) or pattern in f]
    if matching:
        slop_found.append(f"{description}: {', '.join(matching)}")

if slop_found:
    for s in slop_found:
        warnings.append(f"Potential slop: {s}")
else:
    ok.append("No obvious old/temp/backup/versioned loader files found")

# Check 7: Count and verify essential loaders
print("\n[CHECK 7] Verify 9 essential loaders exist")
essential = [
    'eod_bulk_refresh',
    'technical_data_daily',
    'market_health_daily',
    'trend_template_data',
    'buy_sell_daily',
    'signal_quality_scores',
    'algo_metrics_daily',
    'swing_trader_scores',
]

missing_essential = []
for e in essential:
    if e not in terraform_keys:
        missing_essential.append(e)

if missing_essential:
    issues.append(f"MISSING essential loaders from terraform: {', '.join(missing_essential)}")
else:
    ok.append(f"All {len(essential)} essential loaders present in terraform")

# ============================================================
# PRINT RESULTS
# ============================================================
print("\n" + "=" * 80)
print("RESULTS")
print("=" * 80)

if issues:
    print(f"\nCRITICAL ISSUES ({len(issues)}):")
    for issue in issues:
        print(f"  [FAIL] {issue}")

if warnings:
    print(f"\nWARNINGS ({len(warnings)}):")
    for warning in warnings:
        print(f"  [WARN] {warning}")

if ok:
    print(f"\nOK ({len(ok)}):")
    for item in ok[:15]:  # Show first 15
        print(f"  {item}")
    if len(ok) > 15:
        print(f"  ... and {len(ok) - 15} more")

print("\n" + "=" * 80)
print(f"SUMMARY: {len(issues)} critical issues, {len(warnings)} warnings, {len(ok)} OK")
print("=" * 80)

if issues:
    print("\nSYSTEM HAS CRITICAL ISSUES — DO NOT DEPLOY")
    sys.exit(1)
elif warnings:
    print("\nSystem mostly OK but has warnings to review")
    sys.exit(0)
else:
    print("\nLOADER SYSTEM IS CLEAN")
    sys.exit(0)
