"""SEC/XBRL structural-absence symbol gates for ValueQualityGrowthMetricsLoader.

Extracted from load_value_quality_growth_metrics.py (2026-09-04, "mega bloater" cleanup):
these 39 methods are all pure "which symbols structurally lack field X in their SEC filings"
lookups, each caching a DB query for the life of the loader instance. Every one answers the
same question shape - "is a null/missing computed value here a genuine business-state fact
(REIT unclassified balance sheet, pre-revenue biotech, tax-exempt shipping company, ...) or
an actual data gap" - and feeds a `*_unavailable_reason` string, never a computed VALUE. See
each method's own docstring for the specific fix history/live-verified sample counts behind
its exact query shape; those are load-bearing and were preserved byte-for-byte in this move.

Mixed into ValueQualityGrowthMetricsLoader via multiple inheritance - shares that class's
per-instance cache attributes and only depends on DatabaseContext.

DatabaseContext is deliberately NOT imported at module level here: dozens of existing unit
tests monkeypatch `loaders.load_value_quality_growth_metrics.DatabaseContext` to inject a fake
cursor (these tests predate this file and were not rewritten when these methods moved out of
that module). `_database_context()` re-resolves the name from that module on every call so
those patches keep working transparently post-move - a module-level `from ... import
DatabaseContext` here would bind its own copy that the patches can't reach.
"""

from typing import Any


def _database_context() -> Any:
    from loaders import load_value_quality_growth_metrics as _owner

    return _owner.DatabaseContext  # type: ignore[attr-defined]


def _cached_symbols(method: Any) -> Any:
    """Cache a frozenset-returning symbol-gate query for the life of the loader instance.

    All 39 gates below ran this exact getattr/setattr caching dance inline before this
    extraction - same cache key per method (derived from its name), same "run the query once
    per pipeline run, not once per symbol" contract, just no longer copy-pasted 39 times.
    """
    cache_attr = f"_{method.__name__[5:]}_cache"

    def wrapper(self: Any) -> Any:
        cached = getattr(self, cache_attr, None)
        if cached is not None:
            return cached
        result = method(self)
        setattr(self, cache_attr, result)
        return result

    wrapper.__name__ = method.__name__
    wrapper.__doc__ = method.__doc__
    return wrapper


