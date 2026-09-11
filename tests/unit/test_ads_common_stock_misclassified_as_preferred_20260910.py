"""Regression test: _get_preferred_or_debt_security_symbols()'s SQL must not match ordinary
"American Depositary Shares"/"Global Depositary Shares" common-stock ADR listings.

Found live 2026-09-10 (goal: "under 300" push). The bare '%Depositary Share%' clause matched
every ADS/GDS common-stock listing too, since "Depositary Share" is a substring of "American
Depositary Shares" - live-confirmed 271 of 290 total matches (BABA, NIO, JD, VLRS, and ~270
more) were ordinary common-stock ADRs, not preferred securities, causing NIO's pe_ratio and
VLRS's ps_ratio to be wrongly suppressed as "preferred_or_debt_security_no_common_equity_ratio"
instead of computed normally. Real preferred depositary shares in this universe (ATH$A-E,
RNR$F/G, AHL$E/F, USB$A/H, MET$E, TFC$I, EQH$A, FITB$I, STT$G, WAFDP, MNSBP) never say
"American"/"Global" before "Depositary". See
loaders/helpers/vqg_symbol_gates.py's _get_preferred_or_debt_security_symbols() docstring.
"""

import inspect
import re

import loaders.helpers.vqg_symbol_gates as gates_module


def _get_query_source() -> str:
    with open(gates_module.__file__, encoding="utf-8") as fh:
        source = fh.read()
    match = re.search(
        r"def _get_preferred_or_debt_security_symbols.*?(?=\n    @_cached_symbols|\Z)",
        source,
        re.DOTALL,
    )
    assert match is not None, "could not locate _get_preferred_or_debt_security_symbols source"
    return match.group(0)


class TestAdsCommonStockNotMisclassifiedAsPreferred:
    def test_query_excludes_american_and_global_depositary_shares(self):
        method_source = _get_query_source()
        depositary_block = method_source[method_source.index("Depositary Share%%'") :]
        depositary_block = depositary_block[: depositary_block.index(")")]

        assert "NOT ILIKE '%%American Depositary%%'" in depositary_block
        assert "NOT ILIKE '%%Global Depositary%%'" in depositary_block

    def test_mixin_still_importable_and_documents_the_fix(self):
        assert hasattr(gates_module, "SymbolGateMixin")
        source = inspect.getsource(gates_module)
        assert "FIXED 2026-09-10" in source
        assert "American/Global" in source
