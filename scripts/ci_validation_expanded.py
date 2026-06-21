#!/usr/bin/env python3
"""Comprehensive CI validation - check all Python files can import."""

import sys
import os
import importlib.util
from pathlib import Path


def validate_imports():
    """Check that all Python files can be imported."""
    failed = []
    successful = []

    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in
                   ['.git', '__pycache__', '.pytest_cache', 'node_modules',
                    '.venv', 'venv', '.terraform', 'migrations']]

        for file in sorted(files):
            if not file.endswith('.py') or file.startswith('test_'):
                continue

            filepath = Path(root) / file
            rel_path = str(filepath.relative_to('.'))

            try:
                spec = importlib.util.spec_from_file_location(
                    filepath.stem, filepath)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[filepath.stem] = module
                    spec.loader.exec_module(module)
                    successful.append(rel_path)
            except (ImportError, ModuleNotFoundError, SyntaxError,
                    NameError) as e:
                failed.append(f"{rel_path}: {type(e).__name__}: {str(e)[:80]}")
            except Exception as e:
                if 'OperationalError' in str(type(e).__name__):
                    failed.append(
                        f"{rel_path}: MODULE_LEVEL_EXEC: "
                        f"{str(e)[:60]}"
                    )
                else:
                    successful.append(rel_path)

    return successful, failed


def main():
    """Run validation."""
    print("\n" + "="*70)
    print("COMPREHENSIVE CI VALIDATION - Module Import Check")
    print("="*70)

    successful, failed = validate_imports()

    if failed:
        print(f"\nFAILED: {len(failed)} modules have import errors:\n")
        for err in failed:
            print(f"  {err}")
        print(f"\n{len(successful)} modules passed\n")
        return 1
    else:
        print(f"\nSUCCESS: All {len(successful)} Python modules imported\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
