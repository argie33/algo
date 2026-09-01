"""Regression test for the 2026-08-31 (/goal pre-real-money audit) fix in
algo/trading/check_handler_strategies.py's ReentryCheckHandler.process(): the returned
status_dict's "reentry_blocked" boolean used to be derived from `"prior" in error_msg.lower()` -
a second, independent substring check on the same message. check_reentry_rules()'s cooldown
message ("only {days_since_exit}d since stop-out; require ... before re-entry (reset period)")
never contains "prior" at all, so this evaluated to False for the cooldown-block case even though
the handler is already inside `if not valid:` - i.e. the check FAILED, meaning re-entry WAS
blocked, unconditionally, regardless of which of the two block reasons (max-reentries-exceeded
vs cooldown-not-elapsed) actually fired.

Currently inert in production (nothing reads this specific dict key today - the "status" string,
not this boolean, is what phase8_entry_execution.py's _POLICY_REJECTION_STATUSES checks), but a
live-wrong value nonetheless. Fixed to be unconditionally True whenever the handler reaches this
branch at all.
"""

from algo.trading.check_handler_strategies import ReentryCheckHandler


class TestReentryBlockedFlagAlwaysTrueOnFailure:
    def test_max_reentries_exceeded_sets_blocked_true(self):
        """The 'prior re-entries' message shape - already correctly set reentry_blocked=True
        before this fix, since it happens to contain the substring 'prior'. Sanity check that
        the fix didn't regress this case."""
        handler = ReentryCheckHandler()
        result = (False, "AAPL: 3 prior re-entries within 30 days >= 3 max", 0)

        should_return_early, _error_msg, status_dict = handler.process(result)

        assert should_return_early is True
        assert status_dict["status"] == "reentry_blocked"
        assert status_dict["reentry_blocked"] is True

    def test_cooldown_not_elapsed_sets_blocked_true(self):
        """The actual bug scenario: the cooldown message shape contains no 'prior' substring
        at all, so reentry_blocked used to come back False here despite the reentry genuinely
        being blocked - this is what the fix corrects."""
        handler = ReentryCheckHandler()
        result = (False, "AAPL: only 2d since stop-out; require 5d before re-entry (reset period)", 0)

        should_return_early, _error_msg, status_dict = handler.process(result)

        assert should_return_early is True
        assert status_dict["status"] == "reentry_cooldown"
        assert status_dict["reentry_blocked"] is True, (
            "reentry_blocked must be True whenever the check failed (we're inside the "
            "if not valid: branch), regardless of which block reason fired - a value of "
            "False here means the 'prior' substring-matching regression is back"
        )

    def test_passing_check_returns_no_status_dict(self):
        """Sanity check: a passing reentry check must not report blocked at all."""
        handler = ReentryCheckHandler()
        result = (True, None, 2)

        should_return_early, _error_msg, status_dict = handler.process(result)

        assert should_return_early is False
        assert status_dict is None
