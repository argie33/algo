"""Regression test for the 2026-08-21 fix: load_env_local() must let .env.local win over
whatever happens to already be sitting in the OS process environment.

Live-confirmed root cause of a real Alpaca 401 outage: a dead, revoked Alpaca API key
(confirmed 401 on Alpaca's paper/live/AND market-data endpoints) was set as a persistent
Windows USER-level environment variable, invisible to this repo or .env.local. With the old
override=False behavior, load_dotenv() (and the manual-parsing fallback) treated that
pre-existing OS value as authoritative and never let .env.local's real, working key take over -
credential_manager.py's Step 3 (env var check) then silently returned the dead key.

override=True is safe specifically because load_env_local() no-ops entirely when .env.local
doesn't exist (the exists() check at the top of the function) - i.e. it has zero effect in any
real deployed environment (AWS Lambda/ECS) where the file isn't shipped; it only ever changes
behavior on a local dev machine, which is exactly where the checked-in file should be
authoritative over arbitrary OS-level cruft.
"""

import os
from unittest.mock import mock_open, patch

from utils.dotenv_loader import load_env_local


class TestLoadEnvLocalOverridesStaleOSValue:
    def test_manual_parser_overrides_existing_env_var(self) -> None:
        """Fallback path (python-dotenv unavailable): a real value in .env.local must replace
        a stale value already present in os.environ, not be silently skipped."""
        fake_file_content = "APCA_API_KEY_ID=REAL_WORKING_KEY\n"
        with (
            patch.dict(os.environ, {"APCA_API_KEY_ID": "DEAD_STALE_KEY"}, clear=False),
            patch("utils.dotenv_loader.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=fake_file_content)),
            # Force the dotenv-library branch to fail so the manual parser under test runs.
            patch.dict("sys.modules", {"dotenv": None}),
        ):
            load_env_local()
            assert os.environ["APCA_API_KEY_ID"] == "REAL_WORKING_KEY"

    def test_dotenv_library_path_calls_load_dotenv_with_override_true(self) -> None:
        """The primary (python-dotenv) code path must pass override=True - this is the actual
        line that shipped the bug (override=False) and must never regress back."""
        with (
            patch("utils.dotenv_loader.Path.exists", return_value=True),
            patch("dotenv.load_dotenv") as mock_load_dotenv,
        ):
            load_env_local()
            mock_load_dotenv.assert_called_once()
            _args, kwargs = mock_load_dotenv.call_args
            assert kwargs.get("override") is True, (
                "load_dotenv() must be called with override=True so .env.local always wins "
                "over stale OS-level environment variables on a local dev machine - see this "
                "test module's docstring for the live Alpaca-401 incident this prevents."
            )

    def test_missing_env_local_file_is_a_true_noop(self) -> None:
        """No .env.local (e.g. a real AWS deployment) must never touch os.environ at all -
        this is what makes override=True safe: it only ever fires when the file exists."""
        with (
            patch.dict(os.environ, {"SOME_VAR": "untouched"}, clear=False),
            patch("utils.dotenv_loader.Path.exists", return_value=False),
            patch("dotenv.load_dotenv") as mock_load_dotenv,
        ):
            load_env_local()
            mock_load_dotenv.assert_not_called()
            assert os.environ["SOME_VAR"] == "untouched"
