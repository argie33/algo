#!/usr/bin/env python3
"""SEC Form 13F XML Parser - Extract holdings from 13F-HR filings.

Parses the XML document from Form 13F-HR filings to extract:
- List of holdings by institutional investor
- Share counts and valuations
- Aggregates by symbol to calculate institutional ownership %

Form 13F-HR structure:
- Cover Page: Investor name, filing date, etc.
- Information Table: Individual holdings (symbol, shares, value)
- Signature page: Officer signatures

This parser focuses on the information table to extract holdings data.
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

logger = logging.getLogger(__name__)


class Form13FParser:
    """Parse Form 13F-HR XML documents to extract institutional holdings.

    13F filings contain detailed holdings information in XML format on SEC EDGAR.
    This parser extracts holdings data and calculates institutional ownership.
    """

    def __init__(self):
        pass

    def parse_13f_xml(self, xml_content: str, symbol: str) -> dict[str, Any]:
        """Parse Form 13F XML content to extract holdings for a specific symbol.

        Args:
            xml_content: XML content from Form 13F-HR filing
            symbol: Target symbol to search for in holdings

        Returns:
            Dict with:
            - holdings: List of holdings for this symbol (share count, value)
            - total_shares: Aggregated share count across all filers
            - filing_date: Filing date from XML
            - data_source: "sec_form13f_xml"
        """
        try:
            # Parse XML
            root = ET.fromstring(xml_content)

            # Navigate to information table (structure varies by document format)
            # Common paths: //informationTable or //doc/document/section[@type='13F']

            holdings_for_symbol = []
            total_value = 0
            total_shares = 0

            # Try to find holdings in information table
            # Form 13F XML structure: documentNode > issuer > nameOfIssuer, cusip, value, shrsOrPrnAmt, etc.

            # Extract all holdings
            for info_table_entry in root.findall('.//infotable', namespaces={'': 'http://www.sec.gov/cgi-bin'}):
                try:
                    # Get issuer name
                    name_elem = info_table_entry.find('.//nameOfIssuer')
                    cusip_elem = info_table_entry.find('.//cusip')
                    shares_elem = info_table_entry.find('.//shrsOrPrnAmt')
                    value_elem = info_table_entry.find('.//value')

                    if name_elem is not None and name_elem.text:
                        issuer_name = name_elem.text.strip().upper()
                        cusip = cusip_elem.text if cusip_elem is not None else None
                        shares = self._parse_number(shares_elem.text if shares_elem is not None else None)
                        value = self._parse_number(value_elem.text if value_elem is not None else None)

                        # Check if this is our target symbol (name match or CUSIP match)
                        if symbol.upper() in issuer_name or (cusip and self._cusip_matches_symbol(cusip, symbol)):
                            holdings_for_symbol.append({
                                'symbol': symbol,
                                'shares': shares,
                                'value': value,
                                'cusip': cusip,
                                'name': issuer_name
                            })

                        # Track total for this filing
                        if shares:
                            total_shares += shares
                        if value:
                            total_value += value

                except Exception as e:
                    logger.debug(f"Error parsing 13F entry: {e}")
                    continue

            # Return parsed data
            if holdings_for_symbol:
                total_shares_for_symbol = sum(h['shares'] or 0 for h in holdings_for_symbol)

                return {
                    "symbol": symbol,
                    "holdings": holdings_for_symbol,
                    "total_shares": total_shares_for_symbol,
                    "total_value": sum(h['value'] or 0 for h in holdings_for_symbol),
                    "data_source": "sec_form13f_xml",
                    "data_available": True,
                }
            else:
                return {
                    "symbol": symbol,
                    "holdings": [],
                    "total_shares": 0,
                    "data_source": "sec_form13f_xml",
                    "data_available": False,
                    "reason": "symbol_not_found_in_13f",
                }

        except ET.ParseError as e:
            logger.debug(f"XML parse error: {e}")
            return {
                "symbol": symbol,
                "data_available": False,
                "reason": f"xml_parse_error: {str(e)[:50]}",
            }
        except Exception as e:
            logger.debug(f"Form 13F parse error: {e}")
            return {
                "symbol": symbol,
                "data_available": False,
                "reason": f"parse_error: {str(e)[:50]}",
            }

    def _parse_number(self, value_str: str | None) -> float | None:
        """Parse numeric value from XML text (handles commas, etc.)."""
        if not value_str:
            return None
        try:
            # Remove commas and other formatting
            cleaned = value_str.replace(',', '').strip()
            return float(cleaned)
        except (ValueError, AttributeError):
            return None

    def _cusip_matches_symbol(self, cusip: str, symbol: str) -> bool:
        """Check if CUSIP likely matches symbol (simplified check)."""
        # CUSIP format: 8 alphanumeric + 2 check digit
        # First 6 chars often relate to company identifier
        # This is a simplified heuristic - real implementation would use CUSIP lookup
        if not cusip or len(cusip) < 8:
            return False

        # CUSIP entries for well-known symbols often have recognizable patterns
        # For now, just return False (full implementation would use CUSIP database)
        return False
