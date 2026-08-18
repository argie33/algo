"""Regression test: the per-run log tee must flush after every line, not just at close.

Bug (found 2026-08-18, live evidence): _stream_and_capture()'s per-line
`log_file.write(line)` was never followed by a flush, so open()'s default ~8KB block
buffering held every line in memory until the file closed at process exit. Live-reproduced
on current_reports_8k: 53+ minutes into a genuinely healthy, actively-progressing run
(48.68% done per data_loader_status), its per-run log file on disk still showed only the
header line - indistinguishable from a hung/dead process to anyone tailing it mid-run. This
defeated the stated purpose of writing "the full stream to a per-run log file" (2026-08-17
comment in local_loader_scheduler.py) for live monitoring, not just post-mortem diagnosis.
"""

import builtins
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "logs"


def _load_scheduler_module():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test_flush", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stdout_mock(lines=()):
    stdout = MagicMock()
    stdout.__iter__.return_value = iter(lines)
    return stdout


class _FlushCountingFile:
    """Wraps a real file object and counts flush() calls, delegating everything else."""

    def __init__(self, real_file):
        self._real_file = real_file
        self.flush_count = 0

    def write(self, s):
        return self._real_file.write(s)

    def flush(self):
        self.flush_count += 1
        return self._real_file.flush()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return self._real_file.__exit__(*exc_info)


class TestLogTeeFlushesPerLine:
    def test_flush_called_after_every_line_not_just_at_close(self) -> None:
        module = _load_scheduler_module()
        mock_proc = MagicMock()
        mock_proc.pid = 888888
        lines = ["Progress: 100/4930\n", "Progress: 200/4930\n", "Progress: 300/4930\n"]
        mock_proc.stdout = _stdout_mock(lines)
        mock_proc.wait.return_value = 0

        fixed_epoch = 1735689602  # distinct sentinel, not a real run
        expected_log_path = LOGS_DIR / f"load_trend_analysis_{fixed_epoch}.log"
        expected_log_path.unlink(missing_ok=True)

        real_open = builtins.open
        wrapped_files: list[_FlushCountingFile] = []

        def _open_spy(file, *args, **kwargs):
            handle = real_open(file, *args, **kwargs)
            if str(file) == str(expected_log_path):
                wrapped = _FlushCountingFile(handle)
                wrapped_files.append(wrapped)
                return wrapped
            return handle

        try:
            with (
                patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}),
                patch.object(module, "reap_stale_running_loaders", return_value=[]),
                patch.object(module.subprocess, "Popen", return_value=mock_proc),
                patch.object(module, "_mark_loader_failed_after_crash"),
                patch.object(module.time, "time", return_value=fixed_epoch),
                patch("builtins.open", side_effect=_open_spy),
            ):
                module.run_pipeline("test_pipeline")

            assert wrapped_files, "log file was never opened at the expected path"
            # 1 flush for the header + 1 flush per line = 4, strictly more than the
            # pre-fix behavior of a single flush for the header only.
            assert wrapped_files[0].flush_count >= 1 + len(lines), (
                f"expected a flush after every line (>= {1 + len(lines)}), "
                f"got {wrapped_files[0].flush_count} - log won't be readable mid-run"
            )
        finally:
            expected_log_path.unlink(missing_ok=True)
