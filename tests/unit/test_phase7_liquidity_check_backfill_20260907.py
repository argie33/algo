#!/usr/bin/env python3
"""Regression test: Phase 7's `_run_liquidity_checks` must backfill from candidates ranked
below the top LIQUIDITY_CHECK_LIMIT when candidates within that top slice fail liquidity,
instead of just accepting a shrunk candidate pool.

Root cause (2026-09-07, goal session: leaderboard/scoring audit): `_run_liquidity_checks` used
to take a single fixed slice `quality_filtered[:LIQUIDITY_CHECK_LIMIT]` and never looked
further down the composite_score-ranked list - any candidate in that slice failing liquidity
was a wasted slot, never backfilled from a liquid candidate ranked #21+. Live-confirmed same
day: 4 of the live top-20-by-composite_score (CIG.C $9.5K/day, JFIN $126K/day, SGU $234K/day,
XYF $334K/day 20-day dollar volume) were all below algo_config.min_adv_dollars ($500K) and
therefore guaranteed to fail liquidity - the real daily candidate pool was silently 16, not 20,
on a day like that, even though liquid candidates ranked #21+ existed and were never checked.
"""

from datetime import date
from unittest.mock import patch

from algo.orchestrator.phase7_run_steps import _run_liquidity_checks
from algo.orchestrator.validation_thresholds import LIQUIDITY_CHECK_LIMIT, MAX_LIQUIDITY_CANDIDATES_CONSIDERED


def _candidates(n: int) -> list[dict]:
    # composite_score descending, matching the real ranked-list shape this function receives.
    return [{"symbol": f"SYM{i:03d}", "composite_score": 100.0 - i} for i in range(n)]


def _fake_liquidity_check(illiquid_symbols: set[str]):
    def _check(candidate: dict, _run_date: date, _config: dict | None) -> tuple[dict, bool]:
        return candidate, candidate["symbol"] not in illiquid_symbols

    return _check


class TestLiquidityCheckBackfill:
    def test_backfills_from_below_the_limit_when_top_slice_has_failures(self):
        """4 of the top 20 fail liquidity (the FBRX/CIG.C-shaped case) - must pull in 4 more
        candidates from ranks 21-24 to still return LIQUIDITY_CHECK_LIMIT passing candidates,
        not just accept a shrunk pool of 16."""
        candidates = _candidates(40)
        illiquid = {"SYM000", "SYM005", "SYM010", "SYM015"}  # 4 failures inside the top 20

        with patch(
            "algo.orchestrator.phase7_signal_generation._check_liquidity_parallel",
            side_effect=_fake_liquidity_check(illiquid),
        ):
            liq_passed, liq_checked = _run_liquidity_checks(candidates, date(2026, 9, 7), config={})

        # Batches are LIQUIDITY_CHECK_LIMIT-sized, so falling short within the first batch
        # pulls in the WHOLE next batch (indices 20-39), not just the exact shortfall - an
        # intentional overshoot (Phase 8 independently caps real position entries downstream,
        # see phase8_entry_execution.py's max_positions gate), not a bug.
        assert len(liq_passed) >= LIQUIDITY_CHECK_LIMIT
        passed_symbols = {c["symbol"] for c in liq_passed}
        assert illiquid.isdisjoint(passed_symbols)
        # Backfill candidates ranked #21-24 (SYM020-SYM023) must have been pulled in.
        assert {"SYM020", "SYM021", "SYM022", "SYM023"}.issubset(passed_symbols)
        # Second batch (candidates 20-39) was needed - more than just the first 20 got checked.
        assert liq_checked > LIQUIDITY_CHECK_LIMIT

    def test_no_backfill_needed_does_the_same_single_batch_work_as_before(self):
        """Common case: nothing in the top LIQUIDITY_CHECK_LIMIT fails - must check exactly
        that one batch, no wasted work looking further down the list."""
        candidates = _candidates(40)

        with patch(
            "algo.orchestrator.phase7_signal_generation._check_liquidity_parallel",
            side_effect=_fake_liquidity_check(illiquid_symbols=set()),
        ):
            liq_passed, liq_checked = _run_liquidity_checks(candidates, date(2026, 9, 7), config={})

        assert len(liq_passed) == LIQUIDITY_CHECK_LIMIT
        assert liq_checked == LIQUIDITY_CHECK_LIMIT

    def test_gives_up_at_the_safety_cap_instead_of_scanning_the_whole_universe(self):
        """Pathological day where illiquidity dominates the ranking - must stop at
        MAX_LIQUIDITY_CANDIDATES_CONSIDERED rather than walking the entire candidate list
        looking for LIQUIDITY_CHECK_LIMIT survivors that may not exist."""
        candidates = _candidates(500)
        # Only every 10th candidate is liquid - far fewer than LIQUIDITY_CHECK_LIMIT will be
        # found within the first MAX_LIQUIDITY_CANDIDATES_CONSIDERED candidates.
        illiquid = {c["symbol"] for i, c in enumerate(candidates) if i % 10 != 0}

        with patch(
            "algo.orchestrator.phase7_signal_generation._check_liquidity_parallel",
            side_effect=_fake_liquidity_check(illiquid),
        ):
            liq_passed, liq_checked = _run_liquidity_checks(candidates, date(2026, 9, 7), config={})

        assert liq_checked <= MAX_LIQUIDITY_CANDIDATES_CONSIDERED
        assert len(liq_passed) < LIQUIDITY_CHECK_LIMIT  # genuinely couldn't fill the target

    def test_empty_candidate_list_returns_immediately(self):
        liq_passed, liq_checked = _run_liquidity_checks([], date(2026, 9, 7), config={})
        assert liq_passed == []
        assert liq_checked == 0
