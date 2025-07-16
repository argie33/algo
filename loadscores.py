#!/usr/bin/env python3 
# Updated: 2025-07-16 - All routes working - Enhanced deployment trigger v10 - Post middleware fix
import os
import sys
import json
import pandas as pd
import numpy as np
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import calendar
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
SCRIPT_NAME = "loadscores.py"
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
        options='-c statement_timeout=60000'  # 60 seconds for scoring calculations
    )
    return conn

###############################################################################
# DATABASE FUNCTIONS
###############################################################################
def get_symbols_from_db(period_type, limit=None):
    """Get symbols based on period type - different market cap thresholds"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Use different market cap thresholds based on period
        if period_type == 'monthly':
            min_market_cap = 5000000000  # $5B for monthly
        else:
            min_market_cap = 1000000000  # $1B for daily/weekly
            
        q = """
          SELECT symbol
            FROM stock_symbols
           WHERE exchange IN ('NASDAQ','New York Stock Exchange')
             AND market_cap > %s
        """
        if limit:
            q += " LIMIT %s"
            cur.execute(q, (min_market_cap, limit))
        else:
            cur.execute(q, (min_market_cap,))
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

def create_unified_scores_tables(cur):
    """Create unified scoring tables with period_type column"""
    
    # Drop old period-specific tables
    logging.info("🧹 Dropping old period-specific tables...")
    old_tables = [
        'quality_scores_daily', 'quality_scores_weekly', 'quality_scores_monthly',
        'growth_scores_daily', 'growth_scores_weekly', 'growth_scores_monthly',
        'value_scores_daily', 'value_scores_weekly', 'value_scores_monthly',
        'momentum_scores_daily', 'momentum_scores_weekly', 'momentum_scores_monthly',
        'sentiment_scores_daily', 'sentiment_scores_weekly', 'sentiment_scores_monthly',
        'positioning_scores_daily', 'positioning_scores_weekly', 'positioning_scores_monthly',
        'master_scores_daily', 'master_scores_weekly', 'master_scores_monthly'
    ]
    for table in old_tables:
        cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
    
    # Quality scores table
    cur.execute("DROP TABLE IF EXISTS quality_scores CASCADE;")
    cur.execute("""
      CREATE TABLE quality_scores (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        date                DATE NOT NULL,
        period_type         VARCHAR(10) NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly')),
        period_ending       DATE NOT NULL,
        earnings_quality    REAL,
        balance_strength    REAL,
        profitability       REAL,
        management          REAL,
        composite           REAL,
        trend               VARCHAR(20),
        confidence          REAL,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date, period_type)
      );
    """)
    
    # Growth scores table
    cur.execute("DROP TABLE IF EXISTS growth_scores CASCADE;")
    cur.execute("""
      CREATE TABLE growth_scores (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        date                DATE NOT NULL,
        period_type         VARCHAR(10) NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly')),
        period_ending       DATE NOT NULL,
        revenue_growth      REAL,
        earnings_growth     REAL,
        fundamental_growth  REAL,
        market_expansion    REAL,
        composite           REAL,
        trend               VARCHAR(20),
        confidence          REAL,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date, period_type)
      );
    """)
    
    # Value scores table
    cur.execute("DROP TABLE IF EXISTS value_scores CASCADE;")
    cur.execute("""
      CREATE TABLE value_scores (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        date                DATE NOT NULL,
        period_type         VARCHAR(10) NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly')),
        period_ending       DATE NOT NULL,
        pe_score            REAL,
        dcf_score           REAL,
        relative_value      REAL,
        composite           REAL,
        trend               VARCHAR(20),
        confidence          REAL,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date, period_type)
      );
    """)
    
    # Momentum scores table
    cur.execute("DROP TABLE IF EXISTS momentum_scores CASCADE;")
    cur.execute("""
      CREATE TABLE momentum_scores (
        id                      SERIAL PRIMARY KEY,
        symbol                  VARCHAR(20) NOT NULL,
        date                    DATE NOT NULL,
        period_type             VARCHAR(10) NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly')),
        period_ending           DATE NOT NULL,
        price_momentum          REAL,
        fundamental_momentum    REAL,
        technical               REAL,
        volume_analysis         REAL,
        composite               REAL,
        trend                   VARCHAR(20),
        confidence              REAL,
        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date, period_type)
      );
    """)
    
    # Sentiment scores table
    cur.execute("DROP TABLE IF EXISTS sentiment_scores CASCADE;")
    cur.execute("""
      CREATE TABLE sentiment_scores (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        date                DATE NOT NULL,
        period_type         VARCHAR(10) NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly')),
        period_ending       DATE NOT NULL,
        analyst_sentiment   REAL,
        social_sentiment    REAL,
        market_sentiment    REAL,
        news_sentiment      REAL,
        composite           REAL,
        trend               VARCHAR(20),
        confidence          REAL,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date, period_type)
      );
    """)
    
    # Positioning scores table
    cur.execute("DROP TABLE IF EXISTS positioning_scores CASCADE;")
    cur.execute("""
      CREATE TABLE positioning_scores (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        date                DATE NOT NULL,
        period_type         VARCHAR(10) NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly')),
        period_ending       DATE NOT NULL,
        institutional       REAL,
        insider             REAL,
        short_interest      REAL,
        options_flow        REAL,
        composite           REAL,
        trend               VARCHAR(20),
        confidence          REAL,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date, period_type)
      );
    """)
    
    # Master scores table (composite)
    cur.execute("DROP TABLE IF EXISTS master_scores CASCADE;")
    cur.execute("""
      CREATE TABLE master_scores (
        id                  SERIAL PRIMARY KEY,
        symbol              VARCHAR(20) NOT NULL,
        date                DATE NOT NULL,
        period_type         VARCHAR(10) NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly')),
        period_ending       DATE NOT NULL,
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
        UNIQUE(symbol, date, period_type)
      );
    """)
    
    # Create indexes for performance
    cur.execute("CREATE INDEX idx_quality_scores_symbol_period ON quality_scores(symbol, period_type);")
    cur.execute("CREATE INDEX idx_growth_scores_symbol_period ON growth_scores(symbol, period_type);")
    cur.execute("CREATE INDEX idx_value_scores_symbol_period ON value_scores(symbol, period_type);")
    cur.execute("CREATE INDEX idx_momentum_scores_symbol_period ON momentum_scores(symbol, period_type);")
    cur.execute("CREATE INDEX idx_sentiment_scores_symbol_period ON sentiment_scores(symbol, period_type);")
    cur.execute("CREATE INDEX idx_positioning_scores_symbol_period ON positioning_scores(symbol, period_type);")
    cur.execute("CREATE INDEX idx_master_scores_symbol_period ON master_scores(symbol, period_type);")
    cur.execute("CREATE INDEX idx_master_scores_date ON master_scores(date);")

def get_period_ending_date(period_type):
    """Get the appropriate period ending date based on type"""
    today = datetime.now().date()
    
    if period_type == 'daily':
        return today
    elif period_type == 'weekly':
        # Get Friday of current week
        days_ahead = 4 - today.weekday()  # Friday is weekday 4
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        return today + timedelta(days_ahead)
    elif period_type == 'monthly':
        # Get last day of current month
        last_day = calendar.monthrange(today.year, today.month)[1]
        return datetime(today.year, today.month, last_day).date()

def insert_scores(cur, symbol, date, period_type, period_ending, scores_data):
    """Insert scores into all relevant tables with period information"""
    try:
        # Insert quality scores
        quality = scores_data.get('quality', {})
        cur.execute("""
            INSERT INTO quality_scores (symbol, date, period_type, period_ending, earnings_quality, 
                                      balance_strength, profitability, management, composite, trend, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) DO UPDATE SET
                period_ending = EXCLUDED.period_ending,
                earnings_quality = EXCLUDED.earnings_quality,
                balance_strength = EXCLUDED.balance_strength,
                profitability = EXCLUDED.profitability,
                management = EXCLUDED.management,
                composite = EXCLUDED.composite,
                trend = EXCLUDED.trend,
                confidence = EXCLUDED.confidence
        """, (
            symbol, date, period_type, period_ending,
            quality.get('earnings_quality'),
            quality.get('balance_strength'),
            quality.get('profitability'),
            quality.get('management'),
            quality.get('composite'),
            quality.get('trend'),
            90.0  # Default confidence
        ))
        
        # Insert growth scores
        growth = scores_data.get('growth', {})
        cur.execute("""
            INSERT INTO growth_scores (symbol, date, period_type, period_ending, revenue_growth, 
                                     earnings_growth, fundamental_growth, market_expansion, composite, trend, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) DO UPDATE SET
                period_ending = EXCLUDED.period_ending,
                revenue_growth = EXCLUDED.revenue_growth,
                earnings_growth = EXCLUDED.earnings_growth,
                fundamental_growth = EXCLUDED.fundamental_growth,
                market_expansion = EXCLUDED.market_expansion,
                composite = EXCLUDED.composite,
                trend = EXCLUDED.trend,
                confidence = EXCLUDED.confidence
        """, (
            symbol, date, period_type, period_ending,
            growth.get('revenue_growth'),
            growth.get('earnings_growth'),
            growth.get('fundamental_growth'),
            growth.get('market_expansion'),
            growth.get('composite'),
            growth.get('trend'),
            90.0  # Default confidence
        ))
        
        # Insert value scores
        value = scores_data.get('value', {})
        cur.execute("""
            INSERT INTO value_scores (symbol, date, period_type, period_ending, pe_score, 
                                    dcf_score, relative_value, composite, trend, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) DO UPDATE SET
                period_ending = EXCLUDED.period_ending,
                pe_score = EXCLUDED.pe_score,
                dcf_score = EXCLUDED.dcf_score,
                relative_value = EXCLUDED.relative_value,
                composite = EXCLUDED.composite,
                trend = EXCLUDED.trend,
                confidence = EXCLUDED.confidence
        """, (
            symbol, date, period_type, period_ending,
            value.get('pe_score'),
            value.get('dcf_score'),
            value.get('relative_value'),
            value.get('composite'),
            value.get('trend'),
            90.0  # Default confidence
        ))
        
        # Insert momentum scores
        momentum = scores_data.get('momentum', {})
        cur.execute("""
            INSERT INTO momentum_scores (symbol, date, period_type, period_ending, price_momentum, 
                                       fundamental_momentum, technical, volume_analysis, composite, trend, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) DO UPDATE SET
                period_ending = EXCLUDED.period_ending,
                price_momentum = EXCLUDED.price_momentum,
                fundamental_momentum = EXCLUDED.fundamental_momentum,
                technical = EXCLUDED.technical,
                volume_analysis = EXCLUDED.volume_analysis,
                composite = EXCLUDED.composite,
                trend = EXCLUDED.trend,
                confidence = EXCLUDED.confidence
        """, (
            symbol, date, period_type, period_ending,
            momentum.get('price_momentum'),
            momentum.get('fundamental_momentum'),
            momentum.get('technical'),
            momentum.get('volume_analysis'),
            momentum.get('composite'),
            momentum.get('trend'),
            90.0  # Default confidence
        ))
        
        # Insert sentiment scores
        sentiment = scores_data.get('sentiment', {})
        cur.execute("""
            INSERT INTO sentiment_scores (symbol, date, period_type, period_ending, analyst_sentiment, 
                                        social_sentiment, market_sentiment, news_sentiment, composite, trend, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) DO UPDATE SET
                period_ending = EXCLUDED.period_ending,
                analyst_sentiment = EXCLUDED.analyst_sentiment,
                social_sentiment = EXCLUDED.social_sentiment,
                market_sentiment = EXCLUDED.market_sentiment,
                news_sentiment = EXCLUDED.news_sentiment,
                composite = EXCLUDED.composite,
                trend = EXCLUDED.trend,
                confidence = EXCLUDED.confidence
        """, (
            symbol, date, period_type, period_ending,
            sentiment.get('analyst_sentiment'),
            sentiment.get('social_sentiment'),
            sentiment.get('market_sentiment'),
            sentiment.get('news_sentiment'),
            sentiment.get('composite'),
            sentiment.get('trend'),
            90.0  # Default confidence
        ))
        
        # Insert positioning scores
        positioning = scores_data.get('positioning', {})
        cur.execute("""
            INSERT INTO positioning_scores (symbol, date, period_type, period_ending, institutional, 
                                          insider, short_interest, options_flow, composite, trend, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) DO UPDATE SET
                period_ending = EXCLUDED.period_ending,
                institutional = EXCLUDED.institutional,
                insider = EXCLUDED.insider,
                short_interest = EXCLUDED.short_interest,
                options_flow = EXCLUDED.options_flow,
                composite = EXCLUDED.composite,
                trend = EXCLUDED.trend,
                confidence = EXCLUDED.confidence
        """, (
            symbol, date, period_type, period_ending,
            positioning.get('institutional'),
            positioning.get('insider'),
            positioning.get('short_interest'),
            positioning.get('options_flow'),
            positioning.get('composite'),
            positioning.get('trend'),
            90.0  # Default confidence
        ))
        
        # Insert master scores
        composite_score = scores_data.get('composite', 50)
        confidence_level = scores_data.get('confidence_level', 90)
        market_regime = scores_data.get('market_regime', 'neutral')
        
        # Determine recommendation
        if composite_score >= 70:
            recommendation = 'BUY'
        elif composite_score >= 50:
            recommendation = 'HOLD'
        else:
            recommendation = 'SELL'
        
        cur.execute("""
            INSERT INTO master_scores (symbol, date, period_type, period_ending, quality, growth, 
                                     value, momentum, sentiment, positioning, composite, market_regime, 
                                     confidence_level, recommendation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) DO UPDATE SET
                period_ending = EXCLUDED.period_ending,
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
            symbol, date, period_type, period_ending,
            quality.get('composite'),
            growth.get('composite'),
            value.get('composite'),
            momentum.get('composite'),
            sentiment.get('composite'),
            positioning.get('composite'),
            composite_score,
            market_regime,
            confidence_level,
            recommendation
        ))
        
        logging.info(f"✅ Inserted {period_type} scores for {symbol} on {date}: composite={composite_score:.1f}")
        
    except Exception as e:
        logging.error(f"❌ Error inserting {period_type} scores for {symbol}: {e}")
        raise