class SymbolGateMixin:
    """The 39 `_get_*_symbols` structural-absence gates, verbatim."""

    @_cached_symbols
    def _get_unclassified_balance_sheet_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported current_assets in any of their 3 most recent fiscal years.

        REITs/banks/insurers file an unclassified balance sheet (no current/non-current split)
        as a permanent accounting-model difference, not a data gap. A single fiscal year missing
        current_assets can also just be an ordinary extraction/timing gap for an otherwise normal
        filer - requiring 3 consecutive missing years is what actually distinguishes the two,
        rather than guessing from one row.

        FIXED 2026-08-18: originally required COUNT(current_assets) = 0 across EVERY fiscal year
        ever filed, not just recent ones. That misses symbols that switched accounting presentation
        partway through their filing history - e.g. ENVA reported a classified balance sheet in
        FY2013-2014 (pre spin-off from Cash America) but has filed unclassified every year since
        (FY2015-2026, 12 straight years); the old query saw the two ancient non-null years and
        fell through to the generic "missing_sec_data" label, which reads as a loader bug rather
        than the permanent accounting-model difference it actually is. Live-confirmed 49 symbols
        in this "used to report classified, now doesn't" bucket. Cached for the life of this
        loader instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep, same bug class across
        every `rn <= 3` gate in this file): a `data_unavailable = TRUE` row can carry a leftover
        non-NULL value in its data columns (never nulled when the row was flagged unavailable),
        which silently counted as "reported" here. `CASE WHEN data_unavailable THEN NULL...`
        sanitizes the field before counting so a stray leftover value can't masquerade as real
        data. Live-verified this recovers XRTX (3 most recent years all `data_unavailable=TRUE`
        but carrying stray non-NULL current_assets) with zero symbols lost.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol,
                           CASE WHEN data_unavailable THEN NULL ELSE current_assets END AS current_assets,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(current_assets) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_tax_concept_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported pretax_income or income_tax_expense in any of
        their 3 most recent fiscal years.

        Same "3 consecutive years missing a concept = permanent accounting-model
        difference, not a data gap" pattern as _get_unclassified_balance_sheet_symbols
        above (REIT/bank/insurer unclassified balance sheets). Here the structural
        difference is a real corporate-tax exemption: Marshall-Islands/Bermuda-
        incorporated shipping companies under IRC Section 883's tonnage-tax exemption
        (live-confirmed: GASS/ESEA/DSX and 13 more "Marine Shipping" symbols, all
        Greek-operated) and REITs under Subchapter M pass-through status never tag
        IncomeTaxExpenseBenefit/pretax-income concepts because there is no income tax
        line to report - not because the data is missing. roic_pct's effective_tax_rate
        logic (FIXED 2026-08-09 to stop assuming a synthetic 21%/25% rate) correctly
        refuses to guess a rate when tax concepts are absent, but that left these
        genuinely-zero-tax filers permanently unavailable instead of computing a real
        NOPAT = operating_income (0% effective rate) - the same "genuine business-state
        fact, not an absent SEC concept" distinction already applied to
        roic_pct_unprofitable just below. Cached for the life of this loader instance.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - same bug class
        as _get_no_recent_interest_expense_symbols' 2026-09-03 fix, missed in that sweep):
        `WHERE data_unavailable = FALSE` made a symbol whose 3 most recent fiscal years are
        ALL explicitly marked unavailable invisible to this gate. `fiscal_year > 0` keeps the
        ranking free of `_unavailable_marker` sentinel rows while including real-fiscal-year
        unavailable ones. Live-confirmed 109 additional symbols recovered. Label-only.

        FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep, same fix as
        _get_unclassified_balance_sheet_symbols above): sanitize both fields to NULL when their
        row is `data_unavailable` so a leftover stray value can't count as "reported". Live-
        verified 5 additional symbols recovered (ASR/BBAR/CEPU/ENIC/LOMA), zero lost.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol,
                           CASE WHEN data_unavailable THEN NULL ELSE pretax_income END AS pretax_income,
                           CASE WHEN data_unavailable THEN NULL ELSE income_tax_expense END AS income_tax_expense,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(pretax_income) = 0 AND COUNT(income_tax_expense) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_pretax_income_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported pretax_income in any of their 3 most recent
        fiscal years, REGARDLESS of whether they tag income_tax_expense.

        Distinct from _get_no_tax_concept_symbols() above, which requires BOTH concepts
        absent (the fully tax-exempt case: 0% rate, no approximation needed). This
        covers the class that still falls through the cracks: REITs/mortgage trusts
        (ADC, AAT, ABR live-confirmed via real annual_income_statement rows) whose
        10-Ks go straight from revenue to net income with no distinct "income before
        tax" subtotal line to tag at all (REIT pass-through income is structurally not
        the thing being taxed), but DO carry a small, real income_tax_expense most years
        (built-in-gains tax on a taxable REIT subsidiary, state tax, etc.) - live-
        confirmed 165 universe symbols fit this exact profile, 122 of them blocking
        roic_pct on "missing_sec_data". Since there's no pretax_income concept AT ALL
        to be missing, the effective_tax_rate branch below uses (net_income +
        income_tax_expense) as an approximation of the SAME fiscal year's pretax base -
        see that branch's comment for why this narrow use is safe despite the general
        net_income-derivation approach being rejected elsewhere in this file. Cached for
        the life of this loader instance.

        FIXED 2026-09-03 (same bug class/fix as _get_no_tax_concept_symbols above, missed in
        the same original sweep): `WHERE data_unavailable = FALSE` -> `WHERE fiscal_year > 0`
        so a symbol whose 3 most recent fiscal years are ALL explicitly marked unavailable
        isn't invisible to this gate. Live-confirmed 142 additional symbols recovered.
        Label-only.

        FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep, same fix as
        _get_unclassified_balance_sheet_symbols above): sanitize pretax_income to NULL when its
        row is `data_unavailable` so a leftover stray value can't count as "reported". Live-
        verified 6 additional symbols recovered, zero lost.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol,
                           CASE WHEN data_unavailable THEN NULL ELSE pretax_income END AS pretax_income,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(pretax_income) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_interest_expense_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported interest_expense in any of their 3 most recent fiscal years.

        Live audit 2026-08-18 ("no SEC data" goal): 927 of 1525 universe interest_coverage
        "missing_sec_data" rows are this case - not a loader gap. Two distinct real causes land
        in the same bucket: (1) a genuinely debt-free company that never had an interest expense
        line to report, and (2) a company that stopped itemizing interest expense as its own
        line - live-confirmed on AAPL, which reported real interest_expense every year through
        FY2023 ($3.9B) but has netted it into "other income/(expense)" starting FY2024, so its 3
        most recent fiscal years (2024-2026) are structurally NULL despite being a real, large,
        indebted borrower. Same "3 most recent years, not all-time history" windowing as
        _get_unclassified_balance_sheet_symbols() above, for the same reason: a company can
        permanently change what it itemizes partway through its filing history. Cached for the
        life of this loader instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - see
        _get_no_recent_operating_cash_flow_symbols' 2026-09-03 fix comment for the full
        mechanism and the NGG evidence this bug class was first found on, same fix applied
        identically here): `WHERE data_unavailable = FALSE` made a symbol whose 3 most recent
        fiscal years are ALL explicitly marked unavailable invisible to this "genuinely no
        recent X" gate. `fiscal_year > 0` keeps the ranking free of `_unavailable_marker`
        sentinel rows (456 confirmed live) while including real-fiscal-year unavailable ones.
        Label-only - never feeds a computed VALUE, only a reason string.

        FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep, same fix as
        _get_unclassified_balance_sheet_symbols above): sanitize interest_expense to NULL when
        its row is `data_unavailable` so a leftover stray value can't count as "reported".
        Live-verified 9 additional symbols recovered, zero lost.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol,
                           CASE WHEN data_unavailable THEN NULL ELSE interest_expense END AS interest_expense,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(interest_expense) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_interest_expense_symbols(self) -> frozenset[str]:
        """Symbols with at least one real (non-data_unavailable) annual_income_statement row,
        none of which ever carry a real nonzero interest_expense (either NULL, or a real
        reported $0) - a broader, full-history sibling of
        _get_no_recent_interest_expense_symbols() above for filers too recently IPO'd/listed
        to have accumulated the 3 consecutive real fiscal years that gate requires.

        FIX 2026-09-02 (goal: "keep the missing-data number going down" SEC/XBRL audit,
        continuation of [[fcf_yield_capex_never_tagged_reason_fixed_20260902]]). Of
        quality_metrics.interest_coverage's 167-row universe "missing_sec_data" residual, 145
        genuinely have no fiscal year, anywhere in their filing history, with both a real
        interest_expense and a real operating_income/pretax_income together. Live-sampled a
        chunk of those and found 96 have interest_expense NULL in every real row they have (not
        just their 3 most recent - many are recent IPOs/SPAC-mergers with only 1-2 real fiscal
        years on file, e.g. AARD, ADVB, AMBQ, BIOT - the exact same "too new for a 3-year
        window" gap already called out in _get_blank_check_symbols()'s own docstring, applied
        here to a different gate), plus another 14 that report a real $0 (same "treat a real
        zero the same as NULL - it means the same real-world fact" precedent already applied to
        _get_no_recent_revenue_symbols()'s 2026-08-19 fix). 87 of the 167 residual rows matched
        this broader, unified check when live-verified directly against quality_metrics.

        Deliberately additive, not a replacement for _get_no_recent_interest_expense_symbols()
        above (only one call site uses either gate; combined with `or` there) - keeps that
        gate's existing, already-tested 3-consecutive-year confidence bar for the symbols that
        do have enough history, while this one only fires for symbols that plainly never report
        a real interest expense across everything currently on file, an even stronger signal
        precisely because the window isn't fixed-length. Live spot-checked against known
        heavily-indebted borrowers (AAPL, TSLA, T, VZ, F, GE) - none matched. Cached for the
        life of this loader instance; this query runs once per pipeline run, not once per
        symbol.

        FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep, same fix as
        _get_unclassified_balance_sheet_symbols above): a stray non-NULL interest_expense
        leftover on a `data_unavailable = TRUE` row counted as "reported" in this FILTER,
        wrongly excluding the symbol. Sanitize to NULL first. Live-verified 9 additional
        symbols recovered (AEVA/AVLN/EMAT/HAWK/HDRN/HYPR/MAZE/RKTO/WYFI), zero lost.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_income_statement
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1
                   AND COUNT(*) FILTER (
                       WHERE (CASE WHEN data_unavailable THEN NULL ELSE interest_expense END) IS NOT NULL
                         AND (CASE WHEN data_unavailable THEN NULL ELSE interest_expense END) != 0
                   ) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_debt_components_symbols(self) -> frozenset[str]:
        """Symbols with NO debt component (long_term_debt, short_term_debt,
        operating_lease_liability, finance_lease_liability) reported in any of their 3 most
        recent fiscal years - i.e. sec_valuations.total_debt is structurally None for them, not
        a loader gap.

        Live audit 2026-08-18 ("no SEC data" goal): 440 of the universe's total_debt
        "missing_sec_data" rows are this case. Unlike current_ratio/quick_ratio (dominated by
        banks/REITs), this bucket is a genuine mixed bag - SPACs ("Blank Checks", 127), pre-
        revenue pharma/biotech (90), and small tech/services companies (~70) alongside a smaller
        bank/REIT contingent (~40) - most of these companies simply carry no debt at all, not a
        different accounting model for a specific entity type. Same "3 most recent years, not
        all-time history" windowing as the sibling checks above. Cached for the life of this
        loader instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - see
        _get_no_recent_operating_cash_flow_symbols' 2026-09-03 fix comment for the full
        mechanism, same fix applied identically here): `fiscal_year > 0` replaces
        `data_unavailable = FALSE` so a symbol whose 3 most recent fiscal years are ALL
        explicitly marked unavailable isn't invisible to this gate. Label-only.

        FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep, same fix as
        _get_unclassified_balance_sheet_symbols above): sanitize each field to NULL when its
        row is `data_unavailable` so a leftover stray value can't count as "reported".
        Live-verified 7 additional symbols recovered, zero lost.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol,
                           CASE WHEN data_unavailable THEN NULL ELSE long_term_debt END AS long_term_debt,
                           CASE WHEN data_unavailable THEN NULL ELSE short_term_debt END AS short_term_debt,
                           CASE WHEN data_unavailable THEN NULL ELSE operating_lease_liability END AS operating_lease_liability,
                           CASE WHEN data_unavailable THEN NULL ELSE finance_lease_liability END AS finance_lease_liability,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(long_term_debt) = 0 AND COUNT(short_term_debt) = 0
                   AND COUNT(operating_lease_liability) = 0 AND COUNT(finance_lease_liability) = 0
                   AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_debt_components_symbols(self) -> frozenset[str]:
        """Full-history sibling of _get_no_recent_debt_components_symbols() above - see
        _get_never_tagged_net_income_symbols()'s docstring for the general pattern (windowed
        gate requires exactly 3 real fiscal years, missing recent IPOs/SPAC-mergers with fewer
        real years where no debt component is nonetheless genuinely ever reported).

        FIX 2026-09-02 (goal: "keep the missing-data number going down" SEC/XBRL audit): unlike
        the other never-tagged siblings added earlier this session (each recovering a modest
        double-digit slice), this one is the single largest win found this session - the debt-
        components gate turns out to be the dominant blocker for several fields at once.
        Live-verified against quality_metrics/value_metrics: debt_to_equity 115 of 132 (87%),
        roce_pct 115 of 198 (58%), roic_pct 97 of 215 (45%), total_debt 33 of 49 (67%) of their
        respective "missing_sec_data" residual rows recovered. Deliberately NOT wired into
        ev_revenue_unavailable_reason/ev_ebitda_unavailable_reason (value_metrics) despite also
        calling _get_no_recent_debt_components_symbols() - live-checked and only 14 of 232 /
        1 of 49 rows there overlap this gate, consistent with load_sec_valuations.py's own EV
        computation treating a missing total_debt as 0 rather than blocking (see
        [[interest_coverage_and_pe_ratio_reason_gates_fixed_20260902]] for the fuller trace of
        why EV's real blocker is elsewhere and not yet safely diagnosed). Cached for the life
        of this loader instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep, same fix as
        _get_unclassified_balance_sheet_symbols above): sanitize each field to NULL when its
        row is `data_unavailable` so a leftover stray value can't count as "reported".
        Live-verified 10 additional symbols recovered, zero lost.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_balance_sheet
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1
                   AND COUNT(CASE WHEN data_unavailable THEN NULL ELSE long_term_debt END) = 0
                   AND COUNT(CASE WHEN data_unavailable THEN NULL ELSE short_term_debt END) = 0
                   AND COUNT(CASE WHEN data_unavailable THEN NULL ELSE operating_lease_liability END) = 0
                   AND COUNT(CASE WHEN data_unavailable THEN NULL ELSE finance_lease_liability END) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_revenue_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported revenue in any of their 3 most recent fiscal years -
        i.e. structurally pre-revenue, not a loader gap.

        Live audit 2026-08-18 ("no SEC data" goal): ebitda_margin can be None even when ebitda
        itself is a real, computed value (e.g. a real negative EBITDA), because ebitda_margin =
        ebitda / revenue has no fallback denominator (unlike operating_margin, which falls back
        to total_assets) - live-confirmed 511 universe symbols with ebitda present but
        ebitda_margin "missing_sec_data"; of those, 69 have genuinely never reported revenue in
        their 3 most recent fiscal years (dominated by SPACs and pre-revenue clinical-stage
        biotech/pharma, e.g. ABVX/Abivax). The remaining ~440 have real revenue on file in a
        different fiscal year than the one quality_row's balance-sheet anchor selected (e.g.
        AFYA/AIB/AKTS) - a distinct fiscal-year-anchor-selection gap, not this "structurally no
        revenue" case, so deliberately NOT covered by this windowed check. Cached for the life
        of this loader instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-08-19 (pb_ratio negative_book_value follow-up): the HAVING clause was
        `COUNT(revenue) = 0`, which only counts NULL revenue - a company that reports a real,
        correctly-extracted $0.00 revenue for all 3 recent fiscal years (common for pre-revenue
        clinical-stage biotechs/SPACs, e.g. DFTX/DMRA/GNPX/IMVT - the SEC filing genuinely says
        "$0", not "not reported") is NOT NULL, so it silently fell through to the generic
        "missing_sec_data" for ps_ratio/ev_revenue/ebitda_margin/gross_margin alike, even though
        nothing is missing. Live-confirmed 245 universe symbols hit this exact zero-vs-null gap
        (same bug class as the total_debt/roic_pct genuine-zero fixes elsewhere in this file).
        Now treats NULL and real 0 as equivalent "no revenue" for this windowed check.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - see
        _get_no_recent_operating_cash_flow_symbols' 2026-09-03 fix comment for the full
        mechanism, same fix applied identically here): `fiscal_year > 0` replaces
        `data_unavailable = FALSE` so a symbol whose 3 most recent fiscal years are ALL
        explicitly marked unavailable isn't invisible to this gate. Label-only.

        FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep, same fix as
        _get_unclassified_balance_sheet_symbols above): sanitize revenue to NULL when its row
        is `data_unavailable` so a leftover stray value can't count as "reported". Live-
        verified 8 additional symbols recovered, zero lost.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE revenue END AS revenue,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(*) FILTER (WHERE revenue IS NOT NULL AND revenue != 0) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_revenue_available_elsewhere_symbols(self) -> frozenset[str]:
        """Symbols with a real (non-NULL, non-zero) revenue in at least one available
        annual_income_statement fiscal year - the direct positive counterpart to
        _get_no_recent_revenue_symbols() above, not its logical negation. Same "anchor-year
        fiscal mismatch" gate pattern as _get_net_income_available_elsewhere_symbols().

        FIX 2026-09-02 (quality_row_db anchor-year investigation, goal: "keep the missing-
        data number going down"): _get_no_recent_revenue_symbols()'s own docstring already
        documented this exact residual back on 2026-08-18 ("~440 [ebitda_margin symbols] have
        real revenue on file in a different fiscal year than the one quality_row's
        balance-sheet anchor selected ... a distinct fiscal-year-anchor-selection gap ...
        deliberately NOT covered by this windowed check") but never wired a fix for it -
        ebitda_margin/gross_margin/asset_turnover all fell to generic "missing_sec_data" for
        this population ever since. Same root cause as net_income's anchor-year mismatch:
        quality_row_db's revenue column is joined to annual_income_statement via an EXACT
        fiscal_year match to the balance-sheet anchor row, so a real revenue value one year
        off from that anchor is invisible to it even though the symbol clearly has one.
        Cached for the life of this loader instance; this query runs once per pipeline run,
        not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_income_statement
                WHERE data_unavailable = FALSE
                GROUP BY symbol
                HAVING COUNT(*) FILTER (WHERE revenue IS NOT NULL AND revenue != 0) >= 1
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_zero_revenue_anchor_symbols(self) -> frozenset[str]:
        """Symbols whose SEC-selected anchor fiscal year (same tier/fiscal_year-DESC ordering
        load_sec_valuations.py's own income-statement query uses: prefer a row with revenue OR
        earnings_per_share OR net_income present, then most recent fiscal_year) reports a real
        $0.00 revenue for THAT specific year - distinct from _get_no_recent_revenue_symbols()
        above, which requires zero/null revenue across all 3 most recent years. A company can
        have real revenue in prior years yet a genuine $0 anchor year (e.g. a one-off wind-down
        period, a pre-revenue clinical-stage company between commercial products); EV/Revenue
        and P/S are undefined for that period regardless of other years' history, same "not a
        meaningful ratio" class as ev_ebitda's unprofitable_stock treatment of ebitda <= 0.

        FIX 2026-09-02 (goal: "no SEC data" audit continuation, same session as the
        negative_enterprise_value fix above): load_sec_valuations.py's ttm_revenue is exactly
        this anchor row's revenue (its own one-row-back fallback only fires when revenue is
        NULL, never when it's a real 0, so it never rescues this case) - live-confirmed 47 of
        259 (18%) universe ev_revenue "missing_sec_data" residual rows are this exact case
        (e.g. AREC: 2025 anchor revenue=$0.00 despite $11.8M and $34K in the two prior years).
        Cached for the life of this loader instance; this query runs once per pipeline run,
        not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM (
                    SELECT DISTINCT ON (symbol) symbol, revenue
                    FROM annual_income_statement
                    WHERE data_unavailable IS NOT TRUE
                    ORDER BY symbol,
                             (CASE WHEN revenue IS NOT NULL OR earnings_per_share IS NOT NULL
                                        OR net_income IS NOT NULL THEN 0 ELSE 1 END),
                             fiscal_year DESC
                ) anchor
                WHERE revenue = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_revenue_symbols(self) -> frozenset[str]:
        """Full-history sibling of _get_no_recent_revenue_symbols() above - same recent-IPO/
        SPAC-merger/thin-history blind spot already fixed for stockholders_equity/net_income/
        total_assets/debt_components elsewhere in this file (the windowed gate requires exactly
        3 real fiscal years; a symbol with fewer real years that has genuinely never reported a
        real, nonzero revenue anywhere in its (shorter) history falls through it).

        FIX 2026-09-02 (goal: "get all the data we need" audit continuation, live trace of the
        ev_revenue/ps_ratio residual after the negative_enterprise_value/zero_revenue_anchor
        fixes above): of 98 universe ev_revenue "missing_sec_data" residual rows post-backfill,
        44 (45%) genuinely have zero real revenue anywhere in annual_income_statement (thin
        filing history, mostly recent IPOs/SPAC-mergers/pre-revenue biotech) - the exact same
        "no revenue reported" fact _get_no_recent_revenue_symbols() already labels, just not
        caught by its exactly-3-years requirement. Reuses that same "no_revenue_reported"
        reason string rather than inventing a new one - it's the identical underlying fact,
        just a broader detection window. Cached for the life of this loader instance; this
        query runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_income_statement
                WHERE data_unavailable IS NOT TRUE
                GROUP BY symbol
                HAVING COUNT(*) >= 1
                   AND COUNT(*) FILTER (WHERE revenue IS NOT NULL AND revenue != 0) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_eps_absent_from_anchor_year_symbols(self) -> frozenset[str]:
        """Symbols whose SEC-selected anchor fiscal year (same tier/fiscal_year-DESC ordering
        as _get_revenue_absent_from_anchor_year_symbols() below) has NULL earnings_per_share -
        never tagged that specific year - even though a real EPS value exists somewhere else in
        the symbol's history.

        FIX 2026-09-05 (goal: "SEC/XBRL missing data to zero" audit): pe_ratio_reason's final
        "found a real historical EPS but pe_ratio still came out None" branch was landing on the
        generic "missing_sec_data" for this exact case (live-confirmed BRK.A/BRK.B: EPS tagged
        every year through some historical year at real, large per-share values - Berkshire's
        actual per-Class-A-share income - but NULL in every fiscal year since; net_income is
        still tagged every year, so this is a distinct, narrower gap than net_income itself
        being absent) - same "label-only, no value recomputed" discipline as
        _get_revenue_absent_from_anchor_year_symbols() (a 2+-year-stale EPS would produce a
        misleading current-period P/E, so this doesn't fall back to computing one). Cached for
        the life of this loader instance; this query runs once per pipeline run, not once per
        symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM (
                    SELECT DISTINCT ON (symbol) symbol, earnings_per_share
                    FROM annual_income_statement
                    WHERE data_unavailable IS NOT TRUE
                    ORDER BY symbol,
                             (CASE WHEN revenue IS NOT NULL OR earnings_per_share IS NOT NULL
                                        OR net_income IS NOT NULL THEN 0 ELSE 1 END),
                             fiscal_year DESC
                ) anchor
                WHERE anchor.earnings_per_share IS NULL
                  AND anchor.symbol IN (
                      SELECT symbol FROM annual_income_statement
                      WHERE data_unavailable IS NOT TRUE AND earnings_per_share IS NOT NULL
                      GROUP BY symbol
                  )
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_revenue_absent_from_anchor_year_symbols(self) -> frozenset[str]:
        """Symbols whose SEC-selected anchor fiscal year (same tier/fiscal_year-DESC ordering
        as _get_zero_revenue_anchor_symbols() above) has NULL revenue - never tagged that
        specific year - even though a real, nonzero revenue value exists somewhere else in the
        symbol's history. Distinct from _get_zero_revenue_anchor_symbols() (a real $0.00 anchor
        value) and from _get_never_tagged_revenue_symbols() (no real revenue anywhere, ever).

        FIX 2026-09-02 (goal: "get all the data we need" audit continuation): live-confirmed 54
        of 98 universe ev_revenue residual rows are this case - mostly clinical-stage biotechs
        (ABOS, MTNB, PVLA, ...) whose "revenue" is lumpy licensing/collaboration income, real in
        some years and genuinely untagged (not a real $0, just absent) in others, including the
        current anchor year. Deliberately does NOT fall back to computing ev_revenue/ps_ratio
        from that older revenue figure - a 2+-year-stale collaboration payment would produce a
        misleading current-period ratio, the same "don't compute a number from data likely to be
        wrong" discipline as every other reason in this file. Label-only: this changes which
        REASON a null ev_revenue/ps_ratio gets, never what VALUE they get. Cached for the life
        of this loader instance; this query runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM (
                    SELECT DISTINCT ON (symbol) symbol, revenue
                    FROM annual_income_statement
                    WHERE data_unavailable IS NOT TRUE
                    ORDER BY symbol,
                             (CASE WHEN revenue IS NOT NULL OR earnings_per_share IS NOT NULL
                                        OR net_income IS NOT NULL THEN 0 ELSE 1 END),
                             fiscal_year DESC
                ) anchor
                WHERE anchor.revenue IS NULL
                  AND anchor.symbol IN (
                      SELECT symbol FROM annual_income_statement
                      WHERE data_unavailable IS NOT TRUE AND revenue IS NOT NULL AND revenue != 0
                      GROUP BY symbol
                  )
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_preferred_or_debt_security_symbols(self) -> frozenset[str]:
        """Symbols whose own ticker is a preferred stock, subordinated debenture/note, or
        depositary share - not the filer's common equity - even though annual_income_statement/
        annual_balance_sheet carries real net_income/earnings_per_share/stockholders_equity for
        them (these child tickers share their parent company's CIK, so the SAME SEC financial
        facts get attached to both the common ticker and every preferred/debt ticker trading
        under that filer).

        FIX 2026-09-04 (goal: "under 6k the right way" sweep, pe_ratio/pb_ratio/ps_ratio
        missing_sec_data follow-up): live-confirmed AFGB/DTB/DUKB/BHFAL/KMPB/DCBG/MNSBP and
        siblings have zero sec_valuations row at all (no market-equity computation was ever
        attempted for them) yet a real, positive, non-NULL annual EPS on file - e.g. DUKB
        (Duke Energy's 5.625% Junior Subordinated Debentures) shows FY2025 net_income=$4.968B,
        earnings_per_share=$6.31, both belonging to Duke Energy's COMMON stock, not this
        fixed-income instrument - so pe_ratio_reason's `eps_row is not None` branch landed on
        the generic "missing_sec_data" as if this were a recoverable gap. A P/E, P/B, or P/S
        ratio computed from a preferred/debenture's own market price against its parent's
        common-equity EPS/book-value/revenue-per-share would be actively wrong, not just
        missing - the correct outcome is "not applicable", the same class as
        unprofitable_stock/reit_special_entity elsewhere in this file, not a fixable gap.
        Deliberately does NOT touch dividend_yield: a preferred/debenture's fixed coupon
        divided by its own market price IS a real, meaningful yield figure.

        Identified via stock_symbols.security_name text (SEC's own official title for the
        listing), not SIC code or price level - a preferred/debenture always states its own
        instrument type there (e.g. "American Financial Group, Inc. 5.875% Subordinated
        Debentures due 2059"), unlike a REIT/trust whose entity-level SIC code doesn't
        distinguish common from preferred. Cached for the life of this loader instance.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM stock_symbols
                WHERE security_name ILIKE '%%Subordinated Debenture%%'
                   OR security_name ILIKE '%%Subordinated Note%%'
                   OR security_name ILIKE '%%Junior Subordinated%%'
                   OR security_name ILIKE '%%Depositary Share%%'
                   OR security_name ILIKE '%%Preferred Stock%%'
                   OR security_name ILIKE '%%Preferred Share%%'
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_total_assets_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported a real (non-NULL, positive) total_assets in any of
        their 3 most recent fiscal years - i.e. asset_turnover is structurally None for them,
        not a loader gap.

        Live audit 2026-09-02 (goal: "no SEC data" audit continuation, asset_turnover follow-up
        to the debt_to_equity/total_debt mislabeled-genuine-gap fixes): 53 of 294 universe
        asset_turnover "missing_sec_data" rows are this case. Sampled live: overwhelmingly
        foreign private issuers filing 20-F under IFRS (ABEV, AZUL, BBD/BBDO, BBAR, CCU, CIG,
        CRESY, EC, ERIC, GGB, SBS, SUZ, TIMB) - the same "SEC companyfacts convenience API
        doesn't expose this concept the way our extraction expects for non-US-GAAP filers"
        pattern already established for foreign_private_issuer_shares_unavailable/
        foreign_private_issuer_no_quarterly_filings elsewhere in this file, just never given
        its own gate for total_assets specifically. Same "3 most recent years, not all-time
        history" windowing as the sibling checks above. Cached for the life of this loader
        instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - see
        _get_no_recent_operating_cash_flow_symbols' 2026-09-03 fix comment for the full
        mechanism, same fix applied identically here): `fiscal_year > 0` replaces
        `data_unavailable = FALSE` so a symbol whose 3 most recent fiscal years are ALL
        explicitly marked unavailable isn't invisible to this gate. Label-only.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE total_assets END AS total_assets,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(*) FILTER (WHERE total_assets IS NOT NULL AND total_assets > 0) = 0
                   AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_total_assets_symbols(self) -> frozenset[str]:
        """Full-history sibling of _get_no_recent_total_assets_symbols() above - see
        _get_never_tagged_net_income_symbols()'s docstring for the general pattern. Same
        "real, positive value" requirement as the windowed gate (a real $0 total_assets isn't
        meaningful either). Live-verified 10 of roa's 70 universe "missing_sec_data" rows
        match this alone (28 combined with _get_never_tagged_net_income_symbols() above), and
        11 of debt_to_assets' 31 combined with _get_never_tagged_total_liabilities_symbols().
        Cached for the life of this loader instance; this query runs once per pipeline run,
        not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_balance_sheet
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1
                   AND COUNT(*) FILTER (WHERE total_assets IS NOT NULL AND total_assets > 0) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_current_assets_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported a real (non-NULL, positive) current_assets in any of
        their 3 most recent fiscal years - i.e. current_ratio/quick_ratio are structurally None
        for them, not a loader gap. Same shape as _get_no_recent_total_assets_symbols() above,
        for current_ratio/quick_ratio's own current_assets input instead of total_assets.

        FIX 2026-09-03 (SEC/XBRL missing-data sweep): current_ratio/quick_ratio's reason chains
        never checked either of their two structural inputs (current_assets/current_liabilities)
        against a no-data gate at all, unlike every other ratio in this file - a genuine "never
        wired up" gap, not a left-behind sibling asymmetry. Live-confirmed 33 of 64 universe
        current_ratio/quick_ratio "missing_sec_data" rows have current_assets or
        current_liabilities in one of the 4 new gates this fix adds.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - see
        _get_no_recent_operating_cash_flow_symbols' 2026-09-03 fix comment for the full
        mechanism, same fix applied identically here): `fiscal_year > 0` replaces
        `data_unavailable = FALSE` so a symbol whose 3 most recent fiscal years are ALL
        explicitly marked unavailable isn't invisible to this gate. Label-only.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE current_assets END AS current_assets,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(*) FILTER (WHERE current_assets IS NOT NULL AND current_assets > 0) = 0
                   AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_current_assets_symbols(self) -> frozenset[str]:
        """Full-history sibling of _get_no_recent_current_assets_symbols() above - see
        _get_never_tagged_net_income_symbols()'s docstring for the general pattern."""
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_balance_sheet
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1
                   AND COUNT(*) FILTER (WHERE current_assets IS NOT NULL AND current_assets > 0) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_current_liabilities_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported a real (non-NULL, positive) current_liabilities in any
        of their 3 most recent fiscal years - sibling of
        _get_no_recent_current_assets_symbols() above for current_ratio/quick_ratio's other
        structural input.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - see
        _get_no_recent_operating_cash_flow_symbols' 2026-09-03 fix comment for the full
        mechanism, same fix applied identically here): `fiscal_year > 0` replaces
        `data_unavailable = FALSE` so a symbol whose 3 most recent fiscal years are ALL
        explicitly marked unavailable isn't invisible to this gate. Label-only.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE current_liabilities END AS current_liabilities,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(*) FILTER (WHERE current_liabilities IS NOT NULL AND current_liabilities > 0) = 0
                   AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_current_liabilities_symbols(self) -> frozenset[str]:
        """Full-history sibling of _get_no_recent_current_liabilities_symbols() above - see
        _get_never_tagged_net_income_symbols()'s docstring for the general pattern."""
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_balance_sheet
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1
                   AND COUNT(*) FILTER (WHERE current_liabilities IS NOT NULL AND current_liabilities > 0) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_cash_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported a real (non-NULL, positive) cash_and_equivalents in
        any of their 3 most recent fiscal years - i.e. total_cash/cash_per_share are
        structurally None for them, not a loader gap. Same shape as
        _get_no_recent_current_assets_symbols() above, for total_cash's own cash_and_equivalents
        input instead of current_assets.

        FIX 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction, live static-outlier
        sweep): total_cash_unavailable_reason/cash_per_share_unavailable_reason only ever
        reused sec_valuations.reason (a real, but narrower, "why did the whole valuation row
        fail" signal) - unlike every other balance-sheet-input field in this file, they never
        had their own dedicated no-data gate for cash_and_equivalents specifically. Live-
        confirmed FDXF (FedEx Freight Holding Company, a real, large recently-spun-off S&P
        500-flagged filer with real total_assets $6.88B FY2026/$5.02B FY2025) has NULL
        cash_and_equivalents across its entire filing history despite a real, non-trivial
        balance sheet - a genuine "never tagged" gap, not covered by the sec_valuations.reason
        reuse since that row's OTHER valuation metrics compute fine.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE cash_and_equivalents END AS cash_and_equivalents,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(*) FILTER (WHERE cash_and_equivalents IS NOT NULL AND cash_and_equivalents > 0) = 0
                   AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_cash_symbols(self) -> frozenset[str]:
        """Full-history sibling of _get_no_recent_cash_symbols() above - see
        _get_never_tagged_net_income_symbols()'s docstring for the general pattern."""
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_balance_sheet
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1
                   AND COUNT(*) FILTER (
                       WHERE (CASE WHEN data_unavailable THEN NULL ELSE cash_and_equivalents END) IS NOT NULL
                         AND (CASE WHEN data_unavailable THEN NULL ELSE cash_and_equivalents END) > 0
                   ) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_net_income_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported net_income in any of their 3 most recent fiscal
        years - i.e. roe/roa are structurally None for them, not a loader gap.

        Live audit 2026-09-02 (goal: "no SEC data" audit continuation, same fix class as
        debt_to_equity/asset_turnover/roic_pct/roce_pct above): roe/roa's compute blocks
        require BOTH net_income and their own denominator (stockholders_equity/total_assets)
        to be non-None, but their reason blocks were 100% generic "missing_sec_data" with no
        gating at all, unlike every sibling ratio. Sampled live: unlike revenue/total_assets,
        a filer missing net_income for 3 straight years is rare and usually a genuine SEC
        extraction/tagging gap rather than a structural business fact - callers should not
        assume this set is large. Same "3 most recent years, not all-time history" windowing
        as the sibling checks above. Cached for the life of this loader instance; this query
        runs once per pipeline run, not once per symbol.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - see
        _get_no_recent_operating_cash_flow_symbols' 2026-09-03 fix comment for the full
        mechanism, same fix applied identically here): `fiscal_year > 0` replaces
        `data_unavailable = FALSE` so a symbol whose 3 most recent fiscal years are ALL
        explicitly marked unavailable isn't invisible to this gate. Label-only.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE net_income END AS net_income,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(net_income) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_net_income_symbols(self) -> frozenset[str]:
        """Full-history sibling of _get_no_recent_net_income_symbols() above - symbols with at
        least one real annual_income_statement row, none of which ever carry a real net_income
        value, regardless of how many real fiscal years they have on file.

        FIX 2026-09-02 (goal: "keep the missing-data number going down" SEC/XBRL audit,
        continuation of [[interest_coverage_and_pe_ratio_reason_gates_fixed_20260902]]'s
        never-tagged-full-history pattern, applied here to net_income): the windowed gate
        above requires exactly 3 real fiscal years, missing recent IPOs/SPAC-mergers with only
        1-2 real years on file where net_income is nonetheless genuinely never reported. Live-
        confirmed this, OR'd with _get_never_tagged_stockholders_equity_symbols()/
        _get_never_tagged_total_assets_symbols() below, roughly triples roe/roa's residual
        "missing_sec_data" recovery versus either gate alone (roe 9->27 of 68, roa 10->28 of
        70, live-verified against quality_metrics directly). Cached for the life of this
        loader instance; this query runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_income_statement
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1 AND COUNT(net_income) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_net_income_available_elsewhere_symbols(self) -> frozenset[str]:
        """Symbols with a real (non-NULL) net_income in at least one available
        annual_income_statement fiscal year - the direct positive counterpart to
        _get_never_tagged_net_income_symbols() above, not its logical negation.

        FIX 2026-09-02 (quality_row_db anchor-year investigation, goal: "keep the missing-
        data number going down"): roe/roa/net_margin/sustainable_growth_rate's reason blocks
        used to infer "net_income exists somewhere, just not for this specific anchor year"
        from "symbol is in neither _get_no_recent_net_income_symbols() nor
        _get_never_tagged_net_income_symbols()" - but that inference is wrong for a symbol
        with ZERO available annual_income_statement rows at all (both of those gates require
        COUNT(*) >= 1/3 real rows to fire, so a symbol with none slips through un-flagged by
        either while genuinely having no net_income data anywhere, not an anchor-year
        mismatch). Caught by test_quality_metrics_never_tagged_full_history_reason_sweep_
        20260902.py's test_symbols_not_in_any_gate_keep_generic_reason regression test. This
        gate answers the actual question directly instead of inferring it. Cached for the
        life of this loader instance; this query runs once per pipeline run, not once per
        symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_income_statement
                WHERE data_unavailable = FALSE
                GROUP BY symbol
                HAVING COUNT(net_income) >= 1
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_operating_income_available_elsewhere_symbols(self) -> frozenset[str]:
        """Symbols with a real (non-NULL) operating_income in at least one available
        annual_income_statement fiscal year - same "anchor-year fiscal mismatch" gate
        pattern as _get_net_income_available_elsewhere_symbols()/
        _get_revenue_available_elsewhere_symbols().

        FIX 2026-09-02 (quality_row_db anchor-year investigation, goal: "keep the missing-
        data number going down" - the "still OPEN" residual flagged in that investigation's
        own memory note): operating_income_for_margin only ever looks at the anchor row's
        own operating_income, falling back within THAT SAME fiscal year to the EBIT
        approximation (pretax_income + interest_expense) - unlike net_income/revenue/OCF/FCF,
        it never searches a different fiscal year for a real operating_income value. Live-
        confirmed 39 active-universe (quality_metrics) symbols have operating_income NULL AND
        pretax_income NULL in their anchor fiscal year (so operating_income_for_margin comes
        back None) yet have a real operating_income value in some other annual_income_statement
        fiscal year - the same class of gap already fixed for net_income/revenue, just a much
        smaller residual for this field. Cached for the life of this loader instance; this
        query runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_income_statement
                WHERE data_unavailable = FALSE
                GROUP BY symbol
                HAVING COUNT(operating_income) >= 1
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_operating_income_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported operating_income in any of their 3 most recent
        fiscal years - i.e. operating_margin/interest_coverage are structurally None for them
        for a reason distinct from the REIT/tonnage-tax no-tax-concept case
        (_get_no_tax_concept_symbols) and the zero-revenue commodity/crypto-trust case
        (_get_no_recent_revenue_symbols): a real, revenue-generating filer whose income
        statement goes straight from revenue/costs to net income with no distinct "operating
        income" subtotal line ever itemized (common among simplified-format smaller filers and
        some financials). Same "3 most recent years, not all-time history" windowing as the
        sibling checks elsewhere in this file - a filer can permanently change what it itemizes
        partway through its history.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction): operating_margin/
        interest_coverage's reason chains had no gate at all for this case before this fix -
        every check upstream of the generic "missing_sec_data" fallback (implausible_ratio,
        reit_special_entity, operating_income_absent_from_anchor_year, no_revenue_reported) is
        scoped to a different root cause. Live-confirmed 43 active-universe symbols recovered
        from "missing_sec_data" to this specific reason. Cached for the life of this loader
        instance; this query runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE operating_income END AS operating_income,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(operating_income) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_operating_income_symbols(self) -> frozenset[str]:
        """Full-history sibling of _get_no_recent_operating_income_symbols() above - see
        _get_never_tagged_interest_expense_symbols()'s docstring for the general pattern
        (windowed gate requires exactly 3 real fiscal years, missing recent IPOs/SPAC-mergers
        with fewer real years where operating_income is nonetheless genuinely never tagged).

        FIXED 2026-09-03: added alongside _get_no_recent_operating_income_symbols() above -
        see that method's docstring. Cached for the life of this loader instance; this query
        runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_income_statement
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1
                   AND COUNT(*) FILTER (
                       WHERE (CASE WHEN data_unavailable THEN NULL ELSE operating_income END) IS NOT NULL
                   ) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_total_liabilities_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported total_liabilities in any of their 3 most recent
        fiscal years - i.e. debt_to_assets is structurally None for them, not a loader gap.

        Live audit 2026-09-02 (goal: "no SEC data" audit continuation, debt_to_assets follow-up
        to the debt_to_equity fix above): debt_to_assets = total_liabilities / total_assets,
        with no reason gating at all before this fix. Same "3 most recent years, not all-time
        history" windowing as the sibling checks above. Cached for the life of this loader
        instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - see
        _get_no_recent_operating_cash_flow_symbols' 2026-09-03 fix comment for the full
        mechanism, same fix applied identically here): `fiscal_year > 0` replaces
        `data_unavailable = FALSE` so a symbol whose 3 most recent fiscal years are ALL
        explicitly marked unavailable isn't invisible to this gate. Label-only.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE total_liabilities END AS total_liabilities,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(total_liabilities) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_total_liabilities_symbols(self) -> frozenset[str]:
        """Full-history sibling of _get_no_recent_total_liabilities_symbols() above - see
        _get_never_tagged_net_income_symbols()'s docstring for the general pattern (windowed
        gate requires exactly 3 real fiscal years, missing recent IPOs/SPAC-mergers with fewer
        real years where total_liabilities is nonetheless genuinely never reported). Live-
        verified 11 of debt_to_assets' 31 universe "missing_sec_data" rows match this OR'd with
        _get_never_tagged_total_assets_symbols() below. Cached for the life of this loader
        instance; this query runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_balance_sheet
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1 AND COUNT(total_liabilities) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_operating_cash_flow_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported operating_cash_flow in any of their 3 most recent
        fiscal years (in a row not itself flagged data_unavailable) - a genuine structural gap,
        not a loader gap.

        Live audit 2026-09-02 (goal: "no SEC data" audit continuation): operating_cash_flow is
        read directly off the anchor row `fetch_incremental()` selects, with NO cross-year
        fallback attempted (deliberately - see the dividends_paid same-year-only rescue comment
        above: "operating_cash_flow/free_cash_flow correctly stay None either way since those
        fields really are NULL in that row"). Only 43 of 125 universe operating_cash_flow
        "missing_sec_data" rows (34%) are symbols with genuinely no OCF anywhere in their 3 most
        recent fiscal years - the majority of the remaining rows have OCF in an off-anchor year
        instead (a real anchor-row-selection gap, deliberately NOT fixed this pass - see
        [[debt_to_equity_asset_turnover_missing_sec_data_mislabel_fixed_20260902]] for why: fixing
        that would change computed VALUES via cross-year mixing, not just relabel). This gate
        only covers the smaller, unambiguous "genuinely no OCF at all" slice. Cached for the
        life of this loader instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction): live-confirmed NGG
        (National Grid plc, $58B market cap utility) has real net_income/total_assets every
        recent year but ALL 3 of its most recent annual_cash_flow rows are explicitly
        `data_unavailable = TRUE, reason = 'incomplete_sec_filing_cashflow'` - the old `WHERE
        data_unavailable = FALSE` filter meant such a symbol contributes ZERO rows to `recent`,
        can never satisfy `COUNT(*) = 3`, and was invisible to this gate despite the true cause
        already being known and stored right there in annual_cash_flow.reason (same "reason
        already computed upstream but discarded" bug class as
        [[short_interest_pct_reason_propagation_fixed_20260903]]). "Explicitly marked
        unavailable" is at least as strong a "no OCF reported" signal as "reported but the
        column happened to be NULL", so filtering out only the `fiscal_year = 0` sentinel-
        marker rows (`_unavailable_marker`'s own convention - 456 such rows confirmed live)
        instead of every unavailable row keeps the ranking uncorrupted by placeholders while
        including real-fiscal-year unavailable ones. Live-confirmed zero rows lost from the old
        gate's result set, 25+ newly recovered. Label-only (this helper never feeds a computed
        VALUE, only a reason string) - the broader inclusion carries no risk of a wrong number.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE operating_cash_flow END AS operating_cash_flow,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_cash_flow
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(operating_cash_flow) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_free_cash_flow_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported free_cash_flow in any of their 3 most recent fiscal
        years (in a row not itself flagged data_unavailable) - a genuine structural gap, not a
        loader gap.

        Live audit 2026-09-02 (goal: "no SEC data" audit continuation, same bug class as
        _get_no_recent_operating_cash_flow_symbols() just above): free_cash_flow is read
        directly off the anchor row `fetch_incremental()` selects (quality_row[14]), with NO
        cross-year fallback attempted - same anchor-only read as operating_cash_flow. Live-
        confirmed 228 of 424 universe free_cash_flow "missing_sec_data" rows (54%) are symbols
        with genuinely no FCF anywhere in their 3 most recent fiscal years; the rest have FCF in
        an off-anchor year instead (deliberately NOT fixed this pass, same anchor-row-selection
        reasoning as OCF's gate above). Also reused by fcf_to_net_income (which divides by
        free_cash_flow) and fcf_margin (which divides free_cash_flow by revenue - see
        fcf_margin_unavailable_reason for the revenue-side companion gate). Cached for the life
        of this loader instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction, following the
        accruals_ratio/NGG investigation - see _get_no_recent_operating_cash_flow_symbols'
        sibling fix comment just below for the full mechanism, identical bug here): the old
        `WHERE data_unavailable = FALSE` filter meant a symbol whose 3 most recent
        annual_cash_flow rows are ALL explicitly `data_unavailable = TRUE` (e.g. NGG's
        `incomplete_sec_filing_cashflow` every year 2022-2025) contributed ZERO rows to
        `recent`, so it could never satisfy `COUNT(*) = 3` and was invisible to this gate -
        even though "explicitly marked unavailable" is at least as strong a "no FCF reported"
        signal as "reported but the column happened to be NULL". Filtering out only the
        `fiscal_year = 0` sentinel-marker rows (`_unavailable_marker`'s own convention -
        confirmed live: 456 such rows exist in this table) instead keeps the ranking
        uncorrupted by placeholder rows while including real-fiscal-year unavailable rows.
        Live-confirmed zero rows lost from the old gate's result set, 25+ newly recovered.
        Label-only (this helper never feeds a computed VALUE, only a reason string), so the
        broader inclusion carries no risk of a wrong number.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE free_cash_flow END AS free_cash_flow,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_cash_flow
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(free_cash_flow) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_free_cash_flow_symbols(self) -> frozenset[str]:
        """Symbols with at least one real (non-data_unavailable) annual_cash_flow row, none of
        which ever carry a real free_cash_flow value - a broader, full-history sibling of
        _get_no_recent_free_cash_flow_symbols() above for filers too recently IPO'd/listed to
        have accumulated the 3 consecutive real fiscal years that gate requires, same pattern
        as _get_never_tagged_interest_expense_symbols().

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction continuation):
        _get_no_recent_free_cash_flow_symbols() only has 12 sibling helpers total across this
        file, but free_cash_flow itself was missing this full-history counterpart entirely
        (unlike interest_expense/debt_components/revenue/total_assets/current_assets/
        current_liabilities/net_income/total_liabilities/stockholders_equity, which all already
        have one) - live-confirmed 48 additional universe symbols have real annual_cash_flow
        history but never once tag a real free_cash_flow figure, too few consecutive real
        fiscal years (recent IPOs/SPAC-mergers) to satisfy the 3-year window the sibling gate
        requires. Cached for the life of this loader instance; this query runs once per
        pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_cash_flow
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1
                   AND COUNT(*) FILTER (
                       WHERE (CASE WHEN data_unavailable THEN NULL ELSE free_cash_flow END) IS NOT NULL
                   ) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_registered_investment_company_symbols(self) -> frozenset[str]:
        """Symbols SEC-classified as a non-operating entity (company_info_sec.entity_type =
        'other', no SIC code assigned) that nonetheless have real annual_balance_sheet history
        (proving they're an established filer, not just too new for data) but have never once
        tagged a real free_cash_flow figure - closed-end funds/investment trusts (BlackRock
        BBN/BCAT/BGT-class, Gabelli/Eaton Vance/Invesco/Franklin *Trust-class, GAM/TY/ASA-class)
        report a "Statement of Changes in Net Assets" instead of a conventional cash-flow
        statement, so opcf/capex/FCF are structurally absent, not a loader gap - same root fact
        already established for dividends (see load_dividend_data.py's fetch_incremental,
        "registered_investment_company_no_xbrl": companyfacts for this class carries only
        "cef"/"ffd" taxonomy concepts, zero us-gaap).

        FIX 2026-09-05 (goal: "SEC/XBRL missing data to zero" audit): live-verified 83 universe
        symbols fit this exact shape; quality_metrics.fcf_margin was mislabeling them
        "missing_sec_data"/"no_recent_free_cash_flow_reported" (both "Missing SEC/XBRL data" in
        /api/scores/coverage) instead of reusing the already-correctly-bucketed
        "registered_investment_company_no_xbrl" ("Legitimate / not applicable"). Requiring real
        balance-sheet history (not just the entity_type/SIC classification alone) excludes
        genuine operating companies SEC also files as "other" (e.g. many foreign private
        issuers) and brand-new registrants with no filing history yet (live-checked: Bank OZK,
        a real operating bank, has this same entity_type/SIC shape but real annual_cash_flow
        data and is correctly excluded). Cached for the life of this loader instance; this query
        runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT c.symbol
                FROM company_info_sec c
                WHERE c.entity_type = 'other' AND c.sic_code IS NULL
                  AND EXISTS (
                      SELECT 1 FROM annual_balance_sheet b
                      WHERE b.symbol = c.symbol AND b.data_unavailable = FALSE
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM annual_cash_flow f
                      WHERE f.symbol = c.symbol AND f.free_cash_flow IS NOT NULL
                  )
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_etf_symbols(self) -> frozenset[str]:
        """Bare `etf_symbols` membership, no balance-sheet-history precondition.

        ADDED 2026-09-05 (goal: "SEC/XBRL missing data to zero" follow-up, capex-gate fix
        session): total_debt_unavailable_reason/total_cash_unavailable_reason needed an
        ETF/trust fallback distinct from _get_etf_trust_no_stockholders_equity_symbols()
        below - that gate deliberately REQUIRES real annual_balance_sheet history first, to
        avoid mislabeling an ETF that's simply too new to have filed anything yet as
        structurally exempt. But total_debt/total_cash's absence for a UIT/index-tracking
        ETF isn't a function of listing age at all - unlike an operating company (which will
        eventually file a real 10-K balance sheet once it matures), an ETF never files one,
        no matter how long it's been trading. Live-confirmed: SPY (listed 1993, 8,458 real
        trading days, ZERO annual_balance_sheet rows ever) and IGV/BKDV (5 years and ~1.75
        years listed respectively, also zero rows) all hit the exact same "missing_sec_data"
        mislabeling for total_debt/total_cash - age doesn't distinguish them, filer TYPE
        does. Cached for the life of this loader instance; this query runs once per pipeline
        run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute("SELECT symbol FROM etf_symbols")
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_etf_trust_no_stockholders_equity_symbols(self) -> frozenset[str]:
        """`etf_symbols`-registered tickers with real annual_balance_sheet history (proving
        they're an established filer, not just too new for data) that have never once tagged a
        real stockholders_equity figure - physical commodity/currency/crypto trusts (GLD, SLV,
        IAU, AAAU, GLDM, GBTC, ETHE, BITB, BITW, the FXA/FXB/FXC/FXE/FXF/FXY currency trusts,
        the CANE/CORN/SOYB/WEAT/TAGS/USCI/USL/UGA/UNG/UNL commodity-pool ETFs, ...) file a
        "Statement of Assets and Liabilities" reporting only `total_assets`/`total_liabilities`
        (trust shares outstanding, not equity) - same root fact as
        _get_registered_investment_company_symbols() above but for exchange-traded physical/
        commodity trusts, which are real SEC filers with their own exclusive CIK (see
        load_financial_statements.py's shared-CIK ETN/ETF comment - these are explicitly NOT in
        that shared-CIK exclusion list) rather than the "entity_type='other', no sic_code"
        registered-investment-company shape the RIC gate keys off.

        ADDED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep): live-verified 32
        universe `etf_symbols` tickers hit this shape, mislabeled "missing_sec_data"/
        "no_recent_balance_sheet_data_reported" (both "Missing SEC/XBRL data" in
        /api/scores/coverage) across debt_to_equity/roa/roe/roce_pct/asset_turnover/
        gross_profitability/quality_score/sustainable_growth_rate/quarterly_growth_momentum/
        earnings_growth_4q_avg - a structural fact (no GAAP equity concept exists to tag), not
        a loader gap. Requiring real balance-sheet history (not just etf_symbols membership
        alone) excludes any ETF too recently listed to have filed yet. Cached for the life of
        this loader instance; this query runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT e.symbol
                FROM etf_symbols e
                WHERE EXISTS (
                    SELECT 1 FROM annual_balance_sheet b
                    WHERE b.symbol = e.symbol AND b.data_unavailable = FALSE
                )
                AND NOT EXISTS (
                    SELECT 1 FROM annual_balance_sheet b
                    WHERE b.symbol = e.symbol AND b.stockholders_equity IS NOT NULL
                )
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_last_known_zero_dividends_symbols(self) -> frozenset[str]:
        """Symbols whose most recently-tagged (non-NULL) `dividends_paid` fact, however many
        fiscal years back, was exactly $0 - a distinct, narrower gap than
        `prior_year_dividends_paid`'s single-year-back fallback above.

        FIXED 2026-09-02 (goal: "Missing SEC/XBRL data" reduction, following up on
        [[dividends_paid_prior_year_fallback_added_20260902]]'s note that CCL/CMS both did NOT
        recover because their gap spans 3+ consecutive fiscal years, not just the anchor year).
        Live-verified against real SEC companyfacts for both: CCL's `PaymentsOfDividends` was
        tagged $0 for FY2021/FY2022 (dividend suspended, matches its known real 2020 COVID
        suspension) and then simply never tagged again for FY2023-2025 - a common preparer
        pattern of omitting an immaterial/zero line item from XBRL entirely once it stays zero,
        not a real change of fact. CMS's most recent tag was a real NON-zero $546M (FY2022,
        `PaymentsOfOrdinaryDividends`) with nothing tagged since - a materially different shape
        (a real dividend payer whose tag vanished, not a zero carried forward) that stays
        correctly excluded here and left as a genuine open gap; carrying a stale non-zero
        multi-year-old figure forward risks materially overstating a since-changed dividend, an
        asymmetric risk $0 doesn't share (there's no "understating a payout" failure mode when
        the last known fact was already zero).

        Universe scan: 348 distinct symbols fit this exact shape. Cached for the life of this
        loader instance, same one-query-per-run pattern as
        `_get_no_recent_free_cash_flow_symbols()` above.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH ranked AS (
                    SELECT symbol, dividends_paid,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_cash_flow
                    WHERE data_unavailable = FALSE AND dividends_paid IS NOT NULL
                )
                SELECT symbol FROM ranked WHERE rn = 1 AND dividends_paid = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_operating_cash_flow_available_elsewhere_symbols(self) -> frozenset[str]:
        """Symbols with a real (non-NULL) operating_cash_flow in at least one available
        annual_cash_flow fiscal year - the direct positive counterpart to
        _get_no_recent_operating_cash_flow_symbols() above, not its logical negation. Same
        "anchor-year fiscal mismatch" gate pattern as
        _get_net_income_available_elsewhere_symbols()/_get_revenue_available_elsewhere_symbols().

        FIX 2026-09-02 (quality_row_db anchor-year investigation, goal: "keep the missing-
        data number going down"): _get_no_recent_operating_cash_flow_symbols()'s own docstring
        already documented this exact residual ("the majority of the remaining rows have OCF
        in an off-anchor year instead ... deliberately NOT fixed this pass") but never wired a
        label-only fix for it - accruals_ratio/ocf_to_net_income both fell to generic
        "missing_sec_data" for this population. Cached for the life of this loader instance;
        this query runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_cash_flow
                WHERE data_unavailable = FALSE
                GROUP BY symbol
                HAVING COUNT(operating_cash_flow) >= 1
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_free_cash_flow_available_elsewhere_symbols(self) -> frozenset[str]:
        """Symbols with a real (non-NULL) free_cash_flow in at least one available
        annual_cash_flow fiscal year - the direct positive counterpart to
        _get_no_recent_free_cash_flow_symbols() above, not its logical negation. Same
        "anchor-year fiscal mismatch" gate pattern as the operating_cash_flow sibling above.

        FIX 2026-09-02 (quality_row_db anchor-year investigation): _get_no_recent_free_cash_
        flow_symbols()'s own docstring already documented this residual ("the rest have FCF in
        an off-anchor year instead, deliberately NOT fixed this pass") but never wired a
        label-only fix - free_cash_flow/fcf_to_net_income both fell to generic
        "missing_sec_data" for this population. Does NOT cover fcf_margin - that field already
        has its own dedicated cross-year fallback (fcf_margin_free_cash_flow, computed
        separately above) unaffected by this bug. Cached for the life of this loader instance;
        this query runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_cash_flow
                WHERE data_unavailable = FALSE
                GROUP BY symbol
                HAVING COUNT(free_cash_flow) >= 1
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_capex_symbols(self) -> frozenset[str]:
        """Symbols that have real operating_cash_flow but NOT capex in any of their 3 most
        recent fiscal years (in a row not itself flagged data_unavailable) - a genuine
        structural gap, not a loader gap.

        FIX 2026-09-02 (goal: "keep the missing-data number going down" SEC/XBRL audit,
        same bug class as the free_cash_flow/operating_cash_flow gates above, different root
        cause). value_metrics.fcf_yield's 261-row "missing_sec_data" bucket did NOT overlap
        with `_get_no_recent_free_cash_flow_symbols()` for a distinct reason: THIS file's
        loader (load_financial_statements.py) already treats a NULL capex as 0 when writing
        annual_cash_flow.free_cash_flow (so free_cash_flow ends up == operating_cash_flow,
        never NULL), but load_sec_valuations.py's OWN fcf computation for fcf_yield
        deliberately does NOT make that substitution (`fcf = ocf - capex - sbc if ... capex
        is not None else None`) unless the symbol is on the is_capex_exempt allowlist (banks/
        a hand-verified insurer list) - see that file's DEPOSITORY_INSTITUTION_SIC_CODES/
        INSURANCE_CAPEX_EXEMPT_SYMBOLS comments for why treating an unknown capex as 0 is
        only safe for entity types confirmed to have near-zero real capex.

        Live-verified via direct SEC companyfacts JSON for a same-industry-diverse sample
        (MS, PSX, NEE, CAR, IBKR, SYF, WTM, RGLD, VNOM, MSGE, CWT) that this is NOT an
        extraction bug this file's own capex concept-fallback list (see sec_statements.py's
        very long PaymentsToAcquire*/PaymentsForCapitalImprovements chain) could close: these
        real, large, capex-heavy filers (NextEra alone reports ~$12-13B/yr in real capex per
        public disclosure) simply never tag ANY capex-shaped us-gaap concept in their XBRL at
        all, across every fiscal year on file - the companyfacts convenience API structurally
        has nothing to extract, same "SEC XBRL just doesn't expose this" class already
        established for segment revenue elsewhere in this codebase. Unlike is_capex_exempt's
        near-zero-capex entities, these filers' REAL capex is far from zero - silently
        treating it as 0 here would materially overstate fcf_yield, so this gate is
        deliberately label-only (an honest, specific reason instead of generic
        "missing_sec_data"), not a "treat capex as 0" fix. 198 of 261 universe fcf_yield
        "missing_sec_data" rows matched this exact pattern (real OCF, capex NULL in all 3
        recent years) - a mix of these companyfacts-gap large caps, BDCs/closed-end funds
        (BBDC, ARI, BGT, MAIN, ...), and pre-revenue biotech/SPAC-adjacent names, all sharing
        the same "capex was never tagged" structural fact regardless of the underlying reason.
        Cached for the life of this loader instance; this query runs once per pipeline run,
        not once per symbol.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - see
        _get_no_recent_operating_cash_flow_symbols' 2026-09-03 fix comment for the full
        mechanism, same fix applied identically here): `fiscal_year > 0` replaces
        `data_unavailable = FALSE`. Live-verified the 7 symbols this changed (GLNG, TFIN,
        XRTX, EWBC, EMAT, PPCB, CYCN) were previously matching this gate only by reaching
        back to stale, 4+-year-old real OCF data while ignoring that their true 3 most
        recent fiscal years are ALL explicitly unavailable - the fix correctly re-routes
        them to the more accurate no_recent_operating_cash_flow_reported gate instead
        (fixed identically, same table) rather than mislabeling them as "real recent OCF,
        capex specifically missing". Label-only.

        FIXED 2026-09-05 (`capex_never_tagged_in_recent_filings` reason mislabeled/missed -
        cross-session follow-up to the 2026-09-03 fix above): `fiscal_year > 0` alone still let
        a stray trailing placeholder row corrupt the ranking. Many symbols carry a not-yet-filed
        NEXT fiscal year row (`data_unavailable = TRUE`) that nonetheless has leftover non-NULL
        numeric values in some columns (a carry-over that was never nulled when the row was
        flagged unavailable) - because that placeholder wasn't excluded, it silently occupied
        one of the "3 most recent" ranking slots two different ways:
          - CYCN/EMAT/EWBC/PPCB/TFIN: the placeholder's stray non-NULL capex made
            `COUNT(capex) != 0` even though their true 3 most recent REAL fiscal years all have
            real operating_cash_flow and genuinely NULL capex - these 5 wrongly fell through to
            generic "missing_sec_data" instead of this gate's specific reason.
          - AIG/NLY/UHT/AAMI/RZLT/SPWR (39 total, live-confirmed): the placeholder's presence
            pushed a REAL capex-bearing row (e.g. AIG FY2023 capex=$240M) out of the 3-slot
            window entirely, so this gate WRONGLY matched them as "capex never tagged" when
            capex was in fact tagged, just one fiscal year further back than the corrupted
            window could see.
        Fix: exclude a `data_unavailable = TRUE` row ONLY when its fiscal_year is exactly
        (that symbol's own max `data_unavailable = FALSE` fiscal_year) + 1 - i.e. a single
        trailing "not yet filed" placeholder for next year - while still including any OTHER
        data_unavailable = TRUE row in the ranking, so the GLNG-shaped case (multiple
        consecutive real gap years, true recent history is genuinely unavailable, must still
        fall through to no_recent_operating_cash_flow_reported instead) is unaffected; live-
        reverified GLNG still does NOT match after this change.

        This placeholder-only exclusion, if shipped with the old `COUNT(*) = 3` requirement
        unchanged, was live-verified to also DROP 131 already-correctly-matching symbols -
        mostly SPAC/shell tickers (LCCC, MACI, NPAC, RFAI, TAVI, DMAA, PACH, ...) that simply
        have only 2 real filed fiscal years on record (too recently IPO'd/merged to have a 3rd),
        both real years genuinely NULL for capex. Checking those symbols against every earlier
        gate in this file's fcf_yield priority chain (registered-investment-company/etf-trust/
        no-recent-fcf/never-tagged-fcf) showed only 51 of the 131 were re-caught elsewhere; the
        remaining 80 would have regressed from this gate's specific, accurate reason to the
        generic "missing_sec_data" bucket - a real loss of accuracy, not a neutral relabeling.
        `COUNT(*) = 3` replaced with `COUNT(*) >= 2` to admit these thinner-history filers (same
        "too few consecutive real fiscal years, same underlying fact" reasoning already used by
        `_get_never_tagged_free_cash_flow_symbols()`'s `COUNT(*) >= 1` full-history sibling) -
        live-reverified this recovers 129 of the 131 SPAC-shaped symbols (the remaining 2,
        TACO/TWLVR-shaped, have only 1 real fiscal year plus 1 genuinely-unavailable prior year,
        which still clears `COUNT(*) >= 2` and correctly matches too) without reintroducing the
        GLNG-shaped false-match risk, since `rn <= 3` still caps how far back the window can
        reach - a symbol only shows `COUNT(*) < 3` here because it truly has fewer than 3
        (post-placeholder-exclusion) rows in the table, never because real older history was
        excluded by the window. Net effect on the gate's total match set: 639 -> 646 (+7),
        with both directions of the underlying bug corrected. Label-only.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH ranked AS (
                    SELECT symbol, capex, operating_cash_flow, fiscal_year, data_unavailable,
                           MAX(fiscal_year) FILTER (WHERE data_unavailable = FALSE)
                               OVER (PARTITION BY symbol) AS max_real_fy
                    FROM annual_cash_flow
                    WHERE fiscal_year > 0
                ),
                filtered AS (
                    SELECT * FROM ranked
                    WHERE NOT (data_unavailable AND fiscal_year = max_real_fy + 1)
                ),
                recent AS (
                    SELECT symbol, operating_cash_flow, capex,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM filtered
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(capex) = 0 AND COUNT(operating_cash_flow) > 0 AND COUNT(*) >= 2
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_blank_check_symbols(self) -> frozenset[str]:
        """Symbols SEC-classified as SIC 6770 "Blank Checks" - pre-merger SPAC shells.

        FIX 2026-08-19 (goal: "no SEC data" audit, roic_pct/gross_margin/ebitda_margin
        follow-up): a blank-check company has no real operating business before its
        merger (trust-account interest income only, no product/service revenue, no
        meaningful invested-capital deployment) - roic_pct/gross_margin/ebitda_margin
        being unavailable for one is a genuine structural fact, same category as
        reit_special_entity, not a loader gap. Live-confirmed: 343 universe symbols
        carry this exact SIC classification, and 326/270/314 of them respectively were
        mislabeled "missing_sec_data" for those three metrics - reading as a loader
        failure instead of the correct "this entity has no operating business yet".

        Deliberately uses company_info_sec.sic_description (SEC's own authoritative
        classification) rather than extending _get_no_recent_revenue_symbols()'s 3-
        consecutive-fiscal-year window: many SPACs are too recently IPO'd to have 3
        years of filings yet, which would exclude them from that check even though
        their SIC code alone already settles the question, filing history length
        notwithstanding. Cached for the life of this loader instance; this query runs
        once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute("SELECT symbol FROM company_info_sec WHERE sic_description = 'Blank Checks'")
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_no_recent_stockholders_equity_symbols(self) -> frozenset[str]:
        """Symbols that have NOT reported stockholders_equity in any of their 3 most recent
        fiscal years - i.e. debt_to_equity is structurally None for them, not a loader gap.

        Live audit 2026-08-18 ("no SEC data" goal): 156 of 1,048 universe debt_to_equity
        "missing_sec_data" rows are this case. A genuine mixed bag (unlike current_ratio's
        bank/REIT-dominated bucket) - pharma (9), REITs (7), utilities (6), investment advice
        (6), real estate (5) - no single entity type dominates, so this gets its own reason
        string rather than reit_special_entity. Same "3 most recent years, not all-time
        history" windowing as the sibling checks above. Cached for the life of this loader
        instance; this query runs once per pipeline run, not once per symbol.

        FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction - see
        _get_no_recent_operating_cash_flow_symbols' 2026-09-03 fix comment for the full
        mechanism, same fix applied identically here): `fiscal_year > 0` replaces
        `data_unavailable = FALSE` so a symbol whose 3 most recent fiscal years are ALL
        explicitly marked unavailable isn't invisible to this gate. Label-only.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT symbol, CASE WHEN data_unavailable THEN NULL ELSE stockholders_equity END AS stockholders_equity,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE fiscal_year > 0
                )
                SELECT symbol FROM recent
                WHERE rn <= 3
                GROUP BY symbol
                HAVING COUNT(stockholders_equity) = 0 AND COUNT(*) = 3
                """
            )
            return frozenset(row[0] for row in cur.fetchall())

    @_cached_symbols
    def _get_never_tagged_stockholders_equity_symbols(self) -> frozenset[str]:
        """Full-history sibling of _get_no_recent_stockholders_equity_symbols() above - see
        _get_never_tagged_net_income_symbols()'s docstring for the general pattern. Live-
        verified 9 of roe's 68 universe "missing_sec_data" rows match this alone (27 combined
        with _get_never_tagged_net_income_symbols() above). Cached for the life of this loader
        instance; this query runs once per pipeline run, not once per symbol.
        """
        with _database_context()("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM annual_balance_sheet
                WHERE fiscal_year > 0
                GROUP BY symbol
                HAVING COUNT(*) >= 1 AND COUNT(stockholders_equity) = 0
                """
            )
            return frozenset(row[0] for row in cur.fetchall())
