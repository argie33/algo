#!/usr/bin/env python3
"""Final comprehensive fix for all cast issues."""

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
    """Fix all return statements in a file."""
    path = Path(filepath)
    if not path.exists():
        return 0
    
    content = path.read_text()
    
    # Check if cast is imported
    has_cast = 'cast' in content and 'from typing import' in content
    
    # Replace patterns with cast - remove type: ignore comments that are malformed
    # Pattern: return cast(dict[str, Any], ...) ... # type: ignore[no-any-return])
    # Should become: return cast(dict[str, Any], ...)
    content = re.sub(
        r'return cast\(dict\[str, Any\], ([^)]+)\)\s*#\s*type:\s*ignore\[no-any-return\]\)',
        r'return cast(dict[str, Any], \1)',
        content
    )
    
    # Now handle return statements not yet wrapped in cast
    lines = content.split('\n')
    new_lines = []
    fixes = 0
    
    for line in lines:
        # Remove any other lingering type: ignore comments
        line = re.sub(r'\s*#\s*type:\s*ignore\[no-any-return\]$', '', line)
        
        if line.strip().startswith('return ') and 'cast(' not in line:
            match = re.match(r'^(\s*)return\s+(.+)$', line)
            if match:
                indent, return_val = match.groups()
                if any(func in return_val for func in ['error_response(', 'json_response(', 'handle_db_error(']):
                    new_line = f'{indent}return cast(dict[str, Any], {return_val})'
                    new_lines.append(new_line)
                    fixes += 1
                    continue
        new_lines.append(line)
    
    content = '\n'.join(new_lines)
    
    # Add cast import if needed
    if fixes > 0 and not has_cast:
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'from typing import' in line:
                if line.rstrip().endswith(')'):
                    lines[i] = line.rstrip()[:-1] + ', cast)'
                else:
                    lines[i] = line + ', cast'
                break
        content = '\n'.join(lines)
    
    if fixes > 0:
        path.write_text(content)
        return fixes
    return 0

if __name__ == '__main__':
    total = 0
    for file in FILES_TO_FIX:
        fixed = fix_file(file)
        if fixed > 0:
            print(f"FIXED: {file} ({fixed})")
        total += fixed
    print(f"\nTotal: {total}")
