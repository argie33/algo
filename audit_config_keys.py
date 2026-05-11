#!/usr/bin/env python3
"""
Configuration Key Audit - Find all config.get() calls and verify they exist in AlgoConfig.DEFAULTS

Usage:
  python3 audit_config_keys.py          # Audit all .py files
  python3 audit_config_keys.py file.py  # Audit specific file
"""

import re
import sys
from pathlib import Path
from algo_config import AlgoConfig

# Pattern to find config.get() calls
CONFIG_GET_PATTERN = re.compile(
    r"(?:self\.)?config\.get\s*\(\s*['\"](\w+)['\"](?:\s*,\s*(.+?))?\)",
    re.MULTILINE
)

def get_hardcoded_config_keys():
    """Extract all configuration keys used in code"""
    keys_found = {}

    # Scan all Python files
    for filepath in Path(".").glob("algo*.py"):
        if filepath.name == "algo_config.py":
            continue

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

            for match in CONFIG_GET_PATTERN.finditer(content):
                key = match.group(1)
                default_value = match.group(2) or "None"

                if key not in keys_found:
                    keys_found[key] = {
                        "files": [],
                        "default_in_code": default_value,
                    }

                line_num = content[:match.start()].count("\n") + 1
                keys_found[key]["files"].append(f"{filepath.name}:{line_num}")

    return keys_found

def main():
    # Get all config keys from AlgoConfig.DEFAULTS
    defaults = AlgoConfig.DEFAULTS
    known_keys = {k: v for k, v in defaults.items()}

    # Get all keys used in code
    code_keys = get_hardcoded_config_keys()

    # Find missing and extra keys
    missing_keys = {}
    extra_keys = {}

    print("\n" + "="*80)
    print("CONFIGURATION KEY AUDIT")
    print("="*80)

    for key in code_keys:
        if key not in known_keys:
            missing_keys[key] = code_keys[key]

    for key in known_keys:
        if key not in code_keys:
            extra_keys[key] = known_keys[key]

    # Report missing keys
    if missing_keys:
        print("\n❌ MISSING FROM AlgoConfig.DEFAULTS:")
        print("-" * 80)
        for key, info in sorted(missing_keys.items()):
            print(f"\n  Key: {key}")
            print(f"    Default in code: {info['default_in_code']}")
            print(f"    Used in: {', '.join(info['files'][:3])}")
            if len(info["files"]) > 3:
                print(f"             ... and {len(info['files']) - 3} more")
    else:
        print("\n✅ No missing keys - all config.get() calls have defaults")

    # Report extra keys (defined but unused)
    if extra_keys:
        print("\n⚠️  DEFINED BUT UNUSED:")
        print("-" * 80)
        for key, (value, _) in sorted(extra_keys.items()):
            print(f"  {key}: {value}")
    else:
        print("\n✅ No unused config keys")

    # Summary
    print("\n" + "="*80)
    print(f"SUMMARY:")
    print(f"  Keys in code:              {len(code_keys)}")
    print(f"  Keys in AlgoConfig.DEFAULTS: {len(known_keys)}")
    print(f"  Missing from defaults:     {len(missing_keys)}")
    print(f"  Defined but unused:        {len(extra_keys)}")
    print("="*80 + "\n")

    # Return error if missing keys found
    if missing_keys:
        print("ACTION REQUIRED: Add missing keys to AlgoConfig.DEFAULTS")
        return 1
    else:
        print("✅ Configuration audit PASSED")
        return 0

if __name__ == "__main__":
    sys.exit(main())
