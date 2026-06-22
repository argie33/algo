#!/usr/bin/env python3
"""Fix all mypy Returning Any errors by using cast()."""

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
    """Fix cast issues in a single file. Returns number of fixes made."""
    path = Path(filepath)
    if not path.exists():
        print(f"SKIP: {filepath} (does not exist)")
        return 0
    
    content = path.read_text()
    lines = content.split('\n')
    
    # Check if cast is already imported
    has_cast = False
    typing_import_line = -1
    
    for i, line in enumerate(lines):
        if 'from typing import' in line:
            typing_import_line = i
            if 'cast' in line:
                has_cast = True
            break
    
    # Collect all lines that need cast wrapping (return statements not already wrapped)
    fixes = 0
    new_lines = []
    
    for i, line in enumerate(lines):
        # Look for return statements
        if line.strip().startswith('return '):
            # First remove any existing type: ignore comment
            clean_line = re.sub(r'\s*#\s*type:\s*ignore\[no-any-return\]\s*\)', ')', line)
            
            # Check if already wrapped in cast
            if 'cast(' not in clean_line:
                match = re.match(r'^(\s*)return\s+(.+)$', clean_line)
                if match:
                    indent, return_val = match.groups()
                    # Only wrap if returning something that looks like it could be Any
                    if any(func in return_val for func in ['error_response(', 'json_response(', 'handle_db_error(']):
                        new_line = f'{indent}return cast(dict[str, Any], {return_val})'
                        new_lines.append(new_line)
                        fixes += 1
                    else:
                        new_lines.append(clean_line)
                else:
                    new_lines.append(clean_line)
            else:
                new_lines.append(clean_line)
        else:
            new_lines.append(line)
    
    # If we made fixes, ensure cast is imported
    if fixes > 0:
        if not has_cast:
            if typing_import_line >= 0:
                # Add to existing typing import
                line = lines[typing_import_line]
                if line.rstrip().endswith(')'):
                    # Multi-line import
                    new_lines[typing_import_line] = line.rstrip()[:-1] + ', cast)'
                else:
                    # Single-line import
                    new_lines[typing_import_line] = line + ', cast'
            else:
                # Find where to add the import
                for i, line in enumerate(new_lines):
                    if line.startswith('from typing import') or (line.startswith('import ') and i == 0):
                        new_lines.insert(i, 'from typing import cast')
                        break
    
    if fixes > 0:
        new_content = '\n'.join(new_lines)
        path.write_text(new_content)
        print(f"FIXED: {filepath} ({fixes} fixes)")
        return fixes
    else:
        print(f"SKIP: {filepath} (no fixes needed)")
        return 0

if __name__ == '__main__':
    total_fixes = 0
    for file in FILES_TO_FIX:
        total_fixes += fix_file(file)
    print(f"\nTotal fixes: {total_fixes}")
