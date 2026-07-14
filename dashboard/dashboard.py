#!/usr/bin/env python3
"""Algo Ops Terminal Dashboard

Usage (LOCAL DEVELOPMENT - RECOMMENDED):
  python dashboard/dashboard.py --local               # use local API (localhost:3001)
  python dashboard/dashboard.py --local -w 30         # watch mode, auto-refresh every 30s

Usage (AWS/Production - requires Cognito):
  python dashboard/dashboard.py                       # requires COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID env vars
  python dashboard/dashboard.py -w 60                 # watch mode, refresh every 60s

IMPORTANT: For local development, ALWAYS use --local flag!
Without it, dashboard tries to connect to AWS Lambda which requires Cognito authentication.

Modes:
  Local: Run local dev server first (python lambda/api/dev_server.py), then use --local flag
  AWS (default): Set DASHBOARD_API_URL, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID env vars
"""

import os
import sys

# CRITICAL FIX: Windows console encoding (cp1252) cannot display UTF-8.
# Redirect stdout/stderr to use UTF-8 before any Rich console creation.
if sys.platform.startswith("win"):
    import io

    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass  # If redirection fails, continue anyway - better than crashing

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_dashboard_dir = os.path.dirname(os.path.abspath(__file__))
if _dashboard_dir in sys.path:
    sys.path.remove(_dashboard_dir)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import argparse
import threading
import time
from typing import Any
from urllib.parse import urlparse

# AUTO-DETECT LOCAL MODE: Check if localhost:3001 is available; if so, use it by default
# This eliminates the need for users to remember --local flag
# Also support explicit --local flag for backward compatibility
import socket
import os as _os_auto


