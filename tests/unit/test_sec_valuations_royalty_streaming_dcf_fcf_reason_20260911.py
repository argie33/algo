"""Regression test (2026-09-11, goal: "SEC/XBRL missing data under 300" push):
load_sec_valuations.py's dcf_fcf_unavailable_reason chain never distinguished a mining
royalty/streaming company (real, growing operating cash flow, no PP&E-purchase concept because
it buys royalty/streaming interests instead of operating mines) from an ordinary filer with a
genuine capex-tagging gap - both fell into "missing_cash_flow_data"/"capex_never_tagged_in_
recent_filings" ("Missing SEC/XBRL data"), but the royalty/streaming case is a real business-
model fact ("Legitimate / not applicable"), same class as the existing oil-royalty-trust check.

Live-confirmed GROY/MTA/OR/VMET/VOXR: real annual_cash_flow.operating_cash_flow every recent
fiscal year, capex NULL every year, zero ifrs-full:PropertyPlantAndEquipment fact of any kind in
real companyfacts JSON.
"""

from typing import Any

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestSecValuationsRoyaltyStreamingDcfFcfReason:
    def test_royalty_streaming_symbol_gets_legitimate_reason(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        loader._recategorize_royalty_streaming_dcf_fcf_reason("GROY", result)

        assert result["dcf_fcf_unavailable_reason"] == "royalty_streaming_no_capex"

    def test_non_matching_symbol_keeps_generic_reason(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        loader._recategorize_royalty_streaming_dcf_fcf_reason("REALCO", result)

        assert result["dcf_fcf_unavailable_reason"] == "missing_cash_flow_data"

    def test_does_not_touch_a_different_already_specific_reason(self) -> None:
        # Guard against ever overriding anything other than the exact generic
        # "missing_cash_flow_data" fallback this method targets, even for a matching symbol -
        # mirrors _recategorize_royalty_trust_dcf_fcf_reason's identical guard.
        loader = _make_loader()
        result: dict[str, Any] = {"dcf_fcf_unavailable_reason": "negative_free_cash_flow"}

        loader._recategorize_royalty_streaming_dcf_fcf_reason("GROY", result)

        assert result["dcf_fcf_unavailable_reason"] == "negative_free_cash_flow"

    def test_all_five_confirmed_symbols_match(self) -> None:
        loader = _make_loader()
        for symbol in ("GROY", "MTA", "OR", "VMET", "VOXR"):
            result: dict[str, Any] = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}
            loader._recategorize_royalty_streaming_dcf_fcf_reason(symbol, result)
            assert result["dcf_fcf_unavailable_reason"] == "royalty_streaming_no_capex"

    def test_royalty_trust_check_chains_into_streaming_check(self) -> None:
        # _recategorize_royalty_trust_dcf_fcf_reason (the public call site wired into
        # load_sec_valuations.py) must itself invoke this check for a non-trust symbol,
        # since there is no separate call site for it (load_sec_valuations.py is at the
        # 2000-line hard ceiling).
        loader = _make_loader()
        result: dict[str, Any] = {"dcf_fcf_unavailable_reason": "missing_cash_flow_data"}

        loader._recategorize_royalty_trust_dcf_fcf_reason("GROY", result)

        assert result["dcf_fcf_unavailable_reason"] == "royalty_streaming_no_capex"
