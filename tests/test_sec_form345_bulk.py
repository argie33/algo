#!/usr/bin/env python3
"""Regression tests for sec_form345_bulk.py's insider-ownership aggregation.

This is the most complex fallback/aggregation chain among the SEC bulk-data loaders
(per-owner latest-position dedup within a quarter, joint-filer dedup, cross-quarter
position carry-forward) and had zero test coverage before this session despite
load_insider_holdings_sec.py feeding insider_ownership_pct directly into signal
inputs. Each test targets one documented methodology claim in the module docstring
so a future edit that silently breaks the aggregation logic is caught immediately.
"""

import io
import zipfile
from datetime import date

from utils.external.sec_form345_bulk import Form345BulkAggregator, _recent_quarters


def _zip_from(submission: str, owner: str, holding: str = "", trans: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SUBMISSION.tsv", submission)
        zf.writestr("REPORTINGOWNER.tsv", owner)
        zf.writestr(
            "NONDERIV_HOLDING.tsv",
            holding or "ACCESSION_NUMBER\tSHRS_OWND_FOLWNG_TRANS\n",
        )
        zf.writestr(
            "NONDERIV_TRANS.tsv",
            trans or "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tSHRS_OWND_FOLWNG_TRANS\n",
        )
    return buf.getvalue()


def _aggregator_single_quarter(zip_bytes: bytes) -> Form345BulkAggregator:
    """Aggregator that returns the same quarter content regardless of which quarter
    tag is requested - the tests only care about within-quarter aggregation."""
    agg = Form345BulkAggregator(lookback_quarters=1)
    agg._download_quarter = lambda quarter: zip_bytes  # type: ignore[method-assign]
    return agg


def _aggregator_multi_quarter(zips_newest_first: list) -> Form345BulkAggregator:
    """Aggregator whose N most recent real quarter tags map, in order, to the given
    zip contents (index 0 = newest quarter)."""
    today = date.today()
    tags = _recent_quarters(len(zips_newest_first), today)
    zip_by_quarter = dict(zip(tags, zips_newest_first, strict=True))
    agg = Form345BulkAggregator(lookback_quarters=len(zips_newest_first))
    agg._download_quarter = lambda quarter: zip_by_quarter.get(quarter)  # type: ignore[method-assign]
    return agg


def test_two_transactions_same_owner_keeps_only_latest_position() -> None:
    """Per docstring: 'keep only the MOST RECENT holding observation ... the latest
    report IS the insider's current position, not an increment to sum.' An owner who
    filed twice in the quarter must contribute one position (the newer), not both
    summed."""
    submission = (
        "ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERTRADINGSYMBOL\n"
        "0001-24-000001\t01-JUL-2024\t4\t0000123456\tTEST\n"
        "0001-24-000002\t15-AUG-2024\t4\t0000123456\tTEST\n"
    )
    owner = "ACCESSION_NUMBER\tRPTOWNERCIK\n0001-24-000001\t0000000111\n0001-24-000002\t0000000111\n"
    trans = (
        "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tSHRS_OWND_FOLWNG_TRANS\n"
        "0001-24-000001\t01-JUL-2024\tP\t5000\n"
        "0001-24-000002\t15-AUG-2024\tS\t3000\n"
    )
    zip_bytes = _zip_from(submission, owner, trans=trans)
    agg = _aggregator_single_quarter(zip_bytes)

    summary = agg.get_symbol_summary("TEST")

    assert summary is not None
    assert summary.number_of_insiders == 1
    # Must be the later (3000) position, never 5000 + 3000 = 8000.
    assert summary.total_shares == 3000


def test_joint_filers_on_one_accession_counted_once() -> None:
    """Per docstring: 'take the first listed owner per accession ... to avoid
    double-counting the same reported share balance across co-filers.'"""
    submission = "ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERTRADINGSYMBOL\n0001-24-000001\t01-JUL-2024\t4\t0000123456\tTEST\n"
    owner = "ACCESSION_NUMBER\tRPTOWNERCIK\n0001-24-000001\t0000000111\n0001-24-000001\t0000000222\n"
    trans = "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tSHRS_OWND_FOLWNG_TRANS\n0001-24-000001\t01-JUL-2024\tP\t5000\n"
    zip_bytes = _zip_from(submission, owner, trans=trans)
    agg = _aggregator_single_quarter(zip_bytes)

    summary = agg.get_symbol_summary("TEST")

    assert summary is not None
    assert summary.number_of_insiders == 1
    assert summary.total_shares == 5000


def test_older_quarter_does_not_overwrite_newer_owner_position() -> None:
    """Per docstring, positions are carried forward by actual as_of date, not by
    processing order - an owner's older, since-superseded holding from an earlier
    quarter must not clobber their current position."""
    sub_q2 = "ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERTRADINGSYMBOL\n0001-24-000001\t01-APR-2024\t4\t0000123456\tTEST\n"
    own_q2 = "ACCESSION_NUMBER\tRPTOWNERCIK\n0001-24-000001\t0000000111\n"
    trans_q2 = (
        "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tSHRS_OWND_FOLWNG_TRANS\n0001-24-000001\t01-APR-2024\tP\t9000\n"
    )
    zip_q2 = _zip_from(sub_q2, own_q2, trans=trans_q2)

    sub_q3 = "ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERTRADINGSYMBOL\n0001-24-000002\t01-JUL-2024\t4\t0000123456\tTEST\n"
    own_q3 = "ACCESSION_NUMBER\tRPTOWNERCIK\n0001-24-000002\t0000000111\n"
    trans_q3 = (
        "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tSHRS_OWND_FOLWNG_TRANS\n0001-24-000002\t01-JUL-2024\tS\t4000\n"
    )
    zip_q3 = _zip_from(sub_q3, own_q3, trans=trans_q3)

    agg = _aggregator_multi_quarter([zip_q3, zip_q2])

    summary = agg.get_symbol_summary("TEST")

    assert summary is not None
    assert summary.number_of_insiders == 1
    # Current position is the Q3 sale-driven balance (4000), not the stale Q2 value.
    assert summary.total_shares == 4000


def test_recent_buys_sells_only_open_market_codes_in_latest_quarter() -> None:
    """Per docstring: recent_buys/recent_sells count only TRANS_CODE 'P'/'S' within
    the single most-recently-published quarter - not option exercises/gifts, and not
    older quarters' activity."""
    submission = (
        "ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERTRADINGSYMBOL\n"
        "0001-24-000001\t01-JUL-2024\t4\t0000123456\tTEST\n"
        "0001-24-000002\t02-JUL-2024\t4\t0000123456\tTEST\n"
        "0001-24-000003\t03-JUL-2024\t4\t0000123456\tTEST\n"
    )
    owner = (
        "ACCESSION_NUMBER\tRPTOWNERCIK\n"
        "0001-24-000001\t0000000111\n"
        "0001-24-000002\t0000000222\n"
        "0001-24-000003\t0000000333\n"
    )
    trans = (
        "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tSHRS_OWND_FOLWNG_TRANS\n"
        "0001-24-000001\t01-JUL-2024\tP\t1000\n"
        "0001-24-000002\t02-JUL-2024\tS\t2000\n"
        "0001-24-000003\t03-JUL-2024\tA\t3000\n"
    )
    zip_bytes = _zip_from(submission, owner, trans=trans)
    agg = _aggregator_single_quarter(zip_bytes)

    summary = agg.get_symbol_summary("TEST")

    assert summary is not None
    assert summary.recent_buys == 1
    assert summary.recent_sells == 1


def test_symbol_with_no_filings_returns_none() -> None:
    agg = _aggregator_single_quarter(None)
    assert agg.get_symbol_summary("NOPE") is None
