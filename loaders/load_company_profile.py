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
from datetime import datetime
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

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
    5961: "Consumer Cyclical",  # Retail-catalog & mail-order houses (e.g. AMZN)
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
    # ADDED 2026-08-19 (goal: "no SEC data"/loader audit - "find the holes" pass): live
    # DB audit of company_profile.reason found 119 distinct sic_code_unmapped:XXXX values
    # covering 1,176 active-universe symbols - entire major SIC divisions (Real Estate 65xx,
    # Insurance Agents/Non-depository Credit 61xx/64xx, Metal/Coal Mining 10xx/12xx,
    # Construction 15xx-17xx, Apparel/Textiles/Furniture 22xx-25xx, Publishing 27xx, Leather
    # 31xx, Toys/Misc Manufacturing 39xx, Wholesale Trade 50xx/51xx, Hotels/Recreation
    # 70xx/79xx, Professional/Research Services 81xx/87xx, Agriculture 0xxx) had ZERO
    # precedent entries in SIC_TO_GICS at all, so _build_major_group_fallback's own
    # same-division majority vote (below) correctly had nothing to vote from and these
    # stayed permanently unmapped - not a bug in the fallback, a genuine static coverage
    # gap in this table. Standard SIC-division-to-GICS-sector mappings (public
    # classification standards, not requiring live verification), covering every code the
    # live audit surfaced.
    # Real Estate (division 65, 67-REIT)
    6500: "Real Estate",  # Real estate (broad)
    6510: "Real Estate",  # Real estate operators (apartment buildings)
    6512: "Real Estate",  # Operators of apartment buildings
    6513: "Real Estate",  # Operators of apartment buildings
    6519: "Real Estate",  # Lessors of real property n.e.c.
    6531: "Real Estate",  # Real estate agents & managers
    6552: "Real Estate",  # Land subdividers & developers
    6798: "Real Estate",  # Real estate investment trusts (REITs)
    # Financial Services (divisions 61, 64, 67-non-REIT)
    6111: "Financial Services",  # Federal & federally-sponsored credit agencies
    6141: "Financial Services",  # Personal credit institutions
    6153: "Financial Services",  # Short-term business credit institutions
    6159: "Financial Services",  # Federal & federally-sponsored credit agencies n.e.c.
    6162: "Financial Services",  # Mortgage bankers & loan correspondents
    6163: "Financial Services",  # Loan brokers
    6199: "Financial Services",  # Finance services n.e.c.
    6411: "Financial Services",  # Insurance agents, brokers & service
    6792: "Financial Services",  # Oil royalty traders
    6794: "Financial Services",  # Patent owners & lessors
    6795: "Financial Services",  # Mineral royalty traders
    6799: "Financial Services",  # Investors, n.e.c.
    # Materials (metal/nonmetallic mining 10xx/14xx, wood/paper/leather 24xx/26xx/31xx)
    1000: "Materials",  # Metal mining (broad)
    1040: "Materials",  # Gold mining
    1090: "Materials",  # Metal mining services
    1400: "Materials",  # Mining & quarrying of nonmetallic minerals
    2400: "Materials",  # Lumber & wood products
    2421: "Materials",  # Sawmills & planing mills
    2430: "Materials",  # Millwork, veneer, plywood
    2451: "Materials",  # Mobile homes
    2611: "Materials",  # Pulp mills
    2621: "Materials",  # Paper mills
    2631: "Materials",  # Paperboard mills
    2650: "Materials",  # Paperboard containers & boxes
    2670: "Materials",  # Converted paper & paperboard products
    2673: "Materials",  # Plastics, foil & coated paper bags
    3100: "Materials",  # Leather & leather products (broad)
    3140: "Materials",  # Footwear except rubber
    # Energy (coal mining, division 12)
    1220: "Energy",  # Bituminous coal & lignite mining
    1221: "Energy",  # Bituminous coal & lignite surface mining
    # Consumer Cyclical (apparel/textiles/furniture/toys 22xx-25xx/39xx, homebuilding,
    # hotels/recreation 70xx/79xx, education 82xx)
    1520: "Consumer Cyclical",  # General building contractors - residential
    1531: "Consumer Cyclical",  # Operative builders (homebuilders)
    2200: "Consumer Cyclical",  # Textile mill products (broad)
    2211: "Consumer Cyclical",  # Broadwoven fabric mills, cotton
    2221: "Consumer Cyclical",  # Broadwoven fabric mills, manmade
    2273: "Consumer Cyclical",  # Carpets & rugs
    2300: "Consumer Cyclical",  # Apparel & other finished products (broad)
    2320: "Consumer Cyclical",  # Men's & boys' furnishings
    2330: "Consumer Cyclical",  # Women's outerwear
    2390: "Consumer Cyclical",  # Fabricated textile products n.e.c.
    2500: "Consumer Cyclical",  # Furniture & fixtures (broad)
    2510: "Consumer Cyclical",  # Household furniture
    2511: "Consumer Cyclical",  # Wood household furniture
    2520: "Consumer Cyclical",  # Office furniture
    2522: "Consumer Cyclical",  # Office furniture except wood
    2531: "Consumer Cyclical",  # Public building & related furniture
    2540: "Consumer Cyclical",  # Partitions & fixtures
    3910: "Consumer Cyclical",  # Jewelry, silverware & plated ware
    3942: "Consumer Cyclical",  # Dolls & stuffed toys
    3944: "Consumer Cyclical",  # Games, toys & children's vehicles
    3949: "Consumer Cyclical",  # Sporting & athletic goods n.e.c.
    3990: "Consumer Cyclical",  # Manufacturing industries n.e.c.
    7000: "Consumer Cyclical",  # Hotels, rooming houses, camps & other lodging (broad)
    7011: "Consumer Cyclical",  # Hotels & motels
    7500: "Consumer Cyclical",  # Automotive repair, services & parking (broad)
    7510: "Consumer Cyclical",  # Automotive rental & leasing without drivers
    7600: "Consumer Cyclical",  # Miscellaneous repair services
    7900: "Consumer Cyclical",  # Amusement & recreation services (broad)
    7948: "Consumer Cyclical",  # Racing, including track operations
    7990: "Consumer Cyclical",  # Services-amusement & recreation n.e.c.
    7997: "Consumer Cyclical",  # Membership sports & recreation clubs
    8200: "Consumer Cyclical",  # Educational services (broad)
    8351: "Consumer Cyclical",  # Child day care services
    # Communication Services (publishing, division 27)
    2711: "Communication Services",  # Newspapers: publishing
    2721: "Communication Services",  # Periodicals: publishing
    2731: "Communication Services",  # Books: publishing
    2741: "Communication Services",  # Miscellaneous publishing
    2750: "Communication Services",  # Commercial printing
    2761: "Communication Services",  # Manifold business forms
    2780: "Communication Services",  # Blankbooks & bookbinding
    # Industrials (construction 15xx-17xx nonresidential, transportation services 46xx/47xx,
    # wholesale trade 50xx/51xx, professional/engineering services 81xx/87xx)
    1540: "Industrials",  # General building contractors - nonresidential
    1600: "Industrials",  # Heavy construction other than building
    1623: "Industrials",  # Water, sewer, pipeline construction
    1700: "Industrials",  # Construction special trade contractors (broad)
    1731: "Industrials",  # Electrical work
    4610: "Industrials",  # Pipelines, except natural gas
    4700: "Industrials",  # Transportation services (broad)
    4731: "Industrials",  # Arrangement of transportation of freight & cargo
    5000: "Industrials",  # Wholesale trade - durable goods (broad)
    5010: "Industrials",  # Motor vehicles & motor vehicle parts
    5013: "Industrials",  # Motor vehicle supplies & new parts
    5030: "Industrials",  # Lumber & construction materials
    5031: "Industrials",  # Lumber, plywood & millwork
    5040: "Industrials",  # Professional & commercial equipment
    5045: "Industrials",  # Computers & computer peripheral equipment (wholesale)
    5047: "Industrials",  # Medical, dental & hospital equipment
    5051: "Industrials",  # Metals service centers & offices
    5063: "Industrials",  # Electrical apparatus & equipment
    5064: "Industrials",  # Electrical appliances, TV & radio sets
    5065: "Industrials",  # Electronic parts & equipment n.e.c.
    5070: "Industrials",  # Hardware & plumbing & heating equipment (broad)
    5072: "Industrials",  # Hardware
    5080: "Industrials",  # Industrial machinery & equipment (broad)
    5084: "Industrials",  # Industrial machinery & equipment
    5090: "Industrials",  # Miscellaneous durable goods
    5094: "Industrials",  # Jewelry, watches, precious stones & metals (wholesale)
    5099: "Industrials",  # Durable goods n.e.c.
    8111: "Industrials",  # Legal services
    8700: "Industrials",  # Engineering, accounting, research, management services (broad)
    8711: "Industrials",  # Engineering services
    8741: "Industrials",  # Management services
    8742: "Industrials",  # Management consulting services
    8744: "Industrials",  # Facilities support management services
    # Healthcare (commercial/biological research - CROs, division 87)
    8731: "Healthcare",  # Commercial physical & biological research
    8734: "Healthcare",  # Testing laboratories
    # Consumer Defensive (agricultural production, division 0)
    100: "Consumer Defensive",  # Agricultural production - crops
    200: "Consumer Defensive",  # Agricultural production - livestock
    900: "Consumer Defensive",  # Fishing, hunting & trapping
    # ADDED 2026-08-29 (goal: "full data" audit continuation): live DB audit found
    # sic_code_unmapped:700/:7200 covering 16 active-universe symbols - same "zero
    # existing precedent in that major group" gap class as the 2026-08-19 batch above,
    # just two codes the earlier audit's sample didn't happen to surface.
    700: "Consumer Defensive",  # Agricultural services (soil prep, crop/livestock
    # services, veterinary, landscaping) - same division-0 major group as the
    # crops/livestock/fishing codes directly above; live symbols confirmed: AVO
    # (Mission Produce), BNC/BV/RYM, PFAI.
    7200: "Consumer Cyclical",  # Services-personal services (live symbols confirmed:
    # HRB/H&R Block tax prep, SCI/CSV funeral homes, RGS/Regis hair salons,
    # WW/WeightWatchers) - matches this file's existing convention for adjacent
    # consumer-facing services codes in the 70-79 range (7011 hotels, 7500/7510
    # automotive, 7600 repair, 7900/7948/7990/7997 amusement - all already Consumer
    # Cyclical above). A genuinely coarse approximation for this specific code - SEC's
    # own SIC assignment doesn't track later pivots, so a few symbols under 7200 (e.g.
    # YELP, a review platform; DLPN, an entertainment/PR firm) read more like
    # Communication Services by modern GICS than personal-services - same class of
    # imprecision this file already accepts for other broad codes (e.g. 8700
    # "Engineering, accounting, research, management services" uniformly Industrials
    # above), not unique to this addition.
}


