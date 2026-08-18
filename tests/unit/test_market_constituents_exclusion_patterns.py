"""Regression test: preferred-share/subordinated-debt securities that don't say the
literal word "preferred" must still be excluded from the common-equity universe.

Found live 2026-07-28: EXCLUSION_PATTERNS caught `\\bpreferred\\b` but missed "Preference
Shares" (different word), "Subordinated Debentures"/"Subordinated Notes" (junior debt),
and "Pfd Ser"/"Pfd Stock" (abbreviated depositary-share preferred notation) - all real
NASDAQ/NYSE listing-file phrasings. Confirmed live: 58 already-tracked symbols
(BAC$E, ALL$B, AFGC, DTB, RZC, ...) were `active=true` and flowing through technical
indicators/scoring/signals as if they were common equity. Also guards the negative case
that caused the fix to need care: BNS ("Bank Nova Scotia Halifax Pfd 3 Ordinary Shares")
is a real, actively-traded common ADR with a garbled security_name containing "Pfd" -
a bare `\\bpfd\\b` pattern would have wrongly excluded it.
"""

from loaders.load_market_constituents import should_exclude


class TestNewExclusionPatterns:
    def test_preference_shares_excluded(self):
        assert should_exclude("Aspen Insurance Holdings Limited 5.625% Perpetual Non-Cumulative Preference Shares")

    def test_subordinated_debentures_excluded(self):
        assert should_exclude("American Financial Group, Inc. 5.125% Subordinated Debentures due 2059")

    def test_subordinated_notes_excluded(self):
        assert should_exclude("Brookfield BRP Holdings (Canada) Inc. 4.875% Perpetual Subordinated Notes")

    def test_pfd_ser_excluded(self):
        assert should_exclude("Bank of America Corporation Depositary Sh repstg 1/1000th Perp Pfd Ser E")

    def test_pfd_stock_excluded(self):
        assert should_exclude(
            "U.S. Bancorp Depositary Shares, Each representing a 1/100th interest in a share of "
            "Series A Non-CumulativePerpetual Pfd Stock"
        )

    def test_garbled_common_adr_not_excluded(self):
        """BNS is a real, actively-traded common ADR - a garbled security_name containing
        'Pfd' must not exclude it. This is why the fix is `\\bpfd (ser|stock)`, not `\\bpfd\\b`."""
        assert not should_exclude("Bank Nova Scotia Halifax Pfd 3 Ordinary Shares")

    def test_ordinary_common_stock_not_excluded(self):
        assert not should_exclude("Apple Inc. - Common Stock")


class TestRightsWhenIssuedAndDepositaryShareExclusionPatterns:
    """Regression test added 2026-08-03: found while root-causing price_daily's chronic
    ~4% "missing symbol" completion gap. 28 already-active symbols turned out to be SPAC
    rights offerings, when-issued shares, or depositary-share/bare-percentage preferred
    notation - none of which yfinance has a ticker for at all, so they permanently failed
    every price-loader run while silently counting against the completion threshold.
    """

    def test_spac_rights_with_each_wording_excluded(self):
        assert should_exclude(
            "AI Infrastructure Acquisition Corp. Rights, each entitling the holder to "
            "receive one-fifth (1/5) of one Class A Ordinary Share"
        )

    def test_spac_rights_without_each_wording_excluded(self):
        assert should_exclude(
            "GalaxyEdge Acquisition Corporation Rights to receive one-fourth (1/4) of one ordinary share"
        )

    def test_when_issued_common_stock_excluded(self):
        assert should_exclude("Resideo Technologies, Inc. Common Stock When-Issued")

    def test_bare_percentage_series_preferred_excluded(self):
        assert should_exclude("DigitalBridge Group, Inc. 7.125% Series H")

    def test_depositary_shares_excluded(self):
        assert should_exclude("Equitable Holdings, Inc. Depositary Shares")

    def test_dep_shs_abbreviation_excluded(self):
        assert should_exclude("Morgan Stanley Dep Shs Rpstg 1/1000th Int Prd Ser F Fxd to Flag")

    def test_pfd_shs_ser_excluded(self):
        """Not caught by the existing `\\bpfd (ser|stock)` pattern - "Shs" sits between
        "Pfd" and "Ser" in the real listing-file text."""
        assert should_exclude("EPR Properties Series E Cumulative Conv Pfd Shs Ser E")

    def test_mccormick_common_stock_not_excluded(self):
        """MKC.V is a real common stock (McCormick) with an unusual ticker suffix in our
        DB - a data-hygiene question for the symbol table, not a text-exclusion candidate.
        Must not be caught by the new "Series"/rights patterns."""
        assert not should_exclude("McCormick & Company, Incorporated Common Stock")

    def test_sce_trust_not_excluded_by_these_patterns(self):
        """SCE TRUST VI is ambiguous with no distinguishing preferred/rights keyword - a
        bare `\\btrust\\b` pattern would risk false-positiving real REIT common stock, so
        it's deliberately left unmatched pending individual review."""
        assert not should_exclude("SCE TRUST VI")


