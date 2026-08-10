"""Regression test: buy_sell_daily's completion-threshold denominator must respect the
stock_scores universe filter that main() applies before ever calling loader.run().

Bug (found 2026-08-10, real DB evidence): main() deliberately filters the active-symbol list
down to only symbols with a stock_scores row (data_unavailable = false) before running the
loader - documented, intentional behavior ("[UNIVERSE FILTER]"), since stock_scores only
covers ~4.7k of ~4.9k active symbols. But the completion check's `effective_universe` was
computed as min(price_symbols_available, tech_symbols_available) - raw price_daily/
technical_data_daily row counts for the date, entirely ignoring the stock_scores filter. That
made effective_universe (~4885) permanently larger than what the loader could ever process
(~4605, the filtered list), so symbols_processed/effective_universe capped out at ~94.25% -
just under the 95% threshold - and the loader was marked FAILED on every run even when it
processed ~100% of its real, intentionally-filtered universe. Live-verified fix: after
bounding effective_universe by len(symbols), a run that processed 4884/4885 requested symbols
reported COMPLETED at 102.4% (effective universe correctly dropped to the smaller of the three
inputs) instead of FAILED at 94.25%.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "loaders" / "load_buy_sell_daily.py"


def _find_effective_universe_assignment():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    assigns = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "effective_universe"
        # Only the completion-threshold computation, not the min_threshold's own
        # "effective_universe >= 4500" comparison further below.
        and isinstance(node.value, ast.Call)
    ]
    assert len(assigns) == 1, f"Expected exactly one effective_universe assignment, found {len(assigns)}"
    return assigns[0]


def test_effective_universe_is_bounded_by_actual_symbols_list():
    assign = _find_effective_universe_assignment()
    expr = ast.unparse(assign.value)
    assert "len(symbols)" in expr, (
        "effective_universe must be bounded by len(symbols) - the actual, already "
        "stock_scores-filtered population main() passed to loader.run() - not just raw "
        "price_daily/technical_data_daily row counts. Otherwise the denominator can exceed "
        "what the loader was ever asked to process, permanently capping completion_pct below "
        "the threshold regardless of real performance."
    )


def test_effective_universe_still_considers_upstream_coverage():
    """Preserves the original intent: still bounded by real price/technical data availability."""
    assign = _find_effective_universe_assignment()
    expr = ast.unparse(assign.value)
    assert "price_symbols_available" in expr
    assert "tech_symbols_available" in expr
