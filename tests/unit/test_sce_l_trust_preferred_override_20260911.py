"""Regression test: SCE$L ("SCE TRUST VI") must be recognized as a preferred/debt security
even though SymbolGateMixin._get_preferred_or_debt_security_symbols()'s security_name-text
patterns don't match it (its SEC-listed security_name is just "SCE TRUST VI" - none of
"Subordinated"/"Preferred"/"Depositary" appear in it).

Found live 2026-09-11 (goal: "missing SEC/XBRL data under 200" push): landed pe_ratio on
"eps_never_tagged_in_filings" (implies an extraction gap) instead of the correct
"preferred_or_debt_security_no_common_equity_ratio" - SCE$L's own annual_income_statement
rows are genuinely NULL, it never had common EPS to tag. Fixed via a small, explicit,
hand-verified whitelist (_TRUST_PREFERRED_SYMBOL_OVERRIDE in vqg_value.py) rather than
widening the shared gate's query - that file is already past the file-size ratchet's
2000-line hard ceiling (no growth accepted without extracting a module first, out of
proportion for a single verified symbol). See _is_preferred_or_debt_security()'s own
docstring.
"""

from loaders.helpers.vqg_value import ValueMetricsMixin


class _StubLoader(ValueMetricsMixin):
    """Bypasses the real DB-backed gate entirely - only the override whitelist should
    matter for this test."""

    def _get_preferred_or_debt_security_symbols(self):
        return frozenset()


class TestTrustPreferredOverride:
    def test_sce_l_recognized_via_explicit_override(self):
        loader = _StubLoader()
        assert loader._is_preferred_or_debt_security("SCE$L") is True

    def test_unrelated_symbol_not_recognized(self):
        loader = _StubLoader()
        assert loader._is_preferred_or_debt_security("AAPL") is False

    def test_gate_hit_still_recognized_alongside_override(self):
        class _Loader(ValueMetricsMixin):
            def _get_preferred_or_debt_security_symbols(self):
                return frozenset({"DUKB"})

        loader = _Loader()
        assert loader._is_preferred_or_debt_security("DUKB") is True
        assert loader._is_preferred_or_debt_security("SCE$L") is True
        assert loader._is_preferred_or_debt_security("AAPL") is False
