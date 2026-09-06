"""Regression test for the 2026-09-06 fix (goal session: "SEC/XBRL missing data to zero" /
implausible-values audit): gross_margin's shared |ratio|>1000 implausible bound (see
test_quality_metrics_implausible_ratio_reason.py) is far too loose for this specific ratio -
unlike EBITDA margin or ROE/ROA, gross margin is capped at 100% by definition
(gross_profit = revenue - cost_of_revenue, and cost_of_revenue is never negative for a real
filer), so a value like 138% is just as impossible as one like 23,000,000% - it just wasn't
being caught.

Live-confirmed via SAN/BBVA/GFR (foreign banks reporting under IFRS): quality_metrics.
gross_margin stored 138.54/140.53/107.29 with gross_margin_unavailable_reason=NULL, feeding
directly into Quality scoring uncontested. Root cause is a real, current (not stale) concept
mismatch - GrossProfit is IFRS banks' broad "total operating income" concept, but the
fallback-only "interest_revenue_expense" concept mapped into our "revenue" column is a much
narrower net-interest-income figure for these filers - there's no better concept to
substitute, so flagging this as implausible (rather than trying to force a numeric value) is
the correct, final outcome for this data.

Fix: tightened gross_margin's own ceiling to 105% (small buffer for a rare legitimate edge
case, e.g. a vendor-rebate credit pushing slightly over 100%) while leaving the shared
|ratio|>1000 bound used by ebitda_margin/ROE/ROA/etc. untouched - those margins CAN
legitimately exceed 100%.
"""

from tests.unit.test_quality_metrics_implausible_ratio_reason import _make_loader, _quality_row


class TestGrossMarginOver100PctImplausible:
    def test_138_pct_gross_margin_now_flagged_implausible(self, monkeypatch):
        """SAN's real shape: gross_profit=$68.94B, revenue=$49.76B -> 138.5% margin. The old
        1000% bound let this straight through as a real value."""
        loader = _make_loader(monkeypatch)
        row = _quality_row(gross_profit=68_937_560_219.02, revenue=49_759_123_916.06)

        metrics = loader._compute_quality_metrics("SAN", row, ev_metrics=None)

        assert metrics["gross_margin"] is None
        assert metrics["gross_margin_unavailable_reason"] == "implausible_ratio"

    def test_exactly_100_pct_gross_margin_still_accepted(self, monkeypatch):
        """gross_profit == revenue (zero cost_of_revenue) is a legitimate, if rare, real value -
        must not be caught by the new tighter ceiling."""
        loader = _make_loader(monkeypatch)
        row = _quality_row(gross_profit=100_000_000.0, revenue=100_000_000.0)

        metrics = loader._compute_quality_metrics("TEST", row, ev_metrics=None)

        assert metrics["gross_margin"] == 100.0
        assert metrics.get("gross_margin_unavailable_reason") is None

    def test_104_pct_within_buffer_still_accepted(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(gross_profit=104_000_000.0, revenue=100_000_000.0)

        metrics = loader._compute_quality_metrics("TEST", row, ev_metrics=None)

        assert metrics["gross_margin"] == 104.0

    def test_negative_gross_margin_unaffected_by_new_ceiling(self, monkeypatch):
        """A distressed filer with cost_of_revenue > revenue is a real, legitimate negative
        gross margin - the new upper-bound-only check must not touch this side."""
        loader = _make_loader(monkeypatch)
        row = _quality_row(gross_profit=-50_000_000.0, revenue=100_000_000.0)

        metrics = loader._compute_quality_metrics("TEST", row, ev_metrics=None)

        assert metrics["gross_margin"] == -50.0
