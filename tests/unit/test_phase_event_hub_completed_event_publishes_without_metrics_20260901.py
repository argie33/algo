"""Regression test: PhaseCompletedEvent must not require an explicit `metrics` argument.

Before this fix, `metrics: dict[str, Any] | None = None` immediately raised ValueError
whenever a caller relied on that default - a self-defeating signature. The one live
caller, Orchestrator.log_phase_result() (called after literally every orchestrator
phase), has no metrics parameter of its own at all and constructs this event with no
metrics= argument - so this ValueError fired on every single phase completion in
production, silently swallowed by the caller's broad
`except (ValueError, Exception): logger.debug(...)`. Net effect: PhaseEventHub's
dashboard/API subscriber system never received a single real phase_completed event.

Confirmed zero test coverage existed anywhere for phase_event_hub.py or
PhaseCompletedEvent before this fix (repo-wide grep found none).
"""

from algo.orchestration.phase_event_hub import PhaseCompletedEvent, PhaseEventHub, PhaseStatus


class TestPhaseCompletedEventDoesNotRequireMetrics:
    def test_constructing_without_metrics_does_not_raise(self):
        """This is exactly how Orchestrator.log_phase_result() constructs the event -
        must not raise."""
        event = PhaseCompletedEvent(
            phase_num=1,
            phase_name="data_freshness",
            status=PhaseStatus.SUCCESS,
            summary="ok",
        )
        assert event.details["metrics"] == {}

    def test_explicit_metrics_still_passed_through(self):
        event = PhaseCompletedEvent(
            phase_num=1,
            phase_name="data_freshness",
            status=PhaseStatus.SUCCESS,
            summary="ok",
            metrics={"rows_checked": 42},
        )
        assert event.details["metrics"] == {"rows_checked": 42}

    def test_event_actually_publishes_through_the_hub(self):
        """The real-world regression: a phase-completion event constructed the way
        log_phase_result() constructs it must actually reach a subscriber."""
        hub = PhaseEventHub()
        received = []
        hub.subscribe("phase_completed", received.append)

        event = PhaseCompletedEvent(
            phase_num=9,
            phase_name="reconciliation",
            status=PhaseStatus.SUCCESS,
            summary="reconciled",
        )
        hub.publish(event)

        assert len(received) == 1
        assert received[0] is event

    def test_get_phase_status_reflects_published_event(self):
        hub = PhaseEventHub()
        event = PhaseCompletedEvent(
            phase_num=3,
            phase_name="position_monitor",
            status=PhaseStatus.SUCCESS,
            summary="ok",
        )
        hub.publish(event)

        assert hub.get_phase_status(3) == PhaseStatus.SUCCESS
