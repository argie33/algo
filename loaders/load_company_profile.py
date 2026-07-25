#!/usr/bin/env python3
"""Company Profile Loader - Consolidate SEC data into GICS sectors.

Populates company_profile from company_info_sec with proper SIC→GICS mapping.
Required for: position sizing, sector rotation (hardcoded GICS sectors),
dashboard sector enrichment.

Data source: company_info_sec (SEC EDGAR)
Update frequency: Daily (catches new symbols, sector changes)
Quality: Official SEC data + reliable GICS mapping

Run:
    python3 loaders/load_company_profile.py
"""

import logging
import sys
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.optimal_loader import OptimalLoader
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)
configure_socket_timeout(30)

# SIC Code to GICS Sector Mapping (4-digit granularity for accuracy)
# Uses 4-digit SIC codes to map to GICS sectors (11 main categories)
# Aligned with algo hardcoded DEFENSIVE/CYCLICAL sectors
SIC_TO_GICS = {
    # Technology (SICs 35-39, subset)
    3571: "Technology",  # Electronic computers
    3572: "Technology",  # Computer storage devices
    3575: "Technology",  # Computer terminals
    3577: "Technology",  # Computer peripheral equipment
    3578: "Technology",  # Calculating & accounting equipment
    3579: "Technology",  # Office machines n.e.c.
    3661: "Technology",  # Telephone & telegraph apparatus
    3674: "Technology",  # Semiconductors & related devices
    3679: "Technology",  # Electronic components n.e.c.
    3695: "Technology",  # Magnetic & optical recording media
    7372: "Technology",  # Services-Prepackaged software
    7373: "Technology",  # Services-Computer integrated systems
    7374: "Technology",  # Services-Data processing
    7375: "Technology",  # Services-Information retrieval services
    7376: "Technology",  # Services-Computer facilities management
    7377: "Technology",  # Services-Computer rental & leasing
    7378: "Technology",  # Services-Computer maintenance & repair
    7379: "Technology",  # Services-Computer related services n.e.c.
    # Healthcare
    2834: "Healthcare",  # Pharmaceutical preparations
    2835: "Healthcare",  # In vitro & in vivo diagnostic substances
    2836: "Healthcare",  # Biological products except diagnostic
    3842: "Healthcare",  # Orthopedic prosthetic appliances
    3845: "Healthcare",  # Electromedical & electrotherapeutic apparatus
    8000: "Healthcare",  # Health services (broad)
    8060: "Healthcare",  # Hospitals
    8071: "Healthcare",  # Medical laboratories
    # Financial Services
    6000: "Financial Services",  # Depository institutions (broad)
    6021: "Financial Services",  # National commercial banks
    6022: "Financial Services",  # State commercial banks
    6029: "Financial Services",  # Commercial banks n.e.c.
    6035: "Financial Services",  # Savings institutions except federal
    6036: "Financial Services",  # Savings banks except federal
    6211: "Financial Services",  # Security brokers & dealers
    6282: "Financial Services",  # Investment advice
    6311: "Financial Services",  # Life insurance
    6321: "Financial Services",  # Accident & health insurance
    6324: "Healthcare",  # Hospital & medical service plans
    6331: "Financial Services",  # Fire, marine & casualty insurance
    # Consumer Cyclical
    5141: "Consumer Cyclical",  # Grocery & related product wholesale
    5200: "Consumer Cyclical",  # Building material & garden supplies
    5300: "Consumer Cyclical",  # General merchandise stores
    5400: "Consumer Cyclical",  # Grocery stores
    5500: "Consumer Cyclical",  # Auto dealers & service stations
    5600: "Consumer Cyclical",  # Apparel & accessory stores
    5700: "Consumer Cyclical",  # Furniture & home furnishings
    5800: "Consumer Cyclical",  # Eating & drinking places
    3710: "Consumer Cyclical",  # Motor vehicles & car bodies
    # Consumer Defensive
    2000: "Consumer Defensive",  # Food & kindred products (broad)
    2010: "Consumer Defensive",  # Meat packing plants
    2020: "Consumer Defensive",  # Dairy farm products
    2030: "Consumer Defensive",  # Canned & preserved fruits & vegetables
    2040: "Consumer Defensive",  # Grain mill products
    2050: "Consumer Defensive",  # Bakery products
    2060: "Consumer Defensive",  # Sugar & confectionery products
    2070: "Consumer Defensive",  # Fats & oils
    2080: "Consumer Defensive",  # Beverages
    2082: "Consumer Defensive",  # Malt beverages
    2086: "Consumer Defensive",  # Soft drinks & carbonated waters
    2087: "Consumer Defensive",  # Flavoring extracts & syrups
    2090: "Consumer Defensive",  # Food preparations n.e.c.
    2100: "Consumer Defensive",  # Tobacco manufactures
    # Materials
    2800: "Materials",  # Chemicals & allied products (broad)
    2810: "Materials",  # Industrial inorganic chemicals
    2820: "Materials",  # Plastics materials & resins
    2821: "Materials",  # Plastics materials & resins
    2840: "Materials",  # Soap, cleaners, toilet preparations
    2860: "Materials",  # Industrial organic chemicals
    2870: "Materials",  # Agricultural chemicals
    2891: "Materials",  # Adhesives & sealants
    3000: "Materials",  # Rubber & miscellaneous plastics (broad)
    3086: "Materials",  # Plastics film & sheet
    3200: "Materials",  # Stone, clay, glass & concrete (broad)
    3300: "Materials",  # Primary metal industries (broad)
    3310: "Materials",  # Steel works, blast furnaces
    3330: "Materials",  # Primary nonferrous metals
    # Energy
    1311: "Energy",  # Crude petroleum & natural gas
    1381: "Energy",  # Drilling oil & gas wells
    1382: "Energy",  # Oil & gas exploration services
    2911: "Energy",  # Petroleum refining
    # Utilities
    4911: "Utilities",  # Electric services
    4922: "Utilities",  # Natural gas transmission
    4923: "Utilities",  # Natural gas distribution
    4924: "Utilities",  # Natural gas distribution n.e.c.
    4925: "Utilities",  # Gas production & distribution n.e.c.
    # Industrials (Machinery, transportation, manufacturing services)
    3400: "Industrials",  # Fabricated metal products (broad)
    3500: "Industrials",  # Machinery except electrical (broad)
    3510: "Industrials",  # Engines & turbines
    3523: "Industrials",  # Farm machinery & equipment
    3531: "Industrials",  # Construction machinery
    3532: "Industrials",  # Mining machinery
    3537: "Industrials",  # Industrial trucks & tractors
    3550: "Industrials",  # Special industry machinery
    3600: "Industrials",  # Electric & electronic equipment (broad)
    4000: "Industrials",  # Railroad transportation
    4011: "Industrials",  # Railroads, line-haul operating
    4013: "Industrials",  # Railroad switching & terminal services
    4100: "Industrials",  # Local & interurban transportation
    4200: "Industrials",  # Trucking & warehousing
    4400: "Industrials",  # Water transportation
    4500: "Industrials",  # Transportation by air
    # Communication Services
    4812: "Communication Services",  # Radiotelephone communication
    4813: "Communication Services",  # Telephone communication
    4822: "Communication Services",  # Telegraph & other signal services
    4832: "Communication Services",  # Radio broadcasting stations
    4833: "Communication Services",  # Television broadcasting stations
    7812: "Communication Services",  # Motion picture & video production
}


