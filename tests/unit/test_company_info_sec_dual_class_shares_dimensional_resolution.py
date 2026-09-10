"""Regression test for the 2026-08-22 fix (goal session - "BRK.B and those types" follow-up):
the 2026-08-21 ambiguity guard (test_company_info_sec_dual_class_shares_ambiguity_guard.py)
correctly stopped guessing a dual-class filer's shares_outstanding via max(), but left every
dot-suffixed ticker (BRK.A, BRK.B, LEN.B, ...) permanently NULL even when the filing text
unambiguously identifies each class's real share count.

Live-verified against real SEC inline XBRL (Berkshire Hathaway CIK 1067983's and Lennar's
CIK 920760's actual, current 10-Q filings): each <ix:nonFraction> shares-outstanding fact has
a contextRef pointing at an <xbrli:context> whose <xbrldi:explicitMember
dimension="us-gaap:StatementClassOfStockAxis"> names the exact class
(us-gaap:CommonClassAMember / us-gaap:CommonClassBMember) - this is the standard US-GAAP
taxonomy convention, not a per-filer guess. _fetch_shares_outstanding_from_filing_text() now
tries this dimensional resolution first; only falls through to the original ambiguous-reject
guard when it can't determine an unambiguous single match.
"""

from unittest.mock import MagicMock, patch

from loaders.load_company_info_sec import CompanyInfoSECLoader

# Real (structure-preserving, values are the live-verified real ones) shape of Berkshire's
# 10-Q inline XBRL for the two EntityCommonStockSharesOutstanding facts plus their contexts.
_BRK_FILING_TEXT = (
    '<ix:nonFraction id="f-1" contextRef="c-classA" name="dei:EntityCommonStockSharesOutstanding" '
    'unitRef="shares" decimals="INF">488,450</ix:nonFraction>'
    '<ix:nonFraction id="f-2" contextRef="c-classB" name="dei:EntityCommonStockSharesOutstanding" '
    'unitRef="shares" decimals="INF">1,408,035,161</ix:nonFraction>'
    '<xbrli:context id="c-classA"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">'
    "0001067983</xbrli:identifier><xbrli:segment><xbrldi:explicitMember "
    'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember>'
    "</xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2026-07-29</xbrli:instant>"
    "</xbrli:period></xbrli:context>"
    '<xbrli:context id="c-classB"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">'
    "0001067983</xbrli:identifier><xbrli:segment><xbrldi:explicitMember "
    'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember</xbrldi:explicitMember>'
    "</xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2026-07-29</xbrli:instant>"
    "</xbrli:period></xbrli:context>"
)


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions_with_10k(accession: str = "0001067983-26-000018", tickers: list | None = None) -> dict:
    d: dict = {"filings": {"recent": {"form": ["10-K"], "accessionNumber": [accession], "filingDate": ["2026-06-15"]}}}
    if tickers is not None:
        d["tickers"] = tickers
    return d


