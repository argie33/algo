"""Routes - lazy loading for resilience."""

# Note: Modules are loaded dynamically by api_router.py using __import__()
# This __init__.py is minimal to avoid cascading import failures
__all__ = [
    "algo",
    "financials",
    "earnings",
    "signals",
    "prices",
    "stocks",
    "sectors",
    "industries",
    "market",
    "economic",
    "sentiment",
    "scores",
    "research",
    "audit",
    "trades",
    "admin",
    "contact",
    "settings",
    "health",
    "risk_dashboard",
    "data_coverage",
]
