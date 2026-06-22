#!/usr/bin/env python3
"""Smart fix that properly handles multi-line return statements."""

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
    """Fix cast issues in a single file, handling multi-line returns."""
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
    
    # Process lines, handling multi-line returns
    fixes = 0
    i = 0
    new_lines = []
    
    while i < len(lines):
        line = lines[i]
        
        # Remove type: ignore comments
        clean_line = re.sub(r'\s*#\s*type:\s*ignore\[no-any-return\]', '', line)
        
        # Check if this starts a return statement that needs wrapping
        if clean_line.strip().startswith('return ') and 'cast(' not in clean_line:
            # Check if the return is complete on this line
            return_text = clean_line.strip()[7:].strip()  # Remove 'return '
            
            # Check if this returns from a function that needs wrapping
            needs_cast = any(func in return_text for func in ['error_response(', 'json_response(', 'handle_db_error('])
            
            if needs_cast:
                # Check if return is complete (balanced parens)
                j = i
                full_return = clean_line
                open_parens = clean_line.count('(') - clean_line.count(')')
                
                # Collect continuation lines
                while open_parens > 0 and j + 1 < len(lines):
                    j += 1
                    next_line = lines[j]
                    # Remove type: ignore from continuation lines too
                    next_line = re.sub(r'\s*#\s*type:\s*ignore\[no-any-return\]', '', next_line)
                    full_return += '\n' + next_line
                    open_parens += next_line.count('(') - next_line.count(')')
                
                # Now wrap the full return in cast
                match = re.match(r'^(\s*)return\s+(.+)$', full_return, re.DOTALL)
                if match:
                    indent, return_val = match.groups()
                    # Normalize indentation for multi-line
                    lines_in_return = return_val.split('\n')
                    new_return = f'{indent}return cast(dict[str, Any], {return_val})'
                    
                    # Add all lines
                    new_lines.append(new_return)
                    fixes += 1
                    i = j + 1
                    continue
        
        new_lines.append(clean_line)
        i += 1
    
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
