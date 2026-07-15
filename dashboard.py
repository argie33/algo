#!/usr/bin/env python3
"""Direct dashboard launcher - use: python dashboard.py"""

if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Ensure we import the dashboard package from current directory
    # Prevents Python from loading ./dashboard.py instead of ./dashboard/dashboard.py
    root_dir = str(Path(__file__).parent)
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    try:
        from dashboard.dashboard import main

        main()
    except ImportError as e:
        print(f"ERROR: Failed to import dashboard module: {e}")
        print("Make sure you're running from the repo root: python dashboard.py")
        sys.exit(1)