class TestInvestmentCorpSpacVsRealCompany:
    """Regression test added 2026-08-03: a bare `\\binvestment corp\\b` pattern silently
    excluded real, actively-traded common stocks whose legal name happens to end in the
    abbreviated "Investment Corp." rather than the fuller "Investment Corporation" -
    live-confirmed against the actual nasdaqlisted.txt/otherlisted.txt feeds that AGNC
    (AGNC Investment Corp., a large mortgage REIT) and SAR (Saratoga Investment Corp, a
    real BDC) were both missing from stock_symbols entirely. The pattern exists to catch
    serial-SPAC-sponsor shell companies, which - unlike real US operating companies -
    list "Ordinary Shares"/"Rights" instead of "Common Stock"; only exclude when that
    SPAC share-class language is also present.
    """

    def test_agnc_common_stock_not_excluded(self):
        assert not should_exclude("AGNC Investment Corp. - Common Stock")

    def test_saratoga_common_stock_not_excluded(self):
        assert not should_exclude("Saratoga Investment Corp New")

    def test_agnc_preferred_depositary_shares_still_excluded(self):
        assert should_exclude(
            "AGNC Investment Corp. - Depositary Shares Each Representing a 1/1,000th "
            "Interest in a Share of 7.75% Series G Fixed-Rate Reset Cumulative "
            "Redeemable Preferred Stock"
        )

    def test_saratoga_notes_due_still_excluded(self):
        assert should_exclude("Saratoga Investment Corp 8.00% Notes due 2027")

    def test_spac_ordinary_shares_still_excluded(self):
        assert should_exclude("Hennessy Capital Investment Corp. VIII - Class A Ordinary Shares")

    def test_spac_share_rights_still_excluded(self):
        assert should_exclude("Hennessy Capital Investment Corp. VIII - Share Rights")

    def test_spac_units_still_excluded(self):
        assert should_exclude("NewHold Investment Corp III - Units")


class TestMortgageBondAndTrustCertificateExclusionPatterns:
    """Regression test added 2026-08-18 (goal: "no SEC data"/loader-failure audit): utility
    first-mortgage bonds and synthetic trust-certificate/repackaged-note instruments -
    live-confirmed 14 already-active symbols (Entergy ELC/EMP/ENJ/ENO/EAI, GJH/GJO/GJP/
    GJR/GJS/GJT, KTN, JBK, PYT) flowing through value/quality/growth_metrics as common
    equity, each permanently reporting "missing_sec_data" (which reads as a loader bug)
    instead of being excluded like every other non-equity instrument type above. None of
    these are operating companies with SEC financial statements to fetch in the first place.
    """

    def test_entergy_first_mortgage_bonds_excluded(self):
        assert should_exclude("Entergy Mississippi, LLC First Mortgage Bonds, 4.90% Series Due October 1, 2066")

    def test_entergy_collateral_trust_mortgage_bonds_excluded(self):
        assert should_exclude(
            "Entergy Louisiana, Inc. Collateral Trust Mortgage Bonds, 4.875 % Series due September 1, 2066"
        )

    def test_strats_certificates_excluded(self):
        assert should_exclude(
            "Synthetic Fixed-Income Securities, Inc. on behalf of STRATS (SM) Trust for Dominion "
            "Resources, Inc. Securities, Series 2005-6, Floating Rate Structured Repackaged "
            "Asset-Backed Trust Securities (STRATS) Certificates"
        )

    def test_corts_excluded(self):
        assert should_exclude("Structured Products Corp 8.205% CorTS 8.205% Corporate Backed Trust Securities (CorTS)")

    def test_backed_tr_certs_excluded(self):
        assert should_exclude("Lehman ABS 3.50 3.50% Adjustable Corp Backed Tr Certs GS Cap I")

    def test_pplus_tr_excluded(self):
        assert should_exclude("PPlus Tr GSC-2 Tr Ctf Fltg Rate")

    def test_real_mortgage_reit_common_stock_not_excluded(self):
        """A real mortgage REIT's plain common stock must not be caught by the new
        "mortgage bonds" pattern - it doesn't contain the literal phrase "mortgage bonds"."""
        assert not should_exclude("Annaly Capital Management, Inc. Common Stock")


