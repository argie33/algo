"""Regression test: _force_exit_on_timeout()'s critical log line must have stdout/stderr
explicitly flushed before os._exit(1), in both loaders/runner.py and
utils/loaders/timeout_enforcement.py.

BUG FOUND 2026-09-01 (/goal session): this critical log line is the ONE diagnostic signal
explaining why a loader process vanished with no clean exit - and it's the last thing logged
before os._exit(1), which (unlike sys.exit()/normal interpreter shutdown) skips atexit handlers
and does not guarantee buffered output reaches the OS. Live-observed: an AAII sentiment loader
run's log cut off mid-fetch with zero further lines (not even this message) - the exact
silent-disappearance failure mode this flush closes off, regardless of what actually hung.
"""

from unittest.mock import MagicMock, patch

import loaders.runner as loaders_runner
import utils.loaders.timeout_enforcement as timeout_enforcement


class TestLoadersRunnerForceExitFlushesBeforeExit:
    def test_flushes_stdout_and_stderr_before_os_exit(self) -> None:
        loaders_runner.LOADER_TIMEOUT_SECONDS = 600
        call_order: list[str] = []

        mock_stdout = MagicMock()
        mock_stdout.flush.side_effect = lambda: call_order.append("stdout_flush")
        mock_stderr = MagicMock()
        mock_stderr.flush.side_effect = lambda: call_order.append("stderr_flush")

        with (
            patch("sys.stdout", mock_stdout),
            patch("sys.stderr", mock_stderr),
            patch.object(
                loaders_runner.os, "_exit", side_effect=lambda code: call_order.append("os_exit")
            ) as mock_exit,
        ):
            loaders_runner._force_exit_on_timeout()

        assert "stdout_flush" in call_order
        assert "stderr_flush" in call_order
        # Both flushes must happen BEFORE the exit, or they'd never run.
        assert call_order.index("os_exit") == len(call_order) - 1
        mock_exit.assert_called_once_with(1)


class TestTimeoutEnforcementForceExitFlushesBeforeExit:
    def test_flushes_stdout_and_stderr_before_os_exit(self) -> None:
        timeout_enforcement._LOADER_TIMEOUT_SECONDS = 600
        call_order: list[str] = []

        mock_stdout = MagicMock()
        mock_stdout.flush.side_effect = lambda: call_order.append("stdout_flush")
        mock_stderr = MagicMock()
        mock_stderr.flush.side_effect = lambda: call_order.append("stderr_flush")

        with (
            patch("sys.stdout", mock_stdout),
            patch("sys.stderr", mock_stderr),
            patch.object(
                timeout_enforcement.os, "_exit", side_effect=lambda code: call_order.append("os_exit")
            ) as mock_exit,
        ):
            timeout_enforcement._force_exit_on_timeout()

        assert "stdout_flush" in call_order
        assert "stderr_flush" in call_order
        assert call_order.index("os_exit") == len(call_order) - 1
        mock_exit.assert_called_once_with(1)
