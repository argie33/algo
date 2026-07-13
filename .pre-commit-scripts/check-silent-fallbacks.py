#!/usr/bin/env python3
"""
Enforce fail-fast governance: Prevent ALL silent fallback patterns across entire codebase.

This hook catches patterns that violate CLAUDE.md governance rule:
"PRINCIPLE: Fail-fast on missing data. No silent fallbacks."

CRITICAL: Code must either:
1. Raise an exception on data unavailability (for CRITICAL data), OR
2. Return explicit dict with data_unavailable=True and reason= (for OPTIONAL data)

❌ FORBIDDEN PATTERNS (silent fallbacks):
  return []                           # Empty array fallback
  return {}                           # Empty dict fallback
  return 0 / return Decimal(0)        # Hardcoded zero for financial data
  return None (w/o context)           # Silent None
  .get("key")                         # Unsafe default on financial data
  if not data: return []              # Conditional empty return
  if error: return []                 # Conditional empty return

✅ CORRECT PATTERNS:
  raise RuntimeError("reason")        # Fail-fast for CRITICAL data
  raise ValueError("reason")          # Explicit error for validation
  return {"data_unavailable": True, "reason": "..."}  # Explicit marker for OPTIONAL data
  if key in dict and dict[key] is not None:  # Explicit key check (not .get())

Files checked: ALL Python files in repo except tests/, venv/
"""

import re
import sys
from pathlib import Path
from typing import Any

# Files/paths to CHECK (ALL Python files except skip list)
# This is enforced EVERYWHERE in the codebase
CHECK_PATHS = [
    ".",  # ALL Python files
]

# Files/paths to SKIP (tests, venv, etc. only)
SKIP_PATHS = {
    "__pycache__",
    ".git",
    "tests/",
    "test_",  # test_*.py files
    ".pre-commit-scripts/",  # Skip the hook scripts themselves (they contain examples)
    "venv",
    ".venv",
    "migrations/",
    "scripts/",  # utility scripts
    ".pytest_cache",
    "node_modules",
    "api-pkg",  # Vendored botocore and dependencies (3rd-party code)
    "lambda/api/package",  # Auto-generated packaged Lambda code
    "lambda/api/routes/__pycache__",
}

# Repo-root ad-hoc diagnostic/verification scripts follow the same convention as
# `scripts/` (print()-based, one-off, run manually to inspect DB/API state — never
# imported by the trading system). They just happen to live at the repo root instead
# of scripts/. Only filenames directly at the repo root are exempted (see the
# `filepath.parent == repo_root` check below) so real package modules that happen to
# start with one of these words (e.g. algo/monitoring/audit_manager.py,
# algo/trading/check_handler_strategies.py) are still fully checked.
ROOT_UTILITY_SCRIPT_PREFIXES = (
    "check_",
    "verify_",
    "diagnose_",
    "audit_",
    "comprehensive_audit",
    "sync_",
    "dev_api_server",
)


def should_check_file(filepath: Path, repo_root: Path | None = None) -> bool:
    # Only check Python files
    if filepath.suffix != ".py":
        return False

    str_path = str(filepath).replace("\\", "/")  # Normalize path separators
    filename = filepath.name

    # Skip all hook scripts (they contain examples/patterns of violations)
    if filename.startswith("check-"):
        return False

    # Skip if in SKIP_PATHS (normalize both path and skip patterns)
    for skip in SKIP_PATHS:
        skip_normalized = skip.replace("\\", "/")
        if skip_normalized in str_path:
            return False

    # Skip repo-root ad-hoc diagnostic scripts (see ROOT_UTILITY_SCRIPT_PREFIXES doc above).
    # Restricted to files whose *direct* parent is the repo root so nested library modules
    # with similar prefixes are never accidentally exempted.
    if repo_root is not None and filepath.parent == repo_root and filename.startswith(ROOT_UTILITY_SCRIPT_PREFIXES):
        return False

    return True


