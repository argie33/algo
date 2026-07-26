#!/usr/bin/env python3
"""Simple local SEC data loader for testing - bypasses AWS infrastructure.

Run:
    python test_sec_data_loading.py
"""

import sys
import psycopg2
from datetime import datetime, date
from utils.external.sec_edgar import SecEdgarClient
from utils.external.sec_xbrl_segments import XBRLSegmentParser

# Database connection
def get_db_conn():
    return psycopg2.connect(
        host='localhost',
        port=5432,
        user='stocks',
        password='stocks',
        database='stocks'
    )

def test_8k_loader():
    """Test 8-K filings loader."""
    print("\n=== Testing 8-K Loader ===")

    client = SecEdgarClient()
    symbols = ['AAPL', 'MSFT', 'GOOGL']

    conn = get_db_conn()
    cur = conn.cursor()

    for symbol in symbols:
        try:
            cik = client.symbol_to_cik(symbol)
            submissions = client.get_submissions(cik)

            # Get recent 8-K filings
            forms = submissions['filings']['recent'].get('form', [])
            accessions = submissions['filings']['recent'].get('accessionNumber', [])
            dates = submissions['filings']['recent'].get('filingDate', [])

            count = 0
            for i, form in enumerate(forms):
                if form == '8-K' and count < 3:  # Get 3 recent
                    accession = accessions[i]
                    filing_date = dates[i]

                    # Insert or update
                    cur.execute("""
                        INSERT INTO current_reports_8k
                        (symbol, filing_date, accession_number, form_type, created_at, updated_at)
                        VALUES (%s, %s, %s, '8-K', NOW(), NOW())
                        ON CONFLICT (symbol, accession_number) DO NOTHING
                    """, (symbol, filing_date, accession))

                    if cur.rowcount > 0:
                        print(f"  [+] {symbol} {filing_date} {accession}")
                        count += 1

            if count > 0:
                conn.commit()
                print(f"  Inserted {count} 8-K filings for {symbol}")
            else:
                print(f"  No new 8-K filings for {symbol}")

        except Exception as e:
            print(f"  [ERROR] {symbol}: {type(e).__name__}: {str(e)[:100]}")

    cur.close()
    conn.close()

def test_segment_loader():
    """Test XBRL segment info loader."""
    print("\n=== Testing Segment Info Loader ===")

    client = SecEdgarClient()
    symbols = ['AAPL', 'MSFT', 'AMZN']

    conn = get_db_conn()
    cur = conn.cursor()

    for symbol in symbols:
        try:
            cik = client.symbol_to_cik(symbol)
            facts = client.get_company_facts(cik)

            # Parse segment data
            segment_data = XBRLSegmentParser.parse_companyfacts(facts, symbol)

            if segment_data.get('data_available'):
                # Insert aggregate segment data
                cur.execute("""
                    INSERT INTO sec_segment_info
                    (symbol, fiscal_year, fiscal_period, filing_date, segment_count,
                     segment_type, segment_name, largest_segment_revenue_pct,
                     revenue_concentration_hhi, data_unavailable, fetched_at, parsed_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW(), NOW())
                    ON CONFLICT DO NOTHING
                """, (
                    symbol,
                    date.today().year,
                    'FY',
                    date.today(),
                    segment_data.get('segment_count'),
                    segment_data.get('segment_type'),
                    'AGGREGATE',
                    segment_data.get('largest_segment_revenue_pct'),
                    segment_data.get('revenue_concentration_hhi'),
                    False
                ))

                if cur.rowcount > 0:
                    conn.commit()
                    print(f"  [+] {symbol}: {segment_data['segment_count']} segments, HHI={segment_data['revenue_concentration_hhi']:.0f}")
                else:
                    print(f"  [SKIP] {symbol}: already in database")
            else:
                # Insert unavailable marker
                cur.execute("""
                    INSERT INTO sec_segment_info
                    (symbol, fiscal_year, fiscal_period, filing_date, data_unavailable,
                     reason, fetched_at, parsed_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW(), NOW())
                    ON CONFLICT DO NOTHING
                """, (
                    symbol,
                    date.today().year,
                    'FY',
                    date.today(),
                    True,
                    segment_data.get('reason', 'unknown')
                ))

                if cur.rowcount > 0:
                    conn.commit()
                    print(f"  [DATA_UNAVAILABLE] {symbol}: {segment_data.get('reason')}")

        except Exception as e:
            print(f"  [ERROR] {symbol}: {type(e).__name__}: {str(e)[:100]}")

    cur.close()
    conn.close()

def test_insider_velocity_loader():
    """Test insider transaction velocity loader."""
    print("\n=== Testing Insider Transaction Velocity Loader ===")

    client = SecEdgarClient()
    symbols = ['AAPL', 'MSFT']

    conn = get_db_conn()
    cur = conn.cursor()

    for symbol in symbols:
        try:
            cik = client.symbol_to_cik(symbol)

            # For now, just insert a marker that we tried
            # Real loader would fetch Form 3/4/5 data and compute velocity
            cur.execute("""
                INSERT INTO insider_transaction_velocity
                (symbol, measurement_date, data_unavailable, data_unavailable_reason, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (symbol, measurement_date) DO NOTHING
            """, (
                symbol,
                date.today(),
                True,
                'Form345_data_fetch_not_implemented_in_test'
            ))

            if cur.rowcount > 0:
                conn.commit()
                print(f"  [TEST] {symbol}: Placeholder inserted (real data requires Form 3/4/5 parsing)")

        except Exception as e:
            print(f"  [ERROR] {symbol}: {type(e).__name__}: {str(e)[:100]}")

    cur.close()
    conn.close()

def verify_data():
    """Verify data was loaded."""
    print("\n=== Data Verification ===")

    conn = get_db_conn()
    cur = conn.cursor()

    # Check 8-K
    cur.execute("SELECT COUNT(*) FROM current_reports_8k")
    total_8k = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM current_reports_8k")
    symbols_8k = cur.fetchone()[0]

    # Check segments
    cur.execute("SELECT COUNT(*) FROM sec_segment_info WHERE data_unavailable IS NOT TRUE")
    total_seg = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM sec_segment_info WHERE data_unavailable IS NOT TRUE")
    symbols_seg = cur.fetchone()[0]

    print(f"8-K filings: {total_8k} total, {symbols_8k} symbols")
    print(f"Segment info: {total_seg} rows, {symbols_seg} symbols")

    cur.close()
    conn.close()

if __name__ == '__main__':
    try:
        test_8k_loader()
        test_segment_loader()
        test_insider_velocity_loader()
        verify_data()
        print("\n[SUCCESS] Data loading test complete")
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