class TestDimensionalClassResolution:
    def test_brk_a_resolves_to_its_own_class_a_value(self):
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _BRK_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text("BRK.A", "1067983", _submissions_with_10k())

        assert result == 488_450

    def test_brk_b_resolves_to_its_own_class_b_value_not_its_siblings(self):
        """The exact bug this whole fix chain started from: BRK.B must get its OWN real
        ~1.4B share count, not BRK.A's ~488K (the $1.03 QUADRILLION market_cap incident)."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = _BRK_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text("BRK.B", "1067983", _submissions_with_10k())

        assert result == 1_408_035_161

    def test_context_without_class_dimension_falls_through_to_ambiguous_reject(self):
        """A context that exists but carries no ClassOfStockAxis member (e.g. reused from an
        unrelated fact) must not be treated as a match - falls through to the original,
        still-correct reject-on-ambiguity behavior."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction contextRef="c-1" name="dei:EntityCommonStockSharesOutstanding">'
            "601,935</ix:nonFraction>"
            '<ix:nonFraction contextRef="c-2" name="dei:EntityCommonStockSharesOutstanding">'
            "1,389,605,139</ix:nonFraction>"
            '<xbrli:context id="c-1"><xbrli:entity><xbrli:identifier>0001067983</xbrli:identifier>'
            "</xbrli:entity></xbrli:context>"
            '<xbrli:context id="c-2"><xbrli:entity><xbrli:identifier>0001067983</xbrli:identifier>'
            "</xbrli:entity></xbrli:context>"
        )

        result = loader._fetch_shares_outstanding_from_filing_text("BRK.A", "1067983", _submissions_with_10k())

        assert result is None

    def test_bare_ticker_resolves_via_explicit_class_text_in_security_name(self):
        """Lennar-shaped fixture: LEN is bare (no dot) but stock_symbols.security_name
        literally says "...Class A Common Stock" - a real, live-confirmed exception to the
        usual bare-ticker-has-no-signal case, trusted only because the text is explicit."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction contextRef="c-a" name="dei:EntityCommonStockSharesOutstanding">'
            "210,506,003</ix:nonFraction>"
            '<ix:nonFraction contextRef="c-b" name="dei:EntityCommonStockSharesOutstanding">'
            "30,389,139</ix:nonFraction>"
            '<xbrli:context id="c-a"><xbrli:segment><xbrldi:explicitMember '
            'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember'
            "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
            '<xbrli:context id="c-b"><xbrli:segment><xbrldi:explicitMember '
            'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember'
            "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        )

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Lennar Corporation Class A Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text("LEN", "920760", _submissions_with_10k())

        assert result == 210_506_003

    def test_bare_ticker_with_no_class_text_in_security_name_stays_unresolved(self):
        """Real, live-confirmed case (WSO/AGM/GTN/HVT-shaped): security_name is plain
        "...Common Stock" with no class wording - must NOT guess, stays None same as before
        this fix existed."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction contextRef="c-a" name="dei:EntityCommonStockSharesOutstanding">'
            "601,935</ix:nonFraction>"
            '<ix:nonFraction contextRef="c-b" name="dei:EntityCommonStockSharesOutstanding">'
            "1,389,605,139</ix:nonFraction>"
            '<xbrli:context id="c-a"><xbrli:segment><xbrldi:explicitMember '
            'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember'
            "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
            '<xbrli:context id="c-b"><xbrli:segment><xbrldi:explicitMember '
            'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember'
            "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        )

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Watsco, Inc. Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "WSO", "469759", _submissions_with_10k(tickers=["WSO", "WSO-B"])
            )

        assert result is None


class TestTargetClassLetter:
    def test_dot_suffix_resolves_directly_without_db_lookup(self):
        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            assert CompanyInfoSECLoader._target_class_letter("BRK.B") == "B"
            mock_db_ctx.assert_not_called()

    def test_multi_letter_suffix_is_not_a_class_letter(self):
        """Defensive: something like a ".R" (rights) suffix isn't a single-letter class -
        must not be misread as a class letter."""
        assert CompanyInfoSECLoader._target_class_letter("XYZ.WS") is None

    def test_security_name_missing_class_letter_override_resolves_without_db_lookup(self):
        """WLY/WLYB (John Wiley & Sons) both carry the identical generic security_name "John
        Wiley & Sons, Inc. Common Stock" - live-confirmed neither has "Class A"/"Class B" text,
        unlike every other dual-class family sampled in the same sweep. The curated override
        must resolve both without ever needing the (unhelpful) security_name lookup."""
        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            assert CompanyInfoSECLoader._target_class_letter("WLY") == "A"
            assert CompanyInfoSECLoader._target_class_letter("WLYB") == "B"
            mock_db_ctx.assert_not_called()


