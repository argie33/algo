#!/usr/bin/env python3
"""SEC EDGAR XML parsing utilities for Form 4 and SCHEDULE 13G filings.

Provides parsers for:
- Form 4: Insider transaction data (buy/sell activity)
- SCHEDULE 13G: Institutional ownership data (5%+ shareholders)
"""

import logging
from datetime import date, datetime
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


class Form4Parser:
    """Parse Form 4 filings to extract insider transaction data."""

    @staticmethod
    def parse(xml_content: str, symbol: str) -> dict[str, Any]:
        """Parse Form 4 XML and extract insider holdings & transaction data.

        Args:
            xml_content: Raw XML content from SEC EDGAR
            symbol: Stock ticker symbol (for logging)

        Returns:
            Dict with:
            - insider_name: Name of reporting person
            - insider_title: Officer/director title
            - shares_owned: Current insider holdings (shares)
            - ownership_pct: Current % ownership
            - recent_buys: # of purchases in last 90 days
            - recent_sells: # of sales in last 90 days
            - net_transactions: Net shares bought - sold (90 days)
            - latest_transaction_date: Most recent transaction

        Raises:
            ValueError: If XML structure invalid or critical fields missing
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse Form 4 XML for {symbol}: {e}") from e

        # Extract reporter (insider) information
        reporter = root.find(".//reportingOwnerId")
        if reporter is None:
            raise ValueError(f"Form 4 for {symbol}: missing reportingOwnerId element")

        insider_name = reporter.findtext("rptOwnerName", default=None)
        if not insider_name:
            raise ValueError(f"Form 4 for {symbol}: missing rptOwnerName")

        # Get title from reportingOwnerRelationship
        title_elem = root.find(".//reportingOwnerRelationship/officerTitle")
        insider_title = title_elem.text if title_elem is not None else None

        # Extract transaction data
        shares_owned = 0.0
        ownership_pct = 0.0
        recent_buys = 0
        recent_sells = 0
        net_transactions = 0.0
        latest_tx_date = None

        # Process all non-derivative transactions
        for txn in root.findall(".//nonDerivativeTransaction"):
            # Extract transaction date
            tx_date_elem = txn.find("transactionDate")
            if tx_date_elem is None or not tx_date_elem.text:
                continue

            try:
                tx_date = datetime.fromisoformat(tx_date_elem.text).date()
            except (ValueError, TypeError):
                logger.warning(f"[{symbol}] Invalid transaction date: {tx_date_elem.text}")
                continue

            # Track latest transaction
            if latest_tx_date is None or tx_date > latest_tx_date:
                latest_tx_date = tx_date

            # Extract disposition type (A=Acquired/buy, D=Disposed/sell)
            disposition_elem = txn.find(".//transactionAmounts/transactionAcquiredDisposedCode")
            disposition = disposition_elem.text if disposition_elem is not None else None

            # Extract shares in transaction
            shares_elem = txn.find(".//transactionAmounts/transactionShares/sharesOwnedFollowingTransaction")
            try:
                tx_shares = float(shares_elem.text) if shares_elem is not None and shares_elem.text else 0
            except (ValueError, AttributeError):
                tx_shares = 0

            # Count buys and sells
            if disposition == "A":
                recent_buys += 1
                net_transactions += tx_shares
            elif disposition == "D":
                recent_sells += 1
                net_transactions -= tx_shares

        # Extract current holdings (most recent post-transaction amounts)
        post_txn = root.find(".//postTransactionAmounts")
        if post_txn is not None:
            shares_elem = post_txn.find("sharesOwnedFollowingTransaction")
            if shares_elem is not None and shares_elem.text:
                try:
                    shares_owned = float(shares_elem.text)
                except (ValueError, TypeError):
                    shares_owned = 0.0

            pct_elem = post_txn.find("percentageOfClass")
            if pct_elem is not None and pct_elem.text:
                try:
                    ownership_pct = float(pct_elem.text)
                except (ValueError, TypeError):
                    ownership_pct = 0.0

        return {
            "insider_name": insider_name,
            "insider_title": insider_title,
            "shares_owned": int(shares_owned),
            "ownership_pct": float(ownership_pct),
            "recent_buys": recent_buys,
            "recent_sells": recent_sells,
            "net_transactions": int(net_transactions),
            "latest_transaction_date": latest_tx_date,
        }


class Schedule13GParser:
    """Parse SCHEDULE 13G filings to extract institutional holdings data."""

    @staticmethod
    def parse(xml_content: str, symbol: str) -> dict[str, Any]:
        """Parse SCHEDULE 13G XML and extract institutional holdings.

        Args:
            xml_content: Raw XML content from SEC EDGAR
            symbol: Stock ticker symbol (for logging)

        Returns:
            Dict with:
            - investor_name: Name of institutional investor/fund
            - shares_owned: Number of shares held
            - ownership_pct: Percentage of outstanding shares
            - value_usd: Market value of holdings (dollars)
            - sole_voting_power: Shares with sole voting control
            - sole_dispositive_power: Shares investor can dispose of
            - is_amendment: Whether this is a 13G/A (amendment)
            - report_date: Filing report period date

        Raises:
            ValueError: If XML structure invalid or critical fields missing
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse SCHEDULE 13G XML for {symbol}: {e}") from e

        # Extract reporting owner (investor) information
        investor = root.find(".//reportingOwner")
        if investor is None:
            raise ValueError(f"SCHEDULE 13G for {symbol}: missing reportingOwner element")

        investor_name = investor.findtext("reportingOwnerName", default=None)
        if not investor_name:
            raise ValueError(f"SCHEDULE 13G for {symbol}: missing reportingOwnerName")

        # Extract holdings information
        holding = root.find(".//nonDerivativeHolding")
        if holding is None:
            raise ValueError(f"SCHEDULE 13G for {symbol}: missing nonDerivativeHolding element")

        holdings_elem = holding.find("holdings")
        if holdings_elem is None:
            raise ValueError(f"SCHEDULE 13G for {symbol}: missing holdings element")

        # Extract shares owned
        shares_elem = holdings_elem.find("sharesOwnedFollowingTransaction")
        try:
            shares_owned = int(shares_elem.text) if shares_elem is not None and shares_elem.text else 0
        except (ValueError, AttributeError):
            shares_owned = 0

        # Extract ownership percentage
        pct_elem = holdings_elem.find("percentageOfClass")
        try:
            ownership_pct = float(pct_elem.text) if pct_elem is not None and pct_elem.text else 0.0
        except (ValueError, AttributeError):
            ownership_pct = 0.0

        # Extract value (may be in thousands)
        value_usd = 0.0
        value_elem = holdings_elem.find("valueOwnedFollowingTransaction/value")
        if value_elem is not None and value_elem.text:
            try:
                value_usd = float(value_elem.text)
                # Check if value is in thousands (typical for SEC filings)
                if value_usd > 1_000_000_000_000:  # Over $1T in raw value likely thousands
                    value_usd = value_usd / 1000
            except (ValueError, TypeError):
                value_usd = 0.0

        # Extract voting power information
        voting_power = holding.find("votingPower")
        sole_voting = 0
        if voting_power is not None:
            sole_elem = voting_power.find("solePower")
            if sole_elem is not None and sole_elem.text:
                try:
                    sole_voting = int(sole_elem.text)
                except (ValueError, TypeError):
                    sole_voting = 0

        # Extract dispositive power information
        dispositive_power = holding.find("dispositivePower")
        sole_dispositive = 0
        if dispositive_power is not None:
            sole_elem = dispositive_power.find("solePower")
            if sole_elem is not None and sole_elem.text:
                try:
                    sole_dispositive = int(sole_elem.text)
                except (ValueError, TypeError):
                    sole_dispositive = 0

        # Check if this is an amendment (13G/A)
        amendment_elem = root.find(".//amendment")
        is_amendment = amendment_elem is not None and amendment_elem.text == "1"

        # Extract report date
        report_date_elem = root.find(".//periodOfReport")
        report_date = None
        if report_date_elem is not None and report_date_elem.text:
            try:
                report_date = datetime.fromisoformat(report_date_elem.text).date()
            except (ValueError, TypeError):
                report_date = None

        return {
            "investor_name": investor_name,
            "shares_owned": shares_owned,
            "ownership_pct": float(ownership_pct),
            "value_usd": float(value_usd),
            "sole_voting_power": sole_voting,
            "sole_dispositive_power": sole_dispositive,
            "is_amendment": is_amendment,
            "report_date": report_date,
        }
