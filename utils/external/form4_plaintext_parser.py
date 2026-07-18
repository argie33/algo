#!/usr/bin/env python3
"""Form 4 Plain-Text Parser - Extract insider transaction data from SEC Form 4 filings.

SEC Form 4 filings are distributed in both XML (XBRL) and plain-text formats.
Most companies use plain-text format, which requires custom parsing.

This parser extracts:
- Insider holdings (current shares and % ownership)
- Recent buy/sell activity
- Latest transaction date
- Transaction details (date, type, shares, price)
"""

import logging
import re
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Form4PlaintextParser:
    """Parse Form 4 plain-text filings to extract insider transaction data."""

    # Regex patterns for common Form 4 sections
    # Form 4s use tables or line-by-line transaction entries

    # Table header patterns (common in Form 4s)
    TABLE_HEADER_PATTERN = re.compile(
        r"(?:Transaction|Non-Derivative|Derivative|Holding)\s*(?:Title|of|in)\s*(?:of Interest|Relationship)",
        re.IGNORECASE | re.MULTILINE
    )

    # Transaction row pattern: Date, Type, Shares, Price, Total Value
    # Format varies but typically: YYYY-MM-DD | A/D | shares | price | value
    TRANSACTION_PATTERN = re.compile(
        r"(\d{4}-\d{2}-\d{2})\s+[|]?\s*([AD])\s+[|]?\s*([\d,]+(?:\.\d+)?)",
        re.MULTILINE
    )

    # Ownership line pattern: "Shares Owned Following Transaction: X" or similar
    SHARES_OWNED_PATTERN = re.compile(
        r"(?:Shares|Shares Following|Shares Owned Following)\s*(?:Transaction)?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        re.IGNORECASE
    )

    # Percentage ownership pattern: "% of Class: X" or similar
    PERCENT_PATTERN = re.compile(
        r"(?:%\s*(?:of Class|Owned|Ownership)|Percent\s*(?:of Class)?)\s*[:\-]?\s*([\d.]+)%?",
        re.IGNORECASE
    )

    # Insider name pattern (typically in header)
    INSIDER_NAME_PATTERN = re.compile(
        r"(?:Reporting\s*(?:Person|Owner)|Officer|Director)\s*(?:Name)?[:\-]?\s*([A-Za-z\s\-,\.]+?)(?:\n|$)",
        re.IGNORECASE | re.MULTILINE
    )

    # Insider title pattern
    INSIDER_TITLE_PATTERN = re.compile(
        r"(?:Officer\s*Title|Title of|Position/Title)\s*[:\-]?\s*([A-Za-z\s,]+?)(?:\n|$)",
        re.IGNORECASE | re.MULTILINE
    )

    @staticmethod
    def parse(content: str, symbol: str) -> Optional[dict[str, Any]]:
        """Parse Form 4 plain-text content and extract insider data.

        Args:
            content: Raw plain-text Form 4 filing content
            symbol: Stock ticker symbol (for logging)

        Returns:
            Dict with parsed data or None if parsing fails
            {
                "insider_name": str,
                "insider_title": str or None,
                "shares_owned": int,
                "ownership_pct": float,
                "recent_buys": int,
                "recent_sells": int,
                "net_transactions": int,
                "latest_transaction_date": date or None,
            }

        Returns None if critical data cannot be extracted.
        """
        if not content or not isinstance(content, str):
            logger.warning(f"[{symbol}] Form 4: invalid content type")
            return None

        # Extract insider name
        insider_name = Form4PlaintextParser._extract_insider_name(content, symbol)
        if not insider_name:
            logger.warning(f"[{symbol}] Form 4: could not extract insider name")
            return None

        # Extract insider title (optional)
        insider_title = Form4PlaintextParser._extract_insider_title(content, symbol)

        # Extract transactions
        buys, sells, net_txns, latest_date = Form4PlaintextParser._extract_transactions(content, symbol)

        # Extract holdings
        shares_owned = Form4PlaintextParser._extract_shares_owned(content, symbol)
        if shares_owned is None:
            logger.warning(f"[{symbol}] Form 4: could not extract shares owned")
            return None

        # Extract ownership percentage
        ownership_pct = Form4PlaintextParser._extract_ownership_pct(content, symbol)
        if ownership_pct is None:
            logger.warning(f"[{symbol}] Form 4: could not extract ownership percentage")
            ownership_pct = 0.0

        result: dict[str, Any] = {
            "insider_name": insider_name,
            "insider_title": insider_title,
            "shares_owned": shares_owned,
            "ownership_pct": ownership_pct,
            "recent_buys": buys,
            "recent_sells": sells,
            "net_transactions": net_txns,
            "latest_transaction_date": latest_date,
        }
        return result

    @staticmethod
    def _extract_insider_name(content: str, symbol: str) -> Optional[str]:
        """Extract insider name from Form 4 header."""
        # Try multiple patterns for robustness
        patterns = [
            # Pattern 1: "Reporting Person Name: John Smith"
            r"(?:Reporting\s+(?:Person|Owner)\s+Name|Officer|Director)\s*[:\-]?\s*([A-Za-z\s\-,\.]+?)(?:\n|$)",
            # Pattern 2: Look for name at start of "Form 4" section
            r"(?:FORM\s+4\s+)?(?:For|Company)\s+[^\n]*\n\s*([A-Za-z][A-Za-z\s\-,\.]{2,}?)(?:\n|By)",
            # Pattern 3: After "Reporting Owner"
            r"Reporting\s+Owner[^\n]*\n\s*Name\s*[:\-]?\s*([A-Za-z][A-Za-z\s\-,\.]+?)(?:\n|$)",
        ]

        for pattern_str in patterns:
            match = re.search(pattern_str, content, re.IGNORECASE | re.MULTILINE)
            if match:
                name = match.group(1).strip()
                if name and len(name) > 2 and len(name) < 100:
                    return name

        return None

    @staticmethod
    def _extract_insider_title(content: str, symbol: str) -> Optional[str]:
        """Extract insider title/position from Form 4."""
        patterns = [
            r"(?:Officer\s*Title|Title\s*of|Position/Title)\s*[:\-]?\s*([A-Za-z\s,\.]+?)(?:\n|$)",
            r"(?:Relationship|Position|Title)[^:]*[:\-]\s*([A-Za-z][A-Za-z\s,\.]*?)(?:\n|$)",
        ]

        for pattern_str in patterns:
            match = re.search(pattern_str, content, re.IGNORECASE | re.MULTILINE)
            if match:
                title = match.group(1).strip()
                if title and len(title) < 100:
                    return title

        return None

    @staticmethod
    def _extract_transactions(content: str, symbol: str) -> tuple[int, int, int, Optional[date]]:
        """Extract transaction counts and latest date from Form 4.

        Returns:
            (buy_count, sell_count, net_transactions_shares, latest_date)
        """
        buy_count = 0
        sell_count = 0
        net_txns = 0
        latest_date = None

        # Find transaction section (after "Table of Contents" or "Transactions" header)
        transaction_section = Form4PlaintextParser._find_transaction_section(content)
        if not transaction_section:
            logger.debug(f"[{symbol}] Form 4: no transaction section found")
            return 0, 0, 0, None

        # Extract all transactions from section
        for match in Form4PlaintextParser.TRANSACTION_PATTERN.finditer(transaction_section):
            try:
                date_str = match.group(1)
                tx_type = match.group(2)  # 'A' = acquisition (buy), 'D' = disposition (sell)
                shares_str = match.group(3).replace(",", "")
                shares = int(float(shares_str))

                # Parse transaction date
                tx_date = datetime.fromisoformat(date_str).date()
                if latest_date is None or tx_date > latest_date:
                    latest_date = tx_date

                # Count and aggregate
                if tx_type.upper() == "A":
                    buy_count += 1
                    net_txns += shares
                elif tx_type.upper() == "D":
                    sell_count += 1
                    net_txns -= shares

            except (ValueError, AttributeError, IndexError) as e:
                logger.debug(f"[{symbol}] Form 4: failed to parse transaction: {e}")
                continue

        return buy_count, sell_count, net_txns, latest_date

    @staticmethod
    def _extract_shares_owned(content: str, symbol: str) -> Optional[int]:
        """Extract current shares owned following most recent transaction."""
        patterns = [
            r"Shares\s+Owned\s+Following\s+Transaction\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
            r"Shares\s+Following\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
            r"Shares\s+Owned\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
            r"Post[-\s]*Transaction.*?Shares\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        ]

        for pattern_str in patterns:
            match = re.search(pattern_str, content, re.IGNORECASE | re.MULTILINE)
            if match:
                shares_str = match.group(1).replace(",", "")
                try:
                    return int(float(shares_str))
                except (ValueError, TypeError):
                    continue

        return None

    @staticmethod
    def _extract_ownership_pct(content: str, symbol: str) -> Optional[float]:
        """Extract % ownership of class from Form 4."""
        patterns = [
            r"(?:%\s*of\s*Class|Percent\s*of\s*Class|Ownership\s*%)\s*[:\-]?\s*([\d.]+)%?",
            r"Percent\s*(?:of\s*)?Class\s*[:\-]?\s*([\d.]+)%?",
            r"%\s*(?:of\s*)?Class\s*[:\-]?\s*([\d.]+)%?",
        ]

        for pattern_str in patterns:
            match = re.search(pattern_str, content, re.IGNORECASE | re.MULTILINE)
            if match:
                pct_str = match.group(1)
                try:
                    return float(pct_str)
                except (ValueError, TypeError):
                    continue

        return None

    @staticmethod
    def _find_transaction_section(content: str) -> Optional[str]:
        """Find and extract the transaction data section from Form 4."""
        # Common transaction section markers
        markers = [
            (r"Non-Derivative\s+Transactions\s*\n", r"(?:\n\n|Derivative\s+Transactions|EXPLANATION)"),
            (r"Table\s+of\s+Non-Derivative\s+Transactions\s*\n", r"(?:\n\n|Derivative|EXPLANATION)"),
            (r"TRANSACTIONS\s*\n", r"(?:\n\n|HOLDINGS|DERIVATIVE)"),
        ]

        for start_pattern, end_pattern in markers:
            start_match = re.search(start_pattern, content, re.IGNORECASE | re.MULTILINE)
            if start_match:
                start_pos = start_match.end()
                end_match = re.search(end_pattern, content[start_pos:], re.IGNORECASE | re.MULTILINE)
                if end_match:
                    return content[start_pos : start_pos + end_match.start()]
                else:
                    # No explicit end marker, return until next major section or EOF
                    return content[start_pos:]

        # Fallback: return entire content if no section markers found
        return content
