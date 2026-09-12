#!/usr/bin/env python3
"""Segment-sum-to-consolidated-revenue reconciliation, using SEC's free "Financial Statement
and Notes Data Sets" bulk download (NOT the plain "Financial Statement Data Sets" that
scripts/xbrl_dera_bulk_scan.py already uses) - the "notes" variant adds dim.tsv, which records
the real XBRL axis+member for every dimensioned fact (e.g. "BusinessSegments=ReportableSegment;"
vs "ProductOrService=Widgets;Geography=US;"), keyed by a dimhash that num.tsv's `dimh` column
joins against.

Added 2026-09-12 (goal: "SEC/XBRL missing data + resources to tap into" session). This is the
exact capability algo/monitoring/data_patrol/checks/tie_out.py's module docstring says is
missing and is the documented reason the segment-sum-to-consolidated check was investigated and
REJECTED twice (2026-09-06/07): SEC's per-symbol companyfacts API (what every extractor in this
repo reads) flattens all dimensional facts for a concept into one list with no axis/member info,
so a filer's true ASC 280 reportable-segment facts (StatementBusinessSegmentsAxis) and its ASC
606 revenue-disaggregation-by-product/geography facts (ProductOrServiceAxis / GeographyAxis)
can't be told apart - summing every segment-shaped row double/multi-counts the real revenue
several times over (EA's FY2026 10-K, a live example in tie_out.py's docstring, sums to
~2-14x the real consolidated total this way). The "notes" bulk dataset's dim.tsv fixes exactly
this: it gives back the real per-fact axis=member string, so this script keeps only facts
dimensioned SOLELY by a `*Segments`/`*SegmentAxis`-shaped axis (true business-segment facts) and
discards everything tagged under any additional or different axis (product/geography/customer
disaggregations, which is what over-counted before).

Live-verified 2026-09-12 against the 2026-08 notes.zip (~2.4GB uncompressed, ~4,700 distinct
filers with a "pure single-axis BusinessSegments" fact that month): summing ONLY those pure
BusinessSegments-axis Revenues/RevenueFromContractWithCustomerExcludingAssessedTax facts and
comparing to the same accession's non-dimensional (dimh=0x00000000) consolidated total, 56/84
(67%) comparable symbol/periods tied within 10% - categorically different from the fully-
flattened companyfacts approach's live-measured p90=55%/p95=~100%/p99=154% relative error
(see tie_out.py's own docstring for that number and where it came from). The remaining ~33%
still diverging is expected and NOT further investigated here (candidates: multi-axis segment
tables SEC's own presentation doesn't cleanly separate, corporate/eliminations lines not
tagged under any segment member, genuine segment reclassifications between periods) - this
script's own tolerance-based flagging is exactly the mechanism to separate those from real bugs
over time, the same posture as xbrl_yfinance_crosscheck.py/xbrl_calculation_linkbase_check.py.

Deliberately its own standalone script, not wired into tie_out.py or any loader: this makes a
one-time ~300MB monthly bulk download (cached under %TEMP%/algo-fsnds-cache, same convention as
xbrl_dera_bulk_scan.py's quarterly cache) and a full linear scan of num.tsv (1GB+ uncompressed)
- expensive enough to run periodically (e.g. monthly, matching the dataset's own publish cadence)
rather than per-DataPatrol-run. Findings flow into the same data_patrol_log / data_patrol_review
triage queue as every other periodic XBRL check here.

Usage:
    python scripts/xbrl_segment_sum_reconciliation.py                    # latest available month, write findings
    python scripts/xbrl_segment_sum_reconciliation.py --month 2026_08
    python scripts/xbrl_segment_sum_reconciliation.py --dry-run          # print, don't write to data_patrol_log
    python scripts/xbrl_segment_sum_reconciliation.py --symbols GE,MRK
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_FSNDS_CACHE_DIR = Path(tempfile.gettempdir()) / "algo-fsnds-cache"
_FSNDS_BASE_URL = "https://www.sec.gov/files/dera/data/financial-statement-notes-data-sets"
_USER_AGENT = "algo-research contact@example.com"

_REVENUE_TAGS = frozenset({"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"})
_TOLERANCE_RATIO_LOW = 0.90
_TOLERANCE_RATIO_HIGH = 1.10
_MIN_VALUE_FLOOR = 1_000_000.0
_MAX_EXAMPLES = 20


def _current_month() -> str:
    today = date.today()
    # SEC posts month M's data during month M+1 - the prior calendar month is always
    # published; the current one usually isn't yet.
    year, month = today.year, today.month - 1
    if month == 0:
        year, month = year - 1, 12
    return f"{year}_{month:02d}"


def _month_zip_path(month: str) -> Path:
    return _FSNDS_CACHE_DIR / f"{month}_notes.zip"


def download_month(month: str) -> Path | None:
    """Downloads (if not already cached) the notes-dataset zip for one month, e.g. "2026_08".
    Returns None (not an error) for a month SEC hasn't published yet.

    Downloads to a `.part` sibling and renames on success (atomic on the same filesystem) -
    without this, a run killed or a connection dropped mid-download left a truncated file at
    the real cache path, which the `dest.exists() and dest.stat().st_size > 0` cache-hit check
    on the NEXT run would treat as a good cache entry, handing zipfile a corrupt archive with
    no clear signal why (BadZipFile deep inside scan_month, not "the cache is bad, delete and
    retry")."""
    _FSNDS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = _month_zip_path(month)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    partial = dest.with_suffix(dest.suffix + ".part")
    url = f"{_FSNDS_BASE_URL}/{month}_notes.zip"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(partial, "wb") as out:
            while chunk := resp.read(1024 * 1024):
                out.write(chunk)
    except urllib.error.HTTPError as e:
        partial.unlink(missing_ok=True)
        if e.code == 404:
            return None
        raise
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.rename(dest)
    return dest


def _is_pure_segment_axis(segments: str) -> bool:
    """True if `segments` (dim.tsv's semicolon-joined "Axis=Member;" string) is dimensioned by
    exactly one axis and that axis is a business-segment axis (its XBRL local-name is
    "BusinessSegments" or ends in "Segments"/"SegmentAxis" - covers the common
    StatementBusinessSegmentsAxis/BusinessSegments local-name variants seen live). Any
    additional axis (ProductOrService, Geography, ConsolidationItems, etc.) means this is a
    disaggregation-by-something-else fact, not a true reportable-segment total - excluded to
    avoid the double-counting this check was rejected over before (see module docstring)."""
    if segments.count("=") != 1:
        return False
    axis = segments.split("=", 1)[0]
    return axis == "BusinessSegments" or axis.endswith(("Segments", "SegmentAxis"))


def _build_segment_dim_set(zf: zipfile.ZipFile) -> set[str]:
    result: set[str] = set()
    with zf.open("dim.tsv") as f:
        f.readline()
        for line in f:
            parts = line.decode("utf-8", "replace").rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            if _is_pure_segment_axis(parts[1]):
                result.add(parts[0])
    return result


def _build_cik_to_adsh(zf: zipfile.ZipFile, target_ciks: set[str]) -> dict[str, list[str]]:
    """adsh's belonging to one of target_ciks (10-K/10-K-A/20-F annual filings only)."""
    out: dict[str, list[str]] = defaultdict(list)
    with zf.open("sub.tsv") as f:
        header = f.readline().decode().rstrip("\n").split("\t")
        idx = {c: i for i, c in enumerate(header)}
        for line in f:
            parts = line.decode("utf-8", "replace").rstrip("\n").split("\t")
            if len(parts) < len(header):
                continue
            cik = parts[idx["cik"]].lstrip("0") or "0"
            if cik not in target_ciks:
                continue
            form = parts[idx["form"]]
            if not form.startswith(("10-K", "20-F")):
                continue
            out[cik].append(parts[idx["adsh"]])
    return out


def scan_month(month: str, target_ciks: set[str] | None) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Returns (adsh -> list of {axis_member, segment_sum, consolidated, ratio, ddate} findings
    outside tolerance, adsh -> cik for every accession considered). `target_ciks` (zero-padding
    stripped) restricts the scan to a symbol batch; None scans every filer in the month's data -
    the returned adsh->cik map covers exactly the accessions scanned either way, so callers never
    need a second pass over sub.tsv just to label findings by symbol afterward."""
    path = download_month(month)
    if path is None:
        raise RuntimeError(f"SEC has not published a Financial Statement and Notes Data Set for {month} yet")

    with zipfile.ZipFile(path) as zf:
        segment_dims = _build_segment_dim_set(zf)
        logger.info(f"[SEGMENT_SUM] {len(segment_dims)} pure single-axis business-segment dim(s) this month")

        adsh_filter: set[str] | None = None
        adsh_to_cik: dict[str, str] = {}
        if target_ciks is not None:
            cik_to_adsh = _build_cik_to_adsh(zf, target_ciks)
            adsh_filter = {a for accns in cik_to_adsh.values() for a in accns}
            adsh_to_cik = {a: cik for cik, accns in cik_to_adsh.items() for a in accns}
            logger.info(f"[SEGMENT_SUM] restricting to {len(adsh_filter)} accession(s) for {len(target_ciks)} CIK(s)")
        else:
            adsh_to_cik = _build_all_adsh_to_cik(zf)

        # Keyed by dimh (not appended to a list): num.tsv is fact-INSTANCE level, not
        # fact-VALUE level - the same (adsh, ddate, dimh) fact commonly appears multiple times
        # (distinguished only by `iprx`, an occurrence-in-rendering index) when a filer's own
        # HTML rendering repeats the same disclosed number in more than one table (e.g. a
        # segment total shown once in the segment note and again in an MD&A table). These are
        # the SAME underlying fact re-referenced, not additional amounts - live-confirmed via
        # AIT's 0000109563-26-000033 filing, where every duplicated dimh carried an identical
        # value under iprx=0/1/2. Summing the raw rows double- or triple-counted every segment
        # this way (every early live check produced a suspicious, suspiciously-exact ratio of
        # 2.0 across unrelated filers - the tell that this was a systematic parsing bug, not
        # real segment presentation weirdness). Deduping to one value per (adsh, ddate, dimh)
        # fixes it.
        seg_rev: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        consol_rev: dict[tuple[str, str], float] = {}
        with zf.open("num.tsv") as f:
            header = f.readline().decode().rstrip("\n").split("\t")
            idx = {c: i for i, c in enumerate(header)}
            for line in f:
                parts = line.decode("utf-8", "replace").rstrip("\n").split("\t")
                if len(parts) < len(header):
                    continue
                if parts[idx["tag"]] not in _REVENUE_TAGS or parts[idx["qtrs"]] != "4":
                    continue
                adsh = parts[idx["adsh"]]
                if adsh_filter is not None and adsh not in adsh_filter:
                    continue
                try:
                    val = float(parts[idx["value"]])
                except ValueError:
                    continue
                dimh = parts[idx["dimh"]]
                key = (adsh, parts[idx["ddate"]])
                if dimh in segment_dims:
                    seg_rev[key][dimh] = val
                elif dimh == "0x00000000":
                    consol_rev[key] = val

    findings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key, segs_by_dim in seg_rev.items():
        adsh, ddate = key
        segs = list(segs_by_dim.items())
        if len(segs) < 2 or key not in consol_rev:
            continue
        total = sum(v for _, v in segs)
        consol = consol_rev[key]
        if max(abs(total), abs(consol)) < _MIN_VALUE_FLOOR or consol == 0:
            continue
        ratio = total / consol
        if _TOLERANCE_RATIO_LOW <= ratio <= _TOLERANCE_RATIO_HIGH:
            continue
        findings[adsh].append(
            {
                "fiscal_period_end": ddate,
                "segment_count": len(segs),
                "segment_sum": total,
                "consolidated_revenue": consol,
                "ratio": round(ratio, 4),
            }
        )
    return findings, adsh_to_cik


def _build_all_adsh_to_cik(zf: zipfile.ZipFile) -> dict[str, str]:
    """Used only when target_ciks is None (full-universe scan) - every accession's cik, no
    form-type/cik filtering (unlike _build_cik_to_adsh, which is target-batch-only)."""
    out: dict[str, str] = {}
    with zf.open("sub.tsv") as f:
        header = f.readline().decode().rstrip("\n").split("\t")
        idx = {c: i for i, c in enumerate(header)}
        for line in f:
            parts = line.decode("utf-8", "replace").rstrip("\n").split("\t")
            if len(parts) < len(header):
                continue
            out[parts[idx["adsh"]]] = parts[idx["cik"]].lstrip("0") or "0"
    return out


def run(month: str, symbols_override: list[str] | None, dry_run: bool) -> dict[str, Any]:
    from psycopg2.extras import DictCursor

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.db.connection import get_db_connection
    from utils.external.sec_edgar_client import SecEdgarClient
    from utils.loaders.helpers import get_active_symbols

    client = SecEdgarClient()
    ticker_to_cik = client.get_full_ticker_cik_mapping()

    symbols = symbols_override or get_active_symbols(exclude_etfs=True)
    target_ciks = {ticker_to_cik[s].lstrip("0") or "0" for s in symbols if s in ticker_to_cik}
    cik_to_symbol = {ticker_to_cik[s].lstrip("0") or "0": s for s in symbols if s in ticker_to_cik}
    logger.info(f"[SEGMENT_SUM] {len(target_ciks)}/{len(symbols)} symbol(s) resolved to a CIK")

    findings_by_adsh, adsh_to_cik = scan_month(month, target_ciks)
    checked = len(adsh_to_cik)

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor(cursor_factory=DictCursor)

    examples: list[dict[str, Any]] = []
    for adsh, rows in findings_by_adsh.items():
        cik = adsh_to_cik.get(adsh, "")
        symbol = cik_to_symbol.get(cik, f"cik:{cik}")
        for row in rows:
            examples.append({"symbol": symbol, "accession": adsh, **row})

    results: list[CheckResult] = []
    if examples:
        results.append(
            CheckResult(
                "xbrl_segment_sum_reconciliation",
                "warn",
                "annual_income_statement",
                f"{len(examples)} symbol/period(s) (of {checked} accession(s) checked) where "
                f"business-segment revenue facts (pure single-axis, non-disaggregated) sum "
                f"outside {_TOLERANCE_RATIO_LOW:.0%}-{_TOLERANCE_RATIO_HIGH:.0%} of the filing's "
                "own consolidated revenue - review queue, not a confirmed bug: a filer's own "
                "segment presentation can genuinely exclude corporate/eliminations lines or "
                "mix in a differently-dimensioned disaggregation this axis filter didn't catch.",
                {"checked": checked, "flagged": len(examples), "examples": examples[:_MAX_EXAMPLES]},
            )
        )
    elif checked == 0:
        # Distinct from "checked N filings, all tied out clean" - a zero-accession restriction
        # (e.g. the requested symbols filed nothing in this month's bulk snapshot) means nothing
        # was actually compared, and reporting it identically to a real clean pass would be the
        # same silent-success-on-failure shape this repo has fixed elsewhere (see
        # xbrl_dqc_arelle_check.py's DqcRunError / memory
        # check_silent_fallbacks_worktree_skip_path_defeats_check_20260911).
        results.append(
            CheckResult(
                "xbrl_segment_sum_reconciliation",
                "info",
                "annual_income_statement",
                f"0 accession(s) matched for {month} - nothing was actually checked this run "
                "(the requested symbol(s)/universe filed nothing in this month's bulk snapshot), "
                "not a confirmed-clean result",
            )
        )
    else:
        results.append(
            CheckResult(
                "xbrl_segment_sum_reconciliation",
                "info",
                "annual_income_statement",
                f"no segment-sum-vs-consolidated-revenue divergence found across {checked} "
                f"checked accession(s) for {month}",
            )
        )

    if dry_run:
        for r in results:
            logger.info(f"[DRY-RUN] [{r.severity.upper()}] {r.check_name}: {r.message}")
            if r.severity == "warn":
                for ex in examples[:_MAX_EXAMPLES]:
                    logger.info(f"[DRY-RUN]   {ex}")
    else:
        run_id = uuid.uuid4().hex
        patrol_logger = PatrolLogger(run_id)
        patrol_logger.log_results(cur, results)
        conn.commit()
        logger.info(f"[SEGMENT_SUM] Logged {len(results)} result(s) to data_patrol_log (run_id={run_id})")

    cur.close()
    conn.close()
    return {"month": month, "checked": checked, "flagged": len(examples), "results": [r.to_dict() for r in results]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--month", default=_current_month(), help="YYYY_MM month to scan (default: last full month)")
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list, overrides full active universe")
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write to data_patrol_log")
    args = parser.parse_args()

    symbols_override = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    started = time.monotonic()
    summary = run(month=args.month, symbols_override=symbols_override, dry_run=args.dry_run)
    elapsed = time.monotonic() - started
    logger.info(
        f"[SEGMENT_SUM] Done in {elapsed:.1f}s - month={summary['month']} "
        f"checked={summary['checked']} flagged={summary['flagged']}"
    )


if __name__ == "__main__":
    main()
