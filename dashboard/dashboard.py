#!/usr/bin/env python3
"""Algo Ops Terminal Dashboard

Usage:
  python -m dashboard                                 # live view (AWS endpoints, q or Ctrl+C to exit)
  python -m dashboard -w                              # watch mode, auto-refresh every 30s
  python -m dashboard -w 60                           # watch mode, refresh every 60s
  python -m dashboard --compact                       # narrow positions table
  python -m dashboard --local                         # use local API (localhost:3001) instead of AWS

Modes:
  AWS (default): Set DASHBOARD_API_URL, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID env vars
  Local: Run local dev server on localhost:3001 first, then use --local flag
"""

import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import argparse
import threading
import time
from typing import Any
from urllib.parse import urlparse

try:
    import msvcrt

    def _keypress() -> str:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            return str(ch.decode("utf-8", errors="ignore").lower())
        return ""

except ImportError:
    import select
    import termios
    import tty

    def _keypress() -> str:
        if select.select([sys.stdin], [], [], 0)[0]:
            try:
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)  # type: ignore[attr-defined]
                try:
                    tty.setraw(fd)  # type: ignore[attr-defined]
                    ch = sys.stdin.read(1).lower()
                    return ch if ch else ""
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)  # type: ignore[attr-defined]
            except (OSError, AttributeError, ValueError) as e:
                raise RuntimeError(
                    f"Dashboard terminal input failed: {type(e).__name__}: {e}. "
                    "Terminal mode is broken — cannot read user input."
                ) from e
        return ""


from rich.layout import Layout
from rich.live import Live

from dashboard.api_data_layer import set_api_url, set_cognito_auth, validate_api_config
from dashboard.cognito_auth import get_cognito_auth as get_cognito_auth_instance
from dashboard.cognito_auth import save_tokens
from dashboard.core import DashboardContext, ViewMode
from dashboard.error_boundary import error_summary_panel
from dashboard.error_recovery import RenderRecovery
from dashboard.fetchers import load_all
from dashboard.panel_registry import get_panel_registry as _get_panel_registry
from dashboard.panels import loading_layout, mascot_compact
from dashboard.renderers import (
    check_auth_lost,
    render_dashboard_body,
    render_error_panel,
    render_expanded_view,
    render_header_components,
)
from dashboard.utilities import CONSOLE, MASCOT_W, logger
from dashboard.watch import LoadState, WatchModeController, WatchState


class _RenderState:
    """Thread-safe render state wrapper."""

    def __init__(self, compact: bool, data_source: str = "AWS") -> None:
        self.compact = compact
        self.data_source = data_source
        self.elapsed = 0.0
        self.frame = 0
        self.view_mode = "normal"
        self.watch_interval: int | None = None
        self.last_load_time: float | None = None
        self.refreshing = False
        self._lock = threading.Lock()

    def __call__(self, data: dict[str, Any]) -> Layout:
        """Render dashboard with current state."""
        with self._lock:
            elapsed = self.elapsed
            frame = self.frame
            view_mode = self.view_mode
            watch_interval = self.watch_interval
            last_load_time = self.last_load_time
            refreshing = self.refreshing

        return render_dashboard(
            data,
            compact=self.compact,
            elapsed=elapsed,
            frame=frame,
            watch_interval=watch_interval,
            last_load_time=last_load_time,
            refreshing=refreshing,
            view_mode=view_mode,
            data_source=self.data_source,
        )


_PANEL_REGISTRY = None
_REGISTRY_SKIPPED = False

if os.environ.get("SKIP_PANEL_REGISTRY"):
    logger.info("Panel registry disabled via SKIP_PANEL_REGISTRY environment variable")
    _REGISTRY_SKIPPED = True
else:
    try:
        _PANEL_REGISTRY = _get_panel_registry()
    except (ImportError, Exception) as e:
        logger.critical(f"Panel registry initialization failed: {type(e).__name__}: {e}")
        sys.exit(1)


