"""Regression test for the 2026-09-12 industry-conditional Momentum fix to
loaders/stock_scores/momentum_scoring.py's _score_momentum()/_is_bank_momentum_industry().

A real, FDR-confirmed, non-circular Fama-MacBeth panel found depository-bank Momentum
inverts across every component of this pillar's construction (return windows, RSI, MACD,
SMA positioning) - see bank_momentum_inversion_confirmed_and_fixed_20260912 in memory for
the full evidence chain (stable in direction across the full sample and two independent
sub-period splits, ruling out the 2023 regional-bank crisis as the sole driver). The fix
mirrors the final 0-100 score (100 - score) for symbols in DEPOSITORY_BANK_INDUSTRIES only,
leaving the universal formula untouched for every other industry.
"""

from typing import TYPE_CHECKING, Any, Literal

import psycopg2

from loaders.stock_scores.momentum_scoring import MomentumScoringMixin

if TYPE_CHECKING:
    import pytest


class _Loader(MomentumScoringMixin):
    pass


_FULL_COVERAGE_METRICS = {
    "momentum_1m": 2.0,
    "momentum_3m": 8.0,
    "momentum_6m": None,
    "momentum_12m": 15.0,
    "rsi_14": None,
    "macd": None,
    "price_vs_sma_50": None,
    "price_vs_sma_200": None,
}


class TestBankMomentumMirror:
    def test_bank_symbol_score_is_mirrored(self) -> None:
        loader = _Loader()
        loader._bank_momentum_symbols = frozenset({"JPM"})

        universal_score = _Loader()._score_momentum(_FULL_COVERAGE_METRICS, "NONBANK")
        bank_score = loader._score_momentum(_FULL_COVERAGE_METRICS, "JPM")

        assert isinstance(universal_score, float)
        assert isinstance(bank_score, float)
        assert bank_score == 100.0 - universal_score

    def test_non_bank_symbol_is_unmirrored(self) -> None:
        loader = _Loader()
        loader._bank_momentum_symbols = frozenset({"JPM"})

        score = loader._score_momentum(_FULL_COVERAGE_METRICS, "AAPL")

        assert isinstance(score, float)
        # Same as the universal formula with no bank set populated at all.
        assert score == _Loader()._score_momentum(_FULL_COVERAGE_METRICS, "AAPL")

    def test_data_unavailable_marker_is_never_mirrored(self) -> None:
        # A thin-sample/no-data marker dict must pass through untouched regardless of
        # industry - mirroring only applies to a real float score.
        loader = _Loader()
        loader._bank_momentum_symbols = frozenset({"JPM"})

        result = loader._score_momentum(None, "JPM")

        assert isinstance(result, dict)
        assert result["data_unavailable"] is True

    def test_is_bank_momentum_industry_fails_open_on_db_error(self, monkeypatch: "pytest.MonkeyPatch") -> None:
        # If the company_profile lookup can't run at all, _is_bank_momentum_industry must
        # fail open (False) rather than crash the whole scoring run - same contract as
        # vqg_shared.py's SectorIndustryCacheMixin.
        import loaders.load_stock_scores as mod

        class _RaisingDatabaseContext:
            def __call__(self, *args: object, **kwargs: object) -> "_RaisingDatabaseContext":
                return self

            def __enter__(self) -> Any:
                raise psycopg2.OperationalError("db unreachable")

            def __exit__(self, *exc: object) -> Literal[False]:
                return False

        monkeypatch.setattr(mod, "DatabaseContext", _RaisingDatabaseContext())
        loader = _Loader()

        result = loader._is_bank_momentum_industry("ANY")

        assert result is False
