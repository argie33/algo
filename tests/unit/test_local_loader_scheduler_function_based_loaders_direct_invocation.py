"""Regression test: EVERY loader whose module has no discoverable loader class must be
special-cased in local_loader_scheduler.py for direct module invocation.

scripts/run_loader.py's generic dispatch path requires get_loader_class_for_file() to find a
real loader class (OptimalLoader subclass, or a legacy class with "Loader" in its name) - for
a plain function-based module (run()/main() or load()/_load_impl() style, no class at all),
that lookup returns None and scripts/run_loader.py's main() exits 1 before ever reaching the
loader's real logic.

Found via a systematic sweep (2026-08-10) recommended by
[[local_scheduler_trend_analysis_bypass_4th_instance_20260810]]'s own memory note, after that
fix was found via a single stuck-loader incident: load_trend_analysis.py AND
load_economic_data.py both hit this - trend_analysis was the incident that surfaced the bug
class, economic was caught by checking every other LOADER_TABLES entry the same way instead
of waiting for its own incident. economic sits before naaim/aaii/dividends in the
"reference" pipeline, and run_pipeline() aborts on any loader failure - left unfixed, this
would have silently blocked those 3 from ever backfilling locally too.

This test makes the sweep permanent: any THIRD function-based loader added in the future
(or an existing class-based loader refactored away from a class) fails CI immediately
instead of waiting for a stuck-RUNNING incident to surface it.
"""

import ast
from pathlib import Path

import scripts.run_loader as run_loader_module
from loaders.loader_registry import LOADER_TABLES

REPO_ROOT = Path(__file__).resolve().parents[2]


def _direct_invocation_loaders() -> set:
    source = (REPO_ROOT / "scripts" / "local_loader_scheduler.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "loader":
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    names.add(comparator.value)
    return names


def _shorthand_for(loader_filename: str) -> str | None:
    from loaders.loader_registry import SHORTHAND_TO_FILENAME

    for shorthand, fname in SHORTHAND_TO_FILENAME.items():
        if fname == loader_filename:
            return shorthand
    return None


def test_sanity_get_loader_class_finds_a_class_based_loader():
    """Guards the test below against a broken get_loader_class_for_file() silently making
    every loader look function-based (which would make the real assertion vacuous)."""
    assert run_loader_module.get_loader_class_for_file("load_prices.py") is not None


def test_every_function_based_loader_is_directly_invoked():
    direct_invocation_loaders = _direct_invocation_loaders()
    unguarded = []
    for loader_filename in sorted(LOADER_TABLES.keys()):
        if run_loader_module.get_loader_class_for_file(loader_filename) is not None:
            continue  # class-based - the generic scripts/run_loader.py path works fine
        shorthand = _shorthand_for(loader_filename)
        if shorthand not in direct_invocation_loaders:
            unguarded.append((loader_filename, shorthand))

    assert not unguarded, (
        f"These loaders have no discoverable loader class, so scripts/run_loader.py's "
        f"generic path exits 1 immediately for them, but they're not special-cased for "
        f"direct module invocation in local_loader_scheduler.py: {unguarded}. Add an "
        f"`elif loader == \"<shorthand>\": cmd = [sys.executable, f\"loaders/{{loader_filename}}\"]` "
        f"branch, matching the trend_analysis/economic fix."
    )
