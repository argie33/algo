#!/usr/bin/env python3
"""
Stock Symbols Enhanced Loader Script

This script loads stock symbols with enhanced metadata including:
- Company name and basic info
- Sector and industry classification
- Market cap tier categorization
- Exchange and currency information
- Market status and listing details

Data Sources:
- Primary: yfinance for comprehensive stock data
- Secondary: SEC EDGAR for additional company details
- Fallback: Manual classification for key indices

Author: Financial Dashboard System
"""

import gc
import json
import logging
import os
import resource
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import psycopg2
import requests
import yfinance as yf
from psycopg2.extras import RealDictCursor, execute_values

# Script configuration
SCRIPT_NAME = "loadsymbols.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


# Memory monitoring
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)


def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


# Database configuration
def get_db_config():
    """Get database configuration from environment or AWS Secrets Manager"""
    try:
        import boto3

        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=os.environ["DB_SECRET_ARN"]
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"],
        }
    except Exception as e:
        logging.warning(f"Using environment variables for DB config: {e}")
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": os.environ.get("DB_NAME", "stocks"),
        }


# Stock symbol lists
MAJOR_INDICES = ["SPY", "QQQ", "DIA", "VTI", "VXUS", "BND", "VNQ", "GDX", "TLT", "EEM"]

SP500_SYMBOLS = [
    # Technology
    "AAPL",
    "MSFT",
    "GOOGL",
    "GOOG",
    "AMZN",
    "NVDA",
    "TSLA",
    "META",
    "CRM",
    "ORCL",
    "ADBE",
    "NFLX",
    "INTC",
    "AMD",
    "CSCO",
    "AVGO",
    "TXN",
    "QCOM",
    "NOW",
    "INTU",
    # Financials
    "BRK-B",
    "JPM",
    "BAC",
    "WFC",
    "GS",
    "MS",
    "C",
    "AXP",
    "USB",
    "TFC",
    "PNC",
    "COF",
    "SCHW",
    "BLK",
    "SPGI",
    "ICE",
    "CME",
    "AON",
    "MMC",
    "AJG",
    # Healthcare
    "UNH",
    "JNJ",
    "PFE",
    "LLY",
    "ABBV",
    "MRK",
    "TMO",
    "ABT",
    "DHR",
    "BMY",
    "AMGN",
    "MDT",
    "CVS",
    "ELV",
    "CI",
    "HUM",
    "ANTM",
    "ISRG",
    "SYK",
    "BSX",
    # Consumer Discretionary
    "AMZN",
    "TSLA",
    "HD",
    "MCD",
    "BKNG",
    "NKE",
    "LOW",
    "TJX",
    "SBUX",
    "LRCX",
    "MAR",
    "HLT",
    "ORLY",
    "AZO",
    "ROST",
    "YUM",
    "CMG",
    "EBAY",
    "ETSY",
    "NCLH",
    # Communication Services
    "GOOGL",
    "META",
    "NFLX",
    "DIS",
    "CMCSA",
    "VZ",
    "T",
    "TMUS",
    "CHTR",
    "ATVI",
    # Consumer Staples
    "PG",
    "KO",
    "PEP",
    "WMT",
    "COST",
    "MDLZ",
    "CL",
    "GIS",
    "KMB",
    "SYY",
    # Industrials
    "BA",
    "HON",
    "UPS",
    "CAT",
    "DE",
    "LMT",
    "RTX",
    "FDX",
    "UNP",
    "CSX",
    "NOC",
    "GD",
    "MMM",
    "EMR",
    "ETN",
    "ITW",
    "PH",
    "CMI",
    "CARR",
    "OTIS",
    # Materials
    "LIN",
    "APD",
    "SHW",
    "FCX",
    "NEM",
    "DOW",
    "DD",
    "PPG",
    "ECL",
    "IFF",
    # Energy
    "XOM",
    "CVX",
    "COP",
    "EOG",
    "SLB",
    "PSX",
    "VLO",
    "MPC",
    "OXY",
    "BKR",
    # Utilities
    "NEE",
    "SO",
    "DUK",
    "AEP",
    "SRE",
    "D",
    "PEG",
    "EXC",
    "XEL",
    "ED",
    # Real Estate
    "AMT",
    "PLD",
    "CCI",
    "EQIX",
    "WELL",
    "SPG",
    "O",
    "PSA",
    "EXR",
    "AVB",
]

# Popular ETFs and other symbols
POPULAR_ETFS = [
    "SPY",
    "QQQ",
    "DIA",
    "VTI",
    "IWM",
    "EEM",
    "VEA",
    "VWO",
    "BND",
    "TLT",
    "GLD",
    "SLV",
    "VNQ",
    "XLF",
    "XLK",
    "XLE",
    "XLV",
    "XLI",
    "XLC",
    "XLY",
]