def calculate_and_store_scores(symbols, scoring_engine, period_type, batch_size=10):
    """Calculate scores for symbols and store in database with period type"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Create tables (will only create if not exist)
        logging.info("🔧 Creating/updating scoring tables...")
        create_unified_scores_tables(cur)
        conn.commit()
        
        today = datetime.now().date()
        period_ending = get_period_ending_date(period_type)
        total_symbols = len(symbols)
        successful = 0
        failed = 0
        
        logging.info(f"📊 Starting {period_type} score calculation for {total_symbols} symbols...")
        logging.info(f"📅 Period ending: {period_ending}")
        
        for i, symbol in enumerate(symbols):
            try:
                logging.info(f"🔍 Processing {symbol} ({i+1}/{total_symbols})...")
                
                # Calculate scores using our engine
                # TODO: In future, enhance scoring engine to accept period_type 
                # and calculate period-specific metrics
                scores_data = scoring_engine.calculate_composite_score(symbol)
                
                if scores_data:
                    # Insert into database
                    insert_scores(cur, symbol, today, period_type, period_ending, scores_data)
                    successful += 1
                    
                    # Commit every batch_size symbols
                    if (i + 1) % batch_size == 0:
                        conn.commit()
                        logging.info(f"✅ Committed batch at symbol {i+1}")
                else:
                    logging.warning(f"⚠️ No scores data returned for {symbol}")
                    failed += 1
                    
            except Exception as e:
                logging.error(f"❌ Error processing {symbol}: {e}")
                failed += 1
                continue
        
        # Final commit
        conn.commit()
        
        logging.info(f"🎉 {period_type.capitalize()} score calculation complete!")
        logging.info(f"✅ Successful: {successful}")
        logging.info(f"❌ Failed: {failed}")
        logging.info(f"📊 Success rate: {(successful/total_symbols)*100:.1f}%")
        
    except Exception as e:
        logging.error(f"❌ Critical error in {period_type} score calculation: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def main():
    # Get period type from environment variable
    period_type = os.environ.get('PERIOD_TYPE', 'daily').lower()
    
    if period_type not in ['daily', 'weekly', 'monthly']:
        logging.error(f"❌ Invalid PERIOD_TYPE: {period_type}. Must be daily, weekly, or monthly")
        sys.exit(1)
    
    logging.info(f"🚀 Starting {SCRIPT_NAME} for {period_type} scoring")
    
    try:
        # Initialize scoring engine
        logging.info("🔧 Initializing scoring engine...")
        scoring_engine = StockScoringEngine()
        
        # Get symbols from database based on period type
        logging.info(f"📋 Fetching symbols from database for {period_type} processing...")
        
        # Different limits based on period type
        if period_type == 'daily':
            default_limit = 100
        elif period_type == 'weekly':
            default_limit = 50
        else:  # monthly
            default_limit = 25
            
        limit = int(os.environ.get('SYMBOL_LIMIT', default_limit))
        symbols = get_symbols_from_db(period_type, limit=limit)
        
        if not symbols:
            logging.error("❌ No symbols found in database")
            return
        
        logging.info(f"📊 Found {len(symbols)} symbols to process")
        
        # Calculate and store scores
        calculate_and_store_scores(symbols, scoring_engine, period_type)
        
        logging.info(f"✅ {SCRIPT_NAME} completed successfully for {period_type} scoring")
        
    except Exception as e:
        logging.error(f"❌ {SCRIPT_NAME} failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()