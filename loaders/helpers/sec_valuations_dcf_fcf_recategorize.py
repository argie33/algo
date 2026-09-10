"""dcf_fcf_unavailable_reason recategorize methods for SecValuationsLoader, extracted from
load_sec_valuations.py (2026-09-10, file-size ratchet: that file crossed the 2000-line hard
ceiling during a local-main merge). Methods are verbatim, no logic changed - mixed into
SecValuationsLoader, which calls each of these from its own dcf_fcf reason-chain wiring.
"""

from typing import Any

from utils.db.context import DatabaseContext


class DcfFcfRecategorizeMixin:
    """Overrides a generic dcf_fcf_unavailable_reason="missing_cash_flow_data" with a more
    specific, already-established reason string once a structural root cause is identified.
    Not usable standalone - relies on `self` resolving normally through SecValuationsLoader.
    """

    # Oil royalty trusts (SIC 6792) file a "Statement of Distributable Income" with no
    # conventional cash-flow-statement concepts to tag at all - same structural shape as a RIC
    # above, just a different, much smaller (6-symbol) entity class with its own SIC code
    # rather than ValueQualityGrowthMetricsLoader's entity_type='other'/sic_code IS NULL RIC
    # gate. Hardcoded rather than a SIC-code DB query since there are only 6 and the SIC-6792
    # universe is exactly this list (live-confirmed via company_info_sec, 2026-09-06) - no
    # false-positive risk from a broader SIC scan.
    _ROYALTY_TRUST_SYMBOLS_FOR_DCF = frozenset({"NRT", "MTR", "CRT", "PBT", "SBR", "SJT"})

    def _recategorize_ric_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with a specific one for a registered
        investment company. Mutates `valuation_row` in place.

        FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" follow-up): a registered
        investment company (closed-end fund/investment trust) files a "Statement of Changes in
        Net Assets" with no conventional cash-flow-statement concepts to tag at all, so
        dcf_fcf_base always comes back None and _compute_yield_and_dcf_fields's own generic
        "missing_cash_flow_data" fallback fires - same root fact already established for
        fcf_margin/fcf_yield/accruals_ratio/ocf_to_net_income/roic_pct/debt_to_equity in
        loaders/helpers/vqg_quality.py and vqg_value.py, just not recognized here since this
        mixin has no access to ValueQualityGrowthMetricsLoader's
        _get_registered_investment_company_symbols() gate (different class hierarchy) - a small
        inline query instead. Live-confirmed EVN/BSTZ/CEV/BTX/BUI/JHI/PMO (7 universe symbols).
        Only overrides the generic fallback reason, never a real computed value or a more
        specific reason (negative_free_cash_flow/implausible_dcf_result).
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT 1
                FROM company_info_sec c
                WHERE c.symbol = %s AND c.entity_type = 'other' AND c.sic_code IS NULL
                  AND EXISTS (
                      SELECT 1 FROM annual_balance_sheet b
                      WHERE b.symbol = c.symbol AND b.data_unavailable = FALSE
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM annual_cash_flow f
                      WHERE f.symbol = c.symbol AND f.free_cash_flow IS NOT NULL
                        AND f.data_unavailable IS NOT TRUE
                  )
                """,
                (symbol,),
            )
            if cur.fetchone() is not None:
                valuation_row["dcf_fcf_unavailable_reason"] = "registered_investment_company_no_xbrl"

    def _recategorize_unsupported_currency_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with "unsupported_currency_no_fx_rate"
        for a foreign private issuer whose annual_cash_flow row was already tagged that way.
        Mutates `valuation_row` in place.

        ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day follow-up to
        the has_unsupported_currency_only_fact fix in load_financial_statements.py /
        utils/external/sec_statements_shared.py): a foreign private issuer that tags
        operating_cash_flow only under a hyperinflationary/unsupported local currency (e.g.
        ARS - GGAL/BBAR/CRESY/LOMA/IRS and more, live-confirmed via real SEC companyfacts) has
        a real, non-fabricatable ocf=None, so dcf_fcf_base comes back None here too and
        _compute_yield_and_dcf_fields's generic "missing_cash_flow_data" fallback fires - same
        reason-string-doesn't-match-real-cause bug class as the RIC recategorization above,
        just for a different root cause. Reuses annual_cash_flow.reason (already populated by
        load_financial_statements.py's own fix once that table is reloaded) instead of a fresh
        live SEC API call - this mixin has no SecEdgarClient instance to reuse a cache from
        (unlike load_financial_statements.py, which calls get_company_facts() during the same
        extraction pass), so a DB lookup against the sibling table's own already-computed
        reason is far cheaper than a second live fetch per symbol. Only overrides the generic
        fallback reason, never a real computed value or a more specific reason
        (negative_free_cash_flow/implausible_dcf_result/registered_investment_company_no_xbrl
        above, which is checked first and returns early if it already matched).
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT 1
                FROM annual_cash_flow f
                WHERE f.symbol = %s AND f.reason = 'unsupported_currency_no_fx_rate'
                ORDER BY f.fiscal_year DESC
                LIMIT 1
                """,
                (symbol,),
            )
            if cur.fetchone() is not None:
                valuation_row["dcf_fcf_unavailable_reason"] = "unsupported_currency_no_fx_rate"

    def _recategorize_royalty_trust_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with "reit_special_entity" for an oil
        royalty trust. Mutates `valuation_row` in place.

        ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, comprehensive RIC-gap
        scan follow-up): same root fact as _recategorize_ric_dcf_fcf_reason above (no
        conventional cash-flow-statement concepts to tag), already established for
        quality_metrics.fcf_margin/value_metrics.fcf_yield's royalty-trust blocks in
        loaders/helpers/vqg_quality.py and vqg_value.py - this dcf_fcf ground-truth reason
        never checked it either. Live-confirmed all 6 active royalty-trust symbols (NRT, MTR,
        CRT, PBT, SBR, SJT) stuck on the generic "missing_cash_flow_data". Reuses
        "reit_special_entity" (not a new label) - same "Legitimate / not applicable" bucket
        already used for this exact business-model fact throughout the codebase (see
        sec_valuations_yield_dcf.py's own REIT/insurance SIC-code branch, which sits alongside
        this same reason string for the identical entity-type rationale).
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        if symbol in self._ROYALTY_TRUST_SYMBOLS_FOR_DCF:
            valuation_row["dcf_fcf_unavailable_reason"] = "reit_special_entity"

    def _recategorize_capex_never_tagged_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with "capex_never_tagged_in_recent_filings"
        for a filer with real, recent operating cash flow but capex never itemized in its 3 most
        recent real fiscal years. Mutates `valuation_row` in place.

        ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, dcf_fcf missing_cash_flow_
        data investigation): this file's own fcf_base/avg_fcf_fallback computation
        (sec_valuations_yield_dcf.py) requires a real (non-None) capex figure - genuinely absent
        for a large slice of filers who simply never re-tag it (live-confirmed CWH/Camping World:
        real, growing OCF every year, real "PaymentsToAcquireProductiveAssets" capex through
        FY2022, then NOTHING under any capex-shaped concept in its companyfacts JSON since -
        not a currency/entity-type structural fact, an ordinary filing-presentation gap). Same
        root cause already given its own specific reason for quality_metrics.fcf_margin/
        value_metrics.fcf_yield via _get_no_recent_capex_symbols() in vqg_quality.py/vqg_value.py
        (live-confirmed 198 of that gate's own affected rows share this exact profile) - this
        dcf_fcf ground-truth reason never checked it either, so 177 of 210 (84%) of the current
        "missing_cash_flow_data" population were this exact, already-labeled-elsewhere case
        instead of a true undiagnosed gap. Small inline query (this mixin has no access to
        ValueQualityGrowthMetricsLoader's cached gate, different class hierarchy - same
        convention as _recategorize_ric_dcf_fcf_reason above). Still "Missing SEC/XBRL data" -
        this doesn't change the headline category, only gives an honest, specific, already-
        established label instead of the uninformative generic one, matching this file's own
        precedent (RIC/currency/royalty-trust recategorizations just above all keep their
        original category too, e.g. RIC's target `registered_investment_company_no_xbrl` is
        also "Missing SEC/XBRL data").
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH ranked AS (
                    SELECT symbol, capex, operating_cash_flow, fiscal_year, data_unavailable,
                           MAX(fiscal_year) FILTER (WHERE data_unavailable = FALSE)
                               OVER (PARTITION BY symbol) AS max_real_fy
                    FROM annual_cash_flow
                    WHERE symbol = %s AND fiscal_year > 0
                ),
                filtered AS (
                    SELECT * FROM ranked
                    WHERE NOT (data_unavailable AND fiscal_year = max_real_fy + 1)
                ),
                recent AS (
                    SELECT operating_cash_flow, capex,
                           ROW_NUMBER() OVER (ORDER BY fiscal_year DESC) AS rn
                    FROM filtered
                )
                SELECT 1 FROM recent
                WHERE rn <= 3
                GROUP BY 1
                HAVING COUNT(capex) = 0 AND COUNT(operating_cash_flow) > 0 AND COUNT(*) >= 2
                """,
                (symbol,),
            )
            if cur.fetchone() is not None:
                valuation_row["dcf_fcf_unavailable_reason"] = "capex_never_tagged_in_recent_filings"

    def _recategorize_no_recent_ocf_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with "no_recent_operating_cash_flow_
        reported" for a filer with real historical OCF whose 3 most recent fiscal years are all
        unusable. Mutates `valuation_row` in place.

        ADDED 2026-09-10 (goal: "under 500" push, missing_cash_flow_data investigation):
        quality_metrics.accruals_ratio/ocf_to_net_income and value_metrics.fcf_yield already
        recognize this exact structural fact via vqg_symbol_gates.py's
        _get_no_recent_operating_cash_flow_symbols() (a filer whose 3 most recent fiscal years
        are ALL missing operating_cash_flow, despite real values existing further back) - this
        dcf_fcf ground-truth reason chain never checked for it, same "sibling-wiring gap" bug
        class as _recategorize_capex_never_tagged_dcf_fcf_reason just above (which only covers
        the OCF-present-but-capex-missing half of this same population). Live-confirmed GLNG
        (Golar LNG, 20-F filer): real NetCashProvidedByUsedInOperatingActivitiesContinuingOperations
        tagged through FY2021 ($253.9M), then absent under every cash-flow-shaped us-gaap
        concept in its companyfacts payload for FY2022 onward - a genuine filer-side tagging
        stop, not an extraction gap this loader could recover from. XRTX confirmed the same
        shape via the same live audit that established the gate this reuses (see that
        function's own 2026-09-03 fix comment, which names both symbols explicitly).

        Query mirrors _get_no_recent_operating_cash_flow_symbols() exactly (same `fiscal_year >
        0` filter, same 3-most-recent-real-row window, same `COUNT(*) = 3` completeness
        requirement) rather than reusing that cached whole-universe helper directly - this
        mixin has no access to SymbolGateMixin (different class hierarchy), same convention as
        every other _recategorize_*_dcf_fcf_reason inline query in this file. Checked after the
        capex-never-tagged gate above (mutually exclusive: that gate requires real OCF to
        exist, this one requires it not to) so a real cause never gets overridden by a less
        specific one.
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                WITH recent AS (
                    SELECT CASE WHEN data_unavailable THEN NULL ELSE operating_cash_flow END AS operating_cash_flow,
                           ROW_NUMBER() OVER (ORDER BY fiscal_year DESC) AS rn
                    FROM annual_cash_flow
                    WHERE symbol = %s AND fiscal_year > 0
                )
                SELECT 1 FROM recent
                WHERE rn <= 3
                GROUP BY 1
                HAVING COUNT(operating_cash_flow) = 0 AND COUNT(*) = 3
                """,
                (symbol,),
            )
            if cur.fetchone() is not None:
                valuation_row["dcf_fcf_unavailable_reason"] = "no_recent_operating_cash_flow_reported"

    def _recategorize_blank_check_dcf_fcf_reason(self, symbol: str, valuation_row: dict[str, Any]) -> None:
        """Overrides a generic dcf_fcf_unavailable_reason with "no_revenue_reported"
        ("Legitimate / not applicable") for a pre-merger SPAC shell. Mutates `valuation_row` in
        place.

        ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day follow-up to
        _recategorize_blank_check_all_valuation_metrics_null_reason and
        _recategorize_capex_never_tagged_dcf_fcf_reason above): a blank-check company has no
        real operating business before its merger - trust-account interest income only, no
        product/service revenue, and typically too few real fiscal years on file yet to clear
        the capex-never-tagged gate's own >=2-real-year floor - so a recently-listed SPAC still
        fell through both of those checks straight to the generic "missing_cash_flow_data".
        Live-confirmed 11 active-universe symbols (XFLH/PTOR/ALDF/GIX/GIW/NWAX/WENC/QETAR/
        QUMSR/FSHP/FSHPR) hitting this exact gap - same root fact and same "no_revenue_reported"
        reason the whole-row all_valuation_metrics_null fallback already uses for this identical
        population, just never checked for dcf_fcf specifically since it's a narrower field-
        level reason than the whole-row fallback (a SPAC with SOME valuation metrics computed
        but dcf_fcf specifically null wouldn't hit that whole-row check at all). Checked last
        (after RIC/currency/royalty-trust/capex) so a more specific real cause above always
        wins - only overrides the exact generic reason this fix targets, same guard discipline
        as every sibling recategorize_*_dcf_fcf_reason function in this file.
        """
        if valuation_row.get("dcf_fcf_unavailable_reason") != "missing_cash_flow_data":
            return
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT 1 FROM company_info_sec WHERE symbol = %s AND sic_description = 'Blank Checks'",
                (symbol,),
            )
            if cur.fetchone() is not None:
                valuation_row["dcf_fcf_unavailable_reason"] = "no_revenue_reported"
