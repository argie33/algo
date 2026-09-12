"""Tests for apply_mortgage_reit_sector_override (loaders/helpers/vqg_shared.py).

Goal session 2026-09-12: live-verified the "Real Estate" GICS sector - the peer group
`_percent_rank_cheap_high_sector_relative`/`sector_neutral_zscore` use for Value's P/E-P/B-P/S-
dividend-yield percentile ranks and Quality/Growth's sector-neutral z-scores - conflates equity
REITs (PLD, AMT, PSA, SPG) with mortgage/commercial-mortgage REITs (NLY, AGNC, DX, ORC, BXMT,
STWD), a structurally different, book-value/leverage-driven business. Live DB query: mortgage
REITs (n=24 confidently-matched symbols in that pass) averaged value_score ~70 vs equity REITs'
~40, mechanically topping the REIT leaderboard with DX/ORC/NLY/AGNC/MFA/MITT/IVR instead of real
industry leaders. Neither company_profile.sector/industry nor SEC's own SIC code (6798, shared
by both groups) can separate them - MORTGAGE_REIT_SYMBOLS is a curated symbol list, same
data-signal-free fallback this repo already accepts for coarser industry-string frozensets.
"""

from loaders.helpers.vqg_shared import (
    MORTGAGE_REIT_SECTOR_LABEL,
    MORTGAGE_REIT_SYMBOLS,
    apply_mortgage_reit_sector_override,
)


class TestApplyMortgageReitSectorOverride:
    def test_known_mortgage_reit_remapped_out_of_real_estate(self) -> None:
        for symbol in ("NLY", "AGNC", "DX", "ORC", "BXMT", "STWD"):
            assert symbol in MORTGAGE_REIT_SYMBOLS
            assert apply_mortgage_reit_sector_override(symbol, "Real Estate") == MORTGAGE_REIT_SECTOR_LABEL

    def test_equity_reit_untouched(self) -> None:
        for symbol in ("PLD", "AMT", "PSA", "SPG", "EQIX", "O"):
            assert symbol not in MORTGAGE_REIT_SYMBOLS
            assert apply_mortgage_reit_sector_override(symbol, "Real Estate") == "Real Estate"

    def test_only_applies_within_real_estate_sector(self) -> None:
        # A mortgage-REIT symbol somehow classified under a different sector (data drift) is
        # left alone rather than force-relabeled - fail-open, matching this module's convention.
        assert apply_mortgage_reit_sector_override("NLY", "Financial Services") == "Financial Services"

    def test_none_sector_passthrough(self) -> None:
        assert apply_mortgage_reit_sector_override("NLY", None) is None

    def test_unrelated_sector_untouched(self) -> None:
        assert apply_mortgage_reit_sector_override("AAPL", "Technology") == "Technology"

    def test_mortgage_reit_group_meets_minimum_sector_slice(self) -> None:
        # _MIN_SECTOR_SLICE (loaders/stock_scores/value_metrics.py) is 20 - below that the group
        # falls back to the universe-wide residual pool, silently undoing this split.
        assert len(MORTGAGE_REIT_SYMBOLS) >= 20
