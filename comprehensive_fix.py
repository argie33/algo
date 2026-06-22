#!/usr/bin/env python3
"""Comprehensive fix for all mypy Returning Any errors using cast()."""

import re
from pathlib import Path

FILES_TO_FIX = [
    "lambda/api/routes/settings.py",
    "lambda/api/routes/research.py",
    "lambda/api/routes/logs.py",
    "lambda/api/routes/openapi_spec.py",
    "lambda/api/routes/audit.py",
    "lambda/api/routes/algo_handlers/orchestration.py",
    "lambda/api/routes/algo_handlers/external.py",
    "lambda/api/routes/algo_handlers/market.py",
    "lambda/api/routes/algo_handlers/dashboard.py",
    "lambda/api/routes/algo_handlers/sector.py",
    "lambda/api/routes/algo_handlers/signals.py",
    "lambda/api/routes/algo_handlers/config.py",
    "lambda/api/routes/algo_handlers/monitoring.py",
    "lambda/api/routes/algo.py",
    "lambda/api/routes/stocks.py",
    "lambda/api/routes/signals.py",
    "lambda/api/routes/sectors.py",
    "lambda/api/routes/scores.py",
    "lambda/api/routes/health.py",
    "lambda/api/routes/market.py",
    "lambda/api/routes/prices.py",
    "lambda/api/routes/positions.py",
    "lambda/api/routes/sentiment.py",
    "lambda/api/routes/earnings.py",
    "lambda/api/routes/economic.py",
    "lambda/api/routes/financials.py",
    "lambda/api/routes/data_coverage.py",
    "lambda/api/routes/contact.py",
    "lambda/api/routes/trades.py",
    "lambda/api/routes/risk_dashboard.py",
    "lambda/api/routes/admin.py",
    "lambda/api/routes/user_isolation.py",
    "lambda/api/api_router.py",
]

def fix_file(filepath: str) -> int:
    """Fix cast issues in a single file."""
    path = Path(filepath)
    if not path.exists():
        return 0
    
    content = path.read_text()
    lines = content.split('\n')
    
    # Check if cast is imported
    has_cast = False
    typing_import_idx = -1
    for i, line in enumerate(lines):
        if 'from typing import' in line:
            typing_import_idx = i
            if 'cast' in line:
                has_cast = True
            break
    
    fixes = 0
    new_lines = []
    
    for line in lines:
        # Check if this is a return statement
        if line.strip().startswith('return '):
            # Remove type: ignore comment if present, but keep closing parens
            clean_line = re.sub(r'\s*#\s*type:\s*ignore\[no-any-return\]', '', line)
            
            # Now check if it needs cast wrapping
            if 'cast(' not in clean_line:
                match = re.match(r'^(\s*)return\s+(.+)$', clean_line)
                if match:
                    indent, return_val = match.groups()
                    # Check if this returns from a function that needs wrapping
                    if any(func in return_val for func in ['error_response(', 'json_response(', 'handle_db_error(']):
                        # Wrap in cast
                        new_line = f'{indent}return cast(dict[str, Any], {return_val})'
                        new_lines.append(new_line)
                        fixes += 1
                        continue
            
            new_lines.append(clean_line)
        else:
            new_lines.append(line)
    
    # Add cast import if needed
    if fixes > 0 and not has_cast:
        if typing_import_idx >= 0:
            line = new_lines[typing_import_idx]
            if line.rstrip().endswith(')'):
                new_lines[typing_import_idx] = line.rstrip()[:-1] + ', cast)'
            else:
                new_lines[typing_import_idx] = line + ', cast'
    
    if fixes > 0:
        path.write_text('\n'.join(new_lines))
        return fixes
    return 0

if __name__ == '__main__':
    total = 0
    for file in FILES_TO_FIX:
        fixed = fix_file(file)
        if fixed > 0:
            total += fixed
    print(f"Total fixes: {total}")
