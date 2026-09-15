"""Regression test: /api/scores' minMarketCap eligibility filter.

Added 2026-08-31 (/goal session, "make sure the results make sense" investigation). The
composite_score-sorted default view of this endpoint had no investability screen at all -
live-verified the top of the ranking was dominated by nano/micro-caps (SOGP $37.6M market cap,
COHN $19.6M, several under $200K/day dollar volume) since Size was retired as a scoring pillar
with nothing left to offset small-cap-favoring percentile scoring. A liquidity gate already
exists for real trade execution (algo/risk/liquidity_checks.py) but only fires at Phase 8 entry
time, invisible to anyone just browsing this list. `minMarketCap` was originally shipped as an
opt-in query param (no behavior change when omitted) - nobody actually called it, so the
unfiltered nano-cap-dominated leaderboard remained the default anyone actually saw.

DEFAULT CHANGED 2026-09-12 (/goal: industry-factor-list alignment session, live leaderboard
comparison against real Quality/Value/Momentum indices) to $300M when the param is omitted -
$300M is the standard micro-cap/small-cap boundary widely used by index providers (Russell
2000's practical lower bound), not a fitted or invented number, and matches the threshold
already live on the TUI dashboard's own /api/algo/scores endpoint (2026-09-07).

DEFAULT BRIEFLY RAISED 300M -> 2B THEN REVERTED TO 300M (2026-09-15, same-day follow-up /goal
session): verified against 7 real PASSIVE factor ETFs (iShares MTUM/QUAL/VLUE/USMV/IVW, Goldman
GSLC, iShares LRGF - zero holdings under $2B, every one), but explicit user direction is this
system should resemble IBD-style CAN SLIM growth stock-picking, not a passive large-cap factor
ETF. Checked IBD's own published methodology directly: the IBD 50 explicitly spans small/mid/
large-cap companies by design and has NO market-cap floor at all - its real screens are
liquidity-based (minimum share price, minimum average daily volume), not a market-cap dollar
threshold. The 300M revert stopped short of that finding's own conclusion.

MARKET-CAP FLOOR REMOVED AS THE DEFAULT (2026-09-15, same-day second follow-up, user
correction: "we were supposed to remove the cap floor in lieu of the liquidity"). A cap floor
of ANY size (2B or 300M) is the wrong tool for an IBD-style system - not just the wrong number.
The IBD-style liquidity screen (min share price + min average dollar volume, see
TestIbdStyleLiquidityScreen below) is now the sole default investability floor;
`minMarketCap` is opt-in-only (`?minMarketCap=<n>`) for a caller that genuinely wants a
large/mid-cap-only view. `?minMarketCap=0` disables the liquidity screen too, for callers
who want the fully unfiltered universe. See lambda/api/routes/scores.py's own updated comment
for the full evidence trail.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _mock_cursor(rows):
    cursor = Mock()
    cursor.fetchone.return_value = [len(rows)]
    cursor.fetchall.return_value = rows
    return cursor


class TestMinMarketCapLiquidityFloor:
    def test_omitted_param_applies_no_market_cap_floor(self):
        # 2026-09-15 correction: market_cap is no longer defaulted to any value - only the
        # liquidity screen (TestIbdStyleLiquidityScreen below) is on by default.
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(cursor, "/api/scores", "GET", {})

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert not any("JOIN value_metrics mcf" in sql for sql in executed_queries)
        assert not any("mcf.market_cap >= %s" in sql for sql in executed_queries)

        all_params = [p for c in cursor.execute.call_args_list for p in (c.args[1] if len(c.args) > 1 else []) or []]
        assert 300_000_000.0 not in all_params

    def test_explicit_zero_disables_the_liquidity_floor_and_applies_no_cap_floor(self):
        # ?minMarketCap=0 is the escape hatch back to the raw unfiltered universe (internal
        # tooling, tests) - disables the liquidity screen and never applies a cap floor either.
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(cursor, "/api/scores", "GET", {"minMarketCap": "0"})

        # The market_cap join still fires (mcf.market_cap >= 0 is a no-op filter) since the
        # caller explicitly passed a value - but the liquidity screen, the actual default
        # investability floor, is disabled.
        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert not any("liq.symbol = sc.symbol" in sql for sql in executed_queries)

        all_params = [p for c in cursor.execute.call_args_list for p in (c.args[1] if len(c.args) > 1 else []) or []]
        assert 300_000_000.0 not in all_params
        assert 0.0 in all_params

    def test_min_market_cap_adds_join_and_filter_with_param(self):
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(cursor, "/api/scores", "GET", {"minMarketCap": "500000000"})

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("JOIN value_metrics mcf" in sql for sql in executed_queries)
        assert any("mcf.market_cap >= %s" in sql for sql in executed_queries)

        all_params = [p for c in cursor.execute.call_args_list for p in (c.args[1] if len(c.args) > 1 else []) or []]
        assert 500000000.0 in all_params

    def test_min_market_cap_ignored_for_single_symbol_lookup(self):
        # A specific symbol lookup must always work regardless of its market cap - the
        # investability screen is only meant to shape the ranked/browse list.
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(cursor, "/api/scores", "GET", {"symbol": "SOGP", "minMarketCap": "300000000"})

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert not any("JOIN value_metrics mcf" in sql for sql in executed_queries)

    def test_non_numeric_min_market_cap_rejected(self):
        from routes.scores import handle

        cursor = _mock_cursor([])
        response = handle(cursor, "/api/scores", "GET", {"minMarketCap": "not-a-number"})

        assert response["statusCode"] == 400


class TestIbdStyleLiquidityScreen:
    """2026-09-15: IBD's real screens are liquidity-based (min share price, min average daily
    volume), not a market-cap dollar threshold - see this module's own DEFAULT BRIEFLY RAISED
    docstring section. This adds that screen alongside (not instead of) the $300M floor, tied
    to the same on/off toggle, reusing algo_config's min_stock_price/min_adv_dollars - the same
    thresholds already governing real trade execution (algo/risk/liquidity_checks.py)."""

    def test_default_floor_adds_liquidity_join_and_filters(self):
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(cursor, "/api/scores", "GET", {})

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("liq.symbol = sc.symbol" in sql for sql in executed_queries)
        assert any("liq.latest_close >= %s" in sql for sql in executed_queries)
        assert any("liq.avg_dollar_volume_20d >= %s" in sql for sql in executed_queries)

        all_params = [p for c in cursor.execute.call_args_list for p in (c.args[1] if len(c.args) > 1 else []) or []]
        # algo_config lookup returns no rows in this mock, so it falls back to the same
        # defaults already used elsewhere in this codebase (min_stock_price=5.0,
        # min_adv_dollars=500_000.0 - see algo/risk/liquidity_checks.py / algo_config).
        assert 5.0 in all_params
        assert 500_000.0 in all_params

    def test_explicit_zero_disables_the_liquidity_screen_too(self):
        # Both floors share the same on/off toggle - ?minMarketCap=0 must disable the
        # liquidity join exactly like it disables the market-cap join.
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(cursor, "/api/scores", "GET", {"minMarketCap": "0"})

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert not any("liq.symbol = sc.symbol" in sql for sql in executed_queries)

    def test_liquidity_screen_ignored_for_single_symbol_lookup(self):
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(cursor, "/api/scores", "GET", {"symbol": "SOGP", "minMarketCap": "300000000"})

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert not any("liq.symbol = sc.symbol" in sql for sql in executed_queries)

    def test_liquidity_screen_uses_configured_algo_config_thresholds(self):
        from routes.scores import handle

        cursor = _mock_cursor([])
        # fetchall is called twice: once for the algo_config lookup (this test's target),
        # once for the main paginated query's row set (count uses fetchone, not fetchall).
        cursor.fetchall.side_effect = [
            [("min_stock_price", "10.0"), ("min_adv_dollars", "750000")],
            [],
        ]
        handle(cursor, "/api/scores", "GET", {})

        all_params = [p for c in cursor.execute.call_args_list for p in (c.args[1] if len(c.args) > 1 else []) or []]
        assert 10.0 in all_params
        assert 750_000.0 in all_params
