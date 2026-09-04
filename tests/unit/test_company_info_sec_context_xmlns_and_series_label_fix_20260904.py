"""Regression test for the 2026-09-04 fix (goal session: SEC/XBRL missing-data sweep,
DGICA/DGICB and FWONA/FWONK/GLIBA/GLIBK/LLYVA/LLYVK/BATRA/BATRK shares_outstanding
investigation).

Two independent, real bugs in the same dimensional class-resolution path added 2026-08-22:

1. `_CONTEXT_BLOCK_RE_TEMPLATE` hardcoded `<xbrli:context id="{}">` with `id` as the tag's
   first/only attribute - live-confirmed via Donegal Group's real, current 10-K (CIK 800457)
   that some filing agents inject an extra `xmlns=""` attribute before `id`
   (`<xbrli:context xmlns="" id="c4">`), which the exact-match template never found, silently
   blocking dimensional resolution for both DGICA and DGICB even though the filing tags Class A
   and Class B shares distinctly.

2. `_CLASS_LETTER_FROM_SECURITY_NAME_RE` only matched "Class {LETTER}" - live-confirmed the
   entire Liberty Media tracking-stock family (FWONA/FWONK, GLIBA/GLIBK, LLYVA/LLYVK, and
   Atlanta Braves Holdings' BATRA/BATRK) name their security_name "Series {LETTER}" instead,
   so `_target_class_letter` always returned None for these bare (non-dot-suffixed) tickers,
   blocking dimensional resolution before it could even be attempted - even though their
   underlying XBRL member is still the standard "CommonClass{LETTER}Member" shape.

Also covers the companion fix: some filers (Liberty Media family, via Workiva-style
generators) embed the full dimension/member name directly in the contextRef id string itself
rather than defining a separate short `<xbrli:context id="...">` block - `_COMMON_CLASS_MEMBER_IN_ID_RE`
resolves these directly without needing a context-block lookup at all.
"""

from loaders.load_company_info_sec import CompanyInfoSECLoader

# Real (structure-preserving) shape of Donegal Group's actual 10-K inline XBRL: an extra
# xmlns="" attribute before id, which the old exact-match template could not find.
_DGIC_FILING_TEXT = (
    '<ix:nonFraction contextRef="c4" name="dei:EntityCommonStockSharesOutstanding" '
    'scale="0" unitRef="shares">31,426,189</ix:nonFraction>'
    '<ix:nonFraction contextRef="c5" name="dei:EntityCommonStockSharesOutstanding" '
    'scale="0" unitRef="shares">5,576,775</ix:nonFraction>'
    '<xbrli:context xmlns="" id="c4"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">'
    "0000800457</xbrli:identifier><xbrli:segment><xbrldi:explicitMember "
    'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember>'
    "</xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2026-03-02</xbrli:instant>"
    "</xbrli:period></xbrli:context>"
    '<xbrli:context xmlns="" id="c5"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">'
    "0000800457</xbrli:identifier><xbrli:segment><xbrldi:explicitMember "
    'dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember</xbrldi:explicitMember>'
    "</xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2026-03-02</xbrli:instant>"
    "</xbrli:period></xbrli:context>"
)


class TestContextBlockTolerantOfExtraAttributes:
    def test_class_a_resolves_despite_xmlns_attribute_before_id(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        assert loader._class_letter_for_context(_DGIC_FILING_TEXT, "c4") == "A"

    def test_class_b_resolves_despite_xmlns_attribute_before_id(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        assert loader._class_letter_for_context(_DGIC_FILING_TEXT, "c5") == "B"


class TestSeriesLabelSecurityNameResolution:
    def test_target_class_letter_matches_series_a(self):
        assert (
            CompanyInfoSECLoader._CLASS_LETTER_FROM_SECURITY_NAME_RE.search(
                "Liberty Media Corporation - Series A Liberty Formula One Common Stock"
            ).group(1)
            == "A"
        )

    def test_target_class_letter_matches_series_c(self):
        assert (
            CompanyInfoSECLoader._CLASS_LETTER_FROM_SECURITY_NAME_RE.search(
                "Liberty Media Corporation - Series C Liberty Formula One Common Stock"
            ).group(1)
            == "C"
        )

    def test_class_label_still_matches_unchanged(self):
        assert (
            CompanyInfoSECLoader._CLASS_LETTER_FROM_SECURITY_NAME_RE.search(
                "Donegal Group, Inc. - Class A Common Stock"
            ).group(1)
            == "A"
        )


class TestSelfDescribingContextIdResolvedDirectly:
    def test_resolves_class_letter_from_id_string_without_context_block_lookup(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        ctx_id = (
            "As_Of_1_31_2026_us-gaap_StatementClassOfStockAxis_lmca_"
            "LibertyFormulaOneGroupCommonClassBMember_Se1lZdhv3k-DZTuF-VpiOA"
        )
        # Empty filing_text proves resolution came from the id string, not a block search.
        assert loader._class_letter_for_context("", ctx_id) == "B"

    def test_does_not_false_match_the_classofstockaxis_dimension_name_itself(self):
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
        ctx_id = "As_Of_1_31_2026_us-gaap_StatementClassOfStockAxis_no_member_here"
        assert loader._class_letter_for_context("", ctx_id) is None