class CompanyProfileLoader(OptimalLoader):
    """Load company profiles from company_info_sec with SIC→GICS mapping."""

    table_name = "company_profile"
    primary_key = ("ticker",)
    watermark_field = "updated_at"
    is_symbol_based = True

    def fetch_incremental(self, symbol: str, since: Any) -> list[dict[str, Any]] | None:
        """Fetch company info from SEC source, map SIC to GICS."""
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT
                    symbol,
                    entity_name,
                    sic_code,
                    sic_description,
                    shares_outstanding,
                    created_at,
                    updated_at,
                    data_unavailable,
                    reason
                FROM company_info_sec
                WHERE symbol = %s
                LIMIT 1
                """,
                (symbol,),
            )
            row = cur.fetchone()

        if row is None:
            return [{"ticker": symbol, "data_unavailable": True, "reason": f"No data in company_info_sec for {symbol}"}]

        (
            sym,
            entity_name,
            sic_code,
            sic_description,
            shares_outstanding,
            created_at,
            updated_at,
            data_unavailable,
            reason,
        ) = row

        # Map SIC code to GICS sector (4-digit lookup, fail-fast if unmapped)
        # CRITICAL FIX (Session 416): Don't silently default to "Other" sector for unmapped SIC codes.
        # Per GOVERNANCE.md line 77-79: "Add explicit data quality gate, then ALLOW the data_unavailable marker"
        # Unmapped SIC codes indicate incomplete data; must be marked unavailable for operator visibility.
        if not sic_code:
            logger.warning(
                f"[{symbol}] No SIC code in company_info_sec. "
                f"Cannot determine GICS sector. Marking data_unavailable."
            )
            return [
                {
                    "ticker": symbol,
                    "data_unavailable": True,
                    "reason": "no_sic_code_available",
                }
            ]

        sic_code_int = int(sic_code)
        sector = SIC_TO_GICS.get(sic_code_int)

        if sector is None:
            # SIC code unmapped - fail-fast instead of defaulting to "Other"
            # This ensures stock_scores sees incomplete data and marks unavailable appropriately
            logger.warning(
                f"[{symbol}] SIC code {sic_code} not in SIC_TO_GICS mapping. "
                f"ACTION: Expand SIC_TO_GICS mapping or verify this is a tradeable US stock. "
                f"Marking data unavailable to prevent incomplete sector classification."
            )
            return [
                {
                    "ticker": symbol,
                    "data_unavailable": True,
                    "reason": f"sic_code_unmapped:{sic_code}",
                }
            ]

        return [
            {
                "ticker": symbol,
                "symbol": sym,
                "short_name": entity_name or "Unknown",
                "long_name": entity_name or "Unknown",
                "display_name": entity_name or "Unknown",
                "sector": sector,
                "industry": sic_description or "Unknown",
                "exchange": None,
                "website": None,
                "employees": None,
                "currency_code": "USD",
                "created_at": created_at,
                "updated_at": updated_at or None,
                "data_unavailable": data_unavailable or False,
                "reason": reason,
            }
        ]

    @staticmethod
    def _get_symbols() -> list[str]:
        """Get all symbols from company_info_sec."""
        with DatabaseContext("read") as cur:
            cur.execute("SELECT DISTINCT symbol FROM company_info_sec WHERE symbol IS NOT NULL")
            return [row[0] for row in cur.fetchall()]


if __name__ == "__main__":
    run_loader(CompanyProfileLoader)