def _validate_watch_interval(value: str) -> int:
    """Validate watch interval is between 10 and 600 seconds."""
    try:
        int_value = int(value)
        if int_value < 10:
            raise argparse.ArgumentTypeError(f"Watch interval must be at least 10 seconds (got {int_value})")
        if int_value > 600:
            raise argparse.ArgumentTypeError(f"Watch interval must be at most 600 seconds (got {int_value})")
        return int_value
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"Watch interval must be an integer (got {value})") from err


def _validate_api_url(url: str) -> bool:
    """Validate API URL format."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or not parsed.hostname:
            return False
        return True
    except Exception as e:
        logger.error("API URL validation failed for '%s': %s", url, e)
        return False


def render_dashboard(
    data: dict[str, Any],
    compact: bool = False,
    elapsed: float = 0.0,
    frame: int = 0,
    watch_interval: int | None = None,
    last_load_time: float | None = None,
    refreshing: bool = False,
    view_mode: str = "normal",
    data_source: str = "AWS",
) -> Layout:
    """Render dashboard layout for current state."""
    if not ViewMode.is_valid(view_mode):
        logger.warning(f"Invalid view_mode '{view_mode}', falling back to 'normal'")
        view_mode = "normal"

    ctx = DashboardContext(data)
    hdr_panel, exp_panel = render_header_components(
        ctx, elapsed, watch_interval, last_load_time, refreshing, data_source
    )
    mascot_panel = mascot_compact(data, frame)

    auth_lost_panel = check_auth_lost()
    error_panel = error_summary_panel(data)

    outer = Layout()
    if auth_lost_panel:
        outer.split_column(
            Layout(name="auth_error", size=5),
            Layout(name="top", size=10),
            Layout(name="r1", ratio=2),
            Layout(name="r2", ratio=2),
            Layout(name="r3", ratio=2),
            Layout(name="pos", ratio=3),
        )
        outer["auth_error"].update(auth_lost_panel)
    elif error_panel:
        outer.split_column(
            Layout(name="errors", size=3),
            Layout(name="top", size=10),
            Layout(name="r1", ratio=2),
            Layout(name="r2", ratio=2),
            Layout(name="r3", ratio=2),
            Layout(name="pos", ratio=3),
        )
        outer["errors"].update(error_panel)
    else:
        outer.split_column(
            Layout(name="top", size=10),
            Layout(name="r1", ratio=2),
            Layout(name="r2", ratio=2),
            Layout(name="r3", ratio=2),
            Layout(name="pos", ratio=3),
        )

    outer["top"].split_row(
        Layout(name="hdr", ratio=1),
        Layout(name="exposure", ratio=1),
        Layout(name="mascot", size=MASCOT_W),
    )
    outer["top"]["hdr"].update(hdr_panel)
    outer["top"]["exposure"].update(exp_panel)
    outer["top"]["mascot"].update(mascot_panel)

    render_dashboard_body(outer, ctx, compact)

    expanded = render_expanded_view(view_mode, ctx, hdr_panel, exp_panel, mascot_panel, compact)
    return expanded if expanded is not None else outer


def run_once(compact: bool, data_source: str = "AWS") -> None:
    """Single run - load data once and display. Uses same reliable pattern as run_watch()."""
    state = WatchState()
    recovery = RenderRecovery()
    render_state = _RenderState(compact, data_source)
    controller = WatchModeController()

    def load_data() -> None:
        """Load data with 5-second timeout."""
        try:
            state.loading = True
            state.error = None
            t0 = time.monotonic()

            result: list[Any] = [None]
            error: list[Exception | None] = [None]

            def load_with_timeout() -> None:
                try:
                    result[0] = load_all()
                except Exception as e:
                    error[0] = e

            load_thread = threading.Thread(target=load_with_timeout, daemon=True)
            load_thread.start()
            load_thread.join(timeout=5.0)

            if error[0]:
                raise error[0]
            if result[0] is not None:
                state.result = result[0]
            else:
                logger.warning("load_all() returned None (timeout)")
                state.result = {}

            state.elapsed = time.monotonic() - t0
            state.last_load = time.monotonic()
            state.loading = False
        except Exception as e:
            logger.error(f"Data load error: {type(e).__name__}: {e}", exc_info=True)
            state.loading = False
            state.error = f"{type(e).__name__}: {e}"

    load_data_thread = threading.Thread(target=load_data, daemon=False)
    load_data_thread.start()

    with Live(console=CONSOLE, refresh_per_second=4, screen=True) as live:
        try:
            while True:
                key = _keypress()
                if key == "q":
                    break
                controller.handle_keypress(key)

                state.frame = (state.frame + 1) % 1_000_001
                current_frame = state.frame
                current_result = state.result
                current_error = state.error
                is_loading = state.loading
                current_last_load = state.last_load
                current_elapsed = state.elapsed

                if current_result is None:
                    if current_error:
                        try:
                            live.update(render_error_panel(RuntimeError(current_error)))
                        except Exception as e:
                            logger.error(f"Failed to render error panel: {type(e).__name__}: {e}")
                    else:
                        live.update(loading_layout(current_frame, data_source=data_source))
                else:
                    with render_state._lock:
                        render_state.elapsed = current_elapsed
                        render_state.frame = current_frame
                        render_state.view_mode = controller.get_view_mode()
                    try:
                        layout, _ = recovery.render_with_recovery(current_result, render_state)
                        live.update(layout)
                    except Exception as e:
                        logger.error(f"Render failed: {type(e).__name__}: {e}", exc_info=True)
                        try:
                            live.update(render_error_panel(e, recovery.get_recovery_status()))
                        except Exception as panel_error:
                            logger.error(f"Error panel render failed: {type(panel_error).__name__}: {panel_error}")

                time.sleep(0.25)
        except KeyboardInterrupt:
            pass

    load_data_thread.join(timeout=60)


def run_watch(interval: int, compact: bool, data_source: str = "AWS") -> None:
    """Watch mode with auto-refresh."""
    state = WatchState()
    active_threads: list[Any] = []
    active_threads_lock = threading.Lock()
    recovery = RenderRecovery()
    render_state = _RenderState(compact, data_source)
    render_state.watch_interval = interval
    controller = WatchModeController()

    def cleanup_dead_threads() -> None:
        with active_threads_lock:
            active_threads[:] = [t for t in active_threads if t.is_alive()]

    def reload() -> None:
        try:
            state.loading = True
            state.error = None
            t0 = time.monotonic()

            # Load all data with 5-second timeout so dashboard renders quickly
            # with whatever data loads in that time
            result: list[Any] = [None]
            error: list[Exception | None] = [None]

            def load_with_timeout() -> None:
                try:
                    result[0] = load_all()
                except Exception as e:
                    error[0] = e

            load_thread = threading.Thread(target=load_with_timeout, daemon=True)
            load_thread.start()
            load_thread.join(timeout=5.0)

            if error[0]:
                raise error[0]
            if result[0] is not None:
                state.result = result[0]
            else:
                logger.warning("load_all() returned None (timeout)")
                state.result = {}  # Empty dict if timeout

            state.elapsed = time.monotonic() - t0
            state.last_load = time.monotonic()
            state.loading = False
        except Exception as e:
            logger.error(f"Reload thread error: {type(e).__name__}: {e}", exc_info=True)
            state.loading = False
            state.error = f"{type(e).__name__}: {e}"

    try:
        reload_thread = threading.Thread(target=reload, daemon=False)
        reload_thread.start()
        with active_threads_lock:
            active_threads.append(reload_thread)

        with Live(console=CONSOLE, refresh_per_second=4, screen=True) as live:
            try:
                while True:
                    key = _keypress()
                    if key == "q":
                        break
                    controller.handle_keypress(key)

                    state.frame = (state.frame + 1) % 1_000_001
                    current_frame = state.frame
                    current_result = state.result
                    current_error = state.error
                    is_loading = state.loading
                    current_last_load = state.last_load
                    current_elapsed = state.elapsed

                    if current_result is None:
                        if current_error:
                            try:
                                live.update(render_error_panel(RuntimeError(current_error)))
                            except Exception as e:
                                logger.error(f"Failed to render error panel: {type(e).__name__}: {e}")
                        else:
                            live.update(loading_layout(current_frame, data_source=data_source))
                    else:
                        with render_state._lock:
                            render_state.elapsed = current_elapsed
                            render_state.frame = current_frame
                            render_state.last_load_time = current_last_load
                            render_state.refreshing = is_loading
                            render_state.view_mode = controller.get_view_mode()
                        try:
                            layout, _ = recovery.render_with_recovery(current_result, render_state)
                            live.update(layout)
                        except Exception as e:
                            try:
                                live.update(render_error_panel(e, recovery.get_recovery_status()))
                            except Exception as panel_error:
                                logger.error(
                                    f"Failed to render error panel: {type(panel_error).__name__}: {panel_error}"
                                )

                    should_reload = controller.should_reload(current_last_load, interval, is_loading)
                    try:
                        should_retry_load = recovery.should_retry_data_load()
                    except Exception as e:
                        logger.error(f"Failed to check recovery retry status: {type(e).__name__}: {e}")
                        should_retry_load = False

                    if should_reload or should_retry_load:
                        cleanup_dead_threads()
                        reload_thread = threading.Thread(target=reload, daemon=False)
                        reload_thread.start()
                        with active_threads_lock:
                            active_threads.append(reload_thread)
                    time.sleep(0.25)
            except KeyboardInterrupt:
                pass
    finally:
        with active_threads_lock:
            threads_to_join = active_threads[:]
        for thread in threads_to_join:
            thread.join(timeout=60)
            if thread.is_alive():
                logger.error("Thread abandoned after 60s timeout in watch mode")


def _setup_local_api() -> str:
    """Setup local API mode."""
    local_url = "http://localhost:3001"
    if not _validate_api_url(local_url):
        logger.error(f"Invalid local API URL: {local_url}")
        sys.exit(1)
    set_api_url(local_url)
    return "LOCAL"


def _fetch_and_validate_aws_credentials() -> tuple[str, str, str]:
    """Fetch AWS credentials from environment variables (primary source only).

    CRITICAL: Fails fast if any credential is missing. AWS mode requires all three
    credentials (dashboard API URL, Cognito user pool ID, and Cognito client ID).
    No fallback to secondary sources — environment variables are the single source of truth.

    Raises: SystemExit if any credential missing or invalid.
    """
    env_url = os.environ.get("DASHBOARD_API_URL")
    env_pool = os.environ.get("COGNITO_USER_POOL_ID")
    env_client = os.environ.get("COGNITO_CLIENT_ID")

    if not env_url:
        logger.error("[CREDS] DASHBOARD_API_URL environment variable not set")
        try:
            CONSOLE.print("[bold red]ERROR:[/] DASHBOARD_API_URL environment variable required for AWS mode")
            CONSOLE.print("[bold cyan]To set up:[/]")
            CONSOLE.print("[cyan]   export DASHBOARD_API_URL='https://your-api-endpoint'[/]")
            CONSOLE.print("[cyan]   export COGNITO_USER_POOL_ID='your-pool-id'[/]")
            CONSOLE.print("[cyan]   export COGNITO_CLIENT_ID='your-client-id'[/]")
        except Exception as display_err:
            logger.error(f"Failed to display error message: {type(display_err).__name__}: {display_err}")
        sys.exit(1)

    if not env_pool:
        logger.error("[CREDS] COGNITO_USER_POOL_ID environment variable not set")
        try:
            CONSOLE.print("[bold red]ERROR:[/] COGNITO_USER_POOL_ID environment variable required for AWS mode")
        except Exception as display_err:
            logger.error(f"Failed to display error message: {type(display_err).__name__}: {display_err}")
        sys.exit(1)

    if not env_client:
        logger.error("[CREDS] COGNITO_CLIENT_ID environment variable not set")
        try:
            CONSOLE.print("[bold red]ERROR:[/] COGNITO_CLIENT_ID environment variable required for AWS mode")
        except Exception as display_err:
            logger.error(f"Failed to display error message: {type(display_err).__name__}: {display_err}")
        sys.exit(1)

    logger.info("AWS mode: Dashboard credentials loaded from environment variables")
    return env_url, env_pool, env_client


def _configure_aws_and_auth(aws_url: str, pool_id: str, client_id: str) -> None:
    """Configure AWS API and Cognito authentication.

    CRITICAL: Fails fast if authentication cannot be established. AWS mode requires
    valid Cognito credentials and successful user authentication. No degraded-state
    fallbacks are permitted.

    Raises: SystemExit if authentication fails or Cognito credentials invalid.
    """
    set_api_url(aws_url)
    os.environ["DASHBOARD_API_URL"] = aws_url
    os.environ["COGNITO_USER_POOL_ID"] = pool_id
    os.environ["COGNITO_CLIENT_ID"] = client_id
    logger.info("Dashboard credentials configured from environment variables")

    auth = get_cognito_auth_instance(require_auth=True)
    if auth is None or isinstance(auth, dict):
        logger.error("[AUTH] Failed to initialize Cognito authentication instance")
        try:
            CONSOLE.print("[bold red]ERROR:[/] Cognito authentication initialization failed")
            CONSOLE.print("[bold cyan]Required environment variables:[/]")
            CONSOLE.print("[cyan]   COGNITO_USERNAME = 'your_username'[/]")
            CONSOLE.print("[cyan]   COGNITO_PASSWORD = 'your_password' (set via AWS Secrets Manager)[/]")
        except Exception as display_err:
            logger.error(f"Failed to display error message: {type(display_err).__name__}: {display_err}")
        sys.exit(1)

    if not hasattr(auth, "is_authenticated") or not auth.is_authenticated():
        logger.error("[AUTH] Cognito authentication failed - user is not authenticated")
        try:
            CONSOLE.print("[bold red]ERROR:[/] Authentication failed - invalid or missing Cognito credentials")
            CONSOLE.print("[bold cyan]Verify:[/]")
            CONSOLE.print("[cyan]   COGNITO_USERNAME environment variable is set[/]")
            CONSOLE.print("[cyan]   COGNITO_PASSWORD is available in AWS Secrets Manager[/]")
        except Exception as display_err:
            logger.error(f"Failed to display error message: {type(display_err).__name__}: {display_err}")
        sys.exit(1)

    # Type guard: auth is now guaranteed to be non-dict and non-None after the checks above
    set_cognito_auth(auth)
    save_tokens(auth)
    logger.info("[AUTH] Dashboard authentication successful")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Algo trading dashboard - visualize live trading operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local API (localhost:3001) instead of AWS",
    )
    parser.add_argument(
        "-w",
        "--watch",
        nargs="?",
        const=30,
        type=_validate_watch_interval,
        metavar="SECONDS",
        help="Watch mode with auto-refresh (default: 30s, min: 10s, max: 600s)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Use narrow positions table",
    )

    args = parser.parse_args()

    try:
        # Configure data source
        if args.local:
            data_source = _setup_local_api()
        else:
            # AWS mode: fetch and validate credentials
            aws_url, pool_id, client_id = _fetch_and_validate_aws_credentials()
            _configure_aws_and_auth(aws_url, pool_id, client_id)
            data_source = "AWS"

        # Run dashboard with appropriate mode
        if args.watch is not None:
            run_watch(args.watch, args.compact, data_source)
        else:
            run_once(args.compact, data_source)

    except KeyboardInterrupt:
        pass
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Dashboard fatal error: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
