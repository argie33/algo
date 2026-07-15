#!/usr/bin/env python3
"""
Check for CRITICAL credential .get() patterns with default values.

Only flags ACTUAL CREDENTIALS (passwords, API keys, secrets) with defaults.
Intentional patterns (config names, optional flags) are excluded.

CRITICAL PATTERN: Never use .get() with defaults for passwords/API keys
❌ os.environ.get("DB_PASSWORD", "default_pass")
❌ secret.get("password", "")
✅ os.environ.get("DB_PASSWORD")  # Returns None, triggers explicit error handling
✅ os.environ.get("DB_PORT", "5432")  # OK: port is config, not a credential

This enforces the fail-fast credential pattern from CLAUDE.md.
"""

import re
import sys
from pathlib import Path

# CRITICAL CREDENTIALS ONLY: actual passwords, secret values, tokens, API keys
# These MUST fail-fast without defaults. Excludes:
# - Secret ARNs/references (e.g., DB_SECRET_ARN)
# - Secret names (e.g., DASHBOARD_SECRETS_NAME)
# - Config values that look like credentials but are optional
CRITICAL_PATTERNS = [
    r"^password$",  # Exact match: password
    r"^db_password$",  # Exact match: db_password
    r"^smtp_password$",  # Exact match: smtp_password
    r"^api_secret$",  # Exact match: api_secret
    r"^apca_api_secret",  # Alpaca API secret
    r"^private_key$",  # Exact match: private_key
]

# The regex looks for .get("name", "default") or .getenv("NAME", "default")
# We want to flag critical credential patterns with ANY default
GET_WITH_DEFAULT_PATTERN = re.compile(
    r'(?:\.get|getenv)\s*\(\s*["\']([^"\']+)["\']\s*,\s*(["\'].*?["\']|\d+|True|False)',
    re.IGNORECASE,
)

# Files/paths to skip entirely
SKIP_PATHS = {
    ".git",
    "__pycache__",
    "node_modules",
    "migrations",
    ".venv",
    "venv",
    "package/",  # Third-party packages
    "tests/",  # Test files
    ".pre-commit-scripts/",  # Don't check the hook itself
    "check_credential_defaults.py",  # Don't flag our own docstring examples
    "dev_server.py",  # Local dev server with intentional defaults for LOCAL_MODE
    "api-proxy-server.py",  # Local dev helper script
}


def is_critical_credential(var_name: str) -> bool:
    var_lower = var_name.lower()
    for pattern in CRITICAL_PATTERNS:
        if re.search(pattern, var_lower):
            return True
    return False


def check_file(filepath: Path) -> list[str]:
    violations = []

    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return violations

    for line_num, line in enumerate(content.splitlines(), 1):
        # Skip comments and docstrings
        if line.strip().startswith("#") or "❌" in line or "✅" in line:
            continue

        for match in GET_WITH_DEFAULT_PATTERN.finditer(line):
            var_name = match.group(1)
            default_value = match.group(2)

            # Only flag CRITICAL credentials with defaults
            if is_critical_credential(var_name):
                violations.append(
                    f"{filepath}:{line_num}: critical credential '{var_name}' has default {default_value} "
                    f"- must fail-fast with no default"
                )

    return violations


def main() -> int:
    """Scan Python files for critical credential .get() patterns with defaults."""
    repo_root = Path.cwd()
    violations = []

    # Find all Python files
    for py_file in repo_root.rglob("*.py"):
        # Skip excluded paths
        skip_file = False
        for skip_pattern in SKIP_PATHS:
            if skip_pattern in str(py_file):
                skip_file = True
                break
        if skip_file:
            continue

        violations.extend(check_file(py_file))

    if violations:
        print("[FAILED] CREDENTIAL VALIDATION FAILED")
        print("Found critical credentials with default values (fail-fast rule):\n")
        for violation in sorted(violations):
            print(f"  {violation}")
        print(
            "\n[FIX] Remove defaults from critical credential .get() calls.\n"
            "Passwords, API keys, and tokens must fail-fast without defaults."
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
