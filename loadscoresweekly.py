#!/usr/bin/env python3 
import os
import sys
import json
import pandas as pd
import numpy as np
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import logging
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

# Import our scoring engine
sys.path.append('/opt/scoring')
from scoring_engine import StockScoringEngine

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadscoresweekly.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

###############################################################################
# ─── Environment & Secrets ───────────────────────────────────────────────────
###############################################################################
SECRET_ARN = os.environ["DB_SECRET_ARN"]

sm_client = boto3.client("secretsmanager")
secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
creds = json.loads(secret_resp["SecretString"])

DB_USER = creds["username"]
DB_PASSWORD = creds["password"]
DB_HOST = creds["host"]
DB_PORT = int(creds.get("port", 5432))
DB_NAME = creds["dbname"]

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options='-c statement_timeout=60000'
    )
    return conn

def get_symbols_from_db(limit=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        q = """
          SELECT symbol
            FROM stock_symbols
           WHERE exchange IN ('NASDAQ','New York Stock Exchange')
             AND market_cap > 1000000000
        """
        if limit:
            q += " LIMIT %s"
            cur.execute(q, (limit,))
        else:
            cur.execute(q)
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def create_weekly_scores_tables(cur):
    """Create weekly scoring tables"""
    
    # Quality scores weekly
    cur.execute("DROP TABLE IF EXISTS quality_scores_weekly CASCADE;")
    cur.execute("""
      CREATE TABLE quality_scores_weekly (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        week_ending         DATE NOT NULL,
        earnings_quality    REAL,
        balance_strength    REAL,
        profitability       REAL,
        management          REAL,
        composite           REAL,
        trend               VARCHAR(20),
        confidence          REAL,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, week_ending)
      );
    """)
    
    # Growth scores weekly
    cur.execute("DROP TABLE IF EXISTS growth_scores_weekly CASCADE;")
    cur.execute("""
      CREATE TABLE growth_scores_weekly (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        week_ending         DATE NOT NULL,
        revenue_growth      REAL,
        earnings_growth     REAL,
        fundamental_growth  REAL,
        market_expansion    REAL,
        composite           REAL,
        trend               VARCHAR(20),
        confidence          REAL,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, week_ending)
      );
    """)
    
    # Value scores weekly
    cur.execute("DROP TABLE IF EXISTS value_scores_weekly CASCADE;")
    cur.execute("""
      CREATE TABLE value_scores_weekly (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        week_ending         DATE NOT NULL,
        pe_score            REAL,
        dcf_score           REAL,
        relative_value      REAL,
        composite           REAL,
        trend               VARCHAR(20),
        confidence          REAL,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, week_ending)
      );
    """)
    
    # Momentum scores weekly
    cur.execute("DROP TABLE IF EXISTS momentum_scores_weekly CASCADE;")
    cur.execute("""
      CREATE TABLE momentum_scores_weekly (
        id                      SERIAL PRIMARY KEY,
        symbol                  VARCHAR(20) NOT NULL,
        week_ending             DATE NOT NULL,
        price_momentum          REAL,
        fundamental_momentum    REAL,
        technical               REAL,
        volume_analysis         REAL,
        composite               REAL,
        trend                   VARCHAR(20),
        confidence              REAL,
        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, week_ending)
      );
    """)
    
    # Sentiment scores weekly
    cur.execute("DROP TABLE IF EXISTS sentiment_scores_weekly CASCADE;")
    cur.execute("""
      CREATE TABLE sentiment_scores_weekly (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        week_ending         DATE NOT NULL,
        analyst_sentiment   REAL,
        social_sentiment    REAL,
        market_sentiment    REAL,
        news_sentiment      REAL,
        composite           REAL,
        trend               VARCHAR(20),
        confidence          REAL,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, week_ending)
      );
    """)
    
    # Positioning scores weekly
    cur.execute("DROP TABLE IF EXISTS positioning_scores_weekly CASCADE;")
    cur.execute("""
      CREATE TABLE positioning_scores_weekly (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        week_ending         DATE NOT NULL,
        institutional       REAL,
        insider             REAL,
        short_interest      REAL,
        options_flow        REAL,
        composite           REAL,
        trend               VARCHAR(20),
        confidence          REAL,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, week_ending)
      );
    """)
    
    # Master scores weekly
    cur.execute("DROP TABLE IF EXISTS master_scores_weekly CASCADE;")
    cur.execute("""
      CREATE TABLE master_scores_weekly (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        week_ending         DATE NOT NULL,
        quality             REAL,
        growth              REAL,
        value               REAL,
        momentum            REAL,
        sentiment           REAL,
        positioning         REAL,
        composite           REAL,
        market_regime       VARCHAR(20),
        confidence_level    REAL,
        recommendation      VARCHAR(20),
        last_updated        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, week_ending)
      );
    """)

def get_week_ending_date():
    """Get the date for the end of the current week (Friday)"""
    today = datetime.now().date()
    days_ahead = 4 - today.weekday()  # Friday is weekday 4
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return today + timedelta(days_ahead)

def insert_weekly_scores(cur, symbol, week_ending, scores_data):
    """Insert weekly scores into all relevant tables"""
    try:
        # Insert quality scores
        quality = scores_data.get('quality', {})
        cur.execute("""
            INSERT INTO quality_scores_weekly (symbol, week_ending, earnings_quality, balance_strength, 
                                      profitability, management, composite, trend, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, week_ending) DO UPDATE SET
                earnings_quality = EXCLUDED.earnings_quality,
                balance_strength = EXCLUDED.balance_strength,
                profitability = EXCLUDED.profitability,
                management = EXCLUDED.management,
                composite = EXCLUDED.composite,
                trend = EXCLUDED.trend,
                confidence = EXCLUDED.confidence
        """, (
            symbol, week_ending,
            quality.get('earnings_quality'),
            quality.get('balance_strength'),
            quality.get('profitability'),
            quality.get('management'),
            quality.get('composite'),
            quality.get('trend'),
            90.0
        ))
        
        # Insert other scores similarly...
        growth = scores_data.get('growth', {})
        cur.execute("""
            INSERT INTO growth_scores_weekly (symbol, week_ending, revenue_growth, earnings_growth, 
                                     fundamental_growth, market_expansion, composite, trend, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, week_ending) DO UPDATE SET
                revenue_growth = EXCLUDED.revenue_growth,
                earnings_growth = EXCLUDED.earnings_growth,
                fundamental_growth = EXCLUDED.fundamental_growth,
                market_expansion = EXCLUDED.market_expansion,
                composite = EXCLUDED.composite,
                trend = EXCLUDED.trend,
                confidence = EXCLUDED.confidence
        """, (
            symbol, week_ending,
            growth.get('revenue_growth'),
            growth.get('earnings_growth'),
            growth.get('fundamental_growth'),
            growth.get('market_expansion'),
            growth.get('composite'),
            growth.get('trend'),
            90.0
        ))
        
        # Insert master scores
        composite_score = scores_data.get('composite', 50)
        confidence_level = scores_data.get('confidence_level', 90)
        market_regime = scores_data.get('market_regime', 'neutral')
        
        if composite_score >= 70:
            recommendation = 'BUY'
        elif composite_score >= 50:
            recommendation = 'HOLD'
        else:
            recommendation = 'SELL'
        
        cur.execute("""
            INSERT INTO master_scores_weekly (symbol, week_ending, quality, growth, value, momentum, 
                                     sentiment, positioning, composite, market_regime, 
                                     confidence_level, recommendation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, week_ending) DO UPDATE SET
                quality = EXCLUDED.quality,
                growth = EXCLUDED.growth,
                value = EXCLUDED.value,
                momentum = EXCLUDED.momentum,
                sentiment = EXCLUDED.sentiment,
                positioning = EXCLUDED.positioning,
                composite = EXCLUDED.composite,
                market_regime = EXCLUDED.market_regime,
                confidence_level = EXCLUDED.confidence_level,
                recommendation = EXCLUDED.recommendation,
                last_updated = CURRENT_TIMESTAMP
        """, (
            symbol, week_ending,
            quality.get('composite'),
            growth.get('composite'),
            scores_data.get('value', {}).get('composite'),
            scores_data.get('momentum', {}).get('composite'),
            scores_data.get('sentiment', {}).get('composite'),
            scores_data.get('positioning', {}).get('composite'),
            composite_score,
            market_regime,
            confidence_level,
            recommendation
        ))
        
        logging.info(f"✅ Inserted weekly scores for {symbol}: composite={composite_score:.1f}")
        
    except Exception as e:
        logging.error(f"❌ Error inserting weekly scores for {symbol}: {e}")
        raise

def main():
    logging.info(f"🚀 Starting {SCRIPT_NAME}")
    
    try:
        # Initialize scoring engine
        scoring_engine = StockScoringEngine()
        
        # Get symbols
        limit = int(os.environ.get('SYMBOL_LIMIT', 50))
        symbols = get_symbols_from_db(limit=limit)
        
        if not symbols:
            logging.error("❌ No symbols found")
            return
        
        # Get week ending date
        week_ending = get_week_ending_date()
        logging.info(f"📅 Processing for week ending: {week_ending}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # Create tables
            create_weekly_scores_tables(cur)
            conn.commit()
            
            successful = 0
            failed = 0
            
            for i, symbol in enumerate(symbols):
                try:
                    logging.info(f"🔍 Processing {symbol} ({i+1}/{len(symbols)})...")
                    
                    scores_data = scoring_engine.calculate_composite_score(symbol)
                    
                    if scores_data:
                        insert_weekly_scores(cur, symbol, week_ending, scores_data)
                        successful += 1
                        
                        if (i + 1) % 10 == 0:
                            conn.commit()
                    else:
                        failed += 1
                        
                except Exception as e:
                    logging.error(f"❌ Error processing {symbol}: {e}")
                    failed += 1
                    continue
            
            conn.commit()
            logging.info(f"✅ Weekly scoring complete! Success: {successful}, Failed: {failed}")
            
        finally:
            cur.close()
            conn.close()
        
    except Exception as e:
        logging.error(f"❌ {SCRIPT_NAME} failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()