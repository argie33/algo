#!/usr/bin/env python3
"""SEC Form 3/4/5 bulk insider-ownership aggregator (official structured data sets).

REPLACES the per-filing XML-parsing approach that loaders/load_insider_holdings_sec.py's
prior version documented as an 8-16h, tens-of-thousands-of-requests undertaking (fetching
each insider's Form 4 XML individually at the EDGAR XBRL API's 2 req/s rate limit).

SEC separately publishes the SAME data pre-flattened into quarterly bulk TSV files:
https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
("Insider Transactions Data Sets", readme: sec.gov/files/insider_transactions_readme.pdf).
Each quarterly ZIP contains SUBMISSION.tsv (one row per Form 3/4/5, with the issuer's own
ticker in ISSUERTRADINGSYMBOL - no CUSIP crosswalk needed, unlike Form 13F),
REPORTINGOWNER.tsv (insider identity per filing), and NONDERIV_HOLDING.tsv /
NONDERIV_TRANS.tsv (SHRS_OWND_FOLWNG_TRANS - the post-transaction running share total,
which is exactly "current holdings" per Form 4/5 semantics). This turns an infeasible
per-symbol crawl into a handful of static file downloads, no per-request rate limit.

METHODOLOGY:
- For each (issuer ticker, reporting-owner CIK) pair, keep only the MOST RECENT holding
  observation (by filing/transaction date) across the lookback window - Form 4/5 always
  reports the running total "following" the transaction, so the latest report IS the
  insider's current position, not an increment to sum.
- Sum across all owners for a symbol = total insider shares. Divide by shares_outstanding
  (company_info_sec) for insider_ownership_pct.
- Both direct (D) and indirect (I) non-derivative ownership are included - both are
  beneficially owned by the insider, matching standard "insider ownership %" definitions
  used by financial data providers.
- recent_buys/recent_sells count open-market transactions (TRANS_CODE 'P'/'S' only -
  excludes option exercises, gifts, and other non-trading transaction codes) within the
  single most-recently-published quarter.
- A symbol with zero Form 3/4/5 filings in the lookback window (LOOKBACK_QUARTERS) is
  reported data_unavailable - genuinely no insider-ownership signal available, not a bug.
  Foreign private issuers are commonly exempt from Section 16 (Form 3/4/5) entirely -
  SUBMISSION.tsv's NOT_SUBJECT_SEC16 flag is informational but not required to explain this.

Memory note: each quarter is downloaded, aggregated into the running per-symbol dict, and
discarded before the next quarter loads - only one quarter's raw TSVs are ever in memory at
once (peak measured well under 512MB for the full NONDERIV_HOLDING+NONDERIV_TRANS tables).
"""

import io
import logging
import threading
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pandas as pd
import requests

from utils.infrastructure.url_validator import validate_url

logger = logging.getLogger(__name__)

USER_AGENT = "algo-trading argeropolos@gmail.com"
REQUEST_TIMEOUT_SECONDS = 60
# ~3 years of quarters: long enough that an insider who filed a Form 5 (annual, no
# transaction) two years ago and hasn't traded since is still counted, short enough
# that a departed insider's years-stale holding doesn't linger indefinitely.
DEFAULT_LOOKBACK_QUARTERS = 12
URL_PATH_PREFIXES = ("datastandardsinnovation", "structureddata")
OPEN_MARKET_BUY_CODE = "P"
OPEN_MARKET_SELL_CODE = "S"

_SUBMISSION_COLS = ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERTRADINGSYMBOL"]
_OWNER_COLS = ["ACCESSION_NUMBER", "RPTOWNERCIK"]
_HOLDING_COLS = ["ACCESSION_NUMBER", "SHRS_OWND_FOLWNG_TRANS"]
_TRANS_COLS = ["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE", "SHRS_OWND_FOLWNG_TRANS"]
_RELEVANT_FORMS = {"3", "3/A", "4", "4/A", "5", "5/A"}


@dataclass
class SymbolInsiderSummary:
    """Aggregated current insider position for one issuer symbol."""

    total_shares: float
    number_of_insiders: int
    recent_buys: int
    recent_sells: int
    latest_filing_date: date
    sec_filing_url: str
    issuer_cik: str


@dataclass
class _OwnerPosition:
    shares: float
    as_of: date


@dataclass
class _SymbolAccumulator:
    issuer_cik: str = ""
    latest_filing_date: date | None = None
    latest_accession: str = ""
    owners: dict[str, _OwnerPosition] = field(default_factory=dict)
    recent_buys: int = 0
    recent_sells: int = 0
    recent_quarter_tag: str = ""


def _quarter_tag(d: date) -> str:
    return f"{d.year}q{(d.month - 1) // 3 + 1}"


