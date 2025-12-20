#!/usr/bin/env python3
"""
Load price data for the 84 missing symbols
"""
import os
import psycopg2
import yfinance as yf
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database connection with autocommit
conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=int(os.getenv('DB_PORT', '5432')),
    user=os.getenv('DB_USER', 'stocks'),
    password=os.getenv('DB_PASSWORD', 'bed0elAn'),
    database=os.getenv('DB_NAME', 'stocks')
)
conn.autocommit = True

missing_symbols = [
    'AERO', 'AGCC', 'AGIG', 'AGPU', 'AHMA', 'AIXC', 'ALPS', 'AMCI', 'APXT', 'AVX', 'AXIA', 'AZI',
    'BCSS', 'BETA', 'BGIN', 'BGSI', 'BLLN', 'BYAH', 'CABR', 'CBC', 'CBO', 'CBX', 'CCC', 'CD',
    'CDNL', 'CEPV', 'CITR', 'CYPH', 'DCX', 'DNMX', 'DYOR', 'ELE', 'ELWT', 'EMBJ', 'EVMN', 'FEED',
    'FISV', 'FUSE', 'FWDI', 'GFR.R', 'GIW', 'GLIBR', 'GLOO', 'GOLD', 'GRDX', 'HERE', 'HYNE', 'IGZ',
    'IMSR', 'JMG', 'LMRI', 'MBAI', 'MCTA', 'MEHA', 'MICC', 'MPLT', 'MTEST', 'NAVN', 'NBP', 'NCEL',
    'NOMA', 'NPT', 'OPTU', 'OSG', 'OTH', 'PARK', 'POAS', 'PTN', 'PURR', 'Q', 'REED', 'RGNT',
    'RJET', 'SMJF', 'SOLS', 'SVRN', 'TDAY', 'TII', 'TJGC', 'TWAV', 'WLTH', 'WSHP', 'XWIN', 'XXI', 'XZO'
]

logger.info(f"Loading price data for {len(missing_symbols)} symbols...")

cur = conn.cursor()
loaded = 0
failed = []

for idx, sym in enumerate(missing_symbols, 1):
    try:
        df = yf.download(sym, period='5y', interval='1d', progress=False, auto_adjust=False, actions=True)
        if df.empty:
            logger.warning(f"{idx}/{len(missing_symbols)} {sym}: No data available")
            failed.append(sym)
            continue
        
        # Normalize column names
        normalized_cols = {}
        for col in df.columns:
            if isinstance(col, tuple):
                normalized_cols[col] = col[1].lower() if len(col) > 1 else str(col[0]).lower()
            else:
                normalized_cols[col] = str(col).lower()
        df = df.rename(columns=normalized_cols)
        
        # Insert row by row
        for date, row in df.iterrows():
            try:
                cur.execute("""
                    INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO NOTHING
                """, (
                    sym,
                    date.date(),
                    float(row.get('open')) if 'open' in row else None,
                    float(row.get('high')) if 'high' in row else None,
                    float(row.get('low')) if 'low' in row else None,
                    float(row.get('close')) if 'close' in row else None,
                    float(row.get('adj close')) if 'adj close' in row else None,
                    int(row.get('volume', 0)) if 'volume' in row else None,
                    float(row.get('dividends', 0)) if 'dividends' in row else 0,
                    float(row.get('stock splits', 0)) if 'stock splits' in row else 0
                ))
            except Exception as e:
                logger.error(f"  Row error for {sym} on {date}: {str(e)[:50]}")
        
        logger.info(f"✅ {idx}/{len(missing_symbols)} {sym}: Loaded {len(df)} rows")
        loaded += 1
    except Exception as e:
        logger.error(f"❌ {idx}/{len(missing_symbols)} {sym}: {str(e)[:100]}")
        failed.append(sym)

logger.info(f"\n{'='*60}")
logger.info(f"COMPLETE: Loaded prices for {loaded}/{len(missing_symbols)} symbols")
if failed:
    logger.info(f"Failed ({len(failed)}): {', '.join(failed)}")
logger.info(f"{'='*60}")

cur.close()
conn.close()
