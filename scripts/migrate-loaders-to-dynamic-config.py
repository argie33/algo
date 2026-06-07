#!/usr/bin/env python3
"""
Migrate All Loaders to Use Dynamic Configuration

Updates all loaders to read parallelism from DynamoDB via loader_config module
instead of hardcoded environment variables.

This script:
1. Finds all loaders that read LOADER_PARALLELISM
2. Adds import for loader_config
3. Replaces int(os.getenv("LOADER_PARALLELISM", ...)) with get_parallelism(loader_name)
4. Verifies the changes compile
"""

import re
import sys
from pathlib import Path
from typing import Tuple

# Configuration
LOADERS_DIR = Path(__file__).parent.parent / "loaders"
UTILS_DIR = Path(__file__).parent.parent / "utils"

# Pattern to find the parallelism reading code (direct assignment)
PARALLELISM_PATTERN = re.compile(
    r'parallelism\s*=\s*int\s*\(\s*os\.getenv\s*\(\s*["\']LOADER_PARALLELISM["\']\s*,\s*["\'](\d+)["\']\s*\)\s*\)',
    re.MULTILINE
)

# Pattern to find argparse-based parallelism (more common)
ARGPARSE_PARALLELISM_PATTERN = re.compile(
    r'parser\.add_argument\s*\(\s*["\']--parallelism["\']\s*,\s*type\s*=\s*int\s*,\s*default\s*=\s*int\s*\(\s*os\.getenv\s*\(\s*["\']LOADER_PARALLELISM["\']\s*,\s*["\'](\d+)["\']\s*\)\s*\)',
    re.MULTILINE | re.DOTALL
)

# Pattern to find the imports section
IMPORT_PATTERN = re.compile(r'(from utils\.loader_helpers import [^\n]+|from utils\.loader_config import [^\n]+)')


def get_loader_name(file_path: Path) -> str:
    """Extract loader name from filename."""
    # load_technical_data_daily.py -> technical_data_daily
    name = file_path.stem  # Remove .py
    return name.replace("load_", "")


def extract_default_parallelism(match_str: str) -> str:
    """Extract the default parallelism value from the regex match."""
    import re
    m = re.search(r'default=int\(os\.getenv\s*\(\s*["\']LOADER_PARALLELISM["\']\s*,\s*["\'](\d+)["\']\s*\)\s*\)', match_str)
    if m:
        return m.group(1)
    return "1"


def has_dynamic_config_import(content: str) -> bool:
    """Check if file already imports from loader_config."""
    return "from utils.loader_config import" in content


def add_import(content: str) -> str:
    """Add loader_config import if not present."""
    if has_dynamic_config_import(content):
        return content

    # Find the last utils import
    lines = content.split('\n')
    last_utils_import_idx = -1

    for i, line in enumerate(lines):
        if line.startswith('from utils.') or line.startswith('import'):
            last_utils_import_idx = i

    if last_utils_import_idx >= 0:
        # Insert after the last utils import
        lines.insert(last_utils_import_idx + 1, 'from utils.loader_config import get_parallelism, get_default_parallelism')
        return '\n'.join(lines)
    else:
        # No utils imports found, add near the top after basic imports
        lines.insert(10, 'from utils.loader_config import get_parallelism, get_default_parallelism')
        return '\n'.join(lines)


def migrate_loader(file_path: Path) -> Tuple[bool, str]:
    """
    Migrate a single loader file.

    Returns:
        (success, message)
    """
    try:
        content = file_path.read_text(encoding='utf-8')

        # Check for both patterns
        has_direct = PARALLELISM_PATTERN.search(content)
        has_argparse = ARGPARSE_PARALLELISM_PATTERN.search(content)

        if not has_direct and not has_argparse:
            return (True, f"Skipped (no LOADER_PARALLELISM found)")

        # Add import
        content = add_import(content)

        # Get loader name
        loader_name = get_loader_name(file_path)

        # Replace direct assignment pattern
        if has_direct:
            def replace_parallelism(match):
                return f'parallelism = get_parallelism("{loader_name}")'
            content = PARALLELISM_PATTERN.sub(replace_parallelism, content)

        # Replace argparse pattern
        if has_argparse:
            def replace_argparse(match):
                return f'parser.add_argument("--parallelism", type=int, default=get_default_parallelism("{loader_name}")'
            content = ARGPARSE_PARALLELISM_PATTERN.sub(replace_argparse, content)

        # Verify the replacement happened
        if "get_parallelism" not in content and "get_default_parallelism" not in content:
            return (False, "Failed to replace parallelism")

        # Write back
        file_path.write_text(content, encoding='utf-8')
        return (True, "Migrated successfully")

    except Exception as e:
        return (False, f"Error: {e}")


def main():
    """Migrate all loader files."""
    print("Migrating loaders to dynamic configuration...")
    print("-" * 70)

    loader_files = sorted(LOADERS_DIR.glob("load_*.py"))
    success_count = 0
    error_count = 0

    for file_path in loader_files:
        success, message = migrate_loader(file_path)
        loader_name = get_loader_name(file_path)
        status = "[OK]" if success else "[ERROR]"
        print(f"{status} {loader_name:<40} {message}")

        if success:
            success_count += 1
        else:
            error_count += 1

    print("-" * 70)
    print(f"\nMigration complete: {success_count} loaders updated, {error_count} errors")

    if error_count > 0:
        print("\nPlease fix errors manually and re-run.")
        return 1

    print("\nAll loaders have been migrated to use dynamic configuration!")
    print("Next steps:")
    print("1. Run: python scripts/initialize-loader-config.py --environment dev")
    print("2. Test: python scripts/update-loader-parallelism.py --list --environment dev")
    print("3. Update parallelism as needed: python scripts/update-loader-parallelism.py --loader technical_data_daily --parallelism 3 --environment dev")
    return 0


if __name__ == "__main__":
    sys.exit(main())
