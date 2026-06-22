"""Entry point for running dashboard as a module.

Supports:
  python -m tools.dashboard
  python -m tools.dashboard.dashboard
"""

from .dashboard import main

if __name__ == "__main__":
    main()
