"""Regression test: _get_no_recent_capex_symbols()'s ranking window was corrupted by a stray
trailing "not yet filed" placeholder row, in both directions.

Bug (live-verified 2026-09-05, cross-session follow-up to the 2026-09-03 `fiscal_year > 0` fix
already documented on this method): many symbols carry a single `data_unavailable = TRUE` row
for the NEXT fiscal year (e.g. fiscal_year=2026 when the last real filed year is 2025) that
nonetheless has leftover non-NULL numeric values in some columns - a carry-over that was never
nulled when the row was flagged unavailable. Because the old query didn't exclude that
placeholder row, it silently occupied one of the "3 most recent" ranking slots two different
ways:

  - CYCN/EMAT/EWBC/PPCB/TFIN (false negative): the placeholder's stray non-NULL capex made
    `COUNT(capex) != 0` even though the true 3 most recent REAL fiscal years all have real
    operating_cash_flow and genuinely NULL capex - these wrongly fell through to the generic
    "missing_sec_data" reason instead of this gate's specific one.
  - AIG/NLY/UHT/AAMI/RZLT/... (false positive, 39 live-confirmed): the placeholder's presence
    pushed a REAL capex-bearing row (e.g. AIG FY2023 capex=$240M) out of the 3-slot window
    entirely, so the gate wrongly matched them as "capex never tagged" when capex was in fact
    tagged, just one fiscal year further back than the corrupted window could see.

Fix: exclude a `data_unavailable = TRUE` row ONLY when its fiscal_year is exactly (that
symbol's own max `data_unavailable = FALSE` fiscal_year) + 1, while still including any OTHER
`data_unavailable = TRUE` row in the ranking - so a GLNG-shaped symbol (multiple consecutive
real gap years, true recent history is genuinely unavailable) still correctly does NOT match
this gate (falls through to no_recent_operating_cash_flow_reported instead), unchanged from
before this fix.

A naive version of this fix (placeholder exclusion only, `COUNT(*) = 3` left unchanged) was
live-verified to additionally DROP 131 already-correctly-matching symbols - mostly SPAC/shell
tickers (LCCC, MACI, NPAC, RFAI, TAVI, DMAA, PACH, ...) that simply have only 2 real filed
fiscal years on record (too recently IPO'd/merged to have a 3rd), both real years genuinely
NULL for capex. Checking every earlier gate in the fcf_yield priority chain
(registered-investment-company/etf-trust/no-recent-fcf/never-tagged-fcf) showed only 51 of the
131 were re-caught elsewhere; the remaining 80 would have regressed from this gate's specific,
accurate reason to the generic "missing_sec_data" bucket. `COUNT(*) = 3` was relaxed to
`COUNT(*) >= 2` to admit these thinner-history filers (same "too few consecutive real fiscal
years" reasoning `_get_never_tagged_free_cash_flow_symbols()` already uses via its
`COUNT(*) >= 1` full-history sibling) - live-reverified this recovers 129 of the 131 SPAC-shaped
symbols without reintroducing the GLNG-shaped false-match risk, since `rn <= 3` still caps how
far back the window can reach.

This test can't execute the real WITH/window-function SQL against a live Postgres instance (this
repo's unit tests mock the DB layer, per every sibling gate test in this file), so it does two
things instead: (1) asserts the executed SQL text contains the specific fix markers so a future
edit can't silently regress them, and (2) reimplements the query's exact ranking/filtering
semantics in pure Python and runs it against the three live-verified row shapes (CYCN-shaped,
GLNG-shaped, SPAC-shaped) to prove the *logic* embedded in that SQL produces the intended
result - independently corroborated against the real DB (counts/example tickers above).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, symbols):
        self._symbols = symbols
        self.last_query = ""

    def execute(self, query, params=None):
        self.last_query = query

    def fetchall(self):
        return [(s,) for s in self._symbols]

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, symbols=frozenset()):
        self._symbols = symbols
        self.cursor: _FakeCursor | None = None

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        self.cursor = _FakeCursor(self._symbols)
        return self.cursor

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    fake_ctx = _FakeDatabaseContext(symbols)
    monkeypatch.setattr(mod, "DatabaseContext", fake_ctx)
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    return loader, fake_ctx


class TestNoRecentCapexSymbolsSqlShape:
    def test_method_returns_wired_symbols(self, monkeypatch):
        loader, _ = _make_loader(monkeypatch, symbols=frozenset({"CYCN", "EMAT"}))

        result = loader._get_no_recent_capex_symbols()

        assert result == frozenset({"CYCN", "EMAT"})

    def test_sql_excludes_only_single_trailing_next_year_placeholder(self, monkeypatch):
        loader, fake_ctx = _make_loader(monkeypatch)

        loader._get_no_recent_capex_symbols()

        sql = fake_ctx.cursor.last_query
        assert "fiscal_year > 0" in sql
        # The placeholder-exclusion condition: a data_unavailable row is dropped only when its
        # fiscal_year is exactly one past the symbol's own max real fiscal_year.
        assert "max_real_fy" in sql
        assert "fiscal_year = max_real_fy + 1" in sql
        assert "data_unavailable = FALSE" in sql  # still used to compute max_real_fy itself

    def test_sql_relaxes_exact_three_to_at_least_two(self, monkeypatch):
        loader, fake_ctx = _make_loader(monkeypatch)

        loader._get_no_recent_capex_symbols()

        sql = fake_ctx.cursor.last_query
        assert "COUNT(*) >= 2" in sql
        assert "COUNT(*) = 3" not in sql


def _simulate_gate(rows: list[tuple[int, bool, float | None, float | None]]) -> bool:
    """Pure-Python reimplementation of _get_no_recent_capex_symbols()'s per-symbol SQL logic.

    Each row is (fiscal_year, data_unavailable, capex, operating_cash_flow). Returns whether
    this symbol would match the gate (i.e. appear in its result frozenset).
    """
    real_rows = [r for r in rows if r[0] > 0]
    real_fys = [r[0] for r in real_rows if not r[1]]
    max_real_fy = max(real_fys) if real_fys else None

    def _is_next_year_placeholder(r: tuple[int, bool, float | None, float | None]) -> bool:
        fy, unavailable, _capex, _ocf = r
        return bool(unavailable) and max_real_fy is not None and fy == max_real_fy + 1

    filtered = [r for r in real_rows if not _is_next_year_placeholder(r)]
    recent = sorted(filtered, key=lambda r: r[0], reverse=True)[:3]

    count_capex = sum(1 for r in recent if r[2] is not None)
    count_ocf = sum(1 for r in recent if r[3] is not None)
    count_total = len(recent)

    return count_capex == 0 and count_ocf > 0 and count_total >= 2


class TestNoRecentCapexSymbolsRankingLogic:
    def test_cycn_shaped_symbol_matches(self):
        # Real recent years have real OCF and NULL capex; a trailing next-year placeholder
        # (data_unavailable=True) carries a stray non-NULL capex left over from a prior run.
        rows = [
            (2026, True, 50_000.0, 100_000.0),  # placeholder, stray non-NULL capex
            (2025, False, None, 900_000.0),
            (2024, False, None, 800_000.0),
            (2023, False, None, 700_000.0),
        ]

        assert _simulate_gate(rows) is True

    def test_glng_shaped_symbol_still_does_not_match(self):
        # Multiple consecutive real gap years (all data_unavailable=True, no OCF at all) sit in
        # front of real historical data further back - the true 3 most recent years have no
        # OCF, so this must fall through to no_recent_operating_cash_flow_reported, not here.
        rows = [
            (2025, True, None, None),
            (2024, True, None, None),
            (2023, True, None, None),
            (2022, True, None, None),
            (2021, False, None, 253_881_000.0),
            (2020, False, None, -176_527_000.0),
            (2018, False, 0.0, 116_674_000.0),
        ]

        assert _simulate_gate(rows) is False

    def test_spac_shaped_symbol_with_two_real_years_matches(self):
        # Only 2 real fiscal years exist at all (recent IPO/SPAC-merger) - both genuinely never
        # tag capex. Correctly matches under the relaxed COUNT(*) >= 2 threshold: capex truly
        # was never tagged in every real filing this symbol has, same underlying fact as the
        # 3-real-year case, just thinner history. (Live-verified: 129 of 131 such symbols,
        # e.g. LCCC/MACI/NPAC/RFAI/TAVI/DMAA/PACH.)
        rows = [
            (2026, True, None, -119_667.0),  # next-year placeholder, excluded
            (2025, False, None, -1_264_871.0),
            (2024, False, None, -29_124.0),
        ]

        assert _simulate_gate(rows) is True

    def test_symbol_with_real_capex_further_back_does_not_match(self):
        # AIG-shaped: the placeholder previously pushed FY2023's real capex out of the 3-slot
        # window, causing a false match. With the placeholder excluded, the true 3 most recent
        # real years (2025, 2024, 2023) are considered and 2023 has real capex, so this
        # correctly does NOT match.
        rows = [
            (2026, True, None, 155_000_000.0),  # next-year placeholder, excluded
            (2025, False, None, 3_314_000_000.0),
            (2024, False, None, 3_273_000_000.0),
            (2023, False, 240_000_000.0, 6_243_000_000.0),
            (2022, False, 210_000_000.0, 4_134_000_000.0),
        ]

        assert _simulate_gate(rows) is False

    def test_single_real_year_plus_unavailable_prior_year_still_matches(self):
        # Only 1 real fiscal year, plus 1 genuinely-unavailable prior year (not a next-year
        # placeholder, so not excluded). COUNT(*) = 2 (>= 2) still clears the relaxed threshold.
        rows = [
            (2026, True, None, -197_987.0),  # next-year placeholder, excluded
            (2025, False, None, -252_205.0),
            (2024, True, None, None),
        ]

        assert _simulate_gate(rows) is True

    def test_single_real_year_alone_does_not_match(self):
        # Too thin an evidence base (only 1 total row survives filtering) - correctly excluded.
        rows = [
            (2026, True, None, -50_000.0),  # next-year placeholder, excluded
            (2025, False, None, -75_000.0),
        ]

        assert _simulate_gate(rows) is False
