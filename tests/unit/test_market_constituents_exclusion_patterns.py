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

from loaders.load_market_constituents import (
    CORP_SPONSOR_PATTERN,
    KNOWN_FUND_NAME_MISCLASSIFICATIONS,
    KNOWN_SPAC_MISCLASSIFICATIONS,
    _is_excluded,
    should_exclude,
)


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

    def test_comcast_zones_excluded(self):
        """GOVERNANCE 2026-08-21 (goal session - "is analyst coverage really missing"
        audit, same bug class as the TVA Power Bonds fix): CCZ ("Comcast Holdings ZONES" -
        Zero-premium Exchangeable Notes, a structured debt security exchangeable into
        Comcast stock, not common equity) flowed through this loader as real common stock -
        live-confirmed near-zero price_daily volume and Comcast's own whole-company
        financials ($121-124B revenue) misattributed to it, producing a $237.9B "market_cap"
        for what is actually a thinly-traded note."""
        assert should_exclude("Comcast Holdings ZONES")

    def test_exchangeable_voting_shares_not_excluded(self):
        """The new "zones" pattern must not false-positive on real exchangeable common
        equity - Brookfield Wealth Solutions' Class A Exchangeable Limited Voting Shares
        are real, actively-traded common stock, just structured to be exchangeable into
        another share class. Doesn't contain the word "zones" so is unaffected."""
        assert not should_exclude("Brookfield Wealth Solutions Ltd. Class A Exchangeable Limited Voting Shares")


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


