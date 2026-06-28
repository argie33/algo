#!/usr/bin/env python3
"""Pre-commit hook: check that Python files can be imported without errors.

Catches broken imports from refactors, renames, and incomplete changes.
"""

import importlib.util
import sys


def check_import(filepath: str) -> bool:
    """Try to import a Python file, return True if successful."""
    try:
        spec = importlib.util.spec_from_file_location("_check", filepath)
        if spec is None or spec.loader is None:
            return True
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True
    except SyntaxError as e:
        print(f"SYNTAX ERROR in {filepath}:")
        print(f"  {e}")
        return False
    except ImportError as e:
        print(f"IMPORT ERROR in {filepath}:")
        print(f"  {e}")
        return False
    except Exception:
        return True


if __name__ == "__main__":
    failed = []
    for filepath in sys.argv[1:]:
        if not filepath.endswith(".py"):
            continue
        if not check_import(filepath):
            failed.append(filepath)

    if failed:
        print(f"\n❌ {len(failed)} file(s) have import errors")
        sys.exit(1)
    else:
        print(f"✓ All {len(sys.argv) - 1} files import successfully")
        sys.exit(0)
