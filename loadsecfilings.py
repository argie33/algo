#!/usr/bin/env python3
"""
SEC Edgar Financial Data Loader - Get real financial statements from SEC filings
Loads 10-K (annual) and 10-Q (quarterly) filings for all US symbols
"""

import requests
import json
import logging
import psycopg2
import sys
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from db_helper import get_db_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# SEC Edgar API headers (required)
SEC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def get_db_connection():
    """Get database connection with socket fallback."""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "stocks"),
            user=os.getenv("DB_USER", "stocks"),
            password=os.getenv("DB_PASSWORD", "password"),
            port=int(os.getenv("DB_PORT", "5432")),
        )
        return conn
    except psycopg2.OperationalError:
        pass
    
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "stocks"),
            user=os.getenv("DB_USER", "stocks"),
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)

def get_cik_number(symbol: str) -> Optional[str]:
    """Get CIK number for a symbol from SEC Edgar"""
    try:
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={symbol}&type=10-K&dateb=&owner=exclude&count=100&output=json"
        resp = requests.get(url, headers=SEC_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if "cik_lookup" in data:
                cik = data["cik_lookup"].get(symbol.upper())
                if cik:
                    return str(cik).zfill(10)
    except Exception as e:
        logger.warning(f"Failed to get CIK for {symbol}: {e}")
    return None

def get_financial_data_from_filing(cik: str, filing_type: str = "10-K") -> Optional[Dict]:
    """
    Get financial data from latest SEC filing (10-K or 10-Q)
    Uses SEC EDGAR API to get structured financial data
    """
    try:
        # Get filings list
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        resp = requests.get(url, headers=SEC_HEADERS, timeout=10)
        
        if resp.status_code != 200:
            return None
        
        filings = resp.json()
        if "filings" not in filings:
            return None
        
        # Find latest 10-K or 10-Q
        recent_filings = filings["filings"]["recent"]["form"]
        accession_nums = filings["filings"]["recent"]["accessionNumber"]
        
        latest_filing = None
        latest_idx = None
        
        for idx, form in enumerate(recent_filings):
            if form in [filing_type, filing_type + "/A"]:
                latest_idx = idx
                break
        
        if latest_idx is None:
            return None
        
        accession = accession_nums[latest_idx].replace("-", "")
        
        # Get financial facts from filing
        facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        facts_resp = requests.get(facts_url, headers=SEC_HEADERS, timeout=10)
        
        if facts_resp.status_code != 200:
            return None
        
        facts = facts_resp.json()
        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        
        # Extract key financial metrics
        result = {}
        
        # Revenue
        if "Revenues" in us_gaap:
            for item in us_gaap["Revenues"]["units"].get("USD", []):
                if item.get("form") == filing_type:
                    result["revenue"] = item.get("val")
                    result["revenue_date"] = item.get("end")
                    break
        
        # Net Income
        if "NetIncomeLoss" in us_gaap:
            for item in us_gaap["NetIncomeLoss"]["units"].get("USD", []):
                if item.get("form") == filing_type:
                    result["net_income"] = item.get("val")
                    if "net_income_date" not in result:
                        result["net_income_date"] = item.get("end")
                    break
        
        # Operating Income
        if "OperatingIncomeLoss" in us_gaap:
            for item in us_gaap["OperatingIncomeLoss"]["units"].get("USD", []):
                if item.get("form") == filing_type:
                    result["operating_income"] = item.get("val")
                    if "operating_income_date" not in result:
                        result["operating_income_date"] = item.get("end")
                    break
        
        # Total Assets
        if "Assets" in us_gaap:
            for item in us_gaap["Assets"]["units"].get("USD", []):
                if item.get("form") == filing_type:
                    result["total_assets"] = item.get("val")
                    if "assets_date" not in result:
                        result["assets_date"] = item.get("end")
                    break
        
        # Total Liabilities
        if "Liabilities" in us_gaap:
            for item in us_gaap["Liabilities"]["units"].get("USD", []):
                if item.get("form") == filing_type:
                    result["total_liabilities"] = item.get("val")
                    if "liabilities_date" not in result:
                        result["liabilities_date"] = item.get("end")
                    break
        
        # Stockholders Equity
        if "StockholdersEquity" in us_gaap:
            for item in us_gaap["StockholdersEquity"]["units"].get("USD", []):
                if item.get("form") == filing_type:
                    result["stockholders_equity"] = item.get("val")
                    if "equity_date" not in result:
                        result["equity_date"] = item.get("end")
                    break
        
        return result if result else None
        
    except Exception as e:
        logger.warning(f"Failed to get financial data for CIK {cik}: {e}")
        return None

def load_sec_data():
    """Main loader - load SEC data for all symbols"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get all symbols
    cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
    symbols = [row[0] for row in cur.fetchall()]
    
    logger.info(f"Loading SEC data for {len(symbols)} symbols...")
    
    loaded = 0
    failed = 0
    
    for idx, symbol in enumerate(symbols):
        if idx % 100 == 0:
            logger.info(f"Progress: {idx}/{len(symbols)} ({100*idx//len(symbols)}%)")
        
        # Get CIK
        cik = get_cik_number(symbol)
        if not cik:
            failed += 1
            continue
        
        # Try annual first, then quarterly
        data = get_financial_data_from_filing(cik, "10-K")
        if not data:
            data = get_financial_data_from_filing(cik, "10-Q")
        
        if data:
            # Insert into appropriate table
            if "revenue" in data:
                try:
                    cur.execute("""
                        INSERT INTO annual_income_statement (symbol, date, revenue, operating_income, net_income, eps)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            revenue = COALESCE(EXCLUDED.revenue, annual_income_statement.revenue),
                            operating_income = COALESCE(EXCLUDED.operating_income, annual_income_statement.operating_income),
                            net_income = COALESCE(EXCLUDED.net_income, annual_income_statement.net_income),
                            eps = COALESCE(EXCLUDED.eps, annual_income_statement.eps)
                    """, (
                        symbol,
                        data.get("revenue_date"),
                        data.get("revenue"),
                        data.get("operating_income"),
                        data.get("net_income"),
                        None
                    ))
                    conn.commit()
                    loaded += 1
                except Exception as e:
                    logger.warning(f"Failed to insert {symbol}: {e}")
                    conn.rollback()
                    failed += 1
            else:
                failed += 1
        else:
            failed += 1
    
    cur.close()
    conn.close()
    
    logger.info(f"✅ Complete: {loaded} loaded, {failed} failed")

if __name__ == "__main__":
    load_sec_data()