def _is_dev_server_available() -> bool:
    """Check if dev server is running on localhost:3001."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(("localhost", 3001))
        sock.close()
        return result == 0
    except Exception:
        return False


# Parse --local flag early before any dashboard/API modules are imported
_args_temp = argparse.ArgumentParser(add_help=False)
_args_temp.add_argument("--local", action="store_true", help="Use local API (localhost:3001)")
_temp_args, _ = _args_temp.parse_known_args()

# CRITICAL FIX: Only auto-detect localhost if AWS config is NOT explicitly set
# This ensures AWS configuration is never overridden by localhost auto-detection.
# Respects explicit AWS setup while still providing convenience for dev-only scenarios.
_has_aws_config = _os_auto.environ.get("DASHBOARD_API_URL") is not None

# Enable local mode if:
# 1. User explicitly passes --local flag, OR
# 2. Dev server is running on localhost:3001 AND no AWS config is explicitly set
if _temp_args.local or (_is_dev_server_available() and not _has_aws_config):
    _os_auto.environ["DASHBOARD_API_URL"] = "http://localhost:3001"
    _os_auto.environ["LOCAL_MODE"] = "true"
    print("[DASHBOARD_STARTUP] LOCAL MODE DETECTED/ENABLED - Using localhost:3001", flush=True)

try:
    import msvcrt

    def _keypress() -> str:
        """Non-blocking keypress detection on Windows.

        CRITICAL FIX: msvcrt operations can hang on some Windows configs.
        Check kbhit() only, skip getch() to avoid blocking.
        """
        try:
            result = msvcrt.kbhit()
            if result:
                try:
                    ch = msvcrt.getch()
                    return str(ch.decode("utf-8", errors="ignore").lower())
                except Exception:
                    return ""  # Ignore encoding/read errors
            return ""
        except Exception:
            return ""  # Ignore any msvcrt errors

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

# Support both: direct execution (python dashboard/dashboard.py) and module execution (python -m dashboard)
try:
    # Try relative imports first (module execution)
    from .api_data_layer import reset_circuit_breaker, set_api_url, set_cognito_auth, validate_api_config
    from .cognito_auth import get_cognito_auth as get_cognito_auth_instance
    from .cognito_auth import save_tokens
    from .core import DashboardContext, ViewMode
    from .error_boundary import error_summary_panel
    from .error_recovery import RenderRecovery
    from .fetchers import load_all
    from .panel_registry import get_panel_registry as _get_panel_registry
    from .panels import loading_layout, mascot_compact
    from .renderers import (
        check_auth_lost,
        render_dashboard_body,
        render_error_panel,
        render_expanded_view,
        render_header_components,
    )
    from .utilities import CONSOLE, MASCOT_W, logger
    from .watch import LoadState, WatchModeController, WatchState
except ImportError:
    # Fall back to absolute imports (direct script execution)
    from dashboard.api_data_layer import reset_circuit_breaker, set_api_url, set_cognito_auth
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
    from dashboard.watch import WatchModeController, WatchState


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
        """Load data with 20-second timeout."""
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
            load_thread.join(timeout=20.0)

            # CRITICAL FIX: Always set state.result, even on error
            # This ensures the dashboard never gets stuck on the loading screen
            if error[0]:
                # Error occurred - set result to empty dict so dashboard renders with error panel
                state.result = {}
                state.error = f"{type(error[0]).__name__}: {str(error[0])[:100]}"
            elif result[0] is not None:
                # Success - data loaded
                state.result = result[0]
            else:
                # Timeout - set empty result to show dashboard instead of loading screen
                state.result = {}
                state.error = "Data load timeout (exceeded 20 seconds)"

            state.elapsed = time.monotonic() - t0
            state.last_load = time.monotonic()
            state.loading = False
        except Exception as e:
            # Catch-all for any unexpected exceptions
            logger.error(f"Data load error: {type(e).__name__}: {e}", exc_info=True)
            state.result = {}  # Ensure result is set
            state.loading = False
            state.error = f"{type(e).__name__}: {str(e)[:100]}"

    # CRITICAL FIX: Load data BEFORE showing dashboard to avoid infinite loading state
    try:
        logger.info("[STARTUP] Preloading data...")
        state.result = load_all()
        logger.info(f"[STARTUP] Preload SUCCESSFUL: {len(state.result)} fetchers loaded")
        state.loading = False
        state.elapsed = 0.0
        state.last_load = time.monotonic()
    except Exception as e:
        logger.error(f"[STARTUP] Preload FAILED: {type(e).__name__}: {e}", exc_info=True)
        state.result = {}
        state.loading = False
        state.elapsed = 0.0
        state.last_load = time.monotonic()
        state.error = f"{type(e).__name__}: {str(e)[:50]}"

    # Still start the background load_data thread for future refresh cycles (in watch mode)
    load_data_thread = threading.Thread(target=load_data, daemon=False)
    load_data_thread.start()

    # Warm up the render pipeline to avoid 2+ second delay on first render
    def warmup_render() -> None:
        try:
            from .core import DashboardContext
            from .renderers import render_header_components

            ctx = DashboardContext({})
            render_header_components(ctx, 0, None, None, False, "AWS")
        except Exception:
            pass

    threading.Thread(target=warmup_render, daemon=True).start()

    first_render_with_data = False
    data_display_start = None
    with Live(console=CONSOLE, refresh_per_second=4, screen=True) as live:
        try:
            loop_start = time.monotonic()
            while True:
                elapsed_loop = time.monotonic() - loop_start

                # Timeout: if no data after 30 seconds, exit
                if elapsed_loop > 30 and state.result is None:
                    logger.info("[DASHBOARD] run_once() exiting after 30s with no data")
                    break

                # CRITICAL FIX: _keypress was blocking indefinitely on Windows.
                # Non-blocking keypress check with error recovery.
                try:
                    key = _keypress()
                    if key == "q":
                        break
                    if key:
                        controller.handle_keypress(key)
                except Exception as e:
                    logger.warning(f"Keypress check failed: {type(e).__name__}: {e}")

                state.frame = (state.frame + 1) % 1_000_001
                current_frame = state.frame
                current_result = state.result
                current_error = state.error
                is_loading = state.loading
                current_last_load = state.last_load
                current_elapsed = state.elapsed

                # CRITICAL FIX: Force data display after load completes
                # CRITICAL FIX: Render as soon as data is available, regardless of loading flag
                # state.result being set means load_all() completed, show the dashboard
                if current_result is not None:
                    # Data has arrived and loading is done - render it
                    with render_state._lock:
                        render_state.elapsed = current_elapsed
                        render_state.frame = current_frame
                        render_state.view_mode = controller.get_view_mode()
                    try:
                        # CRITICAL FIX: Direct render as fallback to avoid recovery layer issues
                        try:
                            layout, _ = recovery.render_with_recovery(current_result, render_state)
                        except Exception as recovery_err:
                            # Fallback: render directly without recovery
                            logger.warning(f"Recovery failed, using direct render: {recovery_err}")
                            layout = render_state(current_result)

                        live.update(layout)
                        if not first_render_with_data:
                            logger.info(f"[DASHBOARD] Transitioned to data display after {current_elapsed:.1f}s")
                            first_render_with_data = True
                            data_display_start = time.monotonic()
                    except Exception as e:
                        logger.error(f"Render failed: {type(e).__name__}: {e}", exc_info=True)
                        try:
                            live.update(render_error_panel(e, recovery.get_recovery_status()))
                        except Exception as panel_error:
                            logger.error(f"Error panel render failed: {type(panel_error).__name__}: {panel_error}")
                            # Last resort: show loading state instead of crashing
                            try:
                                live.update(loading_layout(current_frame, data_source=data_source))
                            except Exception as load_err:
                                logger.critical(f"All rendering failed: {load_err}")
                elif current_result is None:
                    first_render_with_data = False
                    if current_error:
                        try:
                            live.update(render_error_panel(RuntimeError(current_error)))
                        except Exception as e:
                            logger.error(f"Failed to render error panel: {type(e).__name__}: {e}")
                    else:
                        live.update(loading_layout(current_frame, data_source=data_source))

                time.sleep(0.25)
        except KeyboardInterrupt:
            pass

    load_data_thread.join(timeout=5)


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
            load_thread.join(timeout=20.0)

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

        # Warm up the render pipeline to avoid 2+ second delay on first render
        def warmup_render() -> None:
            try:
                from .core import DashboardContext
                from .renderers import render_header_components

                ctx = DashboardContext({})  # empty context for warmup
                render_header_components(ctx, 0, None, None, False, data_source)
            except Exception:
                pass  # Warmup failures don't block dashboard startup

        threading.Thread(target=warmup_render, daemon=True).start()

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
    """Setup local API mode.

    Checks if dev_server is running on localhost:3001. If not, provides
    helpful instructions to start it. Does NOT auto-start to avoid
    unexpected background processes.
    """
    local_url = "http://localhost:3001"
    if not _validate_api_url(local_url):
        logger.error(f"Invalid local API URL: {local_url}")
        sys.exit(1)

    # Check if dev_server is actually running
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", 3001))
        sock.close()
        if result != 0:
            # Dev server not running
            try:
                CONSOLE.print("\n[bold red]✗ FATAL: Dev server not running on localhost:3001[/]")
                CONSOLE.print("[yellow]The dashboard REQUIRES dev_server to be running in another terminal[/]\n")
                CONSOLE.print("[bold cyan]STEP 1: Start the API server (in a NEW terminal):[/]")
                CONSOLE.print("  [bright_black]$[/] python3 lambda/api/dev_server.py\n")
                CONSOLE.print("[bold cyan]STEP 2: Wait for this message:[/]")
                CONSOLE.print("  [bright_green][INFO] Starting API dev server on http://localhost:3001[/]\n")
                CONSOLE.print("[bold cyan]STEP 3: Start dashboard (in this terminal):[/]")
                CONSOLE.print("  [bright_black]$[/] python3 -m dashboard\n")
                CONSOLE.print("[dim]Note: Dashboard auto-detects dev_server, no --local flag needed[/]\n")
            except Exception as display_err:
                logger.error(f"Failed to display error: {type(display_err).__name__}: {display_err}")
            sys.exit(1)
    except Exception as e:
        logger.warning(f"Failed to check dev_server availability: {e}")

    set_api_url(local_url)
    # Clear Cognito auth for local dev mode so dashboard injects dev-admin token
    set_cognito_auth(None)
    logger.info("[DASHBOARD] ✓ LOCAL MODE: Using localhost:3001 dev server")
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
            CONSOLE.print("\n[bold red]ERROR: Dashboard cannot connect to AWS API[/]")
            CONSOLE.print("[red]Missing: DASHBOARD_API_URL[/]\n")
            CONSOLE.print("[bold cyan]SOLUTION FOR LOCAL DEVELOPMENT:[/]")
            CONSOLE.print("  python -m dashboard [bold cyan]--local[/]\n")
            CONSOLE.print("[bold cyan]SOLUTION FOR AWS PRODUCTION:[/]")
            CONSOLE.print("  Set environment variables:")
            CONSOLE.print("    DASHBOARD_API_URL")
            CONSOLE.print("    COGNITO_USER_POOL_ID")
            CONSOLE.print("    COGNITO_CLIENT_ID")
        except Exception as display_err:
            logger.error(f"Failed to display error message: {type(display_err).__name__}: {display_err}")
        sys.exit(1)

    if not env_pool:
        logger.error("[CREDS] COGNITO_USER_POOL_ID environment variable not set")
        try:
            CONSOLE.print("\n[bold red]ERROR: Dashboard cannot connect to AWS API[/]")
            CONSOLE.print("[red]Missing: COGNITO_USER_POOL_ID[/]\n")
            CONSOLE.print("[bold cyan]SOLUTION FOR LOCAL DEVELOPMENT:[/]")
            CONSOLE.print("  python -m dashboard [bold cyan]--local[/]\n")
            CONSOLE.print("[bold cyan]SOLUTION FOR AWS PRODUCTION:[/]")
            CONSOLE.print("  Set environment variables:")
            CONSOLE.print("    DASHBOARD_API_URL")
            CONSOLE.print("    COGNITO_USER_POOL_ID")
            CONSOLE.print("    COGNITO_CLIENT_ID")
        except Exception as display_err:
            logger.error(f"Failed to display error message: {type(display_err).__name__}: {display_err}")
        sys.exit(1)

    if not env_client:
        logger.error("[CREDS] COGNITO_CLIENT_ID environment variable not set")
        try:
            CONSOLE.print("\n[bold red]ERROR: Dashboard cannot connect to AWS API[/]")
            CONSOLE.print("[red]Missing: COGNITO_CLIENT_ID[/]\n")
            CONSOLE.print("[bold cyan]SOLUTION FOR LOCAL DEVELOPMENT:[/]")
            CONSOLE.print("  python -m dashboard [bold cyan]--local[/]\n")
            CONSOLE.print("[bold cyan]SOLUTION FOR AWS PRODUCTION:[/]")
            CONSOLE.print("  Set environment variables:")
            CONSOLE.print("    DASHBOARD_API_URL")
            CONSOLE.print("    COGNITO_USER_POOL_ID")
            CONSOLE.print("    COGNITO_CLIENT_ID")
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
        # Check both: explicit --local flag OR auto-detected LOCAL_MODE from environment
        use_local = args.local or os.environ.get("LOCAL_MODE") == "true"

        # Log startup mode
        if use_local:
            logger.info("[DASHBOARD_STARTUP] LOCAL MODE enabled - using dev_server on localhost:3001")
        else:
            logger.info("[DASHBOARD_STARTUP] AWS MODE - requires Cognito credentials")

        if use_local:
            data_source = _setup_local_api()
        else:
            # AWS mode: fetch and validate credentials
            aws_url, pool_id, client_id = _fetch_and_validate_aws_credentials()
            _configure_aws_and_auth(aws_url, pool_id, client_id)
            data_source = "AWS"

        # Reset circuit breaker to ensure fresh session (clears stale state from previous runs)
        reset_circuit_breaker()

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
