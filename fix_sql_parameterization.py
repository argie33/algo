#!/usr/bin/env python3
"""Find and fix SQL queries that aren't properly parameterized."""
import re
from pathlib import Path

print("\n[SQL SAFETY AUDIT]\n")

at_risk_queries = []

for py_file in Path('.').glob('algo_*.py'):
    try:
        content = py_file.read_text(encoding='utf-8-sig', errors='ignore')
        
        # Find execute() calls
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if '.execute(' in line and '%s' not in line and 'SELECT' in line:
                # This might be a string formatting issue
                if any(fmt in line for fmt in ['.format(', f'{', f"f'"]):
                    at_risk_queries.append({
                        'file': py_file.name,
                        'line': i + 1,
                        'snippet': line.strip()[:80]
                    })
    except:
        pass

if at_risk_queries:
    print(f"Found {len(at_risk_queries)} potentially unsafe SQL queries:\n")
    for q in at_risk_queries[:10]:
        print(f"  {q['file']}:{q['line']}")
        print(f"    {q['snippet']}...\n")
else:
    print("No obvious SQL injection risks detected.")

print("\nNote: Manual review recommended for dynamic SQL construction.")