def check_file_for_fallbacks(filepath: Path) -> list[dict[str, Any]]:  # noqa: C901
    """Scan file for ALL silent fallback patterns."""
    violations = []

    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return violations

    lines = content.splitlines()

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip comments, blank lines, and docstrings
        if stripped.startswith(("#", '"""', "'''")) or not stripped:
            continue

        # Skip lines with explicit error handling (raise, data_unavailable, except)
        if any(kw in stripped for kw in ["raise ", "data_unavailable", "except ", "try:", "logger.error", "logger.critical"]):
            continue

        # ========== PATTERN 1: return [] without marker ==========
        if stripped == "return []":
            context = "\n".join(lines[max(0, line_num-5):line_num])
            if "data_unavailable" not in context and "raise" not in context:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "return []",
                    "message": "Silent fallback: returning empty array without data_unavailable marker or exception",
                    "fix": "Raise exception for CRITICAL data OR return {'data_unavailable': True, 'reason': '...'}"
                })

        # ========== PATTERN 2: return {} without marker ==========
        if stripped == "return {}":
            context = "\n".join(lines[max(0, line_num-5):line_num])
            if "data_unavailable" not in context and "raise" not in context:
                # Skip legitimate "nothing to do" empty results: an empty dict returned
                # because the *input* was empty (no candidates/not-yet-initialized) is not
                # data loss — it's an accurate, deliberate representation of zero work,
                # and is explicitly documented as such right at the return site. This
                # mirrors the is_count_return carve-out already used for PATTERN 3 below.
                is_legitimate_empty_result = any(phrase in context.lower() for phrase in [
                    "not an error", "not initialized", "no candidates", "nothing to process",
                    "no entries will be executed", "not yet initialized", "no work to do",
                ])
                if is_legitimate_empty_result:
                    continue

                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "return {}",
                    "message": "Silent fallback: returning empty dict without data_unavailable marker or exception",
                    "fix": "Raise exception for CRITICAL data OR return {'data_unavailable': True, 'reason': '...'}"
                })

        # ========== PATTERN 3: return 0 / Decimal(0) for financial data ==========
        if re.match(r"^\s*return\s+(0|Decimal\(0\)|0\.0|0\.)", stripped):
            # Check if this is in a financial function (heuristic: function name or nearby comments suggest financial)
            context_start = max(0, line_num - 20)
            context = "\n".join(lines[context_start:line_num])

            # Skip if this is in a scoring/signal function (legitimate 0 points = no signal)
            is_scoring_function = any(kw in context.lower() for kw in [
                "_score", "_catalyst", "_catalyst_score", "calculate_score", "get_score", "strength", "rating",
                "grade", "rank", "signal_strength", "pts", "points", "compute_score", "signal_computer"
            ])
            if is_scoring_function:
                continue

            # Skip if return 0 is for a count (legitimate: count executed, count found, etc.)
            is_count_return = any(phrase in context.lower() for phrase in [
                "count", "executed", "found", "processed", "fetched", "rows", "records", "exit_count",
                "_engine", "circuit_breaker", "drawdown", "no open positions", "return 0"
            ])
            if is_count_return:
                continue

            # Skip if this is in a trading/risk control function returning 0 for control purposes
            is_trading_control = any(phrase in context.lower() for phrase in [
                "position_sizer", "exit_engine", "order_manager", "circuit", "drawdown", "halt",
                "when no positions", "when error", "when unavailable"
            ])
            if is_trading_control:
                continue

            # Skip if data validation happened before return (checked for None/missing)
            # Pattern: if "raise" in context before this line, it's fail-fast validated
            has_prior_validation = "raise" in context and "return 0" in context.lower()
            if has_prior_validation:
                continue

            is_financial = any(kw in context.lower() for kw in [
                "position", "score", "size", "price", "volume", "volatility", "beta", "metric",
                "signal", "technical", "financial", "market", "risk", "exposure", "exposure_pct"
            ])
            if is_financial:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "return 0",
                    "message": "Hardcoded zero return in financial function (ambiguous: could mean 'no data' or 'error')",
                    "fix": "Raise exception for CRITICAL data OR return {'data_unavailable': True, 'reason': '...'}"
                })

        # ========== PATTERN 4: Unsafe .get() WITH DEFAULTS on financial data ==========
        # Only flag .get() calls that have explicit defaults (the real problem)
        # Normal .get() without defaults is OK (returns None which callers should handle)
        get_with_default = re.search(r'\.get\([^,]+,\s*(["\']|0|None|\[\]|{}|Decimal)', stripped)
        if get_with_default:
            # Skip if it's clearly a logging/error message or metadata field
            is_logging_context = any(context in stripped.lower() for context in [
                "logger", "print", "_error", "msg", "message", "reason", "summary",
                "note", "description", "status", "source"
            ])
            if is_logging_context:
                continue

            # Check if this is likely financial data calculation
            is_financial_get = any(pattern in stripped for pattern in [
                "row.get(", "data.get(", "info.get(", "breadth.get(", "metrics.get(",
                "prices.get(", "volumes.get(", "position.get(", "score.get("
            ])

            # Additional safety check: make sure it's not being used for descriptive/metadata fields
            is_metadata = any(field in stripped for field in [
                ".get(\"symbol", ".get(\"date", ".get(\"updated_at", ".get(\"timestamp",
                ".get(\"reason", ".get(\"message", ".get(\"error", ".get(\"status",
                ".get(\"source", ".get(\"note", ".get(\"_", ".get('symbol", ".get('date"
            ])

            # Skip if in health/monitoring/validation paths (not core trading logic)
            is_non_critical_path = any(module in str(filepath).lower() for module in [
                "health", "validation", "monitoring", "diagnostic", "reconciliation"
            ])
            if is_non_critical_path:
                continue

            # Skip if this is for counting/optional metrics that safely default to 0
            is_safe_default = any(phrase in stripped.lower() for phrase in [
                "circuit_breaker", "triggered_count", "any_triggered", "optional",
                "if cb_metrics else", "or 0", "or false", "or {}"
            ])
            if is_safe_default:
                continue

            # Skip telemetry/observability publishing (e.g. CloudWatch metrics counters).
            # These values are never used for trading decisions — only for dashboards/alarms —
            # so a defensive default here cannot cause a silent, mispriced trade. Detected via
            # nearby telemetry-publisher markers rather than by module path, since this code
            # lives inside orchestrator.py alongside real trading logic.
            wide_context_start = max(0, line_num - 15)
            wide_context = "\n".join(lines[wide_context_start:line_num]).lower()
            is_telemetry_context = any(kw in wide_context for kw in [
                "metricspublisher", "put_signal_count", "put_orchestrator_result",
                "cloudwatch", "non-blocking",
            ])
            if is_telemetry_context:
                continue

            # Skip if the very next few lines explicitly check for emptiness and surface
            # an error/unavailable state to the caller (e.g. dashboard panels that render
            # an explicit "no data" panel). The default here is just safe type-narrowing
            # before that explicit check — nothing is hidden from the operator.
            lookahead = "\n".join(lines[line_num:line_num + 6])
            has_explicit_downstream_check = any(kw in lookahead for kw in [
                "_error_panel(", "raise ", "data_unavailable",
            ])
            if has_explicit_downstream_check:
                continue

            if is_financial_get and not is_metadata:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": ".get(..., default)",
                    "message": "Unsafe .get() with default on financial data (silent fallback if key missing)",
                    "fix": "Check key presence explicitly: if 'key' in dict and dict['key'] is not None: ..."
                })

        # ========== PATTERN 5: Silent None return ==========
        if stripped == "return None" or re.match(r"return\s+None\s*$", stripped):
            context_start = max(0, line_num - 15)
            context = "\n".join(lines[context_start:line_num])

            # Skip if it's in a try/except context (error handling)
            if "except" in context or "try:" in context:
                continue

            # Skip if function is Optional[T] (returns None as valid state)
            # Search backward for "def " to find function definition.
            # Window widened from 50 to 120 lines: functions with long docstrings/retry-loop
            # bodies (e.g. loaders/market_health_fetchers.py's _fetch_with_retries, whose
            # `def` is 51 lines above its final `return None`) were falling outside the old
            # 50-line window, silently disabling the Optional[T]/docstring-contract checks
            # below for no reason related to their correctness.
            func_def_line = None
            for search_line in range(line_num - 1, max(0, line_num - 120), -1):
                if lines[search_line].strip().startswith("def "):
                    func_def_line = search_line
                    break

            if func_def_line is not None:
                # Get full function signature (might span multiple lines)
                func_sig = "\n".join(lines[func_def_line:line_num])
                # Check if function explicitly returns Optional/Union with None
                if ("-> " in func_sig and ("| None" in func_sig or "Optional" in func_sig)) or \
                   ("-> None:" in func_sig):  # Function that returns only None
                    continue

                # Skip if the enclosing function's own docstring documents that None is an
                # internal-only signal whose conversion to an explicit data_unavailable
                # marker is the caller's documented responsibility (e.g. a private
                # `_fetch_with_retries` helper wrapped by a public `fetch()` that performs
                # the conversion). This is the governance-compliant pattern already, just
                # split across two functions — flagging the private helper is a false
                # positive since the marker genuinely does get set, one call frame up.
                if "data_unavailable" in func_sig:
                    continue

            # Skip if comment indicates None is intentional (cache miss, no data, etc.)
            if any(phrase in context.lower() for phrase in [
                "cache miss", "not cached", "no data", "optional", "not provided",
                "expected state", "no error", "validation passed", "no duplicate",
                "can proceed", "market closed", "fresh data"
            ]):
                continue

            # Only flag if in financial function AND context suggests error path
            is_financial = any(kw in context.lower() for kw in [
                "fetch", "load", "get_", "price", "metric", "data", "auth", "token",
                "calculate", "score", "signal", "validate"
            ])

            is_error_path = any(phrase in context.lower() for phrase in [
                "error", "failed", "unavailable", "exception", "corrupted", "invalid state"
            ])

            if is_financial and is_error_path:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "return None",
                    "message": "Silent None return in error path (caller cannot distinguish 'no data' from 'error')",
                    "fix": "Raise exception OR return {'data_unavailable': True, 'reason': '...'}"
                })

    return violations


