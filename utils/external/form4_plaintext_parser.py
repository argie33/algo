#!/usr/bin/env python3
"""Form 4 Plain-Text Parser - Extract insider transaction data from SEC Form 4 filings.

SEC Form 4 filings are distributed in both XML (XBRL) and plain-text formats.
Most companies use plain-text format, which requires custom parsing. The .txt files
from SEC archives often contain HTML markup (tables, tags, entities), requiring
preprocessing before regex matching.

This parser extracts:
- Insider holdings (current shares and % ownership)
- Recent buy/sell activity
- Latest transaction date
- Transaction details (date, type, shares, price)
"""

import html
import logging
import re
from datetime import date, datetime
from typing import Any

from utils.monitoring.form4_parsing_metrics import track_form4_parsing_error, track_form4_parsing_success

logger = logging.getLogger(__name__)


class Form4PlaintextParser:
    """Parse Form 4 plain-text filings to extract insider transaction data.

    Handles both pure plain-text and HTML-embedded SEC Form 4 files by preprocessing
    the content to remove HTML tags and entities before applying regex patterns.
    """

    @staticmethod
    def _strip_html(content: str) -> str:
        """Remove HTML tags and decode HTML entities from SEC plaintext files.

        SEC Form 4 .txt files sometimes contain embedded HTML markup (tables, tags).
        This preprocessor removes tags and converts entities to plain text.

        Args:
            content: Raw SEC filing content potentially with HTML markup

        Returns:
            Cleaned content with HTML removed
        """
        # Decode HTML entities (e.g., &nbsp; -> space, &lt; -> <)
        content = html.unescape(content)

        # Remove HTML tags but preserve newlines between tags
        content = re.sub(r"<[^>]+>", " ", content)

        # Clean up excessive whitespace
        content = re.sub(r" +", " ", content)  # Multiple spaces -> single space
        content = re.sub(r"\n\s+", "\n", content)  # Indent at line start -> just newline

        return content

    # Regex patterns for common Form 4 sections
    # Form 4s use tables or line-by-line transaction entries

    # Table header patterns (common in Form 4s)
    TABLE_HEADER_PATTERN = re.compile(
        r"(?:Transaction|Non-Derivative|Derivative|Holding)\s*(?:Title|of|in)\s*(?:of Interest|Relationship)",
        re.IGNORECASE | re.MULTILINE
    )

    # Transaction row pattern: Date, Type, Shares, Price, Total Value
    # Format varies: "YYYY-MM-DD | A/D | shares" or "YYYY-MM-DD  A  shares" (after HTML strip)
    # Flexible on separators (pipe, tabs, multiple spaces) and case (A/D or a/d)
    TRANSACTION_PATTERN = re.compile(
        r"(\d{4}-\d{2}-\d{2})\s+[|]?\s*([ADad])\s+[|]?\s*([\d,]+(?:\.\d+)?)",
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
    def parse(content: str, symbol: str) -> dict[str, Any] | None:
        """Parse Form 4 plain-text content and extract insider data.

        Handles both pure plain-text and HTML-embedded SEC Form 4 files.

        Args:
            content: Raw plain-text Form 4 filing content (may contain HTML markup)
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
            track_form4_parsing_error(symbol, "invalid_content", "non_string_or_empty")
            return None

        # Preprocess: remove HTML tags and entities from SEC plaintext files
        content = Form4PlaintextParser._strip_html(content)

        # Extract insider name
        insider_name = Form4PlaintextParser._extract_insider_name(content, symbol)
        if not insider_name:
            logger.warning(f"[{symbol}] Form 4: could not extract insider name")
            track_form4_parsing_error(symbol, "insider_name_extraction_failed")
            return None

        # Extract insider title (optional)
        insider_title = Form4PlaintextParser._extract_insider_title(content, symbol)

        # Extract transactions
        buys, sells, net_txns, latest_date = Form4PlaintextParser._extract_transactions(content, symbol)

        # Extract holdings
        shares_owned = Form4PlaintextParser._extract_shares_owned(content, symbol)
        if shares_owned is None:
            logger.warning(f"[{symbol}] Form 4: could not extract shares owned")
            track_form4_parsing_error(symbol, "shares_owned_extraction_failed")
            return None

        # Extract ownership percentage
        ownership_pct = Form4PlaintextParser._extract_ownership_pct(content, symbol)
        if ownership_pct is None:
            logger.warning(f"[{symbol}] Form 4: could not extract ownership percentage")
            track_form4_parsing_error(symbol, "ownership_pct_extraction_failed")
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
        track_form4_parsing_success(symbol)
        return result

    @staticmethod
    def _extract_insider_name(content: str, symbol: str) -> str | None:
        """Extract insider name from Form 4 header.

        Tries multiple patterns to handle variations in SEC Form 4 formatting,
        including HTML-embedded files.
        """
        patterns = [
            # Pattern 1: "Reporting Person Name: John Smith" or just "Name: ..."
            r"(?:Reporting\s+(?:Person|Owner)\s+)?Name\s*[:\-]?\s*([A-Za-z][A-Za-z\s\-,\.]*?)(?:\n|$)",
            # Pattern 2: "Reporting Owner: John Smith"
            r"Reporting\s+(?:Person|Owner)\s*[:\-]?\s*([A-Za-z][A-Za-z\s\-,\.]{2,}?)(?:\n|$)",
            # Pattern 3: After "Reporting Owner" header with newline, name on next line
            r"(?:Reporting\s+(?:Person|Owner)|REPORTING\s+(?:PERSON|OWNER))[^\n]*\n\s*([A-Za-z][A-Za-z\s\-,\.]{2,}?)(?:\n|$)",
            # Pattern 4: Look for name at start of Form 4 section
            r"(?:FORM\s+4\s+)?(?:For|Company)\s+[^\n]*\n\s*([A-Za-z][A-Za-z\s\-,\.]{2,}?)(?:\n|By)",
        ]

        for pattern_str in patterns:
            match = re.search(pattern_str, content, re.IGNORECASE | re.MULTILINE)
            if match:
                name = match.group(1).strip()
                # Validate: must be 3+ chars, under 100 chars, mostly letters
                if name and 3 <= len(name) < 100 and sum(c.isalpha() for c in name) > len(name) * 0.5:
                    return name

        return None

    @staticmethod
    def _extract_insider_title(content: str, symbol: str) -> str | None:
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
    def _extract_transactions(content: str, symbol: str) -> tuple[int, int, int, date | None]:
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
    def _extract_shares_owned(content: str, symbol: str) -> int | None:
        """Extract current shares owned following most recent transaction.

        Tries multiple patterns to handle SEC Form 4 variations.
        """
        patterns = [
            r"Shares\s+Owned\s+Following\s+Transaction\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
            r"Shares\s+Following\s+Transaction\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
            r"Shares\s+Following\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
            r"Shares\s+Owned\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
            # Handle cases where "following" or "transaction" may be on different line
            r"(?:Shares|shares).*?(?:Following|following).*?(?:Transaction|transaction)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        ]

        for pattern_str in patterns:
            match = re.search(pattern_str, content, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                shares_str = match.group(1).replace(",", "")
                try:
                    return int(float(shares_str))
                except (ValueError, TypeError):
                    continue

        return None

    @staticmethod
    def _extract_ownership_pct(content: str, symbol: str) -> float | None:
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
    def _find_transaction_section(content: str) -> str | None:
        r"""Find and extract the transaction data section from Form 4.

        Tries multiple section markers to handle variations in SEC Form 4 structure.
        Uses \Z (absolute end of string) not $ (end of line) to avoid MULTILINE mode issues.
        """
        markers = [
            # Pattern: "Non-Derivative Transactions" header, then skip whitespace to first transaction
            (r"Non-Derivative\s+Transactions\s*\n\s*", r"(?:Derivative\s+Transactions|EXPLANATION|HOLDINGS|\Z)"),
            # Variation: table header
            (r"Table\s+of\s+Non-Derivative\s+Transactions\s*\n\s*", r"(?:Derivative|EXPLANATION|HOLDINGS|\Z)"),
            # Uppercase variation
            (r"(?:Non-Derivative\s+)?TRANSACTIONS\s*\n\s*", r"(?:HOLDINGS|DERIVATIVE|EXPLANATION|\Z)"),
            # Catch-all: look for transaction rows (date | type | shares)
            (r"(\d{4}-\d{2}-\d{2})", None),  # Start at first date; no end pattern
        ]

        for start_pattern, end_pattern in markers:
            start_match = re.search(start_pattern, content, re.IGNORECASE | re.MULTILINE)
            if start_match:
                start_pos = start_match.end()
                if end_pattern is None:
                    # For catch-all pattern, backtrack to start of line and return rest of file
                    start_pos = content.rfind("\n", 0, start_pos) + 1
                    return content[start_pos:]
                end_match = re.search(end_pattern, content[start_pos:], re.IGNORECASE | re.MULTILINE)
                if end_match:
                    return content[start_pos : start_pos + end_match.start()]
                else:
                    # No explicit end marker, return until end of file
                    return content[start_pos:]

        # Fallback: return entire content if no section markers found
        return content
