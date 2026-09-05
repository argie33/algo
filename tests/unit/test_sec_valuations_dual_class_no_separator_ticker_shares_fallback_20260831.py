"""Regression test for the 2026-08-31 fix: load_sec_valuations.py's dual-class sibling check
only recognized the dot-separated ticker convention (BRK.A/BRK.B via `symbol.split(".")[0]`) -
companies whose two share classes are ticker-suffixed with no separator at all (DGICA/DGICB,
not DGIC.A/DGIC.B) were never detected as dual-class, so their SEC-derived tiers all ran
unguarded (risking the same one-class's-count-attributed-to-its-sibling bug the dot-based check
exists to prevent) and, when those tiers failed, they fell through to a permanent
"shares_outstanding_unavailable" with no yfinance fallback ever tried.

Live-confirmed via company_info_sec.entity_name: DGICA/DGICB (Donegal Group), KELYA/KELYB
(Kelly Services), LBTYA/LBTYB/LBTYK (Liberty Global), BELFA/BELFB (Bel Fuse), SENEA/SENEB
(Seneca Foods), RUSHA/RUSHB (Rush Enterprises) all share an identical entity_name across their
listed classes. Fixed via an explicit, curated `DUAL_CLASS_NO_SEPARATOR_ROOTS` allowlist -
deliberately NOT a generic "strip the trailing letter, look for another symbol with the same
root" heuristic, since that produces real false positives in this repo's own universe (e.g.
NTR/NTRA/NTRB/NTRP/NTRS are five completely unrelated companies that only coincidentally share
a 3-letter prefix - see the module-level DUAL_CLASS_NO_SEPARATOR_ROOTS comment).
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[Any]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple[Any, ...]]:
        # 2026-09-05: pe_ratio/pb_ratio's implausible-anchor cross-year fallback
        # (loaders/load_sec_valuations.py) can issue one additional fetchall() beyond this
        # fixture's originally-scripted sequence - return empty (no plausible fallback found)
        # rather than IndexError once the scripted list is exhausted, since these fixtures don't
        # care about that fallback's content.
        if self._fetchall_idx >= len(self._fetchall_results):
            return []
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self) -> Any:
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


def _run_fetch_incremental(
    symbol: str, income_rows: list[tuple[Any, ...]], fetchone_results: list[Any]
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _FakeCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


# Same shape as test_sec_valuations_dual_class_yfinance_shares_fallback.py's BRK.A case, but
# for a no-separator ticker (DGICA) - every SEC-derived tier fails, so the fix must reach the
# live yfinance fallback via the NEW no-separator-root sibling check, not the dot-split one.
_INCOME_ROWS = [
    (2025, 400_000_000.0, 90_000_000.0, 5.0, None, None, None, None, None, None, False),
]
_FETCHONE_BASE = [
    (5_000_000.0,),  # cash_and_equivalents
    (10_000_000.0, None, None, None),  # debt_row
    None,  # dot-based sibling check - no match (DGICA has no "." in it)
    (1,),  # NEW: no-separator-root sibling check - found (DGICB exists)
    # tiers 1-3 gated off by has_dual_class_sibling, no query. Tier 4 (company_info_sec
    # fallback) is deliberately ungated - one query, no row.
    None,  # company_info_sec fallback (tier 4) - no row
]


class TestDualClassNoSeparatorTickerSharesFallback:
    def test_no_separator_dual_class_falls_back_to_live_yfinance(self) -> None:
        fetchone_results = [
            *_FETCHONE_BASE,
            (25.50,),  # price_daily.close
            (300_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot sanity check
        ]

        with patch.object(
            SecValuationsLoader,
            "_fetch_live_dual_class_shares_outstanding",
            return_value=31_542_507.0,
        ) as mock_dual_class_fetch:
            result = _run_fetch_incremental("DGICA", _INCOME_ROWS, fetchone_results)

        mock_dual_class_fetch.assert_called_once_with("DGICA")
        row = result[0]
        assert row.get("data_unavailable") is False
        assert row["shares_outstanding"] == 31_542_507.0
        assert row["data_source"] == "sec_audited_except_dual_class_shares_yfinance"

    def test_no_separator_root_not_in_curated_list_is_not_treated_as_dual_class(self) -> None:
        """NTRA (Natera) must NOT be treated as a sibling of NTRB/NTRS/etc. - 'NTR' is not in
        DUAL_CLASS_NO_SEPARATOR_ROOTS (those are five unrelated companies, not share classes
        of one company) - guards against ever widening the curated list to a blind heuristic.
        The live yfinance dual-class fallback must never even be attempted for it."""
        fetchone_results = [
            (5_000_000.0,),  # cash_and_equivalents
            (10_000_000.0, None, None, None),  # debt_row
            None,  # dot-based sibling check - no match
            # 'NTRA' does not start with any DUAL_CLASS_NO_SEPARATOR_ROOTS entry - the fix's
            # no-separator branch must not even issue a query here. Every downstream tier is
            # irrelevant to what this test guards (dual-class detection), so let the reported-
            # shares tier resolve cleanly with a matching company_info_sec value (no scale
            # mismatch noise) rather than modeling every later tier precisely.
            (1_500_000.0,),  # reported shares_outstanding tier (tier 1) - real row
            (1_500_000.0,),  # company_info_sec cross-check - matches, no mismatch
            (45.0,),  # price_daily.close
            (900_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot sanity check
        ]

        with patch.object(SecValuationsLoader, "_fetch_live_dual_class_shares_outstanding") as mock_dual_class_fetch:
            _run_fetch_incremental("NTRA", _INCOME_ROWS, fetchone_results)

        mock_dual_class_fetch.assert_not_called()
