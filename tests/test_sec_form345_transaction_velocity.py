#!/usr/bin/env python3
"""Regression test: insider transaction volume must come from TRANS_SHARES, not
SHRS_OWND_FOLWNG_TRANS.

TRANS_SHARES is the actual quantity moved in a single Form 4 transaction.
SHRS_OWND_FOLWNG_TRANS is the insider's cumulative running-total holding after the
transaction (used by sec_form345_bulk.py for current-holdings, a different metric).
Confusing the two previously made total_buy_shares_30d/total_sell_shares_90d in the
insider_transaction_velocity table report the insider's total post-trade position
instead of the shares actually bought/sold - wildly wrong for a large, long-tenured
holder making a small trade.
"""

import io
import zipfile
from datetime import date

from utils.external.sec_form345_transaction_velocity import Form345TransactionVelocityAggregator

SUBMISSION_TSV = (
    "ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERTRADINGSYMBOL\n"
    "0001-24-000001\t01-JUL-2024\t4\t0000123456\tTEST\n"
)
REPORTINGOWNER_TSV = (
    "ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tISCLERK\tISDIRECTOR\tISOFFICER\n"
    "0001-24-000001\t0000000111\tJohn Doe\tFALSE\tTRUE\tFALSE\n"
)
# TRANS_SHARES (100) deliberately differs from SHRS_OWND_FOLWNG_TRANS (10000000) so a
# regression that reads the wrong column is unmistakable.
NONDERIV_TRANS_TSV = (
    "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICE\tSHRS_OWND_FOLWNG_TRANS\n"
    "0001-24-000001\t01-JUL-2024\tP\t100\t10.50\t10000000\n"
)


def _make_quarter_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SUBMISSION.tsv", SUBMISSION_TSV)
        zf.writestr("REPORTINGOWNER.tsv", REPORTINGOWNER_TSV)
        zf.writestr("NONDERIV_TRANS.tsv", NONDERIV_TRANS_TSV)
    return buf.getvalue()


def test_transaction_volume_uses_trans_shares_not_running_total() -> None:
    aggregator = Form345TransactionVelocityAggregator(lookback_quarters=1)
    zip_bytes = _make_quarter_zip()
    aggregator._quarters_attempted = 1
    aggregator._download_quarter = lambda quarter: zip_bytes  # type: ignore[method-assign]

    metrics = aggregator.get_velocity_metrics("TEST", measurement_date=date(2024, 7, 15))

    assert metrics.data_unavailable is False
    assert metrics.buy_transactions_30d == 1
    # Must be the 100-share transaction, never the 10,000,000-share running total.
    assert metrics.total_buy_shares_30d == 100
    assert metrics.total_sell_shares_30d == 0
