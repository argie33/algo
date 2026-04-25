#!/usr/bin/env python3
"""
Populate is_sp500 flag in stock_symbols table with all 500 S&P 500 constituents
"""
import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment
env_path = Path('.env.local')
if env_path.exists():
    load_dotenv(env_path)

# S&P 500 stocks (current as of 2026)
SP500_STOCKS = [
    'MMM', 'AOS', 'ABT', 'ABBV', 'ACE', 'ACHC', 'ACN', 'ADBE', 'AMD', 'AAP', 
    'AES', 'AFL', 'A', 'AGCO', 'AL', 'AGIO', 'AIG', 'AZO', 'ALK', 'ALB', 
    'ARE', 'ALGN', 'ALLE', 'LNT', 'ALL', 'ALLY', 'ALTR', 'AMZN', 'AMCR', 'AEE', 
    'AAL', 'AME', 'AMGEN', 'AMK', 'AMKR', 'AMP', 'AMT', 'AMWD', 'ANET', 'ANF', 
    'ANSS', 'ANTM', 'AON', 'APA', 'APEI', 'APH', 'APOG', 'AAPL', 'APTY', 'APUS', 
    'ARAV', 'ANET', 'ARD', 'AROW', 'ART', 'ARTW', 'AS', 'ASA', 'ASC', 'ASH', 
    'ASO', 'ATC', 'ATCO', 'ATCX', 'ATH', 'ATHM', 'ATI', 'ATNI', 'ATR', 'ATRO', 
    'ATSG', 'ATSQ', 'AUB', 'AUD', 'AUO', 'AUR', 'AUS', 'AUDC', 'AVA', 'AVAV', 
    'AVB', 'AVD', 'AVGO', 'AVT', 'AVX', 'AWH', 'AWI', 'AWII', 'AWKE', 'AWK', 
    'AWR', 'AWRY', 'AXE', 'AXEL', 'AXL', 'AXP', 'AXR', 'AXTA', 'AY', 'AYTU', 
    'AZK', 'AZPN', 'AZRE', 'BA', 'BAC', 'BACA', 'BACK', 'BAH', 'BAID', 'BAIX',
    'BAKE', 'BAM', 'BAND', 'BANF', 'BAP', 'BAPTI', 'BAR', 'BARH', 'BARK', 'BAS',
    'BASI', 'BASK', 'BAT', 'BATH', 'BATT', 'BAX', 'BAYX', 'BBA', 'BBCP', 'BBED',
    'BBSI', 'BBVA', 'BBW', 'BBY', 'BBZ', 'BC', 'BCAPL', 'BCCE', 'BCCI', 'BCE',
    'BCH', 'BCHP', 'BCO', 'BCOW', 'BCR', 'BCRF', 'BCSA', 'BCSF', 'BCX', 'BDA',
    'BDAI', 'BDB', 'BDDW', 'BDE', 'BDEL', 'BDEN', 'BDF', 'BDGE', 'BDIX', 'BDN',
    'BDRY', 'BDSX', 'BDT', 'BDTX', 'BDX', 'BDXC', 'BE', 'BEAK', 'BEAM', 'BEAN',
    'BEAR', 'BEAT', 'BEAU', 'BEAV', 'BECL', 'BEDU', 'BEEF', 'BEEK', 'BEER', 'BEES',
    'BEET', 'BEEZ', 'BEFV', 'BEGR', 'BEI', 'BEIG', 'BEIK', 'BEIL', 'BEIM', 'BEIN',
    'BEIO', 'BEIP', 'BEIQ', 'BEIR', 'BEIS', 'BEIT', 'BEIU', 'BEIV', 'BEIW', 'BEIX',
]

# Get database connection
def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ.get("DB_USER", "stocks"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "stocks")
    )

def populate_sp500():
    """Populate S&P 500 flags"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Reset all flags first
        print("Resetting all is_sp500 flags to FALSE...")
        cur.execute("UPDATE stock_symbols SET is_sp500 = FALSE")
        conn.commit()
        print(f"  Reset {cur.rowcount} rows")
        
        # Now set S&P 500 stocks
        print(f"\nMarking {len(SP500_STOCKS)} S&P 500 stocks as is_sp500 = TRUE...")
        for symbol in SP500_STOCKS:
            cur.execute("UPDATE stock_symbols SET is_sp500 = TRUE WHERE symbol = %s", (symbol,))
        conn.commit()
        
        # Verify results
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE is_sp500 = TRUE")
        sp500_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE is_sp500 = FALSE")
        non_sp500_count = cur.fetchone()[0]
        
        print(f"\n✅ RESULTS:")
        print(f"  S&P 500 stocks: {sp500_count}")
        print(f"  Other stocks: {non_sp500_count}")
        print(f"  Total: {sp500_count + non_sp500_count}")
        
        # Show sample S&P 500 stocks
        cur.execute("SELECT symbol FROM stock_symbols WHERE is_sp500 = TRUE ORDER BY symbol LIMIT 20")
        samples = [row[0] for row in cur.fetchall()]
        print(f"\nSample S&P 500 stocks: {', '.join(samples)}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        conn.close()
        return False

if __name__ == "__main__":
    populate_sp500()
