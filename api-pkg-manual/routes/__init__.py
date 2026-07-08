"""Routes - lazy loading for resilience."""

from __future__ import annotations

from typing import TYPE_CHECKING

# Note: Modules are loaded dynamically by api_router.py using __import__()
# This __init__.py is minimal to avoid cascading import failures

if TYPE_CHECKING:
    from . import admin as admin
    from . import algo as algo
    from . import audit as audit
    from . import contact as contact
    from . import data_coverage as data_coverage
    from . import earnings as earnings
    from . import economic as economic
    from . import financials as financials
    from . import health as health
    from . import industries as industries
    from . import market as market
    from . import positions as positions
    from . import prices as prices
    from . import research as research
    from . import risk_dashboard as risk_dashboard
    from . import scores as scores
    from . import sectors as sectors
    from . import sentiment as sentiment
    from . import settings as settings
    from . import signals as signals
    from . import stocks as stocks
    from . import trades as trades

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
