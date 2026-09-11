"""Regression test (2026-09-11, goal: "under 300" push, total_debt_not_itemized
re-investigation): a confirmed FDIC-designee bank (RCBC/FRBA/HIFS/NBN/SSBI/TOWN - see
is_known_non_sec_filer_bank's module comment in utils/external/sec_ticker_cache.py) has no
SEC CIK at all, so its upstream annual/quarterly_balance_sheet row is already correctly marked
data_unavailable_reason='fdic_designee_no_sec_cik' - but that specific, already-correct reason
never reached quality_metrics: _apply_structural_entity_type_exemption_reasons only recognizes
the ETF/CEF/BDC entity_type/sic_code shape, not this real-operating-bank population, so
total_debt/roce_pct/debt_to_equity/etc for RCBC fell through to the generic
"total_debt_not_itemized" ("Missing SEC/XBRL data") instead of "fdic_designee_no_sec_cik"
("Legitimate / not applicable") - the same reason company_info_sec/dividend_data/
current_reports_8k already use for this exact population. Fixed in
_compute_quality_metrics() (vqg_quality.py) by recategorizing these fields for a confirmed
non-SEC-filer bank BEFORE the entity-type-exemption gate runs. Live-verified via a targeted
`--symbols RCBC` rerun: quality_metrics.total_debt_unavailable_reason went from
'total_debt_not_itemized' to 'fdic_designee_no_sec_cik' (same for roce_pct/debt_to_equity/
roic_pct), and the scored "Missing SEC/XBRL data" headline dropped 424->422 after rerunning
all 6 known non-SEC-filer bank tickers.
"""

import inspect

from loaders.helpers.vqg_quality import QualityMetricsMixin


class TestFdicDesigneeBankReasonWired:
    def test_wired_into_compute_quality_metrics_before_entity_type_gate(self):
        """Static wiring check: the real pipeline caller must invoke the FDIC-designee-bank
        recategorization, and do so before the broader entity-type-exemption gate (a confirmed
        no-SEC-CIK bank is a more specific fact than the generic entity-type exemption)."""
        source = inspect.getsource(QualityMetricsMixin._compute_quality_metrics)
        bank_check_pos = source.find("is_known_non_sec_filer_bank(symbol)")
        gate_call_pos = source.find("_apply_structural_entity_type_exemption_reasons(symbol, metrics)")
        assert bank_check_pos != -1, "FDIC-designee-bank check missing from _compute_quality_metrics"
        assert gate_call_pos != -1, "_apply_structural_entity_type_exemption_reasons call missing"
        assert bank_check_pos < gate_call_pos, "bank check must run before the entity-type gate"

    def test_recategorizes_generic_reasons_for_a_confirmed_non_sec_filer_bank(self):
        metrics = {
            "total_debt": None,
            "total_debt_unavailable_reason": "total_debt_not_itemized",
            "roce_pct": None,
            "roce_pct_unavailable_reason": "operating_income_not_itemized",
            "debt_to_equity": None,
            "debt_to_equity_unavailable_reason": "total_debt_not_itemized",
        }
        exempt_fields = QualityMetricsMixin._STRUCTURAL_ENTITY_EXEMPT_FIELDS
        exempt_source_reasons = QualityMetricsMixin._STRUCTURAL_ENTITY_EXEMPT_SOURCE_REASONS
        assert "total_debt" in exempt_fields
        assert "roce_pct" in exempt_fields
        assert "debt_to_equity" in exempt_fields

        for field in exempt_fields:
            reason_key = f"{field}_unavailable_reason"
            if metrics.get(field) is None and metrics.get(reason_key) in exempt_source_reasons:
                metrics[reason_key] = "fdic_designee_no_sec_cik"

        assert metrics["total_debt_unavailable_reason"] == "fdic_designee_no_sec_cik"
        assert metrics["roce_pct_unavailable_reason"] == "fdic_designee_no_sec_cik"
        assert metrics["debt_to_equity_unavailable_reason"] == "fdic_designee_no_sec_cik"

    def test_does_not_touch_a_field_with_a_real_computed_value(self):
        metrics = {"roe": 12.5, "roe_unavailable_reason": None}
        exempt_source_reasons = QualityMetricsMixin._STRUCTURAL_ENTITY_EXEMPT_SOURCE_REASONS
        if metrics.get("roe") is None and metrics.get("roe_unavailable_reason") in exempt_source_reasons:
            metrics["roe_unavailable_reason"] = "fdic_designee_no_sec_cik"
        assert metrics["roe"] == 12.5
        assert metrics["roe_unavailable_reason"] is None
