"""Regression test for the 2026-09-06 fix: DUAL_CLASS_NO_SEPARATOR_ROOTS' prefix+length
heuristic (`symbol.startswith(r) and len(symbol) == len(r) + 1`) can never match when the
CURRENT symbol IS the bare root itself, since that requires len(symbol) == len(symbol) + 1.
That's harmless for DGIC/KELY/LBTY/BELF/SENE/RUSH (none of those bare roots are real tickers),
but several real dual-class families use a real, actively-traded ticker AS the root, with the
sibling class suffixed onto it with no separator - UONE/UONEK (Urban One Class A/D), live-
confirmed via matching company_info_sec.entity_name ("URBAN ONE, INC.") for both. Before this
fix, processing symbol="UONE" always produced has_dual_class_sibling=False, denying it the same
entity-wide fcf_yield/dividend_yield/DCF pairing correction already applied to TAP/TAP.A-shaped
dual-class filers.

Fixed via a SEPARATE exact-family-membership structure (`DUAL_CLASS_BARE_ROOT_SIBLING_FAMILIES`),
not by folding these roots into DUAL_CLASS_NO_SEPARATOR_ROOTS's wildcard/prefix matching: several
of the new roots are short/common enough to collide with real, unrelated tickers under that
heuristic (UA would wildcard-match UAL/United Airlines; FOX would wildcard-match FOXF/Fox Factory
and FOXX) - the second test below guards against exactly that regression.

Tests _resolve_shares_outstanding directly (rather than the full fetch_incremental integration,
which has many unrelated downstream tiers/queries that would make this brittle) with a cursor
that returns None for every query after the sibling-detection ones under test - every later tier
already tolerates "no row" the same way it tolerates a real absence of data.
"""

from typing import Any
from unittest.mock import MagicMock

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    loader = SecValuationsLoader.__new__(SecValuationsLoader)
    loader.MIN_PLAUSIBLE_SHARES_OUTSTANDING = 100_000  # type: ignore[attr-defined]
    loader.MAX_PLAUSIBLE_SHARES_OUTSTANDING = 50_000_000_000  # type: ignore[attr-defined]
    loader.SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO = 50  # type: ignore[attr-defined]
    loader._fetch_live_dual_class_shares_outstanding = MagicMock(return_value=None)  # type: ignore[attr-defined]
    loader._fetch_live_fpi_shares_outstanding_yfinance = MagicMock(return_value=None)  # type: ignore[attr-defined]
    return loader


class _SiblingDetectionCursor:
    """Scripts only the fetchone() calls the sibling-detection tiers under test issue, then
    returns None (a real "no row found") for every subsequent query so later tiers fail out
    cleanly without needing to be modeled."""

    def __init__(self, scripted: list[Any]) -> None:
        self._scripted = list(scripted)
        self._idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple[Any, ...]]:
        return []

    def fetchone(self) -> Any:
        if self._idx < len(self._scripted):
            result = self._scripted[self._idx]
            self._idx += 1
            return result
        return None


def _has_dual_class_sibling(symbol: str, scripted: list[Any]) -> bool:
    loader = _make_loader()
    cur = _SiblingDetectionCursor(scripted)
    _shares_out, has_dual_class_sibling, _from_dc_yf, _from_fpi_yf = loader._resolve_shares_outstanding(
        cur,
        symbol,
        income_rows=[],
        ttm_fiscal_year=None,
        ttm_eps_basic=None,
        _ttm_net_income=None,
        eps_substituted_from_row1=False,
        is_foreign_private_issuer=False,
        reported_shares_outstanding=None,
    )
    return has_dual_class_sibling


class TestDualClassBareRootSiblingFix:
    def test_bare_root_ticker_detects_no_separator_dual_class_sibling(self) -> None:
        """UONE (the bare root, Urban One Class A) must be detected as having a dual-class
        sibling (UONEK, Class D) via the new exact-family lookup."""
        scripted = [
            None,  # dot-based sibling check - no match ("UONE" has no ".")
            # no-separator-root (prefix+length) check: "UONE" doesn't start with any of
            # DUAL_CLASS_NO_SEPARATOR_ROOTS's 6 original roots, so no_sep_root is None and that
            # branch issues no query at all (matching the existing NTRA-style short-circuit).
            (1,),  # NEW: bare-root exact-family sibling check - found (UONEK exists)
        ]
        assert _has_dual_class_sibling("UONE", scripted) is True

    def test_suffixed_side_of_bare_root_family_also_detected(self) -> None:
        """UONEK (the suffixed sibling) must also resolve via the same exact-family lookup -
        neither the dot check nor the existing prefix+length check matches it either, since
        'UONE' (the family's other root-shaped member) is not in DUAL_CLASS_NO_SEPARATOR_ROOTS."""
        scripted = [
            None,  # dot-based sibling check
            # no-separator-root (prefix+length) check: "UONEK" doesn't start with any of
            # DUAL_CLASS_NO_SEPARATOR_ROOTS's 6 original roots either, so again no query issued.
            (1,),  # bare-root exact-family sibling check - found (UONE exists)
        ]
        assert _has_dual_class_sibling("UONEK", scripted) is True

    def test_short_root_collision_is_not_treated_as_dual_class(self) -> None:
        """UAL (United Airlines) must NOT be treated as a dual-class sibling of UA/UAA (Under
        Armour) just because it shares the 'UA' prefix - guards the exact-family design against
        ever degrading into the wildcard/prefix heuristic DUAL_CLASS_NO_SEPARATOR_ROOTS's own
        docstring already warns against (the NTR/NTRA/NTRB/NTRP/NTRS false-positive class).
        Neither branch should even issue a query for UAL - the family-membership check for 'UA'
        (UAL is not in it) never fires the DB query, so only two scripted rows are needed."""
        scripted = [
            None,  # dot-based sibling check
            # no-separator-root (prefix+length) check: "UAL" doesn't start with any of
            # DUAL_CLASS_NO_SEPARATOR_ROOTS's 6 original roots, so no query issued there either.
        ]
        assert _has_dual_class_sibling("UAL", scripted) is False
