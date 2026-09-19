"""Remediation for the "YTD cumulative mistaken for standalone quarter" bug (see memory:
ytd_cumulative_mistaken_for_quarter_systemic_20260919), applied to quarterly_income_statement.

Same mechanism and same safety gate as
scripts/fix_ytd_cumulative_quarterly_cashflow_20260919.py (that tool's own docstring has the
full background) - income-statement duration/flow concepts (revenue, net_income,
operating_income, ...) are just as susceptible to this bug as cash-flow ones, since SEC filers
tag both kinds of concept the same YTD-cumulative way for Q2-Q4. Not previously checked against
this statement type. For each candidate (symbol, fiscal_year, fiscal_quarter) with 3+
simultaneously-divergent quarterly_income_statement fields, computes the standalone quarter as
(this-quarter-end YTD fact) - (prior-quarter-end YTD fact) and only writes when that matches
yfinance's own flagged value within 1% tolerance - never a blind pattern-apply.

Deliberately excludes EPS/diluted_eps/shares_outstanding_* - those are NOT simple YTD-minus-
prior-YTD subtractable quantities (EPS is income/shares, not additive across quarters; a
weighted-average share count over a longer YTD span isn't the standalone quarter's own count
either) - a different bug investigation, not this mechanism.
"""

import argparse
import os
from typing import Any

import psycopg2
from dotenv import load_dotenv

from utils.external.sec_edgar_client import SecEdgarClient

load_dotenv(".env.local")

FIELD_CONCEPTS: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "gross_profit": ["GrossProfit"],
    "operating_expenses": ["OperatingExpenses", "CostsAndExpenses"],
    "operating_income": ["OperatingIncomeLoss"],
    "interest_expense": ["InterestExpense", "InterestExpenseDebt"],
    "income_tax_expense": ["IncomeTaxExpenseBenefit"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "net_income_attributable_to_common": ["NetIncomeLossAvailableToCommonStockholdersBasic"],
    "depreciation_expense": ["DepreciationDepletionAndAmortization", "Depreciation"],
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
        help="Minimum simultaneously-divergent quarterly_income_statement fields to consider a symbol/quarter a candidate",
    )
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT symbol, fiscal_year, fiscal_quarter
        FROM xbrl_yfinance_line_item_report
        WHERE divergent AND review_status = 'unreviewed' AND our_table = 'quarterly_income_statement'
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
            WHERE symbol=%s AND fiscal_year=%s AND fiscal_quarter=%s AND our_table='quarterly_income_statement'
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
                                f"UPDATE quarterly_income_statement SET {field}=%s WHERE symbol=%s AND fiscal_year=%s AND fiscal_quarter=%s",
                                (standalone, symbol, fy, fq),
                            )
                            cur.execute(
                                """
                                UPDATE xbrl_yfinance_line_item_report
                                SET review_status='reviewed_fixed', review_note=%s, reviewed_at=now(), reviewed_by='automated_ytd_fix_income_statement_20260919'
                                WHERE symbol=%s AND fiscal_year=%s AND fiscal_quarter=%s AND our_field=%s AND our_table='quarterly_income_statement'
                                """,
                                (
                                    "Automated fix: YTD-cumulative-mistaken-for-standalone-quarter bug "
                                    "(see ytd_cumulative_mistaken_for_quarter_systemic_20260919 memory note, "
                                    "extended to quarterly_income_statement 2026-09-19). "
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
