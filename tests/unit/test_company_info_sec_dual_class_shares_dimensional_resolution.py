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
