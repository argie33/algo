#!/usr/bin/env python3
"""Automated E501 line-too-long fixer.

Identifies lines >120 chars and attempts intelligent breaks:
- f-strings: extract variables before the f-string
- method chains: break before dots
- string concatenation: keep logical flow
- function calls: break long argument lists
"""

import re
from pathlib import Path


def fix_long_line(line: str, max_length: int = 120) -> str:
    """Attempt to fix an overly-long line."""
    if len(line.rstrip()) <= max_length:
        return line

    # Don't touch docstrings or comments that are intentionally long
    if line.strip().startswith('"""') or line.strip().startswith("'''"):
        return line

    # Strategy 1: Break f-strings by extracting variables
    match = re.match(r'^(\s*)f"([^"]+)"(.*)', line)
    if match and len(line) > max_length:
        indent, content, _rest = match.groups()
        # Try to extract the variable part before the f-string
        if '{' in content:
            # This is complex, skip for now
            pass

    # Strategy 2: Break long function calls before arguments
    if '(' in line and ')' in line and len(line) > max_length:
        # Find the opening paren
        paren_idx = line.rfind('(')
        if paren_idx > 20:  # Substantial function name
            indent = len(line) - len(line.lstrip())
            pre_paren = line[:paren_idx]
            post_paren = line[paren_idx + 1:]

            # If we can reasonably break here, do it
            if ',' in post_paren and len(pre_paren) < max_length:
                # Break before arguments
                indent_str = ' ' * (indent + 4)
                return pre_paren + '(\n' + indent_str + post_paren

    # Strategy 3: Break string concatenations
    if ' + ' in line and '"' in line and len(line) > max_length:
        # Find the last string part and break before it
        parts = line.split(' + ')
        if len(parts) > 1:
            indent = len(line) - len(line.lstrip())
            indent_str = ' ' * indent
            return (' +\n' + indent_str).join(parts) + '\n'

    # If nothing worked, return original
    return line


def process_file(filepath: Path) -> int:
    """Fix E501 errors in a file. Return number of fixes."""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return 0

    lines = content.split('\n')
    fixed = 0

    for i, line in enumerate(lines):
        if len(line.rstrip()) > 120:
            fixed_line = fix_long_line(line)
            if fixed_line != line:
                lines[i] = fixed_line
                fixed += 1

    if fixed > 0:
        try:
            filepath.write_text('\n'.join(lines), encoding='utf-8')
        except Exception:
            pass

    return fixed


if __name__ == '__main__':
    algo_dir = Path('algo')
    total_fixed = 0

    for pyfile in algo_dir.rglob('*.py'):
        fixed = process_file(pyfile)
        if fixed > 0:
            total_fixed += fixed
            print(f'{pyfile}: {fixed} fixes')

    print(f'\nTotal E501 fixes applied: {total_fixed}')
