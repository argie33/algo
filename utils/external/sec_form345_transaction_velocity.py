#!/usr/bin/env python3
"""SEC Form 3/4/5 insider transaction velocity aggregator (from official bulk data).

Extracts insider BUY/SELL activity patterns from SEC's bulk insider-transactions
data sets. Reuses sec_form345_bulk.py's download infrastructure but focuses on
transaction counts and share volumes rather than current holdings.

Transaction velocity indicators:
- recent_buys/recent_sells: count of open-market buys/sells (TRANS_CODE P/S)
- transaction_momentum: net buys - sells (positive = confidence)
- insider_confidence_score: 0-100 scale based on buy/sell ratio
"""

import io
import logging
import threading
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from utils.infrastructure.url_validator import validate_url

logger = logging.getLogger(__name__)

USER_AGENT = "algo-trading argeropolos@gmail.com"
REQUEST_TIMEOUT_SECONDS = 60
DEFAULT_LOOKBACK_QUARTERS = 12
URL_PATH_PREFIXES = ("datastandardsinnovation", "structureddata")

# Transaction codes for classification
OPEN_MARKET_BUY_CODE = "P"  # "Purchase on open market"
OPEN_MARKET_SELL_CODE = "S"  # "Sale on open market"
OPTION_CODES = ("M", "X", "C", "H")  # Option exercises (skip for "real" insider transactions)


@dataclass
class TransactionRecord:
    """Single insider transaction from Form 4/5."""

    symbol: str
    insider_cik: str
    insider_name: str
    trans_date: date
    trans_code: str  # P = buy, S = sell, etc.
    shares: int
    trans_price: float | None
    is_director: bool
    is_officer: bool
    filing_date: date


@dataclass
class VelocityMetrics:
    """Aggregated insider transaction velocity for one symbol."""

    symbol: str
    measurement_date: date
    buy_transactions_30d: int = 0
    sell_transactions_30d: int = 0
    buy_transactions_90d: int = 0
    sell_transactions_90d: int = 0
    total_buy_shares_30d: int = 0
    total_sell_shares_30d: int = 0
    total_buy_shares_90d: int = 0
    total_sell_shares_90d: int = 0
    data_unavailable: bool = False
    reason: str | None = None


