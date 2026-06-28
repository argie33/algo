"""Entry point for running dashboard as a module.

Supports:
  python -m dashboard
  python -m dashboard.dashboard
"""

from .dashboard import main

if __name__ == "__main__":
    main()