class TestCapitalTrustAndSpacSponsorGapsFoundInFactorScoreReview:
    """Regression test added 2026-09-01 (/goal session, recovered from a stranded branch -
    see risk_min_weight_available_floor_added_20260831 memory entry for the broader pattern
    of fixes stuck on growth-factor-realignment never reaching main). Live-verified
    stock_scores' Risk pillar top-50 was 12/50 pre-merger SPAC shells (trust-account cash
    boxes that trade near-flat, near-zero beta, ranking above Royal Bank of Canada/Manulife)
    plus DDT (Dillard's Capital Trust I, a trust-preferred security wrongly carrying
    Dillard's Inc.'s whole-company financials in company_profile, ranking it in Value's
    top-15 too).
    """

    def test_capital_trust_preferred_security_excluded(self):
        """DDT: whole-company Dillard's Inc. financials were misattributed to this trust-
        preferred security (same "shared CIK, wrong entity" bug class as the CCZ/ZONES fix
        above), producing a nonsense PE of 0.72 and 97% margin of safety."""
        assert should_exclude("Dillard's Capital Trust I")

    def test_merger_corp_sponsor_now_caught(self):
        """ "Merger Corp" is a common SPAC-sponsor naming convention CORP_SPONSOR_PATTERN
        didn't cover - it only recognized "investment"/"acquisition" before "corp"."""
        assert should_exclude("West Enclave Merger Corp. Ordinary Shares")
        assert should_exclude("Highview Merger Corp. - Class A Ordinary Share")

    def test_acquisition_limited_sponsor_now_caught(self):
        """SPAC sponsors sometimes use "Limited"/"Ltd" instead of "Corp" as the entity
        suffix - CORP_SPONSOR_PATTERN required literal "Corp(oration)"."""
        assert should_exclude("Newbridge Acquisition Limited - Class A Ordinary Share")
        assert should_exclude("Oxley Bridge Acquisition Limited - Class A Ordinary Shares")
        assert should_exclude("Blueport Acquisition Ltd - Class A Ordinary Shares")

    def test_broadened_sponsor_pattern_does_not_catch_real_companies(self):
        """The "merger"/"limited"/"ltd" additions to CORP_SPONSOR_PATTERN must not
        false-positive on real operating companies - verified against the full active
        universe before shipping (zero new false positives found)."""
        assert not should_exclude("AGNC Investment Corp. - Common Stock")
        assert not should_exclude("Saratoga Investment Corp New")
        assert not should_exclude("First Majestic Silver Corp. Ordinary Shares (Canada)")
        assert not should_exclude("Telus Corporation Ordinary Shares")

    def test_known_spac_misclassifications_individually_verified(self):
        """GIW/APUR/NWAX/XFLH/SBXD/DYNC/CUB have no sponsor keyword ("acquisition"/
        "investment"/"merger") in their name at all (e.g. "GigCapital8 Corp.", "Aperture
        AC", "Lionheart Holdings") - broadening CORP_SPONSOR_PATTERN further to catch them
        generically (e.g. any "Corp"/"Corporation" + "Ordinary Shares") was tested against
        the full active universe and matches 47 symbols, most of them real large operating
        companies (First Majestic Silver/AG, Telus/TU, Pembina Pipeline/PBA, Eldorado
        Gold/EGO, Denison Mines/DNN, Webull/BULL, ProKidney/PROK) - the same false-positive
        shape CORP_SPONSOR_PATTERN's own two-signal design exists to avoid. Each of these 7
        was instead individually verified via stability_metrics (near-zero beta/volatility,
        the SPAC trust-mechanic fingerprint) and growth_metrics (zero computable operating
        history) before adding to the override list, same convention as
        KNOWN_WHEN_ISSUED_MISCLASSIFICATIONS/KNOWN_ETF_MISCLASSIFICATIONS.
        """
        for symbol in ("GIW", "APUR", "NWAX", "XFLH", "SBXD", "DYNC", "CUB"):
            assert symbol in KNOWN_SPAC_MISCLASSIFICATIONS

        assert _is_excluded("GIW", "GigCapital8 Corp. - Class A Ordinary Shares")
        assert _is_excluded("APUR", "Aperture AC - Class A Ordinary Shares")
        assert _is_excluded("NWAX", "New America Acquisition I Corp. Class A Common Stock")
        assert _is_excluded("XFLH", "XFLH Capital Corporation Ordinary Shares")
        assert _is_excluded("SBXD", "SilverBox Corp IV Class A Ordinary Shares")
        assert _is_excluded("DYNC", "Dynamix Corporation - Class A Ordinary Share")
        assert _is_excluded("CUB", "Lionheart Holdings - Class A Ordinary Shares")

    def test_first_majestic_silver_not_caught_by_broadened_pattern(self):
        """Regression guard: CORP_SPONSOR_PATTERN's broadened suffix group must not, on its
        own (without a sponsor keyword), match a real Canadian miner's plain "Corp.
        Ordinary Shares (Canada)" listing convention."""
        assert not CORP_SPONSOR_PATTERN.search("First Majestic Silver Corp. Ordinary Shares (Canada)")