class TestWileyClassLetterOverrideDimensionalResolution:
    """End-to-end: WLY/WLYB's real current 10-Q (jwa-20260731.htm, CIK 107140) tags both
    classes with standard dimensions - live-confirmed us-gaap:CommonClassAMember=41,925,511
    (WLY) and us-gaap:CommonClassBMember=8,758,419 (WLYB). Before the override, both fell
    through target_letter=None into the ambiguous-reject path despite this being fully
    resolvable, identical bug shape to BRK.A/BRK.B before that fix landed."""

    _WLY_FILING_TEXT = (
        '<ix:nonFraction contextRef="c-4" name="dei:EntityCommonStockSharesOutstanding">'
        "41,925,511</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-5" name="dei:EntityCommonStockSharesOutstanding">'
        "8,758,419</ix:nonFraction>"
        '<xbrli:context id="c-4"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-5"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
    )

    def test_wly_resolves_to_its_own_class_a_value(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._WLY_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text(
            "WLY", "107140", _submissions_with_10k(tickers=["WLY", "WLYB"])
        )

        assert result == 41_925_511

    def test_wlyb_resolves_to_its_own_class_b_value_not_its_siblings(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._WLY_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text(
            "WLYB", "107140", _submissions_with_10k(tickers=["WLY", "WLYB"])
        )

        assert result == 8_758_419


class TestAtroVerifiedCustomDefaultClassMember:
    """ATRO (Astronics Corporation, CIK 8063) has only ONE registered common ticker - its real
    current 10-K (atro-20260226) tags its plain "common stock" (the class ATRO actually trades,
    31,868,534 shares) under a filer-custom `atro:CommonClassUndefinedMember` dimension member
    instead of the standard `us-gaap:CommonStockMember` - live-confirmed via the filing's own
    prose ("consisting of 36,107,984 [sic, a later filing's count] shares of common stock ...
    and ... shares of Class B common stock"). Before the fix, `_context_is_generic_common_class`
    correctly refused to trust the non-standard member name (same caution that caught the UHAL
    bug), so ATRO fell through to the ambiguous reject despite having only one real ticker."""

    _ATRO_FILING_TEXT = (
        '<ix:nonFraction contextRef="c-2" name="dei:EntityCommonStockSharesOutstanding">'
        "31,868,534</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-3" name="dei:EntityCommonStockSharesOutstanding">'
        "3,822,641</ix:nonFraction>"
        '<xbrli:context id="c-2"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">atro:CommonClassUndefinedMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-3"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
    )

    def test_atro_resolves_to_its_plain_common_stock_value_via_verified_override(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._ATRO_FILING_TEXT

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Astronics Corporation - Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "ATRO", "8063", _submissions_with_10k(tickers=["ATRO", "ATROB"])
            )

        assert result == 31_868_534

    def test_unverified_symbol_with_same_shape_stays_unresolved(self):
        """Guards the allowlist discipline: a DIFFERENT symbol with the identical
        CommonClassUndefinedMember shape must NOT be trusted just because ATRO's is - only an
        individually-verified entry in _VERIFIED_DEFAULT_CLASS_CUSTOM_MEMBERS is trusted."""
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._ATRO_FILING_TEXT

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Some Other Company Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "ZZZZ", "999999", _submissions_with_10k(tickers=["ZZZZ", "ZZZZB"])
            )

        assert result is None


class TestTrSecurityNameOverride:
    """TR (Tootsie Roll Industries) - same vendor/master-data gap shape as WLY: real current
    10-K (CIK 98677) embeds the class dimension directly in the contextRef id string (Workiva-
    style, same shape as the Liberty Media family), fully resolvable once TR's own class letter
    is known via the override."""

    _TR_FILING_TEXT = (
        '<ix:nonFraction contextRef="As_Of_2_11_2026_us-gaap_StatementClassOfStockAxis_'
        'us-gaap_CommonClassAMember_P1fjnRulyUK9I85TyF2i8A" '
        'name="dei:EntityCommonStockSharesOutstanding">41,820,966</ix:nonFraction>'
        '<ix:nonFraction contextRef="As_Of_2_11_2026_us-gaap_StatementClassOfStockAxis_'
        'us-gaap_CommonClassBMember_j2i8fgtt-kWU94OHTVgKLQ" '
        'name="dei:EntityCommonStockSharesOutstanding">31,165,664</ix:nonFraction>'
    )

    def test_tr_resolves_to_its_own_class_a_value_without_db_lookup(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._TR_FILING_TEXT

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            result = loader._fetch_shares_outstanding_from_filing_text(
                "TR", "98677", _submissions_with_10k(tickers=["TR", "TROLB"])
            )
            mock_db_ctx.assert_not_called()

        assert result == 41_820_966


class TestMovVerifiedCustomDefaultClassMember:
    """MOV (Movado Group) - same non-standard-custom-member shape as ATRO but a DIFFERENT
    filer-specific string (`mov:CommonStockClassUndefinedMember`, not ATRO's
    `atro:CommonClassUndefinedMember`) - live-confirmed via the filing's own prose ("shares
    outstanding of the registrant's Common Stock and Class A Common Stock ... were 15,622,386
    and 6,455,602")."""

    _MOV_FILING_TEXT = (
        '<ix:nonFraction contextRef="c-mov-1" name="dei:EntityCommonStockSharesOutstanding">'
        "15,622,386</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-mov-2" name="dei:EntityCommonStockSharesOutstanding">'
        "6,455,602</ix:nonFraction>"
        '<xbrli:context id="c-mov-1"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">mov:CommonStockClassUndefinedMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-mov-2"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
    )

    def test_mov_resolves_to_its_plain_common_stock_value(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._MOV_FILING_TEXT

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Movado Group Inc. Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "MOV", "72573", _submissions_with_10k(tickers=["MOV", "MOVAA"])
            )

        assert result == 15_622_386

    def test_atro_custom_member_string_does_not_leak_to_mov(self):
        """Guards that ATRO's `commonclassundefinedmember` entry doesn't accidentally also
        match MOV's differently-spelled `commonstockclassundefinedmember` string or vice versa -
        each filer's exact custom member string is checked independently."""
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        # Same shape as MOV's real filing, but tagged with ATRO's exact custom string instead.
        loader.sec_client.get_filing_plaintext.return_value = self._MOV_FILING_TEXT.replace(
            "mov:CommonStockClassUndefinedMember", "mov:CommonClassUndefinedMember"
        )

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Movado Group Inc. Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "MOV", "72573", _submissions_with_10k(tickers=["MOV", "MOVAA"])
            )

        # MOV's allowlist entry only covers "commonstockclassundefinedmember" - the ATRO-shaped
        # string must NOT resolve for MOV even though it happens to match ATRO's own entry.
        assert result is None


class TestAgmSecurityNameOverride:
    """AGM (Federal Agricultural Mortgage Corp/"Farmer Mac") has THREE classes - live-confirmed
    via CIK 845877's real current 10-K: Class A (1,030,780, restricted, separately ticketed as
    AGM.A), Class B (500,301, restricted, no separate ticker), Class C (9,325,900, the actual
    NYSE-traded public float, ticker AGM). Bare "AGM" has the WLY-shaped security_name gap
    (generic "...Common Stock", no "Class X" text)."""

    _AGM_FILING_TEXT = (
        '<ix:nonFraction contextRef="c-10" name="dei:EntityCommonStockSharesOutstanding">'
        "1,030,780</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-11" name="dei:EntityCommonStockSharesOutstanding">'
        "500,301</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-12" name="dei:EntityCommonStockSharesOutstanding">'
        "9,325,900</ix:nonFraction>"
        '<xbrli:context id="c-10"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-11"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-12"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassCMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
    )

    def test_agm_resolves_to_its_own_class_c_value_without_db_lookup(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._AGM_FILING_TEXT

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            result = loader._fetch_shares_outstanding_from_filing_text(
                "AGM", "845877", _submissions_with_10k(tickers=["AGM", "AGM-A"])
            )
            mock_db_ctx.assert_not_called()

        assert result == 9_325_900


class TestFwonaLetterlessClassMemberOverride:
    """FWONA (Liberty Media's Formula One tracking stock, Series A) has its own target_letter
    correctly resolved to "A" via security_name ("...Series A Liberty Formula One Common
    Stock"), but its real current 10-K tags Series A's own value under a genuinely letterless
    filer-custom member (`lmca:LibertyFormulaOneGroupCommonClassMember`) - unlike its siblings'
    `...CommonClassBMember`/`...CommonClassCMember`, which DO carry a letter and already resolve
    via the standard path."""

    _FWONA_FILING_TEXT = (
        '<ix:nonFraction contextRef="c-a" name="dei:EntityCommonStockSharesOutstanding">'
        "23,991,058</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-b" name="dei:EntityCommonStockSharesOutstanding">'
        "2,381,188</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-c" name="dei:EntityCommonStockSharesOutstanding">'
        "224,102,531</ix:nonFraction>"
        '<xbrli:context id="c-a"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">lmca:LibertyFormulaOneGroupCommonClassMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-b"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">lmca:LibertyFormulaOneGroupCommonClassBMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-c"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">lmca:LibertyFormulaOneGroupCommonClassCMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
    )

    def test_fwona_resolves_to_its_own_series_a_value(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._FWONA_FILING_TEXT

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Liberty Media Corporation - Series A Liberty Formula One Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "FWONA", "1560385", _submissions_with_10k(tickers=["FWONA", "FWONK", "FWONB"])
            )

        assert result == 23_991_058

    def test_unverified_symbol_with_same_letterless_member_stays_unresolved(self):
        """Guards the allowlist discipline: a DIFFERENT symbol hitting the identical letterless
        member shape must NOT be trusted just because FWONA's is - only an individually-
        verified entry in _VERIFIED_LETTERLESS_CLASS_MEMBER_OVERRIDES is trusted, same as the
        MKC/MKC.V corruption this replaces was reverted for trying to generalize."""
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._FWONA_FILING_TEXT.replace("FWONA", "ZZZZA").replace(
            "lmca:LibertyFormulaOneGroupCommonClassMember", "lmca:LibertyFormulaOneGroupCommonClassMember"
        )

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Some Other Corp - Series A Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "ZZZZA", "999999", _submissions_with_10k(tickers=["ZZZZA", "ZZZZK", "ZZZZB"])
            )

        assert result is None


class TestPreferredClassMemberDoesNotCollideWithCommonClassLetter:
    """PGY (Pagaya Technologies) - real current 10-K (CIK 1883085) tags THREE contexts:
    us-gaap:CommonClassAMember (71,237,859, PGY's real Class A ordinary shares),
    us-gaap:CommonClassBMember (11,288,577), and us-gaap:PreferredClassAMember (2,027,147, an
    unrelated preferred series that merely happens to share the letter "A"). Before the fix,
    _class_letter_for_context's letter-extraction regex matched "A" for BOTH the common and
    preferred Class A contexts, so target_letter="A" (from security_name's "Class A Ordinary
    Shares") found 2 dimensional matches instead of exactly 1 and fell through to the
    ambiguous reject despite the common-class value being fully resolvable."""

    _PGY_FILING_TEXT = (
        '<ix:nonFraction contextRef="c-4" name="dei:EntityCommonStockSharesOutstanding">'
        "71,237,859</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-5" name="dei:EntityCommonStockSharesOutstanding">'
        "11,288,577</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-6" name="dei:EntityCommonStockSharesOutstanding">'
        "2,027,147</ix:nonFraction>"
        '<xbrli:context id="c-4"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-5"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-6"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:PreferredClassAMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
    )

    def test_pgy_resolves_to_its_own_common_class_a_value_not_the_preferred_class_a(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._PGY_FILING_TEXT

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Pagaya Technologies Ltd. - Class A Ordinary Shares",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "PGY", "1883085", _submissions_with_10k(tickers=["PGY", "PGYWW"])
            )

        assert result == 71_237_859


class TestPlainProseUnitsOutstandingFallback:
    """5 oil/gas royalty trusts (CRT, MTR, PBT, SBR, SJT) tag ZERO inline-XBRL shares-
    outstanding fact at all - real unit counts live only in free-form cover-page prose, in one
    of two live-confirmed shapes. Deliberately gated to this exact symbol set - see
    _VERIFIED_PLAIN_PROSE_UNIT_SYMBOLS' own comment for the false-positive risk this guards."""

    def _loader_with_text(self, text: str) -> CompanyInfoSECLoader:
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = text
        return loader

    def test_crt_resolves_via_there_were_phrasing(self):
        loader = self._loader_with_text(
            "At March 18, 2026, there were 6,000,000 units outstanding and approximately "
            "145 unitholders of record; 5,968,235 of these units were held by ..."
        )
        result = loader._fetch_shares_outstanding_from_filing_text("CRT", "881787", _submissions_with_10k())
        assert result == 6_000_000

    def test_mtr_resolves_via_units_outstanding_were_held_by_phrasing(self):
        loader = self._loader_with_text(
            "At December 31, 2025, the 1,863,590 units outstanding were held by 374 unitholders of record."
        )
        result = loader._fetch_shares_outstanding_from_filing_text("MTR", "313364", _submissions_with_10k())
        assert result == 1_863_590

    def test_pbt_resolves_via_units_of_beneficial_interest_phrasing(self):
        loader = self._loader_with_text(
            "At March 27, 2026, there were 46,608,796 Units of Beneficial Interest of the Trust outstanding."
        )
        result = loader._fetch_shares_outstanding_from_filing_text("PBT", "319654", _submissions_with_10k())
        assert result == 46_608_796

    def test_percentage_threshold_mention_is_not_falsely_matched(self):
        """A trust indenture routinely mentions "75% of all Units outstanding" as a voting
        threshold, not the total outstanding count - the regex's minimum-digit-length floor
        must reject this and keep scanning for the real cover-page statement."""
        loader = self._loader_with_text(
            "the Trustee may not sell all or any part of the Royalties unless approved by "
            "holders of 75% of all Units outstanding in which case the sale must be final. "
            "At March 27, 2026, there were 46,608,796 Units of Beneficial Interest of the "
            "Trust outstanding."
        )
        result = loader._fetch_shares_outstanding_from_filing_text("PBT", "319654", _submissions_with_10k())
        assert result == 46_608_796

    def test_unverified_symbol_with_same_units_phrasing_stays_unresolved(self):
        """Guards the allowlist discipline: an unrelated company's RSU/stock-unit disclosure
        must NOT be trusted just because it matches the same "N units ... outstanding" shape -
        only the 5 individually-verified royalty trusts are checked at all."""
        loader = self._loader_with_text("As of the record date, 500,000 stock units outstanding under the 2024 Plan.")
        result = loader._fetch_shares_outstanding_from_filing_text("ZZZZ", "999999", _submissions_with_10k())
        assert result is None


class TestPlainProseClassSharesFallback:
    """BTGO (BitGo Holdings) tags ZERO inline-XBRL shares-outstanding fact - real dual-class
    counts live only in free-form cover-page prose. BTGO's own ticker is Class A."""

    _BTGO_FILING_TEXT = (
        "On March 19, 2026, the registrant had 106,611,583 shares of Class A common stock "
        "and 8,855,382 shares of Class B common stock outstanding."
    )

    def test_btgo_resolves_to_its_own_class_a_value(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._BTGO_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text("BTGO", "1740604", _submissions_with_10k())

        assert result == 106_611_583

    def test_unverified_symbol_with_same_class_shares_phrasing_stays_unresolved(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._BTGO_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text("ZZZZ", "999999", _submissions_with_10k())

        assert result is None


class TestNonBreakingSpaceEntityNormalization:
    """FIXED 2026-09-09: get_filing_plaintext returns the raw, un-rendered .txt submission,
    where real filing HTML often separates a number from the following word with a literal
    "&#160;"/"&nbsp;" non-breaking-space ENTITY rather than an actual whitespace character -
    every `\\s+`-based prose regex silently failed to match despite the real text being present.

    Live-confirmed via MTR (Mesa Royalty Trust)'s real, current 10-K (CIK 313364, accession
    0001104659-26-036896): its raw .txt cover page literally reads "1,863,590&#160;Units of
    Beneficial Interest were outstanding" - zero matches before this fix even though MTR is a
    verified plain-prose-units symbol, while its 4 royalty-trust siblings (CRT/PBT/SBR/SJT)
    resolved correctly the same run because their specific filings happened to use a real space
    at the equivalent spot.
    """

    def _loader_with_text(self, text: str) -> CompanyInfoSECLoader:
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = text
        return loader

    def test_mtr_resolves_when_number_and_units_are_joined_by_nbsp_entity(self):
        loader = self._loader_with_text(
            "As of March 24, 2026, 1,863,590&#160;Units of Beneficial Interest were outstanding in Mesa Royalty Trust."
        )
        result = loader._fetch_shares_outstanding_from_filing_text("MTR", "313364", _submissions_with_10k())
        assert result == 1_863_590

    def test_mtr_resolves_when_joined_by_named_nbsp_entity(self):
        loader = self._loader_with_text(
            "At December 31, 2025, the 1,863,590&nbsp;units outstanding were held by 374 unitholders."
        )
        result = loader._fetch_shares_outstanding_from_filing_text("MTR", "313364", _submissions_with_10k())
        assert result == 1_863_590

    def test_mtr_resolves_when_joined_by_hex_nbsp_entity(self):
        loader = self._loader_with_text(
            "At December 31, 2025, the 1,863,590&#xA0;units outstanding were held by 374 unitholders."
        )
        result = loader._fetch_shares_outstanding_from_filing_text("MTR", "313364", _submissions_with_10k())
        assert result == 1_863_590

    def test_normalization_does_not_break_plain_space_case(self):
        """Regression guard: the pre-existing plain-space phrasing (already covered by
        TestPlainProseUnitsOutstandingFallback above) must keep resolving unchanged."""
        loader = self._loader_with_text(
            "At December 31, 2025, the 1,863,590 units outstanding were held by 374 unitholders of record."
        )
        result = loader._fetch_shares_outstanding_from_filing_text("MTR", "313364", _submissions_with_10k())
        assert result == 1_863_590


class TestUhalSecurityNameOverrideAndLetterlessClassMember:
    """UHAL/UHAL.B (U-Haul Holding Company/AMERCO) - live-confirmed via CIK 4457's real current
    10-K (uhal-20260331.htm): cover page tags `us-gaap:CommonClassAMember`=19,607,788 (UHAL's
    own closely-held voting class) and `us-gaap:NonvotingCommonStockMember`=176,470,092 (UHAL.B's
    Series N Non-Voting class). UHAL's bare security_name has no "Class X" text (needs
    _SECURITY_NAME_MISSING_CLASS_LETTER_OVERRIDES), and UHAL.B's real member name carries no
    letter at all despite its own target_letter resolving to "B" via the dot suffix (needs
    _VERIFIED_LETTERLESS_CLASS_MEMBER_OVERRIDES) - this is the "UHAL-burn" case
    `_context_is_generic_common_class`'s docstring already documents the ground truth for."""

    _UHAL_FILING_TEXT = (
        '<ix:nonFraction contextRef="c-a" name="dei:EntityCommonStockSharesOutstanding">'
        "19,607,788</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-b" name="dei:EntityCommonStockSharesOutstanding">'
        "176,470,092</ix:nonFraction>"
        '<xbrli:context id="c-a"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-b"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:NonvotingCommonStockMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
    )

    def test_uhal_resolves_to_its_own_voting_class_a_value_without_db_lookup(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._UHAL_FILING_TEXT

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            result = loader._fetch_shares_outstanding_from_filing_text(
                "UHAL", "4457", _submissions_with_10k(tickers=["UHAL", "UHAL.B"])
            )
            mock_db_ctx.assert_not_called()

        assert result == 19_607_788

    def test_uhal_b_resolves_to_its_own_nonvoting_value_not_its_sibling(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._UHAL_FILING_TEXT

        result = loader._fetch_shares_outstanding_from_filing_text(
            "UHAL.B", "4457", _submissions_with_10k(tickers=["UHAL", "UHAL.B"])
        )

        assert result == 176_470_092

    def test_unverified_symbol_with_same_nonvoting_member_stays_unresolved(self):
        """Guards the allowlist discipline: a DIFFERENT dot-suffixed symbol hitting the
        identical `NonvotingCommonStockMember` shape must NOT be trusted just because UHAL.B's
        is - only the individually-verified UHAL.B entry is trusted."""
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._UHAL_FILING_TEXT.replace("c-b", "c-z")

        result = loader._fetch_shares_outstanding_from_filing_text(
            "ZZZZ.B", "999999", _submissions_with_10k(tickers=["ZZZZ", "ZZZZ.B"])
        )

        assert result is None


class TestCentVerifiedCustomDefaultClassMember:
    """CENT (Central Garden & Pet Company) has THREE classes - live-confirmed via CIK 887733's
    real current 10-K (cent-20250927.htm): `cent:CommonClassOneMember`=9,650,221 (CENT's own
    plain "Common Stock"), `us-gaap:CommonClassAMember`=51,080,111 (CENTA, not in this
    universe), `us-gaap:CommonClassBMember`=1,602,374 (closely-held, no separate ticker). The
    filing's own prose confirms: "the number of shares outstanding of the registrant's Common
    Stock was 9,650,221 ... Class A Common Stock was 51,080,111 ... 1,602,374 shares of its
    Class B Stock" - CENT must resolve to the SMALLEST value here, not the largest (a naive
    "take the max" would wrongly pick CENTA's count)."""

    _CENT_FILING_TEXT = (
        '<ix:nonFraction contextRef="c-7" name="dei:EntityCommonStockSharesOutstanding">'
        "9,650,221</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-8" name="dei:EntityCommonStockSharesOutstanding">'
        "51,080,111</ix:nonFraction>"
        '<ix:nonFraction contextRef="c-9" name="dei:EntityCommonStockSharesOutstanding">'
        "1,602,374</ix:nonFraction>"
        '<xbrli:context id="c-7"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">cent:CommonClassOneMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-8"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
        '<xbrli:context id="c-9"><xbrli:segment><xbrldi:explicitMember '
        'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember'
        "</xbrldi:explicitMember></xbrli:segment></xbrli:context>"
    )

    def test_cent_resolves_to_its_own_plain_common_stock_value_via_verified_override(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._CENT_FILING_TEXT

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Central Garden & Pet Company - Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "CENT", "887733", _submissions_with_10k(tickers=["CENT", "CENTA"])
            )

        assert result == 9_650_221

    def test_unverified_symbol_with_same_custom_member_stays_unresolved(self):
        """Guards the allowlist discipline: a DIFFERENT symbol hitting the identical
        `CommonClassOneMember` shape must NOT be trusted just because CENT's is."""
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        loader.sec_client = MagicMock()
        loader.sec_client.get_filing_plaintext.return_value = self._CENT_FILING_TEXT.replace(
            "cent:CommonClassOneMember", "zzzz:CommonClassOneMember"
        )

        with patch("loaders.load_company_info_sec.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = ("Some Other Company Common Stock",)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader._fetch_shares_outstanding_from_filing_text(
                "ZZZZ", "999999", _submissions_with_10k(tickers=["ZZZZ", "ZZZZA"])
            )

        assert result is None
