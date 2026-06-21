"""Routes - lazy loading for resilience."""

# Note: Modules are loaded dynamically by api_router.py using __import__()
# This __init__.py is minimal to avoid cascading import failures
__all__ = [
    "admin",
    "algo",
    "audit",
    "contact",
    "data_coverage",
    "earnings",
    "economic",
    "financials",
    "health",
    "industries",
    "market",
    "positions",
    "prices",
    "research",
    "risk_dashboard",
    "scores",
    "sectors",
    "sentiment",
    "settings",
    "signals",
    "stocks",
    "trades",
]
