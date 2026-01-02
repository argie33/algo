#!/usr/bin/env python3
"""
Fix sector and industry classification inconsistencies in the database

Issues to resolve:
1. Consolidate duplicate sectors (Financials/Financial Services, Materials/Basic Materials)
2. Standardize sector names to match GICS
3. Fix Consumer Defensive -> Consumer Staples
4. Fill NULL sectors based on industry classifications
5. Remove Consumer Cyclical -> should be Consumer Discretionary
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2

load_dotenv('.env.local')

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'stocks')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'bed0elAn')
DB_NAME = os.getenv('DB_NAME', 'stocks')

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        return conn
    except Exception as e:
        print(f"Failed to connect: {e}")
        sys.exit(1)

conn = get_db_connection()
cursor = conn.cursor()

try:
    print("🔧 Fixing sector classifications...\n")
    
    # 1. Consolidate Financial Services -> Financials
    print("1. Consolidating 'Financial Services' -> 'Financials'")
    cursor.execute("UPDATE company_profile SET sector = 'Financials' WHERE sector = 'Financial Services'")
    print(f"   ✅ Updated {cursor.rowcount} rows")
    conn.commit()
    
    # 2. Consolidate Basic Materials -> Materials
    print("2. Consolidating 'Basic Materials' -> 'Materials'")
    cursor.execute("UPDATE company_profile SET sector = 'Materials' WHERE sector = 'Basic Materials'")
    print(f"   ✅ Updated {cursor.rowcount} rows")
    conn.commit()
    
    # 3. Consumer Defensive -> Consumer Staples
    print("3. Consolidating 'Consumer Defensive' -> 'Consumer Staples'")
    cursor.execute("UPDATE company_profile SET sector = 'Consumer Staples' WHERE sector = 'Consumer Defensive'")
    print(f"   ✅ Updated {cursor.rowcount} rows")
    conn.commit()
    
    # 4. Consumer Cyclical -> Consumer Discretionary
    print("4. Consolidating 'Consumer Cyclical' -> 'Consumer Discretionary'")
    cursor.execute("UPDATE company_profile SET sector = 'Consumer Discretionary' WHERE sector = 'Consumer Cyclical'")
    print(f"   ✅ Updated {cursor.rowcount} rows")
    conn.commit()
    
    # 5. Fill NULL sectors based on industry mapping (GICS standard)
    print("5. Filling NULL sectors based on industry classifications...")
    
    sector_mapping = {
        'Biotechnology': 'Healthcare',
        'Banks - Regional': 'Financials',
        'Software - Application': 'Technology',
        'Software - Infrastructure': 'Technology',
        'Medical Devices': 'Healthcare',
        'Asset Management': 'Financials',
        'Capital Markets': 'Financials',
        'Drug Manufacturers - Specialty & Generic': 'Healthcare',
        'Aerospace & Defense': 'Industrials',
        'Internet Content & Information': 'Communication Services',
        'Specialty Industrial Machinery': 'Industrials',
        'Oil & Gas E&P': 'Energy',
        'Information Technology Services': 'Technology',
        'Semiconductors': 'Technology',
        'Packaged Foods': 'Consumer Staples',
        'Telecom Services': 'Communication Services',
        'Specialty Chemicals': 'Materials',
        'Medical Instruments & Supplies': 'Healthcare',
        'Restaurants': 'Consumer Discretionary',
        'Auto Parts': 'Consumer Discretionary',
        'Engineering & Construction': 'Industrials',
        'Entertainment': 'Communication Services',
        'Health Information Services': 'Healthcare',
        'Medical Care Facilities': 'Healthcare',
        'Diagnostics & Research': 'Healthcare',
        'Credit Services': 'Financials',
        'Oil & Gas Equipment & Services': 'Energy',
        'Gold': 'Materials',
        'Specialty Retail': 'Consumer Discretionary',
        'Electrical Equipment & Parts': 'Industrials',
        'Electronic Components': 'Technology',
        'Other Industrial Metals & Mining': 'Materials',
        'Specialty Business Services': 'Industrials',
        'Insurance - Property & Casualty': 'Financials',
        'Communication Equipment': 'Technology',
        'Education & Training Services': 'Consumer Discretionary',
        'Advertising Agencies': 'Communication Services',
        'Oil & Gas Midstream': 'Energy',
        'Real Estate Services': 'Real Estate',
        'Utilities - Regulated Electric': 'Utilities',
        'Insurance - Life': 'Financials',
        'Consumer Electronics': 'Technology',
        'Apparel Manufacturing': 'Consumer Discretionary',
        'Beverages - Alcoholic': 'Consumer Staples',
        'Beverages - Non-Alcoholic': 'Consumer Staples',
        'Home Furnishings & Fixtures': 'Consumer Discretionary',
        'Department Stores': 'Consumer Discretionary',
        'Insurance - Specialty': 'Financials',
    }
    
    for industry, sector in sector_mapping.items():
        cursor.execute("UPDATE company_profile SET sector = %s WHERE (sector IS NULL OR sector = '') AND industry = %s", 
                      (sector, industry))
        updated = cursor.rowcount
        if updated > 0:
            print(f"   {industry:45} -> {sector:25} ({updated} stocks)")
        conn.commit()
    
    # 6. Fill any remaining NULL sectors with 'Other'
    print("6. Filling any remaining NULL sectors...")
    cursor.execute("UPDATE company_profile SET sector = 'Other' WHERE sector IS NULL OR sector = ''")
    print(f"   ✅ Updated {cursor.rowcount} rows")
    conn.commit()
    
    # Show final results
    print("\n📊 Final sector distribution:\n")
    cursor.execute("SELECT sector, COUNT(*) as count FROM company_profile GROUP BY sector ORDER BY count DESC")
    for sector, count in cursor.fetchall():
        print(f"  {sector:25} {count:5} stocks")
    
    print("\n✅ Sector classifications fixed successfully!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()
finally:
    cursor.close()
    conn.close()
