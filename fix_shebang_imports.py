#!/usr/bin/env python3
"""Fix files that have imports before shebang lines."""
import re
from pathlib import Path

ROOT = Path('.')
SKIP = {'.git', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'venv'}
fixed = 0
failed = 0

for py_file in sorted(ROOT.glob('**/*.py')):
    # Skip git and cache directories
    if any(skip in py_file.parts for skip in SKIP):
        continue

    try:
        content = py_file.read_text(encoding='utf-8')
        lines = content.split('\n')

        # Check if file starts with an import before shebang
        if not lines[0].startswith('#!') and lines[0].startswith(('import ', 'from ')):
            # Check if shebang exists in first 3 lines
            shebang_idx = None
            for i in range(min(3, len(lines))):
                if lines[i].startswith('#!'):
                    shebang_idx = i
                    break

            if shebang_idx is not None and shebang_idx > 0:
                # Move shebang to line 0
                shebang = lines.pop(shebang_idx)
                lines.insert(0, shebang)
                new_content = '\n'.join(lines)
                py_file.write_text(new_content, encoding='utf-8')
                print(f"[OK] {py_file.relative_to(ROOT)}")
                fixed += 1
    except Exception as e:
        print(f"[FAIL] {py_file.relative_to(ROOT)}: {e}")
        failed += 1

print(f"\nFixed: {fixed}, Failed: {failed}")
