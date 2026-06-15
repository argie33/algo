#!/usr/bin/env python3
"""Rewrite all imports to use new submodule paths."""

from pathlib import Path

# Mapping old imports to new imports
IMPORT_MAPPING = {
    # algo/ reorganization
    "from algo.signals import": "from algo.signals import",
    "from algo.signals import": "from algo.signals import",
    "from algo.signals import": "from algo.signals import",
    "from algo.signals import": "from algo.signals import",
    "from algo.signals import": "from algo.signals import",
    "from algo.signals import": "from algo.signals import",
    "from algo.signals import": "from algo.signals import",
    "from algo.signals import": "from algo.signals import",
    "from algo.risk import": "from algo.risk import",
    "from algo.risk import": "from algo.risk import",
    "from algo.risk import": "from algo.risk import",
    "from algo.risk import": "from algo.risk import",
    "from algo.risk import": "from algo.risk import",
    "from algo.risk import": "from algo.risk import",
    "from algo.risk import": "from algo.risk import",
    "from algo.trading import": "from algo.trading import",
    "from algo.trading import": "from algo.trading import",
    "from algo.trading import": "from algo.trading import",
    "from algo.trading import": "from algo.trading import",
    "from algo.trading import": "from algo.trading import",
    "from algo.monitoring import": "from algo.monitoring import",
    "from algo.monitoring import": "from algo.monitoring import",
    "from algo.monitoring import": "from algo.monitoring import",
    "from algo.monitoring import": "from algo.monitoring import",
    "from algo.reporting import": "from algo.reporting import",
    "from algo.reporting import": "from algo.reporting import",
    "from algo.reporting import": "from algo.reporting import",
    "from algo.reporting import": "from algo.reporting import",
    "from algo.reporting import": "from algo.reporting import",
    "from algo.orchestration import": "from algo.orchestration import",
    "from algo.orchestration import": "from algo.orchestration import",
    "from algo.orchestration import": "from algo.orchestration import",
    "from algo.infrastructure import": "from algo.infrastructure import",
    "from algo.infrastructure import": "from algo.infrastructure import",
    "from algo.infrastructure import": "from algo.infrastructure import",
    "from algo.infrastructure import": "from algo.infrastructure import",
    "from algo.infrastructure import": "from algo.infrastructure import",
    "from algo.infrastructure import": "from algo.infrastructure import",
    "from algo.infrastructure import": "from algo.infrastructure import",
    "from algo.infrastructure import": "from algo.infrastructure import",
    # utils/ reorganization
    "from utils.db import": "from utils.db import",
    "from utils.db import": "from utils.db import",
    "from utils.db import": "from utils.db import",
    "from utils.db import": "from utils.db import",
    "from utils.db import": "from utils.db import",
    "from utils.db import": "from utils.db import",
    "from utils.db import": "from utils.db import",
    "from utils.logging import": "from utils.logging import",
    "from utils.logging import": "from utils.logging import",
    "from utils.logging import": "from utils.logging import",
    "from utils.logging import": "from utils.logging import",
    "from utils.logging import": "from utils.logging import",
    "from utils.logging import": "from utils.logging import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.validation import": "from utils.validation import",
    "from utils.data import": "from utils.data import",
    "from utils.data import": "from utils.data import",
    "from utils.data import": "from utils.data import",
    "from utils.data import": "from utils.data import",
    "from utils.data import": "from utils.data import",
    "from utils.signals import": "from utils.signals import",
    "from utils.signals import": "from utils.signals import",
    "from utils.signals import": "from utils.signals import",
    "from utils.signals import": "from utils.signals import",
    "from utils.signals import": "from utils.signals import",
    "from utils.trading import": "from utils.trading import",
    "from utils.trading import": "from utils.trading import",
    "from utils.trading import": "from utils.trading import",
    "from utils.trading import": "from utils.trading import",
    "from utils.loaders import": "from utils.loaders import",
    "from utils.loaders import": "from utils.loaders import",
    "from utils.loaders import": "from utils.loaders import",
    "from utils.loaders import": "from utils.loaders import",
    "from utils.external import": "from utils.external import",
    "from utils.external import": "from utils.external import",
    "from utils.infrastructure import": "from utils.infrastructure import",
    "from utils.infrastructure import": "from utils.infrastructure import",
    "from utils.infrastructure import": "from utils.infrastructure import",
    "from utils.infrastructure import": "from utils.infrastructure import",
    "from utils.infrastructure import": "from utils.infrastructure import",
    "from utils.infrastructure import": "from utils.infrastructure import",
    "from utils.infrastructure import": "from utils.infrastructure import",
    "from utils.infrastructure import": "from utils.infrastructure import",
    "from utils.infrastructure import": "from utils.infrastructure import",
    "from utils.infrastructure import": "from utils.infrastructure import",
    "from utils.ops import": "from utils.ops import",
    "from utils.ops import": "from utils.ops import",
    "from utils.ops import": "from utils.ops import",
}

def update_file(filepath: Path) -> bool:
    """Update imports in a single file."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return False

    original = content
    for old_import, new_import in IMPORT_MAPPING.items():
        # Simple string replacement for 'from X import' statements
        content = content.replace(old_import, new_import)

    if content != original:
        try:
            filepath.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    return False

def main():
    repo_root = Path(".")
    py_files = list(repo_root.glob("**/*.py"))

    print(f"[*] Scanning {len(py_files)} Python files for import updates...")

    updated_count = 0
    for py_file in sorted(py_files):
        # Skip __pycache__ and .pyc files
        if "__pycache__" in str(py_file):
            continue
        # Skip generated __init__.py files (we already generated them)
        if py_file.parent.name in ["algo", "utils"] and py_file.name == "__init__.py":
            continue

        if update_file(py_file):
            updated_count += 1
            rel_path = py_file.relative_to(repo_root)
            print(f"  [+] Updated {rel_path}")

    print(f"\n[OK] Updated {updated_count} files")

if __name__ == "__main__":
    main()