class TestPluralAndSuffixBroadenedSponsorPattern:
    """GOVERNANCE 2026-09-01: a "top 10 per factor" review found Risk's safest list still
    12/50-SPAC-polluted despite the 2026-08-31 fix - newer SPAC cohorts use "Acquisitions"
    (plural) or Company/Group/Inc/Co suffixes CORP_SPONSOR_PATTERN didn't cover. Fingerprint-
    verified (stability_metrics near-zero beta/volatility/drawdown + growth_metrics zero
    computable history) before broadening, same standard as the 2026-08-31 fix.
    """

    def test_plural_acquisitions_now_caught(self):
        assert should_exclude("TRG Latin America Acquisitions Corp. - Class A Ordinary Shares")
        assert should_exclude("Twelve Seas Investment Company III - Class A Ordinary Shares")

    def test_acquisition_company_suffix_now_caught(self):
        assert should_exclude("American Drive Acquisition Company - Class A Ordinary Shares")
        assert should_exclude("Republic Digital Acquisition Company - Class A Ordinary Shares")
        assert should_exclude("Jackson Acquisition Company II Class A Ordinary Shares")

    def test_acquisition_group_and_inc_and_co_suffixes_now_caught(self):
        assert should_exclude("Shreya Acquisition Group Class A Ordinary Shares")
        assert should_exclude("APEX Tech Acquisition Inc. Ordinary Shares")
        assert should_exclude("Chenghe Acquisition III Co. - Class A Ordinary Shares")

    def test_broadened_suffix_group_does_not_catch_real_companies(self):
        """Same false-positive guard as the 2026-08-31 fix: the plural/suffix broadening
        must not newly match real operating companies that happen to carry "Investment"/
        "Acquisition"/"Merger" language without also being a pre-merger SPAC shell -
        verified against the full active universe before shipping (zero new false
        positives beyond the fingerprint-confirmed shells)."""
        assert not should_exclude("AGNC Investment Corp. - Common Stock")
        assert not should_exclude("Saratoga Investment Corp New")

    def test_new_known_spac_misclassifications_individually_verified(self):
        """12 more sponsor-brand-only names (no investment/acquisition/merger keyword at
        all) plus 4 found via a data-shape (not name-pattern) fingerprint sweep across the
        whole active universe - IRHO/SDHI use "Common Stock" instead of "Ordinary Shares"
        (evading SPAC_SHARE_CLASS_PATTERN the same way NWAX's predecessor name did), and
        GRAF/TONT are two different symbols sharing one verbatim security_name string.
        Each individually verified via stability_metrics + growth_metrics, same convention
        as the original 7."""
        for symbol in (
            "KBON",
            "KRAQ",
            "DNMX",
            "GTEN",
            "CEPF",
            "SCPQ",
            "SVCC",
            "TLNC",
            "KPET",
            "SBXE",
            "DYOR",
            "ALDF",
            "IRHO",
            "SDHI",
            "GRAF",
            "TONT",
        ):
            assert symbol in KNOWN_SPAC_MISCLASSIFICATIONS

        assert _is_excluded("KBON", "Karbon Capital Partners Corp. - Class A Ordinary Shares")
        assert _is_excluded("KRAQ", "KRAKacquisition Corp - Class A Ordinary Shares")
        assert _is_excluded("IRHO", "Iron Horse Acquisitions II Corp. - Common Stock")
        assert _is_excluded("SDHI", "Siddhi Acquisition Corp - Class A Common stock")
        assert _is_excluded("GRAF", "Graf Global Corp. Class A ordinary shares")
        assert _is_excluded("TONT", "Graf Global Corp. Class A ordinary shares")

    def test_thin_data_real_companies_not_misclassified(self):
        """HYNE/NUTR/WSBK matched the same SPAC-shaped fingerprint (near-zero beta/
        volatility, zero computable growth history) but are real, if obscure and thinly
        traded, operating companies (small community banks / a travel-booking company) -
        NOT SPAC shells. Confirms the fingerprint alone isn't a sufficient signal without
        the name-pattern check too."""
        assert not should_exclude("Hoyne Bancorp, Inc. - Common Stock")
        assert not should_exclude("Nusatrip Incorporated - Common Stock")
        assert not should_exclude("Winchester Bancorp, Inc. - Common Stock")
        for symbol in ("HYNE", "NUTR", "WSBK"):
            assert symbol not in KNOWN_SPAC_MISCLASSIFICATIONS


class TestAdsWarrantAbbreviationExcluded:
    """GOVERNANCE 2026-09-01: PSNYW ("Polestar Automotive Holding UK Limited - Class C-1
    ADS (ADW)") is Polestar's publicly traded ADS warrant, not common equity - the bare
    `\\bwarrant(s)?\\b` pattern never matches because the word "warrant" is abbreviated to
    "(ADW)". Live-confirmed via price action: PSNYW went from $0.2645 (2025-09-30) to $5.75
    (2026-08-31), a ~21.7x move, while the underlying PSNY common ADS only traded $12.59
    that same day - the leveraged-warrant amplification signature, not a plausible common-
    equity return. This inflated a single-instrument leverage artifact into Momentum's
    top-10 above real operating companies.
    """

    def test_psnyw_ads_warrant_excluded(self):
        assert should_exclude("Polestar Automotive Holding UK Limited - Class C-1 ADS (ADW)")

    def test_psny_common_ads_not_excluded(self):
        assert not should_exclude("Polestar Automotive Holding UK Limited - Class A ADS")


