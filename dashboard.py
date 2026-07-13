#!/usr/bin/env python3
"""Direct dashboard launcher - use: python dashboard.py"""
if __name__ == "__main__":
    import sys
    import os

    # Ensure we import the dashboard package, not this script
    sys.path.insert(0, os.path.dirname(__file__))

    # Import and run
    from dashboard.dashboard import main
    main()
