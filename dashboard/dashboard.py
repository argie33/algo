#!/usr/bin/env python3
"""Algo Trading Dashboard - Simple, working version."""

import argparse
import os
import sys
import time

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_dashboard_dir = os.path.dirname(os.path.abspath(__file__))
if _dashboard_dir in sys.path:
    sys.path.remove(_dashboard_dir)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# Handle Windows UTF-8 encoding
if sys.platform.startswith('win'):
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass


def get_cli_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Algo Trading Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--local', action='store_true', help='Use local dev_server (localhost:3001)')
    parser.add_argument('-w', '--watch', type=int, default=0, help='Auto-refresh interval in seconds')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    return parser.parse_args()


def main() -> None:
    """Main dashboard entry point."""
    try:
        # Parse arguments
        args = get_cli_args()

        # Auto-detect local mode
        if args.local or (not os.getenv('DASHBOARD_API_URL') and _is_dev_server_available()):
            os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
            os.environ['LOCAL_MODE'] = 'true'
            print("[DASHBOARD] Using localhost:3001", flush=True)

        # Set default API URL if not set
        if not os.getenv('DASHBOARD_API_URL'):
            print("[DASHBOARD] ERROR: No API URL configured")
            print("  For local dev: python dashboard/dashboard.py --local")
            print("  For AWS: Set DASHBOARD_API_URL environment variable")
            sys.exit(1)

        # Import dashboard components
        from dashboard.api_data_layer import set_api_url
        from dashboard.fetchers import load_all

        # Configure API
        api_url = os.environ['DASHBOARD_API_URL']
        set_api_url(api_url)

        # Test API connectivity with simple health check
        print(f"[DASHBOARD] Connecting to {api_url}...", flush=True)
        try:
            import json
            import urllib.request

            # Quick health check
            try:
                with urllib.request.urlopen(f"{api_url}/api/health", timeout=2) as response:
                    health = json.loads(response.read().decode())
                    print("[DASHBOARD] API health: OK", flush=True)
            except Exception as e:
                print(f"[DASHBOARD] Warning: API health check failed: {e}", flush=True)

            # Test data fetch
            print("[DASHBOARD] Loading portfolio data...", flush=True)
            try:
                req = urllib.request.Request(
                    f"{api_url}/api/algo/portfolio",
                    headers={'Authorization': 'Bearer dev-admin'}
                )
                with urllib.request.urlopen(req, timeout=3) as response:
                    portfolio = json.loads(response.read().decode())
                    if isinstance(portfolio, dict) and 'data' in portfolio:
                        data = portfolio['data']
                        total_val = data.get('total_portfolio_value', 'N/A')
                        positions = data.get('position_count', 0)
                        print(f"[DASHBOARD] Portfolio: {total_val} ({positions} positions)", flush=True)
            except Exception as e:
                print(f"[DASHBOARD] Warning: Could not load portfolio: {e}", flush=True)

            print("[DASHBOARD] Ready (press Ctrl+C to exit)", flush=True)

            # Keep running
            while True:
                time.sleep(1)
                if args.watch > 0:
                    time.sleep(args.watch - 1)
                    print("[DASHBOARD] Refreshing...", flush=True)
                    try:
                        req = urllib.request.Request(
                            f"{api_url}/api/algo/portfolio",
                            headers={'Authorization': 'Bearer dev-admin'}
                        )
                        with urllib.request.urlopen(req, timeout=3) as response:
                            portfolio = json.loads(response.read().decode())
                            if isinstance(portfolio, dict) and 'data' in portfolio:
                                data = portfolio['data']
                                total_val = data.get('total_portfolio_value', 'N/A')
                                print(f"[DASHBOARD] Updated: {total_val}", flush=True)
                    except Exception as e:
                        print(f"[DASHBOARD] Refresh error: {e}", flush=True)

        except Exception as e:
            print(f"[DASHBOARD] ERROR: {e}", flush=True)
            if args.debug:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n[DASHBOARD] Closed by user", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"[DASHBOARD] FATAL: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def _is_dev_server_available() -> bool:
    """Check if dev server is running on localhost:3001."""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(('localhost', 3001))
        sock.close()
        return result == 0
    except Exception:
        return False


if __name__ == "__main__":
    main()
