#!/usr/bin/env python3
"""
Safe float conversion v2: Line-by-line processing without regex.
Avoids recursive regex issues and malformed output.
"""

import ast
from pathlib import Path
from typing import Optional


def can_parse_as_python(text: str) -> bool:
    """Check if text is valid Python syntax."""
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


def simple_line_replacer(content: str) -> str:
    """Simple line-by-line float() -> safe_float() replacement."""
    lines = content.split('\n')
    modified = False

    for i, line in enumerate(lines):
        # Skip comments and empty lines
        if not line.strip() or line.strip().startswith('#'):
            continue

        # Count float( occurrences
        count = line.count('float(')
        if count == 0:
            continue

        # Simple replacement for common patterns
        # Only replace if line looks safe
        if 'float(' in line:
            # Pattern 1: float(x) -> safe_float(x, default=0.0, context="...")
            # Do simple textual replacement for single-occurrence lines
            if count == 1 and line.count('(') <= 3 and line.count(')') <= 3:
                # Extract context from surrounding code
                context = line.split('float(')[0][-10:].strip()
                if not context:
                    context = "value"

                # Replace: float(...) with safe_float(..., default=0.0, context="...")
                # This is a simple single-replacement approach
                parts = line.split('float(', 1)
                before = parts[0]

                # Find matching closing paren
                rest = parts[1]
                paren_depth = 1
                end_idx = 0
                for j, ch in enumerate(rest):
                    if ch == '(':
                        paren_depth += 1
                    elif ch == ')':
                        paren_depth -= 1
                        if paren_depth == 0:
                            end_idx = j
                            break

                if end_idx > 0:
                    inner = rest[:end_idx]
                    after = rest[end_idx + 1:]

                    new_line = f'{before}safe_float({inner}, default=0.0, context="{context}">{after}'
                    lines[i] = new_line
                    modified = True

    if modified:
        return '\n'.join(lines)
    return content


def add_import_if_needed(content: str) -> str:
    """Add safe_float import if using it and not imported."""
    if 'safe_float(' not in content:
        return content

    if 'from utils.safe_data_conversion import safe_float' in content:
        return content

    # Add import after last import statement
    lines = content.split('\n')
    last_import_idx = -1

    for i, line in enumerate(lines):
        if line.startswith(('from ', 'import ')):
            last_import_idx = i

    if last_import_idx >= 0:
        lines.insert(last_import_idx + 1, 'from utils.safe_data_conversion import safe_float')
        return '\n'.join(lines)

    return content


def process_file_safe(fpath: str) -> tuple[int, bool]:
    """
    Process file with safe line-by-line approach.
    Returns: (replacements, has_error)
    """
    p = Path(fpath)
    if not p.exists():
        return 0, True

    try:
        with open(p, encoding='utf-8', errors='replace') as f:
            original = f.read()
    except Exception:
        return 0, True

    # Count unsafe float() calls
    count_before = original.count('float(') - original.count('safe_float(')
    if count_before <= 0:
        return 0, False

    # Try to do safe replacement
    content = simple_line_replacer(original)
    content = add_import_if_needed(content)

    # Verify result is valid Python
    if not can_parse_as_python(content):
        # Don't write corrupted file
        return 0, True

    # Write only if different AND valid
    if content != original:
        try:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(content)

            count_after = content.count('float(') - content.count('safe_float(')
            count_replaced = count_before - count_after
            return count_replaced, False
        except Exception:
            return 0, True

    return 0, False


def main():
    """Process priority files with safe line-by-line approach."""
    priority_files = [
        "algo/infrastructure/config.py",
        "algo/risk/var.py",
        "algo/trading/executor.py",
        "algo/trading/exit_engine.py",
        "algo/risk/circuit_breaker.py",
        "lambda/api/routes/market.py",
        "loaders/load_signal_quality_scores.py",
        "tools/dashboard/panels/health.py",
    ]

    print("=" * 70)
    print("SAFE FLOAT CONVERSION v2 (line-by-line)")
    print("=" * 70)
    print()

    total = 0
    for fpath in priority_files:
        count, has_error = process_file_safe(fpath)
        status = f"FIXED {count}" if count > 0 else ("ERROR" if has_error else "SKIP")
        print(f"{fpath:50} {status:12}")
        total += count

    print()
    print(f"TOTAL: {total} replacements")


if __name__ == "__main__":
    main()
