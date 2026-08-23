"""Regression test: trend_template_data's SLA must account for its own documented
structural one-trading-day processing lag.

loaders/load_trend_analysis.py runs ~2:15 AM ET (per its own module docstring) and depends on
price_daily - at 2:15 AM the current trading day's own close does not exist yet, so this
loader always computes off the PRIOR trading day's close. Confirmed live via
data_loader_status_history: every sampled run (2026-08-18 through 2026-08-21) wrote data dated
exactly one trading day before the run's own calendar date.

With sla_days=1 (same as every other same-day-close table here), a perfectly healthy run
always sits at age_days=1 on a normal weekday - one _gap_adjusted_sla() weekend/holiday
padding away from a false STALE despite zero actual problem (live-confirmed 2026-08-23: 78/82
-> flagged STALE for age_days=3 vs effective_sla=2 across a 2-day weekend gap). Bumped to
sla_days=2 to absorb the loader's own permanent baseline lag before gap-padding is even
applied.

signal_quality_scores shows the same STALE symptom under the same conditions but was
confirmed to be a local-dev sequencing artifact (upstream buy_sell_daily simply hadn't loaded
that day yet at the time it ran), not a structural lag like this one - deliberately NOT given
the same treatment. See signal_quality_trend_template_weekend_staleness_open_question_20260823
in memory for the full investigation distinguishing the two.
"""

from algo.monitoring.pipeline_health import PipelineHealth


def test_trend_template_data_sla_absorbs_its_own_structural_one_day_lag():
    assert PipelineHealth.CRITICAL_TABLES["trend_template_data"]["sla_days"] == 2


def test_signal_quality_scores_sla_unchanged_not_a_structural_lag():
    # Confirmed to be a local-dev timing artifact, not a real structural lag - must NOT get
    # the same SLA bump, or a genuine future upstream-ordering regression would be masked.
    assert PipelineHealth.CRITICAL_TABLES["signal_quality_scores"]["sla_days"] == 1


def test_trend_template_data_healthy_across_a_normal_weekend_gap():
    """A healthy run that's exactly 1 trading day behind (its permanent baseline) must not
    flip to STALE just because _gap_adjusted_sla() also padded for a 2-day weekend gap."""
    monitor = PipelineHealth()
    from datetime import date

    # Sunday 2026-08-23: most recent trading day is Friday 2026-08-21 -> gap_days=2.
    sunday = date(2026, 8, 23)
    effective_sla = monitor._gap_adjusted_sla("trend_template_data", base_sla_days=2, today=sunday)
    # Loader's baseline age on a healthy run (1 day) + the weekend's extra day (1 day) = 2,
    # must stay <= effective_sla so it reports HEALTHY, not STALE.
    baseline_plus_weekend_age = 1 + 1
    assert baseline_plus_weekend_age <= effective_sla