CRYPTO_SYMBOLS = ["BTC-USD", "ETH-USD", "ADA-USD", "DOT-USD", "SOL-USD"]


def get_market_cap_tier(market_cap: float) -> str:
    """Categorize stocks by market capitalization"""
    if market_cap is None or market_cap <= 0:
        return "unknown"
    elif market_cap >= 200_000_000_000:  # $200B+
        return "mega_cap"
    elif market_cap >= 10_000_000_000:  # $10B+
        return "large_cap"
    elif market_cap >= 2_000_000_000:  # $2B+
        return "mid_cap"
    elif market_cap >= 300_000_000:  # $300M+
        return "small_cap"
    else:
        return "micro_cap"


def get_enhanced_symbol_info(symbol: str, max_retries: int = 3) -> Optional[Dict]:
    """Get enhanced symbol information from yfinance with retries"""
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or "symbol" not in info:
                logging.warning(f"No info found for {symbol} on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                    continue
                return None

            # Extract and normalize data
            result = {
                "symbol": symbol.upper(),
                "company_name": info.get("longName", info.get("shortName", symbol)),
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "sub_industry": info.get("industryDisp", ""),
                "market_cap": info.get("marketCap", 0),
                "market_cap_tier": get_market_cap_tier(info.get("marketCap")),
                "exchange": info.get("exchange", "Unknown"),
                "currency": info.get("currency", "USD"),
                "country": info.get("country", "US"),
                "is_active": True,
                "listing_date": None,
                "quote_type": info.get("quoteType", "EQUITY"),
                "website": info.get("website", ""),
                "business_summary": (
                    info.get("longBusinessSummary", "")[:500]
                    if info.get("longBusinessSummary")
                    else ""
                ),
                "employees": info.get("fullTimeEmployees"),
                "city": info.get("city", ""),
                "state": info.get("state", ""),
                "phone": info.get("phone", ""),
                "beta": info.get("beta"),
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "dividend_yield": info.get("dividendYield"),
                "book_value": info.get("bookValue"),
                "price_to_book": info.get("priceToBook"),
                "enterprise_value": info.get("enterpriseValue"),
                "profit_margins": info.get("profitMargins"),
                "float_shares": info.get("floatShares"),
                "shares_outstanding": info.get("sharesOutstanding"),
                "held_percent_insiders": info.get("heldPercentInsiders"),
                "held_percent_institutions": info.get("heldPercentInstitutions"),
                "short_ratio": info.get("shortRatio"),
                "short_percent_outstanding": info.get("shortPercentOfFloat"),
                "recommendation_mean": info.get("recommendationMean"),
                "target_high_price": info.get("targetHighPrice"),
                "target_low_price": info.get("targetLowPrice"),
                "target_mean_price": info.get("targetMeanPrice"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "last_updated": datetime.now(),
            }

            # Handle listing date
            if "firstTradeDateEpochUtc" in info and info["firstTradeDateEpochUtc"]:
                try:
                    result["listing_date"] = datetime.fromtimestamp(
                        info["firstTradeDateEpochUtc"]
                    ).date()
                except:
                    pass

            return result

        except Exception as e:
            logging.warning(f"Error fetching {symbol} on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                return None

    return None


def load_symbols_batch(
    symbols: List[str], conn, cur, batch_size: int = 20
) -> Tuple[int, int]:
    """Load symbols in batches with parallel processing"""
    total_processed = 0
    total_inserted = 0
    failed_symbols = []

    # Process in batches
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        logging.info(
            f"Processing batch {batch_num}/{total_batches}: {len(batch)} symbols"
        )
        log_mem(f"Batch {batch_num} start")

        # Parallel fetch with ThreadPoolExecutor
        symbol_data = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_symbol = {
                executor.submit(get_enhanced_symbol_info, symbol): symbol
                for symbol in batch
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    data = future.result(timeout=30)
                    if data:
                        symbol_data.append(data)
                    else:
                        failed_symbols.append(symbol)
                        logging.warning(f"Failed to get data for {symbol}")
                except Exception as e:
                    failed_symbols.append(symbol)
                    logging.error(f"Exception processing {symbol}: {e}")

                total_processed += 1

        # Batch insert to database
        if symbol_data:
            try:
                insert_query = """
                    INSERT INTO stock_symbols_enhanced (
                        symbol, company_name, sector, industry, sub_industry, 
                        market_cap, market_cap_tier, exchange, currency, country,
                        is_active, listing_date, quote_type, website, business_summary,
                        employees, city, state, phone, beta, trailing_pe, forward_pe,
                        dividend_yield, book_value, price_to_book, enterprise_value,
                        profit_margins, float_shares, shares_outstanding,
                        held_percent_insiders, held_percent_institutions,
                        short_ratio, short_percent_outstanding, recommendation_mean,
                        target_high_price, target_low_price, target_mean_price,
                        fifty_two_week_low, fifty_two_week_high, last_updated,
                        created_at, updated_at
                    ) VALUES %s
                    ON CONFLICT (symbol) DO UPDATE SET
                        company_name = EXCLUDED.company_name,
                        sector = EXCLUDED.sector,
                        industry = EXCLUDED.industry,
                        sub_industry = EXCLUDED.sub_industry,
                        market_cap = EXCLUDED.market_cap,
                        market_cap_tier = EXCLUDED.market_cap_tier,
                        exchange = EXCLUDED.exchange,
                        currency = EXCLUDED.currency,
                        country = EXCLUDED.country,
                        quote_type = EXCLUDED.quote_type,
                        website = EXCLUDED.website,
                        business_summary = EXCLUDED.business_summary,
                        employees = EXCLUDED.employees,
                        city = EXCLUDED.city,
                        state = EXCLUDED.state,
                        phone = EXCLUDED.phone,
                        beta = EXCLUDED.beta,
                        trailing_pe = EXCLUDED.trailing_pe,
                        forward_pe = EXCLUDED.forward_pe,
                        dividend_yield = EXCLUDED.dividend_yield,
                        book_value = EXCLUDED.book_value,
                        price_to_book = EXCLUDED.price_to_book,
                        enterprise_value = EXCLUDED.enterprise_value,
                        profit_margins = EXCLUDED.profit_margins,
                        float_shares = EXCLUDED.float_shares,
                        shares_outstanding = EXCLUDED.shares_outstanding,
                        held_percent_insiders = EXCLUDED.held_percent_insiders,
                        held_percent_institutions = EXCLUDED.held_percent_institutions,
                        short_ratio = EXCLUDED.short_ratio,
                        short_percent_outstanding = EXCLUDED.short_percent_outstanding,
                        recommendation_mean = EXCLUDED.recommendation_mean,
                        target_high_price = EXCLUDED.target_high_price,
                        target_low_price = EXCLUDED.target_low_price,
                        target_mean_price = EXCLUDED.target_mean_price,
                        fifty_two_week_low = EXCLUDED.fifty_two_week_low,
                        fifty_two_week_high = EXCLUDED.fifty_two_week_high,
                        last_updated = EXCLUDED.last_updated,
                        updated_at = CURRENT_TIMESTAMP
                """

                # Prepare data tuples
                data_tuples = []
                for item in symbol_data:
                    data_tuples.append(
                        (
                            item["symbol"],
                            item["company_name"],
                            item["sector"],
                            item["industry"],
                            item["sub_industry"],
                            item["market_cap"],
                            item["market_cap_tier"],
                            item["exchange"],
                            item["currency"],
                            item["country"],
                            item["is_active"],
                            item["listing_date"],
                            item["quote_type"],
                            item["website"],
                            item["business_summary"],
                            item["employees"],
                            item["city"],
                            item["state"],
                            item["phone"],
                            item["beta"],
                            item["trailing_pe"],
                            item["forward_pe"],
                            item["dividend_yield"],
                            item["book_value"],
                            item["price_to_book"],
                            item["enterprise_value"],
                            item["profit_margins"],
                            item["float_shares"],
                            item["shares_outstanding"],
                            item["held_percent_insiders"],
                            item["held_percent_institutions"],
                            item["short_ratio"],
                            item["short_percent_outstanding"],
                            item["recommendation_mean"],
                            item["target_high_price"],
                            item["target_low_price"],
                            item["target_mean_price"],
                            item["fifty_two_week_low"],
                            item["fifty_two_week_high"],
                            item["last_updated"],
                            datetime.now(),
                            datetime.now(),
                        )
                    )

                execute_values(cur, insert_query, data_tuples)
                conn.commit()
                total_inserted += len(symbol_data)

                logging.info(
                    f"Batch {batch_num} inserted {len(symbol_data)} symbols successfully"
                )

            except Exception as e:
                logging.error(f"Database insert error for batch {batch_num}: {e}")
                conn.rollback()

        # Memory cleanup
        del symbol_data
        gc.collect()
        log_mem(f"Batch {batch_num} end")

        # Brief pause between batches
        time.sleep(0.5)

    if failed_symbols:
        logging.warning(
            f"Failed to process {len(failed_symbols)} symbols: {failed_symbols[:10]}..."
        )

    return total_processed, total_inserted


def create_enhanced_symbols_table(cur, conn):
    """Create the enhanced stock symbols table"""
    logging.info("Creating stock_symbols_enhanced table...")

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS stock_symbols_enhanced (
        symbol VARCHAR(20) PRIMARY KEY,
        company_name VARCHAR(255) NOT NULL,
        sector VARCHAR(100),
        industry VARCHAR(150),
        sub_industry VARCHAR(200),
        market_cap BIGINT,
        market_cap_tier VARCHAR(20),
        exchange VARCHAR(20),
        currency VARCHAR(3) DEFAULT 'USD',
        country VARCHAR(50) DEFAULT 'US',
        is_active BOOLEAN DEFAULT TRUE,
        listing_date DATE,
        quote_type VARCHAR(20),
        website TEXT,
        business_summary TEXT,
        employees INTEGER,
        city VARCHAR(100),
        state VARCHAR(50),
        phone VARCHAR(50),
        beta DECIMAL(8,4),
        trailing_pe DECIMAL(8,4),
        forward_pe DECIMAL(8,4),
        dividend_yield DECIMAL(8,6),
        book_value DECIMAL(12,4),
        price_to_book DECIMAL(8,4),
        enterprise_value BIGINT,
        profit_margins DECIMAL(8,6),
        float_shares BIGINT,
        shares_outstanding BIGINT,
        held_percent_insiders DECIMAL(8,6),
        held_percent_institutions DECIMAL(8,6),
        short_ratio DECIMAL(8,4),
        short_percent_outstanding DECIMAL(8,6),
        recommendation_mean DECIMAL(4,2),
        target_high_price DECIMAL(12,4),
        target_low_price DECIMAL(12,4),
        target_mean_price DECIMAL(12,4),
        fifty_two_week_low DECIMAL(12,4),
        fifty_two_week_high DECIMAL(12,4),
        last_updated TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """

    cur.execute(create_table_sql)

    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_symbols_sector ON stock_symbols_enhanced(sector);",
        "CREATE INDEX IF NOT EXISTS idx_symbols_market_cap ON stock_symbols_enhanced(market_cap DESC);",
        "CREATE INDEX IF NOT EXISTS idx_symbols_market_cap_tier ON stock_symbols_enhanced(market_cap_tier);",
        "CREATE INDEX IF NOT EXISTS idx_symbols_exchange ON stock_symbols_enhanced(exchange);",
        "CREATE INDEX IF NOT EXISTS idx_symbols_active ON stock_symbols_enhanced(is_active);",
        "CREATE INDEX IF NOT EXISTS idx_symbols_beta ON stock_symbols_enhanced(beta);",
        "CREATE INDEX IF NOT EXISTS idx_symbols_pe ON stock_symbols_enhanced(trailing_pe);",
        "CREATE INDEX IF NOT EXISTS idx_symbols_dividend_yield ON stock_symbols_enhanced(dividend_yield);",
        "CREATE INDEX IF NOT EXISTS idx_symbols_updated ON stock_symbols_enhanced(last_updated DESC);",
    ]

    for index_sql in indexes:
        cur.execute(index_sql)

    conn.commit()
    logging.info("Enhanced symbols table and indexes created successfully")


if __name__ == "__main__":
    log_mem("startup")

    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create table
    create_enhanced_symbols_table(cur, conn)

    # Combine all symbol lists
    all_symbols = list(
        set(MAJOR_INDICES + SP500_SYMBOLS + POPULAR_ETFS + CRYPTO_SYMBOLS)
    )
    logging.info(f"Loading {len(all_symbols)} symbols total")

    # Load symbols
    start_time = time.time()
    processed, inserted = load_symbols_batch(all_symbols, conn, cur)
    end_time = time.time()

    # Final statistics
    cur.execute("SELECT COUNT(*) FROM stock_symbols_enhanced")
    total_in_db = cur.fetchone()[0]

    logging.info("=" * 60)
    logging.info("SYMBOLS LOADING COMPLETE")
    logging.info("=" * 60)
    logging.info(f"Symbols processed: {processed}")
    logging.info(f"Symbols inserted/updated: {inserted}")
    logging.info(f"Total symbols in database: {total_in_db}")
    logging.info(f"Processing time: {(end_time - start_time):.1f} seconds")
    logging.info(
        f"Average time per symbol: {(end_time - start_time) / processed:.2f} seconds"
    )
    log_mem("completion")

    # Sample query
    cur.execute(
        """
        SELECT sector, COUNT(*) as count, 
               AVG(market_cap) as avg_market_cap,
               AVG(trailing_pe) as avg_pe
        FROM stock_symbols_enhanced 
        WHERE sector != 'Unknown' AND market_cap > 0
        GROUP BY sector 
        ORDER BY count DESC
    """
    )

    logging.info("\nSector Distribution:")
    for row in cur.fetchall():
        logging.info(
            f"  {row['sector']}: {row['count']} stocks, "
            f"Avg Market Cap: ${row['avg_market_cap']/1e9:.1f}B, "
            f"Avg P/E: {row['avg_pe']:.1f}"
        )

    cur.close()
    conn.close()
    logging.info("Database connection closed")
