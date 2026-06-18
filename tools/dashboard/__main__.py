"""Entry point for running dashboard as a module.

Supports both:
  python -m tools.dashboard
  python -m tools.dashboard.dashboard
  python tools/dashboard/dashboard.py (via sys.path hack)
"""

from .dashboard import main


if __name__ == "__main__":
    main()