class TestAmericanDepositarySharesNotExcluded:
    """Regression test added 2026-08-18 (goal: "no SEC data"/loader-failure audit): the
    bare `\\bdepositary shares?\\b`/`\\bdep shs?\\b` patterns (added 2026-08-03 to catch
    real preferred-stock "X% Series Y Depositary Shares" notation like ATH$D/BAC$E/
    EQH$A) were never scoped to exclude "American Depositary Shares"/"American
    Depositary Receipts" - the standard listing terminology for ANY foreign company's
    US-exchange common stock (ADRs). Live-confirmed 272 real, liquid, large-cap common
    stocks (BABA, JD, ERIC, GRFS, IQ, FUTU, HIMX, BHP, SHEL, VOD, GSK, UL, ARM, NTES,
    PDD, SONY, and more) were silently excluded/`active=false`, starving them from the
    entire metrics/loader pipeline. Fix: DEPOSITARY_SHARES_PATTERN/
    AMERICAN_DEPOSITARY_PATTERN two-signal check (same shape as CORP_SPONSOR_PATTERN/
    SPAC_SHARE_CLASS_PATTERN) - exclude only when "depositary shares" is NOT immediately
    preceded by "American", since every confirmed real preferred depositary-share name in
    the local DB (ATH$*, BAC$E, EQH$A, FITB$I, MET$E, MS$F, RNR$F) omits that word.
    """

    def test_alibaba_adr_not_excluded(self):
        assert not should_exclude(
            "Alibaba Group Holding Limited American Depositary Shares each representing eight Ordinary share"
        )

    def test_ericsson_adr_not_excluded(self):
        assert not should_exclude("Ericsson - American Depositary Shares each representing 1 underlying Class B share")

    def test_bhp_adr_not_excluded(self):
        assert not should_exclude(
            "BHP Group Limited American Depositary Shares (Each representing two Ordinary Shares)"
        )

    def test_lowercase_american_depositary_shares_not_excluded(self):
        assert not should_exclude(
            "Himax Technologies, Inc. - American depositary shares, each of which represents two ordinary shares."
        )

    def test_real_preferred_depositary_shares_still_excluded(self):
        """EQH$A has zero "preferred"/"series"/"%" language in its stored name at all -
        the ONLY distinguishing signal available is the absence of "American" before
        "Depositary Shares"."""
        assert should_exclude("Equitable Holdings, Inc. Depositary Shares")

    def test_real_preferred_dep_shs_abbreviation_still_excluded(self):
        assert should_exclude("Morgan Stanley Dep Shs Rpstg 1/1000th Int Prd Ser F Fxd to Flag")

    def test_real_preferred_with_preference_share_language_still_excluded(self):
        assert should_exclude(
            "Athene Holding Ltd. Depositary Shares, Each Representing a 1/1,000th Interest in a "
            "4.875% Fixed-Rate Perpetual Non-Cumulative Preference Share, Series D"
        )

    def test_american_international_group_not_falsely_matched(self):
        """ "American" appearing elsewhere in a preferred-stock issuer's legal name (not
        immediately adjacent to "Depositary Shares") must not accidentally exempt a real
        preferred security - AMERICAN_DEPOSITARY_PATTERN requires strict adjacency."""
        assert should_exclude("American International Group, Inc. Depositary Shares, Series A")

    def test_global_depositary_shares_not_excluded(self):
        """Global Depositary Shares (GDS/GDR) is the same foreign-listing mechanism as
        ADRs under a different regional name - live-confirmed on IRS (IRSA Inversiones Y
        Representaciones, a real $11.4B Argentine real-estate company)."""
        assert not should_exclude(
            "IRSA Inversiones Y Representaciones S.A. Global Depositary Shares "
            "(Each representing ten shares of Common Stock)"
        )


class TestRightToReceiveAdrRatioNotExcluded:
    """Regression test added 2026-08-18 (goal: "no SEC data"/loader-failure audit): the
    bare `\\brights?\\b` EXCLUSION_PATTERNS entry (intended for real SPAC-rights
    instruments like "... - Rights") also matched ordinary ADR-ratio prose describing the
    underlying-share conversion ("American Depositary Shares... each representing the
    RIGHT TO RECEIVE 20 Series B Shares"). Live-confirmed 3 real common stocks (AMX/
    America Movil, RLX/RLX Technology, WDH/Waterdrop) wrongly excluded this way. A real
    rights-offering ticker's name never says "right(s) to receive" - negative lookahead
    excludes just that phrasing, not the instrument type.
    """

    def test_america_movil_adr_not_excluded(self):
        assert not should_exclude(
            "America Movil, S.A.B. de C.V. American Depositary Shares (each representing the right "
            "to receive twenty (20) Series B Shares"
        )

    def test_rlx_adr_not_excluded(self):
        assert not should_exclude(
            "RLX Technology Inc. American Depositary Shares, each representing the right to receive one"
        )

    def test_waterdrop_adr_not_excluded(self):
        assert not should_exclude(
            "Waterdrop Inc. American Depositary Shares (each representing the right to receive 10 Class"
        )

    def test_real_spac_rights_suffix_still_excluded(self):
        assert should_exclude("Artius II Acquisition Inc. - Rights")

    def test_real_spac_right_singular_suffix_still_excluded(self):
        assert should_exclude("Calisa Acquisition Corp - Right")
