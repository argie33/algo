"""Regression test: trend_analysis must be invoked as `python loaders/load_trend_analysis.py`
directly, never routed through scripts/run_loader.py's generic class-lookup path.

Bug (found 2026-08-10, live-reproduced): load_trend_analysis.py is a plain function-based
module (run()/main() functions, no OptimalLoader subclass or any class at all).
run_loader.py's get_loader_class_for_file() requires finding a loader CLASS before it will
call run_loader_generic() - whose own "trend_template_data" special-case branch is therefore
dead code, unreachable. `python scripts/run_loader.py load_trend_analysis.py` exits 1
immediately with "Could not find OptimalLoader subclass" / "Could not load class". Since
"trend_analysis" wasn't special-cased for direct invocation (unlike financial_statements/
buy_sell/prices, the same bug class found earlier the same session), every local "morning"
pipeline run's trend_analysis step always failed outright - and since a failed loader aborts
run_pipeline(), this also silently blocked sector_industry (the next "morning" step) from
ever running locally. Root cause of trend_template_data sitting stuck in RUNNING for 6+ hours
with no owning process alive. `python loaders/load_trend_analysis.py` directly (production's
real entrypoint) works fine - live-verified: completed in 6s, RUNNING -> COMPLETED.
"""

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_run_loader_py_cannot_find_a_class_for_trend_analysis():
    """Documents the underlying brokenness this fix routes around - if this ever starts
    passing (e.g. load_trend_analysis.py gains a real loader class), the direct-invocation
    special-case below becomes unnecessary, not silently wrong."""
    import scripts.run_loader as run_loader_module

    assert run_loader_module.get_loader_class_for_file("load_trend_analysis.py") is None


def test_local_loader_scheduler_invokes_trend_analysis_directly():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert "trend_analysis" in module.PIPELINES["morning"]

    source = (REPO_ROOT / "scripts" / "local_loader_scheduler.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    direct_invocation_loaders = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "loader":
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    direct_invocation_loaders.add(comparator.value)

    assert "trend_analysis" in direct_invocation_loaders, (
        "trend_analysis must be special-cased for direct module invocation "
        "(loaders/load_trend_analysis.py), not routed through scripts/run_loader.py's "
        "generic class-lookup path, which cannot find a loader class for this module."
    )
