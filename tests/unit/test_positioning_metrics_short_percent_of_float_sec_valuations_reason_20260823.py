"""Regression test (2026-08-23, goal session: real-money-readiness "Missing SEC/XBRL data"
bucket audit): load_positioning_metrics.py's short_percent_of_float fallback queried
sec_valuations.shares_outstanding but discarded sec_valuations.reason when that lookup also
failed, hardcoding the generic "missing_sec_data" even when sec_valuations already knew exactly
why (live-confirmed 759/832 universe rows were "foreign_private_issuer_shares_unavailable" - a
permanent regulatory exemption already correctly mapped to "Legitimate / not applicable" on the
coverage dashboard for every OTHER ownership field, but silently miscategorized as a generic
SEC/XBRL data gap here since the specific reason never reached this loader's output).

Fixed: the sec_valuations fallback query now also selects `reason`, and when shares_outstanding
is still unusable, that reason (if present) is used instead of the generic fallback.
"""

from loaders.load_positioning_metrics import PositioningMetricsLoader


class _FakeCursor:
    def __init__(self, short_interest_rows, sec_valuations_row):
        self._short_interest_rows = short_interest_rows
        self._sec_valuations_row = sec_valuations_row
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "short_interest_finra" in self._last_query:
            return self._short_interest_rows
        return []

    def fetchone(self):
        if "sec_valuations" in self._last_query:
            return self._sec_valuations_row
        # company_info_sec (and everything else) has nothing on file.
        return None


class _FakeDatabaseContext:
    def __init__(self, short_interest_rows, sec_valuations_row):
        self._short_interest_rows = short_interest_rows
        self._sec_valuations_row = sec_valuations_row

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._short_interest_rows, self._sec_valuations_row)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, short_interest_rows, sec_valuations_row):
    import loaders.load_positioning_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(short_interest_rows, sec_valuations_row))
    loader = PositioningMetricsLoader.__new__(PositioningMetricsLoader)
    monkeypatch.setattr(loader, "_compute_ad_rating", lambda symbol: (None, "insufficient_history"))
    return loader


class TestShortPercentOfFloatSecValuationsReason:
    def test_fpi_reason_from_sec_valuations_surfaces_instead_of_generic(self, monkeypatch):
        # FINRA reported real short_shares, but neither company_info_sec nor sec_valuations
        # has a usable shares_outstanding - sec_valuations does know why, though.
        rows = [
            (0.23, 12823, "2026-07-15", 1.00, 91930),
            (0.73, 40968, "2026-06-30", 1.00, 668475),
        ]
        loader = _make_loader(monkeypatch, rows, sec_valuations_row=(None, "foreign_private_issuer_shares_unavailable"))

        result = loader.fetch_incremental("FAKEFPI", since=None)[0]

        assert result["short_percent_of_float"] is None
        assert result["short_percent_of_float_unavailable_reason"] == "foreign_private_issuer_shares_unavailable"

    def test_no_sec_valuations_reason_falls_back_to_generic(self, monkeypatch):
        rows = [
            (0.23, 12823, "2026-07-15", 1.00, 91930),
            (0.73, 40968, "2026-06-30", 1.00, 668475),
        ]
        loader = _make_loader(monkeypatch, rows, sec_valuations_row=None)

        result = loader.fetch_incremental("FAKENOROW", since=None)[0]

        assert result["short_percent_of_float"] is None
        assert result["short_percent_of_float_unavailable_reason"] == "missing_sec_data"

    def test_sec_valuations_has_usable_shares_outstanding_computes_normally(self, monkeypatch):
        # Sanity check: the fix must not break the real fallback-succeeds path.
        rows = [
            (0.23, 12823, "2026-07-15", 1.00, 91930),
            (0.73, 40968, "2026-06-30", 1.00, 668475),
        ]
        loader = _make_loader(monkeypatch, rows, sec_valuations_row=(1_000_000, None))

        result = loader.fetch_incremental("FAKEHASSHARES", since=None)[0]

        assert result["short_percent_of_float"] == 1.2823
        assert result["short_percent_of_float_unavailable_reason"] is None
