#!/usr/bin/env python3
"""Apply comprehensive error standardization fixes across all phases.

Phases:
- Phase 2: API Routes (already done via fix_phase2_routes.py)
- Phase 3: Loaders (add LoaderErrorContext imports)
- Phase 4: Database Operations (add transactional pattern hints)
- Phase 5: External APIs (add timeout to all requests.get/post)
- Phase 6: Utilities (add centralized error classification)
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

def apply_phase3_loaders():
    """Phase 3: Add LoaderErrorContext imports and pattern hints."""
    loaders_dir = REPO_ROOT / "loaders"
    files = sorted([f for f in loaders_dir.glob("load_*.py") if f.exists()])

    changes = 0
    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            original = f.read()

        modified = original

        # Add LoaderErrorContext import if using try/except
        if "try:" in modified and "LoaderErrorContext" not in modified:
            if "from utils" in modified:
                # Find last utils import and add after it
                lines = modified.split("\n")
                import_end = 0
                for i, line in enumerate(lines):
                    if line.startswith("from utils"):
                        import_end = i
                lines.insert(
                    import_end + 1, "from utils.contexts import LoaderErrorContext"
                )
                modified = "\n".join(lines)
                changes += 1

        if modified != original:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(modified)

    return changes

def apply_phase4_database_ops():
    """Phase 4: Add transactional imports for multi-statement operations."""
    algo_dir = REPO_ROOT / "algo"
    files = list(algo_dir.glob("*.py"))

    changes = 0
    for filepath in files:
        if any(x in filepath.name for x in ["signal", "metrics", "config"]):
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            original = f.read()

        modified = original

        # Look for multi-statement operations
        if original.count("cur.execute(") > 1 and "try:" in original:
            # Add transactional decorator import
            if "from utils.decorators import" not in modified:
                if "from utils" in modified:
                    lines = modified.split("\n")
                    for i, line in enumerate(lines):
                        if line.startswith("from utils"):
                            lines.insert(
                                i + 1, "from utils.decorators import transactional"
                            )
                            modified = "\n".join(lines)
                            break
                    changes += 1

        if modified != original:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(modified)

    return changes

def apply_phase5_external_apis():
    """Phase 5: Ensure all requests.get/post have timeout parameter."""
    files_to_check = []
    files_to_check.extend((REPO_ROOT / "loaders").glob("load_*.py"))
    files_to_check.extend((REPO_ROOT / "utils" / "external").glob("*.py"))

    changes = 0
    for filepath in files_to_check:
        if not filepath.exists():
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            original = f.read()

        modified = original

        # Add timeout to requests.get/post calls that don't have it
        # Pattern: requests.get(url) → requests.get(url, timeout=10)
        pattern = r"requests\.(get|post)\(([^,\)]+)\)(?!.*timeout)"
        if re.search(pattern, modified):

            def add_timeout(match):
                method = match.group(1)
                args = match.group(2)
                return f"requests.{method}({args}, timeout=10)"

            modified = re.sub(pattern, add_timeout, modified)
            changes += len(re.findall(pattern, original))

        # Add external_api_handler decorator import if needed
        if "requests." in modified and "@external_api_handler" not in modified:
            if "from utils.decorators import" not in modified:
                if "from utils" in modified:
                    lines = modified.split("\n")
                    for i, line in enumerate(lines):
                        if line.startswith("from utils"):
                            lines.insert(
                                i + 1,
                                "from utils.decorators import external_api_handler",
                            )
                            modified = "\n".join(lines)
                            break

        if modified != original:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(modified)

    return changes

def apply_phase6_utilities():
    """Phase 6: Add centralized error classification to utility modules."""
    utils_dir = REPO_ROOT / "utils"
    config_dir = REPO_ROOT / "config"

    all_files = list(utils_dir.glob("*.py")) + list(config_dir.glob("*.py"))

    changes = 0
    for filepath in all_files:
        with open(filepath, "r", encoding="utf-8") as f:
            original = f.read()

        modified = original

        # Add error_handlers import if module has try/except
        if "try:" in modified and "except" in modified:
            if (
                "from utils.error_handlers import" not in modified
                and "classify_exception" not in modified
            ):
                # Check if it should use error classification
                if "except Exception" in modified:
                    lines = modified.split("\n")
                    import_added = False
                    for i, line in enumerate(lines):
                        if line.startswith("from") or line.startswith("import"):
                            if not import_added:
                                lines.insert(
                                    i + 1,
                                    "from utils.error_handlers import classify_exception, make_error_response",
                                )
                                import_added = True
                                changes += 1
                                break

                    if import_added:
                        modified = "\n".join(lines)

        if modified != original:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(modified)

    return changes

def main():
    """Apply all phase fixes."""
    print("\n" + "=" * 70)
    print("APPLYING ALL PHASE FIXES")
    print("=" * 70 + "\n")

    print("Phase 3: Loaders - adding LoaderErrorContext imports...")
    p3_changes = apply_phase3_loaders()
    print(f"  Applied {p3_changes} import additions\n")

    print("Phase 4: Database Operations - adding transactional decorator imports...")
    p4_changes = apply_phase4_database_ops()
    print(f"  Applied {p4_changes} import additions\n")

    print("Phase 5: External APIs - adding timeout parameters...")
    p5_changes = apply_phase5_external_apis()
    print(f"  Applied {p5_changes} timeout additions\n")

    print("Phase 6: Utilities - adding error classification imports...")
    p6_changes = apply_phase6_utilities()
    print(f"  Applied {p6_changes} import additions\n")

    total = p3_changes + p4_changes + p5_changes + p6_changes
    print("=" * 70)
    print(f"Total changes: {total}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
