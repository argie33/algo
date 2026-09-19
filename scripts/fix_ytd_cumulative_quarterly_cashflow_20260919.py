"""One-off remediation for the 2026-09-19 "YTD cumulative mistaken for standalone quarter"
bug (see memory: ytd_cumulative_mistaken_for_quarter_systemic_20260919). Confirmed across 5
symbols (ABT, CASS, ACGL, CLPR, partial ACI) so far, all by hand.

For each candidate (symbol, fiscal_year, fiscal_quarter) with 3+ simultaneously-divergent
quarterly_cash_flow fields (the detection signature), tries each of a small set of known SEC
concept names per our field, fetches the filer's REAL company facts, and computes the
standalone quarter value as (this-quarter-end YTD fact) - (prior-quarter-end YTD fact) using
the SAME fiscal-year start date. Only WRITES a correction when the computed value matches
yfinance's own flagged value within 1% tolerance - this is the safety gate that makes this
different from a blind pattern-apply: a filer whose numbers don't reconcile this way (like
ACI's remaining fields, or CGC's currency-converted figures) is silently skipped, not forced.

Always marks the row via the sanctioned xbrl_line_item_review.py-equivalent DB write (same
review_status write path) - never bypasses per-row review, just automates the verification
labor that was previously done by hand for each row.
"""

import argparse
import os
from typing import Any

import psycopg2
from dotenv import load_dotenv

from utils.external.sec_edgar_client import SecEdgarClient

load_dotenv(".env.local")