class TestBdcFundNameMisclassificationExcluded:
    """GOVERNANCE 2026-09-07 (goal: stock_scores factor/composite sanity audit - BDC/REIT
    universe coverage check): business development companies (BDCs) are real, actively-
    traded operating lending businesses that are nonetheless legally organized as closed-
    end investment companies under the Investment Company Act of 1940, so NASDAQ's own
    listing feed tags many of them "<Name> - Closed End Fund" or includes "Fund" directly
    in the legal name - both false-positiving on EXCLUSION_PATTERNS' \\bfund\\b/
    \\bclosed[- ]end\\b entries (correctly meant to catch real pooled funds).

    Found by spot-checking ARCC/FSK/PSEC/HTGC/OBDC/GBDC/TSLX/GSBD/BXSL/TPVG against
    stock_symbols - 4 missing (ARCC/PSEC/GBDC/BXSL). An initial pass wrongly concluded
    ARCC/PSEC/GBDC weren't should_exclude() false positives by testing GUESSED plain
    legal names instead of the real raw nasdaqlisted.txt row text ("Ares Capital
    Corporation - Closed End Fund", etc.) - re-checked against the real feed strings and
    all 4 are should_exclude() false positives via \\bclosed[- ]end\\b or \\bfund\\b. Each
    individually verified as a genuine operating company (not a pooled fund) via SEC's own
    live submissions API: entityType="operating", real recent 10-K filings (ARCC CIK
    1287750, PSEC CIK 1287032, GBDC CIK 1476765).
    """

    def test_bxsl_fund_name_false_positive_excluded_by_bare_pattern(self):
        """Confirms the bug: without the override, the real BDC's raw feed name matches."""
        assert should_exclude("Blackstone Secured Lending Fund Common Shares of Beneficial Interest")

    def test_closed_end_fund_suffix_false_positive_on_real_bdcs(self):
        """ARCC/PSEC/GBDC's real nasdaqlisted.txt security_name (not a guessed plain legal
        name) is caught via \\bclosed[- ]end\\b, the same false-positive shape as BXSL."""
        assert should_exclude("Ares Capital Corporation - Closed End Fund")
        assert should_exclude("Prospect Capital Corporation - Closed End Fund")
        assert should_exclude("Golub Capital BDC, Inc. - Closed End Fund")

    def test_bdcs_not_excluded_via_is_excluded_override(self):
        assert not _is_excluded("BXSL", "Blackstone Secured Lending Fund Common Shares of Beneficial Interest")
        assert not _is_excluded("ARCC", "Ares Capital Corporation - Closed End Fund")
        assert not _is_excluded("PSEC", "Prospect Capital Corporation - Closed End Fund")
        assert not _is_excluded("GBDC", "Golub Capital BDC, Inc. - Closed End Fund")

    def test_all_four_bdcs_in_known_fund_name_misclassifications(self):
        assert {"ARCC", "BXSL", "GBDC", "PSEC"} == KNOWN_FUND_NAME_MISCLASSIFICATIONS

    def test_real_closed_end_funds_still_excluded(self):
        """The override must be scoped to these 4 symbols alone - a real closed-end/mutual
        fund without a symbol-level override must still be excluded, including one carrying
        the exact same "- Closed End Fund" suffix as the real BDCs above."""
        assert should_exclude("Blackrock Multi-Sector Income Trust Fund")
        assert _is_excluded("BXFAKE", "Blackrock Multi-Sector Income Trust Fund")
        assert should_exclude("Calamos Convertible Opportunities and Income Fund - Closed End Fund")
        assert _is_excluded("CHI", "Calamos Convertible Opportunities and Income Fund - Closed End Fund")
