"""Regression test for a 2026-08-20 bug in load_sec_valuations.py's fetch_incremental call site
(goal: finance-accuracy audit) that coerced a genuinely missing (NULL) capex to 0.0 before ever
reaching _compute_valuations.

_compute_valuations already has a correct guard - `if ocf and capex is not None:` (skip fcf_yield
entirely when capex is unknown) - matching the documented "CRITICAL: Don't convert None to 0.0"
convention this same function follows for ttm_revenue/book_value/total_debt. But the call site
in fetch_incremental still used the old `float(capex) if capex else 0.0` pattern, so that guard
never actually saw a None: a latest fiscal year with real operating_cash_flow but not-yet-tagged
capex (common - a filer's OCF can post before its capex line is separately broken out) silently
became "free cash flow = full OCF, capex = $0", producing a fabricated fcf_yield.

Live-confirmed via the real DB: AAL (American Airlines) FY2026 operating_cash_flow=$4.694B,
capex=NULL -> fcf_yield computed as 51.32% (vs a real few-percent figure); same pattern hit HMY,
CSAN, DXC, GT, WD and others - all real companies with well within the -1000%/+1000% sanity
bound the fcf_yield calc already enforces, so that bound never caught it.

Fixed by preserving None (`float(capex) if capex is not None else None`) at the call site, same
convention as the sibling fields immediately above it.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestCapexNoneNotCoercedToZero:
    def _base_kwargs(self) -> dict:
        return {
            "symbol": "AAL",
            "current_price": 13.86,
            "shares_out": 659_964_000.0,
            "ttm_eps": 1.0,
            "ttm_revenue": 54_000_000_000.0,
            "book_value": None,
            "ocf": 4_694_000_000.0,
            "capex": None,  # genuinely not-yet-tagged for the latest fiscal year
            "prior_year_eps": 1.0,
            "dividends_paid": None,
            "total_debt": None,
            "total_cash": None,
            "ebitda": None,
        }

    def test_capex_none_leaves_fcf_yield_unavailable_not_fabricated(self) -> None:
        """This is what _compute_valuations must do when handed a real None (the state the
        fetch_incremental call site now preserves) - the fix under test is at the call site,
        not here, but this locks in the contract the call site now depends on."""
        loader = _make_loader()
        result = loader._compute_valuations(**self._base_kwargs())

        assert result["fcf_yield"] is None
        # Other ratios must still compute normally - a missing capex must not sink the whole row.
        assert result["pe_ratio"] is not None

    def test_capex_zero_still_computes_fcf_yield(self) -> None:
        """A genuine, real $0 capex (falsy but not None) must still be usable - only a real
        None (unknown) should suppress fcf_yield, not a real zero."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["capex"] = 0.0
        result = loader._compute_valuations(**kwargs)

        assert result["fcf_yield"] is not None
