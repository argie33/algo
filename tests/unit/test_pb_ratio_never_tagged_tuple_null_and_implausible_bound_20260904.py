"""Regression test: two gaps in pb_ratio_unavailable_reason found in the 2026-09-04
"Missing SEC/XBRL data" reduction goal session, both in the same code block as
test_pb_ratio_never_tagged_equity_reason_20260902.py.

1. Tuple-wrapped-NULL bug: the full-history equity query has no `stockholders_equity IS NOT
   NULL` filter (by design, to mirror load_sec_valuations.py's own CASE-prioritized query), so a
   symbol with real annual_balance_sheet rows on file but stockholders_equity NULL in every one
   of them still returns a non-None `equity_row` (a 1-tuple wrapping None) - the `equity_row is
   None` check can only ever fire when the symbol has NO balance-sheet rows at all, a narrower
   condition than the "never tagged" case it was meant to detect. Live-confirmed BAR/NRT/PAC/BMA
   (real royalty-trust/ADR filers with real annual_balance_sheet history, stockholders_equity
   NULL throughout) fell to generic "missing_sec_data" as a result.

2. Missing implausible-ratio bound check: load_sec_valuations.py's own pb_ratio computation
   rejects (silently logs + leaves NULL, no reason recorded) any ratio outside
   MIN_PLAUSIBLE_PB_RATIO(0.05)..1000 - this reason chain never re-checked that same bound, so a
   real, positive-but-tiny book value (CL: $54M equity / 1.47B shares -> bvps=$0.037, pb~2412;
   PBT: an oil/gas royalty trust with an atypically thin residual equity base) fell to generic
   "missing_sec_data" instead of "implausible_ratio".
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _EquityQueryCursor:
    def __init__(self, equity_row):
        self._equity_row = equity_row
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "SELECT stockholders_equity" in self.last_query:
            return self._equity_row
        return None

    def fetchall(self):
        return []


class TestPbRatioTupleWrappedNullReportsNeverTagged:
    def test_row_exists_but_equity_value_is_null_reports_never_tagged(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # A real annual_balance_sheet row exists (fetchone returns a 1-tuple), but its
            # stockholders_equity value itself is NULL - the BAR/NRT/PAC/BMA shape.
            mock_db_ctx.return_value.__enter__.return_value = _EquityQueryCursor(equity_row=(None,))
            metrics = loader._build_value_metrics(
                "BAR",
                _FakeSecValRow(
                    {"pe_ratio": 20.0, "peg_ratio": 1.0, "pb_ratio": None, "current_price": 43.68, "market_cap": 1e9}
                ),
            )

        assert metrics["pb_ratio"] is None
        assert metrics["pb_ratio_unavailable_reason"] == "stockholders_equity_never_tagged_in_filings"


class TestPbRatioImplausibleBound:
    def test_real_tiny_book_value_reports_implausible_ratio(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # CL-shaped: real, positive stockholders_equity ($54M) but tiny relative to shares
            # outstanding (1.4657B) -> bvps ~= $0.037, pb ~= 2412 (> 1000 bound).
            mock_db_ctx.return_value.__enter__.return_value = _EquityQueryCursor(equity_row=(54_000_000.0,))
            metrics = loader._build_value_metrics(
                "CL",
                _FakeSecValRow(
                    {
                        "pe_ratio": 20.0,
                        "peg_ratio": 1.0,
                        "pb_ratio": None,
                        "current_price": 88.77,
                        "market_cap": 1.3e11,
                        "shares_outstanding": 1_465_706_360.0,
                    }
                ),
            )

        assert metrics["pb_ratio"] is None
        assert metrics["pb_ratio_unavailable_reason"] == "implausible_ratio"

    def test_real_book_value_below_lower_bound_reports_implausible_ratio(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # bvps huge relative to price -> pb far below the 0.05 lower bound.
            mock_db_ctx.return_value.__enter__.return_value = _EquityQueryCursor(equity_row=(10_230_300_000.0,))
            metrics = loader._build_value_metrics(
                "TAPA",
                _FakeSecValRow(
                    {
                        "pe_ratio": 15.0,
                        "peg_ratio": 1.0,
                        "pb_ratio": None,
                        "current_price": 47.96,
                        "market_cap": 1.2e8,
                        "shares_outstanding": 2_563_034.0,
                    }
                ),
            )

        assert metrics["pb_ratio"] is None
        assert metrics["pb_ratio_unavailable_reason"] == "implausible_ratio"

    def test_real_book_value_per_share_below_floor_reports_implausible_ratio(self):
        """FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" audit, same fix as
        ps_ratio's identical gap). load_sec_valuations.py's own pb computation rejects a real
        book-value-per-share below $0.10 even when the implied pb itself lands inside
        0.05..1000 - this reason chain never re-derived that floor, only the implied-pb
        bounds, so a real bvps just under $0.10 with a normal price fell through to
        "missing_sec_data" instead of "implausible_ratio".
        """
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # bvps = 5M / 100M shares = $0.05 (< $0.10 floor), price $5 -> pb = 100, well
            # within 0.05..1000 - the bare bounds check alone would miss this.
            mock_db_ctx.return_value.__enter__.return_value = _EquityQueryCursor(equity_row=(5_000_000.0,))
            metrics = loader._build_value_metrics(
                "THINEQUITYCO",
                _FakeSecValRow(
                    {
                        "pe_ratio": 10.0,
                        "peg_ratio": 1.0,
                        "pb_ratio": None,
                        "current_price": 5.0,
                        "market_cap": 5e8,
                        "shares_outstanding": 100_000_000.0,
                    }
                ),
            )

        assert metrics["pb_ratio"] is None
        assert metrics["pb_ratio_unavailable_reason"] == "implausible_ratio"

    def test_real_book_value_in_bounds_keeps_generic_reason_without_shares_outstanding(self):
        # Same as test_pb_ratio_never_tagged_equity_reason_20260902.py's AMBIGCO case: no
        # shares_outstanding on the sec_valuations row means the implausible-ratio recompute
        # can't run, so this must still fall through to the generic reason, unchanged.
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _EquityQueryCursor(equity_row=(200_000_000.0,))
            metrics = loader._build_value_metrics(
                "AMBIGCO",
                _FakeSecValRow(
                    {"pe_ratio": 10.0, "peg_ratio": 1.0, "pb_ratio": None, "current_price": 10.0, "market_cap": 1e9}
                ),
            )

        assert metrics["pb_ratio"] is None
        assert metrics["pb_ratio_unavailable_reason"] == "missing_sec_data"

    def test_real_book_value_with_plausible_ratio_keeps_generic_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # bvps = 200M / 100M shares = $2.00, price $10 -> pb = 5.0, well within bounds -
            # this symbol's pb still came out null for some other, genuinely ambiguous reason.
            mock_db_ctx.return_value.__enter__.return_value = _EquityQueryCursor(equity_row=(200_000_000.0,))
            metrics = loader._build_value_metrics(
                "PLAUSIBLECO",
                _FakeSecValRow(
                    {
                        "pe_ratio": 10.0,
                        "peg_ratio": 1.0,
                        "pb_ratio": None,
                        "current_price": 10.0,
                        "market_cap": 1e9,
                        "shares_outstanding": 100_000_000.0,
                    }
                ),
            )

        assert metrics["pb_ratio"] is None
        assert metrics["pb_ratio_unavailable_reason"] == "missing_sec_data"