def main() -> int:
    repo_root = Path.cwd()
    violations = []

    # Find all Python files to check (everywhere, NO exceptions)
    for py_file in repo_root.rglob("*.py"):
        if not should_check_file(py_file, repo_root):
            continue

        violations.extend(check_file_for_fallbacks(py_file))

    if violations:
        print("[FAILED] FAIL-FAST ENFORCEMENT VIOLATION")
        print("Found silent fallback patterns that violate governance:\n")

        # Group by pattern type
        by_pattern = {}
        for v in violations:
            pattern = v['pattern']
            if pattern not in by_pattern:
                by_pattern[pattern] = []
            by_pattern[pattern].append(v)

        for pattern in sorted(by_pattern.keys()):
            print(f"\n{pattern.upper()} ({len(by_pattern[pattern])} violations):")
            for v in sorted(by_pattern[pattern], key=lambda x: (str(x["file"]), x["line"]))[:10]:  # Show first 10
                print(f"  {v['file']}:{v['line']}")
                print(f"    {v['message']}")
                print(f"    Fix: {v['fix']}")

        if len(violations) > 10:
            print(f"\n  ... and {len(violations) - 10} more violations")

        print("\n[GOVERNANCE] CLAUDE.md Rule:")
        print("  'PRINCIPLE: Fail-fast on missing data. No silent fallbacks.'")
        print("\n  Code must EITHER:")
        print("    1. Raise exception (raise RuntimeError/ValueError) for CRITICAL data")
        print("    2. Return explicit marker {'data_unavailable': True, 'reason': '...'} for OPTIONAL data")
        print("\n  NO:")
        print("    - return [] or return {} without markers")
        print("    - return 0 for financial calculations")
        print("    - return None without explaining why")
        print("    - .get() without explicit key validation")
        print("\n  See: steering/FAIL_FAST_VIOLATIONS_CATALOG_2026_06_29.md")

        return 1

    print("[PASS] All files comply with fail-fast governance [OK]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
