"""Entry point for running dashboard as a module.

Supports:
  python -m dashboard
  python -m dashboard.dashboard
  python -m dashboard --local
"""

if __name__ == "__main__":
    import sys
    from .dashboard import main
    main()
