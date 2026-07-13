#!/usr/bin/env python3
"""Direct dashboard launcher from dashboard directory"""
if __name__ == "__main__":
    import sys
    import os
    from pathlib import Path

    # Get repo root (parent of dashboard directory)
    dashboard_dir = Path(__file__).parent
    repo_root = dashboard_dir.parent

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from dashboard.dashboard import main
        main()
    except ImportError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
