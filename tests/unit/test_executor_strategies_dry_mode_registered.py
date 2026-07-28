"""Regression test: create_execution_mode_strategy() must register a "dry" strategy.

Found live 2026-07-28, same discovery/bug class as execution_mode="live"/"review" gaps in
orchestrator.py and lambda_function.py (see test_orchestrator_execution_mode_live_rejected.py):
algo/infrastructure/config/execution_config.py's get_execution_mode() has always advertised
"dry" as one of only 4 valid execution_mode values (paper|dry|review|auto), and
order_manager.py/executor.py both already have real "dry" branches that treat it identically
to "paper" (LOCAL-only order, never reaches Alpaca) - but create_execution_mode_strategy(),
the factory TradeExecutor.__init__ calls unconditionally before any of that code runs, only
ever registered paper/review/auto. A config actually set to "dry" would crash immediately
inside TradeExecutor.__init__ with ValueError, before its already-correct "dry" handling in
_submit_and_validate_order was ever reached.
"""

from algo.trading.executor_strategies import create_execution_mode_strategy


class TestDryExecutionModeRegistered:
    def test_dry_mode_creates_a_strategy_without_raising(self):
        strategy = create_execution_mode_strategy("dry")
        assert strategy.name == "dry"

    def test_dry_mode_behaves_like_paper_for_routing(self):
        strategy = create_execution_mode_strategy("dry")
        assert strategy.resolve_paper_mode() is True
        assert "paper-api.alpaca.markets" in strategy.resolve_base_url(None)