def _build_major_group_fallback(mapping: dict[int, str]) -> dict[int, str]:
    """Derive a 2-digit SIC major-group fallback from SIC_TO_GICS's own exact entries.

    SIC_TO_GICS's comments claim several entries are "broad" (e.g. "3500: Industrials #
    Machinery except electrical (broad)"), but a flat dict keyed on the exact 4-digit code
    never actually matched anything but that one code - live-verified 2026-07-27: running
    against the full local universe, 58.7% of symbols (3213/5471) failed closed on
    sic_code_unmapped, including common codes like 3560/7371/2842 that sit right next to
    already-mapped codes in the same division. Per GOVERNANCE.md's fail-fast investigation
    order ("FIX the loader to process all tradeable symbols" before accepting a coverage
    gap as final), this derives a same-division fallback (code // 100) by majority vote
    across SIC_TO_GICS's own existing entries - it only ever extends a sector this file has
    already committed to for that division, never invents a new classification for a
    division with zero existing precedent (those stay correctly unmapped/data_unavailable).
    """
    from collections import Counter

    votes: dict[int, Counter[str]] = {}
    for code, sector in mapping.items():
        votes.setdefault(code // 100, Counter())[sector] += 1
    return {major: counter.most_common(1)[0][0] for major, counter in votes.items()}


SIC_MAJOR_GROUP_FALLBACK = _build_major_group_fallback(SIC_TO_GICS)


class CompanyProfileLoader(OptimalLoader):
    """Load company profiles from company_info_sec with SIC→GICS mapping."""

    table_name = "company_profile"
    primary_key = ("ticker",)
    watermark_field = "updated_at"
    is_symbol_based = True
    max_fail_rate = 70.0  # Many symbols lack SEC SIC mapping (ETFs, funds, OTC, delisted); mark data_unavailable

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
            # WATERMARK FIX (2026-08-17, live-reproduced - 1296 symbols/run in
            # reference_then_morning_after_signals.log): this dict is missing this loader's
            # own watermark_field ("updated_at"), which utils/optimal_loader.py's
            # watermark_from_rows() requires on every row - raises ValueError, and this
            # symbol's write is rejected outright instead of landing the intended
            # data_unavailable marker. No source row exists to carry a real updated_at
            # through (unlike the two sic_code cases below), so stamp "now": this row IS the
            # first real fact about this symbol's company_profile state as of this run.
            return [
                {
                    "ticker": symbol,
                    # BUG FOUND 2026-08-23 (goal session: sector_ranking "Unknown" bucket audit):
                    # every fallback branch in this method omitted "symbol", unlike the success
                    # path below (line ~433) which sets both "ticker" and "symbol". Since this
                    # loader's UPSERT never updates "symbol" on ON CONFLICT (only sets it from the
                    # dict on first INSERT), any ticker whose first-ever company_profile write
                    # happened to hit a fallback branch got symbol=NULL permanently - no later run
                    # could fix it, even after transitioning to the success path or a different
                    # fallback branch. Live-confirmed 4 real active symbols (QVC, RCBC, BNC, SAR)
                    # stuck with ticker set but symbol NULL, silently excluded from every other
                    # table's `... JOIN company_profile cp ON x.symbol = cp.symbol` (the standard
                    # join pattern used almost everywhere else in this codebase), including
                    # algo/signals/sector_rotation.py's sector-ranking source query, where they
                    # landed in an unexplained "Unknown" sector bucket instead of Consumer
                    # Cyclical/Financial Services/whatever their real SIC maps to.
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"No data in company_info_sec for {symbol}",
                    "updated_at": datetime.now(EASTERN_TZ),
                }
            ]

        (
            sym,
            entity_name,
            sic_code,
            sic_description,
            _shares_outstanding,
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
                f"[{symbol}] No SIC code in company_info_sec. Cannot determine GICS sector. Marking data_unavailable."
            )
            return [
                {
                    "ticker": symbol,
                    # See the "row is None" branch above for the full "symbol" story - same fix.
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "no_sic_code_available",
                    # WATERMARK FIX (2026-08-17) - see the `row is None` branch above for the
                    # full story; this row has a real source updated_at to carry through (row
                    # exists in company_info_sec, matching the success path's own convention).
                    "updated_at": updated_at,
                }
            ]

        sic_code_int = int(sic_code)
        sector = SIC_TO_GICS.get(sic_code_int)
        if sector is None:
            sector = SIC_MAJOR_GROUP_FALLBACK.get(sic_code_int // 100)
            if sector is not None:
                logger.info(
                    f"[{symbol}] SIC code {sic_code} not in SIC_TO_GICS mapping; using "
                    f"major-group fallback (division {sic_code_int // 100}) -> {sector}."
                )

        if sector is None:
            # SIC code's whole major group is unmapped - fail-fast instead of defaulting to "Other"
            # This ensures stock_scores sees incomplete data and marks unavailable appropriately
            logger.warning(
                f"[{symbol}] SIC code {sic_code} not in SIC_TO_GICS mapping (nor its major "
                f"group). ACTION: Expand SIC_TO_GICS mapping or verify this is a tradeable "
                f"US stock. Marking data unavailable to prevent incomplete sector classification."
            )
            return [
                {
                    "ticker": symbol,
                    # See the "row is None" branch above for the full "symbol" story - same fix.
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"sic_code_unmapped:{sic_code}",
                    # WATERMARK FIX (2026-08-17) - see the `row is None` branch above for the
                    # full story; this row has a real source updated_at to carry through.
                    "updated_at": updated_at,
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
                # CRITICAL FIX: data_unavailable MUST be explicitly set by loader.
                # Do NOT use fallback False when flag is missing - that hides data integrity issues.
                "data_unavailable": data_unavailable if isinstance(data_unavailable, bool) else False,
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