class Form345TransactionVelocityAggregator:
    """Extracts insider transaction velocity from SEC bulk Form 3/4/5 data."""

    def __init__(self, lookback_quarters: int = DEFAULT_LOOKBACK_QUARTERS, session: requests.Session | None = None):
        self._lookback_quarters = lookback_quarters
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
        self._lock = threading.Lock()
        self._built = False
        self._transactions: dict[str, list[TransactionRecord]] = {}  # symbol -> list of transactions
        self._quarters_loaded: list[str] = []
        self._quarters_attempted = 0

    def get_velocity_metrics(self, symbol: str, measurement_date: date | None = None) -> VelocityMetrics:
        """Compute insider transaction velocity for a symbol.

        Args:
            symbol: Stock ticker
            measurement_date: Date to measure from (default: today)

        Returns:
            VelocityMetrics with buy/sell counts, volumes, and confidence score
        """
        self._ensure_built()
        if measurement_date is None:
            measurement_date = datetime.now(timezone.utc).date()

        metrics = VelocityMetrics(symbol=symbol, measurement_date=measurement_date)
        transactions = self._transactions.get(symbol.upper(), [])

        if not transactions:
            metrics.data_unavailable = True
            metrics.reason = "no_insider_transactions_in_lookback"
            return metrics

        # Calculate 30-day and 90-day windows
        thirty_days_ago = measurement_date - timedelta(days=30)
        ninety_days_ago = measurement_date - timedelta(days=90)

        for txn in transactions:
            # Only count open-market buys/sells, skip option exercises and gifts
            if txn.trans_code not in (OPEN_MARKET_BUY_CODE, OPEN_MARKET_SELL_CODE):
                continue

            # 30-day window
            if thirty_days_ago <= txn.trans_date <= measurement_date:
                if txn.trans_code == OPEN_MARKET_BUY_CODE:
                    metrics.buy_transactions_30d += 1
                    metrics.total_buy_shares_30d += txn.shares
                elif txn.trans_code == OPEN_MARKET_SELL_CODE:
                    metrics.sell_transactions_30d += 1
                    metrics.total_sell_shares_30d += txn.shares

            # 90-day window
            if ninety_days_ago <= txn.trans_date <= measurement_date:
                if txn.trans_code == OPEN_MARKET_BUY_CODE:
                    metrics.buy_transactions_90d += 1
                    metrics.total_buy_shares_90d += txn.shares
                elif txn.trans_code == OPEN_MARKET_SELL_CODE:
                    metrics.sell_transactions_90d += 1
                    metrics.total_sell_shares_90d += txn.shares

        return metrics

    def _ensure_built(self) -> None:
        if self._built:
            return
        with self._lock:
            if self._built:
                return
            self._build()
            self._built = True

    def _build(self) -> None:
        """Download and aggregate transaction data from SEC bulk quarterly ZIPs."""
        now = datetime.now(timezone.utc).date()

        def _quarter_tag(d: date) -> str:
            return f"{d.year}q{(d.month - 1) // 3 + 1}"

        def _recent_quarters(n: int, start_from: date) -> list[str]:
            tags = []
            year, quarter = start_from.year, (start_from.month - 1) // 3 + 1
            for _ in range(n):
                tags.append(f"{year}q{quarter}")
                quarter -= 1
                if quarter == 0:
                    quarter = 4
                    year -= 1
            return tags

        candidate_quarters = _recent_quarters(self._lookback_quarters + 2, now)
        loaded = 0

        for quarter in candidate_quarters:
            if loaded >= self._lookback_quarters:
                break
            self._quarters_attempted += 1
            zip_bytes = self._download_quarter(quarter)
            if zip_bytes is None:
                continue
            self._process_quarter(zip_bytes)
            self._quarters_loaded.append(quarter)
            loaded += 1

        logger.info(
            f"[FORM345_VELOCITY] Loaded {loaded} quarters ({self._quarters_loaded}): "
            f"{len(self._transactions)} symbols with insider transaction data"
        )

    def _download_quarter(self, quarter: str) -> bytes | None:
        """Download a single quarter's Form 3/4/5 bulk data ZIP."""
        for prefix in URL_PATH_PREFIXES:
            url = f"https://www.sec.gov/files/{prefix}/data/insider-transactions-data-sets/{quarter}_form345.zip"
            is_valid, error_msg = validate_url(url, allowed_domains=["sec.gov"])
            if not is_valid:
                logger.warning(f"[FORM345_VELOCITY] SSRF validation failed: {error_msg}")
                continue
            try:
                resp = self._session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            except (requests.ConnectionError, requests.Timeout) as e:
                logger.warning(f"[FORM345_VELOCITY] Network error: {e}")
                continue
            if resp.status_code == 404:
                continue
            if resp.status_code != 200:
                logger.warning(f"[FORM345_VELOCITY] Status {resp.status_code} for {url}")
                continue
            logger.debug(f"[FORM345_VELOCITY] Downloaded {quarter} ({len(resp.content)} bytes)")
            return bytes(resp.content)
        return None

    def _process_quarter(self, zip_bytes: bytes) -> None:
        """Extract transaction records from a quarter's bulk data."""
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                # Load the three key tables
                submission = pd.read_csv(
                    zf.open("SUBMISSION.tsv"),
                    sep="\t",
                    usecols=["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERTRADINGSYMBOL"],
                    dtype=str,
                    low_memory=False,
                )

                # Filter to relevant forms
                submission = submission[submission["DOCUMENT_TYPE"].isin({"3", "3/A", "4", "4/A", "5", "5/A"})]
                submission = submission[submission["ISSUERTRADINGSYMBOL"].notna()]

                if submission.empty:
                    return

                # Load owner and transaction details
                # SEC format changed - try to read with newer columns first, fall back to older format
                owners_usecols = ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME"]
                try:
                    # Newer format (Q2 2024+) - column names changed
                    owners = pd.read_csv(
                        zf.open("REPORTINGOWNER.tsv"),
                        sep="\t",
                        usecols=["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "ISCLERK", "ISDIRECTOR", "ISOFFICER"],
                        dtype=str,
                        low_memory=False,
                    )
                except (ValueError, KeyError):
                    # Fallback - read without the director/clerk/officer columns
                    # These are informational only and can be skipped
                    logger.debug("[FORM345_VELOCITY] REPORTINGOWNER.tsv format changed - reading without director/clerk/officer columns")
                    owners = pd.read_csv(
                        zf.open("REPORTINGOWNER.tsv"),
                        sep="\t",
                        usecols=owners_usecols,
                        dtype=str,
                        low_memory=False,
                    )
                    # Add dummy columns so downstream code doesn't break
                    owners["ISDIRECTOR"] = "FALSE"
                    owners["ISCLERK"] = "FALSE"
                    owners["ISOFFICER"] = "FALSE"

                transactions = pd.read_csv(
                    zf.open("NONDERIV_TRANS.tsv"),
                    sep="\t",
                    usecols=[
                        "ACCESSION_NUMBER",
                        "TRANS_DATE",
                        "TRANS_CODE",
                        "SHRS_OWND_FOLWNG_TRANS",
                        "TRANS_PRICE",
                    ],
                    dtype=str,
                    low_memory=False,
                )

                submission_idx = submission.set_index("ACCESSION_NUMBER")
                owners_idx = owners.set_index("ACCESSION_NUMBER")

                # Parse transactions
                for _, txn in transactions.iterrows():
                    acc = txn["ACCESSION_NUMBER"]

                    # Validate accession exists
                    if acc not in submission_idx.index:
                        continue

                    # Parse transaction details
                    try:
                        trans_date = pd.to_datetime(txn["TRANS_DATE"], format="%d-%b-%Y", errors="coerce").date()
                        if pd.isna(trans_date):
                            continue

                        shares = int(pd.to_numeric(txn["SHRS_OWND_FOLWNG_TRANS"], errors="coerce"))
                        if shares <= 0:
                            continue

                        trans_price = pd.to_numeric(txn["TRANS_PRICE"], errors="coerce")
                        trans_price = float(trans_price) if pd.notna(trans_price) else None
                    except (ValueError, TypeError):
                        continue

                    # Get filing and symbol info
                    filing_date = pd.to_datetime(
                        submission_idx.at[acc, "FILING_DATE"], format="%d-%b-%Y", errors="coerce"
                    ).date()
                    symbol = submission_idx.at[acc, "ISSUERTRADINGSYMBOL"]
                    issuer_cik = submission_idx.at[acc, "ISSUERCIK"]

                    # Get owner info
                    if acc not in owners_idx.index:
                        continue

                    owner_row = owners_idx.loc[acc]
                    if isinstance(owner_row, pd.DataFrame):
                        owner_row = owner_row.iloc[0]  # Take first if multiple

                    insider_cik = owner_row.get("RPTOWNERCIK", "")
                    insider_name = owner_row.get("RPTOWNERNAME", "")
                    is_director = str(owner_row.get("ISDIRECTOR", "")).upper() == "TRUE"
                    is_officer = str(owner_row.get("ISOFFICER", "")).upper() == "TRUE"

                    # Create record
                    record = TransactionRecord(
                        symbol=symbol,
                        insider_cik=insider_cik,
                        insider_name=insider_name,
                        trans_date=trans_date,
                        trans_code=txn["TRANS_CODE"],
                        shares=shares,
                        trans_price=trans_price,
                        is_director=is_director,
                        is_officer=is_officer,
                        filing_date=filing_date,
                    )

                    # Add to symbol's transaction list
                    if symbol not in self._transactions:
                        self._transactions[symbol] = []
                    self._transactions[symbol].append(record)

        except Exception as e:
            logger.error(f"[FORM345_VELOCITY] Error processing quarter: {e}")
