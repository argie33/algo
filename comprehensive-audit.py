#!/usr/bin/env python3
"""Comprehensive system audit - find all issues"""

import os
import re
from pathlib import Path

print("=" * 70)
print("COMPREHENSIVE SYSTEM AUDIT")
print("=" * 70)

# 1. Check all loader files for issues
print("\n[1] LOADER FILES AUDIT")
print("-" * 70)

loaders = sorted([f for f in os.listdir('.') if f.startswith('load') and f.endswith('.py')])
print(f"Total loaders: {len(loaders)}\n")

issues = {
    'missing_threadpool': [],
    'missing_error_handling': [],
    'missing_secrets_manager': [],
    'missing_batch_insert': [],
    'unicode_issues': []
}

for loader in loaders:
    with open(loader) as f:
        content = f.read()
    
    # Check for issues
    if 'ThreadPoolExecutor' not in content and loader not in [
        'loadnews.py', 'loadsentiment.py', 'loadsectors.py', 'loadstockscores.py',
        'loadmarket.py', 'loadfactormetrics.py', 'loadecondata.py'
    ]:
        issues['missing_threadpool'].append(loader)
    
    if content.count('try:') < 5 or 'except' not in content:
        issues['missing_error_handling'].append(loader)
    
    if '–' in content or '—' in content:  # em-dash check
        issues['unicode_issues'].append(loader)

print(f"Missing ThreadPoolExecutor (not yet parallel): {len(issues['missing_threadpool'])}")
if issues['missing_threadpool'][:5]:
    for f in issues['missing_threadpool'][:5]:
        print(f"  - {f}")
if len(issues['missing_threadpool']) > 5:
    print(f"  ... and {len(issues['missing_threadpool']) - 5} more")

print(f"\nMissing error handling (try/except): {len(issues['missing_error_handling'])}")

print(f"\nUnicode issues (em-dashes): {len(issues['unicode_issues'])}")
if issues['unicode_issues']:
    for f in issues['unicode_issues']:
        print(f"  - {f}")

# 2. Check Dockerfiles
print("\n[2] DOCKERFILE AUDIT")
print("-" * 70)

dockerfiles = sorted([f for f in os.listdir('.') if f.startswith('Dockerfile')])
print(f"Total Dockerfiles: {len(dockerfiles)}")

missing_dockerfiles = []
for loader in loaders:
    loader_name = loader.replace('load', '').replace('.py', '')
    dockerfile = f"Dockerfile.load{loader_name}"
    if dockerfile not in dockerfiles:
        missing_dockerfiles.append((loader, dockerfile))

print(f"Loaders without Dockerfiles: {len(missing_dockerfiles)}")
if missing_dockerfiles[:5]:
    for loader, dockerfile in missing_dockerfiles[:5]:
        print(f"  - {loader} (needs {dockerfile})")

# 3. Check CloudFormation templates
print("\n[3] CLOUDFORMATION TEMPLATES AUDIT")
print("-" * 70)

templates = [f for f in os.listdir('.') if f.startswith('template-') and f.endswith('.yml')]
print(f"Templates found: {len(templates)}")
for t in sorted(templates):
    print(f"  - {t}")

# 4. Check GitHub Actions workflows
print("\n[4] GITHUB ACTIONS AUDIT")
print("-" * 70)

workflows_dir = '.github/workflows'
if os.path.exists(workflows_dir):
    workflows = [f for f in os.listdir(workflows_dir) if f.endswith('.yml')]
    print(f"Workflows configured: {len(workflows)}")
    for w in sorted(workflows)[:5]:
        print(f"  - {w}")

# 5. Database tables
print("\n[5] DATABASE SCHEMA AUDIT")
print("-" * 70)

batch5_tables = [
    'quarterly_income_statement',
    'annual_income_statement',
    'quarterly_balance_sheet',
    'annual_balance_sheet',
    'quarterly_cash_flow',
    'annual_cash_flow'
]

print(f"Batch 5 tables required: {len(batch5_tables)}")
for t in batch5_tables:
    print(f"  - {t}")

# 6. Code quality checks
print("\n[6] CODE QUALITY AUDIT")
print("-" * 70)

# Check for hardcoded credentials
print("Checking for hardcoded secrets...")
secret_patterns = ['password=', 'api_key=', 'secret=', '0x[a-f0-9]+']
found_secrets = []

for py_file in loaders:
    with open(py_file) as f:
        for i, line in enumerate(f, 1):
            if any(pattern.lower() in line.lower() for pattern in secret_patterns):
                if 'environ' not in line and 'os.get' not in line:
                    found_secrets.append((py_file, i, line.strip()[:50]))

if found_secrets:
    print(f"Found {len(found_secrets)} potential hardcoded secrets:")
    for f, line_no, content in found_secrets[:3]:
        print(f"  - {f}:{line_no}")
else:
    print("✓ No hardcoded secrets found")

print("\n" + "=" * 70)
print("AUDIT COMPLETE")
print("=" * 70)

print("\nSUMMARY:")
print(f"  Loaders ready for AWS: {len(loaders) - len(issues['missing_threadpool'])}/{len(loaders)}")
print(f"  Dockerfiles: {len(dockerfiles)}")
print(f"  CloudFormation templates: {len(templates)}")
print(f"  Workflows: {len(workflows) if os.path.exists(workflows_dir) else 0}")