# our_field -> candidate raw XBRL concept names, tried in order, first one present wins.
FIELD_CONCEPTS: dict[str, list[str]] = {
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "dividends_paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "common_stock_repurchased": ["PaymentsForRepurchaseOfCommonStock"],
    "financing_cash_flow": ["NetCashProvidedByUsedInFinancingActivities"],
    "investing_cash_flow": ["NetCashProvidedByUsedInInvestingActivities"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "stock_based_compensation": ["ShareBasedCompensation"],
}


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def _facts_for_concept(facts: dict[str, Any], concept: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = (
        facts.get("facts", {}).get("us-gaap", {}).get(concept, {}).get("units", {}).get("USD", [])
    )
    return result


def _find_ytd_value(entries: list[dict[str, Any]], fy_start: str, end_date: str) -> float | None:
    for e in entries:
        if e.get("start") == fy_start and e.get("end") == end_date:
            return float(e["val"])
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--apply", action="store_true", help="Write corrections; default is dry-run")
    parser.add_argument(
        "--min-fields",
        type=int,
        default=3,
        help="Minimum simultaneously-divergent quarterly_cash_flow fields to consider a symbol/quarter a candidate",
    )
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT symbol, fiscal_year, fiscal_quarter
        FROM xbrl_yfinance_line_item_report
        WHERE divergent AND review_status = 'unreviewed' AND our_table = 'quarterly_cash_flow'
        GROUP BY symbol, fiscal_year, fiscal_quarter
        HAVING count(*) >= %s
        ORDER BY count(*) DESC
        LIMIT %s
        """,
        (args.min_fields, args.limit),
    )
    candidates = cur.fetchall()
    print(f"Checking {len(candidates)} candidate (symbol, fiscal_year, fiscal_quarter) group(s)...")

    client = SecEdgarClient()
    total_fixed = 0
    for symbol, fy, fq in candidates:
        if fq == 0:
            continue  # annual rows can't have this bug
        cur.execute(
            """
            SELECT our_field, our_value, yfinance_value FROM xbrl_yfinance_line_item_report
            WHERE symbol=%s AND fiscal_year=%s AND fiscal_quarter=%s AND our_table='quarterly_cash_flow'
              AND divergent AND review_status='unreviewed'
            """,
            (symbol, fy, fq),
        )
        rows = cur.fetchall()
        try:
            cik = client.symbol_to_cik(symbol)
            facts = client.get_company_facts(cik)
        except Exception as e:
            print(f"  {symbol}: SKIP (fetch error: {e})")
            continue

        # Determine this row's real period_end and the fiscal year's start date, and the
        # prior quarter's end date, from quarterly_income_statement's period_end column
        # (quarterly_cash_flow itself lacks one) for the SAME symbol/fiscal_year/quarter.
        cur.execute(
            "SELECT period_end FROM quarterly_income_statement WHERE symbol=%s AND fiscal_year=%s AND fiscal_quarter=%s",
            (symbol, fy, fq),
        )
        pe_row = cur.fetchone()
        if not pe_row or pe_row[0] is None:
            print(f"  {symbol} FY{fy}Q{fq}: SKIP (no period_end on record)")
            continue
        end_date = pe_row[0].isoformat()
        cur.execute(
            "SELECT period_end FROM quarterly_income_statement WHERE symbol=%s AND fiscal_year=%s AND fiscal_quarter=%s",
            (symbol, fy, fq - 1),
        )
        prior_row = cur.fetchone()
        if not prior_row or prior_row[0] is None:
            print(f"  {symbol} FY{fy}Q{fq}: SKIP (no prior-quarter period_end on record)")
            continue
        prior_end_date = prior_row[0].isoformat()
        # Fiscal year start: derive from the prior quarter's own start by using the same
        # calendar year as fq=1's period start would imply - simplest safe proxy is
        # (fq1_end - ~90 days) rounded to a plausible fiscal-year-start; instead, just try
        # both the calendar-year start and a same-year proxy against the actual facts (the
        # exact match check below rejects any wrong guess).
        fy_year = int(end_date[:4])
        candidate_starts = [f"{fy_year}-01-01", f"{int(end_date[:4]) - 1}-01-01"]

        for field, our_val, yf_val in rows:
            concepts = FIELD_CONCEPTS.get(field)
            if not concepts:
                continue
            fixed = False
            for concept in concepts:
                entries = _facts_for_concept(facts, concept)
                if not entries:
                    continue
                for fy_start in candidate_starts:
                    this_ytd = _find_ytd_value(entries, fy_start, end_date)
                    prior_ytd = _find_ytd_value(entries, fy_start, prior_end_date)
                    if this_ytd is None or prior_ytd is None:
                        continue
                    standalone = this_ytd - prior_ytd
                    if abs(standalone - float(yf_val)) <= max(1.0, abs(float(yf_val)) * 0.01):
                        print(
                            f"  MATCH {symbol} {field} FY{fy}Q{fq}: {this_ytd:,.0f} - {prior_ytd:,.0f} = "
                            f"{standalone:,.0f} (yfinance {float(yf_val):,.0f}, ours was {float(our_val):,.0f})"
                        )
                        if args.apply:
                            cur.execute(
                                f"UPDATE quarterly_cash_flow SET {field}=%s WHERE symbol=%s AND fiscal_year=%s AND fiscal_quarter=%s",
                                (standalone, symbol, fy, fq),
                            )
                            cur.execute(
                                """
                                UPDATE xbrl_yfinance_line_item_report
                                SET review_status='reviewed_fixed', review_note=%s, reviewed_at=now(), reviewed_by='automated_ytd_fix_20260919'
                                WHERE symbol=%s AND fiscal_year=%s AND fiscal_quarter=%s AND our_field=%s AND our_table='quarterly_cash_flow'
                                """,
                                (
                                    "Automated fix: YTD-cumulative-mistaken-for-standalone-quarter bug "
                                    "(see ytd_cumulative_mistaken_for_quarter_systemic_20260919 memory note). "
                                    f"Corrected via {concept} YTD subtraction, verified within 1% of yfinance.",
                                    symbol,
                                    fy,
                                    fq,
                                    field,
                                ),
                            )
                            conn.commit()
                        fixed = True
                        total_fixed += 1
                        break
                if fixed:
                    break
            if not fixed:
                print(f"  no match {symbol} {field} FY{fy}Q{fq} (ours={our_val}, yfinance={yf_val})")

    print(f"\n{total_fixed} row(s) {'fixed' if args.apply else 'would be fixed (dry-run)'}")


if __name__ == "__main__":
    main()
