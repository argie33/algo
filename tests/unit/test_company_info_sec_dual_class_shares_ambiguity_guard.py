"""Regression test for the 2026-08-21 fix (goal session - "BRK.B and those types" audit):
_fetch_shares_outstanding_from_filing_text()'s max()-of-candidates heuristic assumes the
publicly-traded class always has the LARGER share count (true for PLNT: Class A 79.7M
public / Class B 316K founder-held). That assumption is backwards for filers where the
dot-suffixed class is itself the low-share-count, high-price class.

Live-confirmed: BRK.A/BRK.B, BF.A/BF.B, CRD.A/CRD.B, MOG.A/MOG.B all resolved to the
IDENTICAL shares_outstanding in company_info_sec, because this function has no
symbol-vs-context awareness - both tickers of a pair get whichever value max() picks. For
Berkshire this produced BRK.A market_cap = $1.03 QUADRILLION in value_metrics (real ~$1.1T):
BRK.B's real ~1.39B share count applied to BRK.A's ~$744k/share price, off by the ~1,500:1
A-to-B conversion ratio.

Fix: when multiple plausible values are found in the filing text AND the symbol being
resolved is itself dot-suffixed (a known multi-class ticker), refuse to guess via max() -
return None (unavailable) instead. Bare tickers (no dot) keep the existing max() behavior,
since there the ambiguity is against an untracked closely-held class, not a sibling ticker
that could silently receive the wrong number.
"""

from unittest.mock import MagicMock

from loaders.load_company_info_sec import CompanyInfoSECLoader


def _loader() -> CompanyInfoSECLoader:
    loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _submissions_with_10k(accession: str = "0001067983-26-000018") -> dict:
    return {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": [accession],
            }
        }
    }


class TestDualClassSharesAmbiguityGuard:
    def test_dot_suffixed_symbol_with_multiple_candidates_returns_none(self):
        """Berkshire-shaped fixture: two classes tagged in the same filing, symbol is
        dot-suffixed - must not guess via max()."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction unitRef="shares" contextRef="c-1" '
            'name="dei:EntityCommonStockSharesOutstanding" decimals="INF">601,935'
            "</ix:nonFraction> shares of Class A Common Stock, "
            '<ix:nonFraction unitRef="shares" contextRef="c-2" '
            'name="dei:EntityCommonStockSharesOutstanding" decimals="INF">1,389,605,139'
            "</ix:nonFraction> shares of Class B Common Stock"
        )

        result = loader._fetch_shares_outstanding_from_filing_text("BRK.A", "1067983", _submissions_with_10k())

        assert result is None

    def test_other_dot_suffixed_symbol_same_filing_also_returns_none(self):
        """The sibling ticker hitting the identical filing text must also refuse to guess -
        not just the one that happened to be checked first."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding">601,935</ix:nonFraction> '
            'Class A, <ix:nonFraction name="dei:EntityCommonStockSharesOutstanding">1,389,605,139'
            "</ix:nonFraction> Class B"
        )

        result = loader._fetch_shares_outstanding_from_filing_text("BRK.B", "1067983", _submissions_with_10k())

        assert result is None

    def test_dot_suffixed_symbol_with_single_candidate_still_resolves(self):
        """No real ambiguity when only one plausible value exists - the dot-suffix guard
        must not suppress a perfectly resolvable single-value case."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding">34,944,441</ix:nonFraction>'
        )

        result = loader._fetch_shares_outstanding_from_filing_text("WSO.B", "0000000000", _submissions_with_10k())

        assert result == 34_944_441

    def test_bare_symbol_with_multiple_candidates_keeps_max_behavior(self):
        """Regression guard: PLNT-style bare (non-dot) tickers must be unaffected - the new
        ambiguity check is scoped to dot-suffixed symbols only."""
        loader = _loader()
        loader.sec_client.get_filing_plaintext.return_value = (
            '<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding">79,697,889</ix:nonFraction> '
            'Class A, <ix:nonFraction name="dei:EntityCommonStockSharesOutstanding">316,128'
            "</ix:nonFraction> Class B"
        )

        result = loader._fetch_shares_outstanding_from_filing_text("PLNT", "0000000000", _submissions_with_10k())

        assert result == 79_697_889
