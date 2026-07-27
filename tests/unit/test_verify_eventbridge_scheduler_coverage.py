"""Regression test: verify_eventbridge_scheduler.py must monitor every real,
currently-deployed loader-pipeline EventBridge schedule, and must read the
correct AWS API field for a schedule's timezone.

Bug 1: EXPECTED_SCHEDULES only listed morning-pipeline and eod-pipeline. A
third loader pipeline schedule - computed-metrics-pipeline-<env>, which drives
quality/growth/value/stability/stock_scores computation
(terraform/modules/pipeline/main.tf: aws_scheduler_schedule.computed_metrics_pipeline_trigger,
cron(0 19 ? * MON-FRI *) America/New_York) - existed in terraform but was never
added here. CLAUDE.md tells operators to run this script + --fix for "Stale
data", so a disabled/misconfigured computed-metrics schedule would go
completely undetected while this tool reported "2/2 OK".

Bug 2: check_schedule() computed `correct_tz` from
schedule.get("ScheduleExpressionTimezone") (the real AWS API field) but the
returned diagnostic dict stored "timezone": schedule.get("Timezone") - a key
that doesn't exist in the scheduler API response - so a MISCONFIGURED report
always printed "(None)" for timezone instead of the actual misconfigured
value, misleading an operator trying to debug a live scheduling gap.
"""

from scripts.verify_eventbridge_scheduler import EXPECTED_SCHEDULES, check_schedule


class TestComputedMetricsPipelineIsMonitored:
    def test_computed_metrics_pipeline_schedule_is_expected(self):
        matches = [name for name in EXPECTED_SCHEDULES if "computed-metrics-pipeline" in name]
        assert matches, (
            "computed-metrics-pipeline schedule (drives quality/growth/value/"
            "stability/stock_scores) is missing from EXPECTED_SCHEDULES"
        )
        expected = EXPECTED_SCHEDULES[matches[0]]
        assert expected["schedule"] == "cron(0 19 ? * MON-FRI *)"
        assert expected["timezone"] == "America/New_York"


class TestScheduleTimezoneFieldReadCorrectly:
    def test_correct_config_reports_status_ok_with_real_timezone(self, monkeypatch):
        fake_schedule = {
            "State": "ENABLED",
            "ScheduleExpression": "cron(5 16 ? * MON-FRI *)",
            "ScheduleExpressionTimezone": "America/New_York",
        }
        monkeypatch.setattr(
            "scripts.verify_eventbridge_scheduler.run_aws_cli",
            lambda args: fake_schedule,
        )

        result = check_schedule(
            "algo-eod-pipeline-dev",
            {"schedule": "cron(5 16 ? * MON-FRI *)", "timezone": "America/New_York"},
        )

        assert result["status"] == "OK"
        # Regression: this used to read schedule.get("Timezone") -> always None,
        # even on a schedule that is actually correctly configured.
        assert result["timezone"] == "America/New_York"

    def test_misconfigured_timezone_is_visible_in_diagnostic_output(self, monkeypatch):
        fake_schedule = {
            "State": "ENABLED",
            "ScheduleExpression": "cron(5 16 ? * MON-FRI *)",
            "ScheduleExpressionTimezone": "UTC",
        }
        monkeypatch.setattr(
            "scripts.verify_eventbridge_scheduler.run_aws_cli",
            lambda args: fake_schedule,
        )

        result = check_schedule(
            "algo-eod-pipeline-dev",
            {"schedule": "cron(5 16 ? * MON-FRI *)", "timezone": "America/New_York"},
        )

        assert result["status"] == "MISCONFIGURED"
        # Regression: pre-fix, this was always None regardless of the real
        # (wrong) timezone returned by AWS, hiding the actual misconfiguration.
        assert result["timezone"] == "UTC"