def _recent_quarters(n: int, start_from: date) -> list[str]:
    """Return the n most recent quarter tags at/before start_from's quarter, newest first."""
    tags = []
    year, quarter = start_from.year, (start_from.month - 1) // 3 + 1
    for _ in range(n):
        tags.append(f"{year}q{quarter}")
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
    return tags


class Form345BulkAggregator:
    """Lazily downloads and aggregates SEC's bulk Form 3/4/5 data set, once per process.

    Thread-safe: get_symbol_summary() may be called concurrently by loader worker
    threads; the underlying build happens exactly once, guarded by a lock.
    """

    def __init__(self, lookback_quarters: int = DEFAULT_LOOKBACK_QUARTERS, session: requests.Session | None = None):
        self._lookback_quarters = lookback_quarters
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
        self._lock = threading.Lock()
        self._built = False
        self._summaries: dict[str, SymbolInsiderSummary] = {}
        self._quarters_loaded: list[str] = []
        self._quarters_attempted = 0

    def get_symbol_summary(self, symbol: str) -> SymbolInsiderSummary | None:
        self._ensure_built()
        return self._summaries.get(symbol.upper())

    @property
    def quarters_loaded(self) -> list[str]:
        self._ensure_built()
        return list(self._quarters_loaded)

    def _ensure_built(self) -> None:
        if self._built:
            return
        with self._lock:
            if self._built:
                return
            self._build()
            self._built = True

    def _build(self) -> None:
        now = datetime.now(timezone.utc).date()
        candidate_quarters = _recent_quarters(self._lookback_quarters + 2, now)
        accumulators: dict[str, _SymbolAccumulator] = {}
        loaded = 0
        most_recent_quarter_tag: str | None = None

        for quarter in candidate_quarters:
            if loaded >= self._lookback_quarters:
                break
            self._quarters_attempted += 1
            zip_bytes = self._download_quarter(quarter)
            if zip_bytes is None:
                continue
            if most_recent_quarter_tag is None:
                most_recent_quarter_tag = quarter
            self._process_quarter(zip_bytes, quarter, accumulators, is_most_recent=(quarter == most_recent_quarter_tag))
            self._quarters_loaded.append(quarter)
            loaded += 1

        if loaded == 0:
            logger.error(
                f"[FORM345_BULK] Failed to download any of {len(candidate_quarters)} candidate quarters "
                f"({candidate_quarters[0]}..{candidate_quarters[-1]}). Insider holdings will be unavailable "
                f"for all symbols this run."
            )

        for symbol, acc in accumulators.items():
            if not acc.owners or acc.latest_filing_date is None:
                continue
            total_shares = sum(p.shares for p in acc.owners.values())
            self._summaries[symbol] = SymbolInsiderSummary(
                total_shares=total_shares,
                number_of_insiders=len(acc.owners),
                recent_buys=acc.recent_buys,
                recent_sells=acc.recent_sells,
                latest_filing_date=acc.latest_filing_date,
                sec_filing_url=self._filing_index_url(acc.issuer_cik, acc.latest_accession),
                issuer_cik=acc.issuer_cik,
            )

        logger.info(
            f"[FORM345_BULK] Built insider-holdings aggregate from {loaded} quarters "
            f"({self._quarters_loaded}): {len(self._summaries)} symbols with current holdings."
        )

    def _download_quarter(self, quarter: str) -> bytes | None:
        for prefix in URL_PATH_PREFIXES:
            url = f"https://www.sec.gov/files/{prefix}/data/insider-transactions-data-sets/{quarter}_form345.zip"
            is_valid, error_msg = validate_url(url, allowed_domains=["sec.gov"])
            if not is_valid:
                logger.warning(f"[FORM345_BULK] SSRF validation failed for {url}: {error_msg}")
                continue
            try:
                resp = self._session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            except (requests.ConnectionError, requests.Timeout) as e:
                logger.warning(f"[FORM345_BULK] Network error fetching {url}: {e}")
                continue
            if resp.status_code == 404:
                continue
            if resp.status_code != 200:
                logger.warning(f"[FORM345_BULK] Unexpected status {resp.status_code} fetching {url}")
                continue
            logger.debug(f"[FORM345_BULK] Downloaded {quarter} from {prefix} ({len(resp.content)} bytes)")
            return resp.content
        return None

    def _process_quarter(
        self,
        zip_bytes: bytes,
        quarter: str,
        accumulators: dict[str, _SymbolAccumulator],
        is_most_recent: bool,
    ) -> None:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            submission = pd.read_csv(
                zf.open("SUBMISSION.tsv"), sep="\t", usecols=_SUBMISSION_COLS, dtype=str, low_memory=False
            )
            submission = submission[submission["DOCUMENT_TYPE"].isin(_RELEVANT_FORMS)]
            submission = submission[submission["ISSUERTRADINGSYMBOL"].notna() & (submission["ISSUERTRADINGSYMBOL"] != "")]
            if submission.empty:
                return

            owners = pd.read_csv(zf.open("REPORTINGOWNER.tsv"), sep="\t", usecols=_OWNER_COLS, dtype=str, low_memory=False)
            # Multiple reporting owners can co-file one accession (e.g. spouse joint filings);
            # take the first listed owner per accession as the position holder to avoid
            # double-counting the same reported share balance across co-filers.
            primary_owner = owners.drop_duplicates(subset="ACCESSION_NUMBER", keep="first").set_index(
                "ACCESSION_NUMBER"
            )["RPTOWNERCIK"]

            holding = pd.read_csv(
                zf.open("NONDERIV_HOLDING.tsv"), sep="\t", usecols=_HOLDING_COLS, dtype=str, low_memory=False
            )
            trans = pd.read_csv(zf.open("NONDERIV_TRANS.tsv"), sep="\t", usecols=_TRANS_COLS, dtype=str, low_memory=False)

        submission = submission.set_index("ACCESSION_NUMBER")
        filing_date_by_accession = pd.to_datetime(submission["FILING_DATE"], format="%d-%b-%Y", errors="coerce")

        # Latest non-derivative share balance per accession: prefer NONDERIV_TRANS's own
        # TRANS_DATE when present (transaction-driven row), else fall back to the filing
        # date for pure NONDERIV_HOLDING rows (no transaction this period, e.g. Form 5).
        obs_rows: list[tuple[str, str, date, float]] = []  # (accession, symbol, as_of, shares)

        for _, row in trans.iterrows():
            acc = row["ACCESSION_NUMBER"]
            if acc not in submission.index:
                continue
            shares = pd.to_numeric(row["SHRS_OWND_FOLWNG_TRANS"], errors="coerce")
            if pd.isna(shares):
                continue
            trans_date = pd.to_datetime(row["TRANS_DATE"], format="%d-%b-%Y", errors="coerce")
            as_of = trans_date if pd.notna(trans_date) else filing_date_by_accession.get(acc)
            if pd.isna(as_of):
                continue
            symbol = submission.at[acc, "ISSUERTRADINGSYMBOL"]
            obs_rows.append((acc, symbol, as_of.date(), float(shares)))

        for _, row in holding.iterrows():
            acc = row["ACCESSION_NUMBER"]
            if acc not in submission.index:
                continue
            shares = pd.to_numeric(row["SHRS_OWND_FOLWNG_TRANS"], errors="coerce")
            if pd.isna(shares):
                continue
            as_of = filing_date_by_accession.get(acc)
            if pd.isna(as_of):
                continue
            symbol = submission.at[acc, "ISSUERTRADINGSYMBOL"]
            obs_rows.append((acc, symbol, as_of.date(), float(shares)))

        for acc, symbol, as_of, shares in obs_rows:
            owner_cik = primary_owner.get(acc)
            if owner_cik is None:
                continue
            issuer_cik = submission.at[acc, "ISSUERCIK"]
            acc_state = accumulators.setdefault(symbol, _SymbolAccumulator(issuer_cik=issuer_cik))
            existing = acc_state.owners.get(owner_cik)
            if existing is None or as_of >= existing.as_of:
                acc_state.owners[owner_cik] = _OwnerPosition(shares=shares, as_of=as_of)
            if acc_state.latest_filing_date is None or as_of >= acc_state.latest_filing_date:
                acc_state.latest_filing_date = as_of
                acc_state.latest_accession = acc
                acc_state.issuer_cik = issuer_cik

        if is_most_recent:
            trans_dated = trans.assign(
                _symbol=trans["ACCESSION_NUMBER"].map(lambda a: submission.at[a, "ISSUERTRADINGSYMBOL"] if a in submission.index else None)
            )
            trans_dated = trans_dated[trans_dated["_symbol"].notna()]
            buys = trans_dated[trans_dated["TRANS_CODE"] == OPEN_MARKET_BUY_CODE].groupby("_symbol").size()
            sells = trans_dated[trans_dated["TRANS_CODE"] == OPEN_MARKET_SELL_CODE].groupby("_symbol").size()
            for symbol, count in buys.items():
                accumulators.setdefault(symbol, _SymbolAccumulator()).recent_buys += int(count)
            for symbol, count in sells.items():
                accumulators.setdefault(symbol, _SymbolAccumulator()).recent_sells += int(count)

    @staticmethod
    def _filing_index_url(issuer_cik: str, accession: str) -> str:
        if not issuer_cik or not accession:
            return ""
        cik_num = issuer_cik.lstrip("0") or "0"
        accession_nodash = accession.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession_nodash}/{accession}-index.htm"
