#!/usr/bin/env python3
"""
Fixed Sentiment Data Loader - Real Google Trends and Reddit Data

This script loads REAL sentiment analysis data including:
- Google Trends search data (REAL - no API key required)
- Reddit sentiment from actual discussions (REAL - requires Reddit API)
- Replaces all fake/random data generation with real data sources

Data Sources:
- Google Trends: pytrends library (FREE, no API key)
- Reddit: PRAW library (FREE, requires app registration)
- Analyst: yfinance (existing, working)

To use this:
1. Install: pip install pytrends praw
2. Setup Reddit app at https://www.reddit.com/prefs/apps
3. Store credentials in AWS Secrets Manager
4. Replace old loadsentiment.py with this version
"""

import sys
import time
import logging
import json
import os
from datetime import datetime, date, timedelta
from typing import Dict, Optional

import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np

# Real data source imports
try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False
    logging.warning("⚠️  PyTrends not installed - install with: pip install pytrends")

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False
    logging.warning("⚠️  PRAW not installed - install with: pip install praw")

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    logging.warning("⚠️  TextBlob not installed - install with: pip install textblob")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ============================================================================
# REAL DATA: Google Trends Implementation
# ============================================================================

def get_google_trends_real(symbol: str) -> Dict:
    """
    Get REAL Google Trends data for a stock symbol

    Returns:
    - search_volume_index: Current search volume (0-100 scale)
    - search_trend_7d: 7-day trend (% change)
    - search_trend_30d: 30-day trend (% change)
    """
    data = {
        'symbol': symbol,
        'date': date.today(),
        'search_volume_index': None,
        'search_trend_7d': None,
        'search_trend_30d': None,
        'data_source': 'google_trends'
    }

    if not PYTRENDS_AVAILABLE:
        logging.warning(f"PyTrends not available - cannot fetch real Google Trends for {symbol}")
        return data

    try:
        logging.info(f"📊 Fetching REAL Google Trends data for {symbol}...")
        pytrends = TrendReq(hl='en-US', tz=360)

        # Search for stock symbol variations
        search_terms = [f"{symbol} stock price"]

        # Get 30-day interest
        pytrends.build_payload(search_terms, cat=0, timeframe='today 1-m', geo='US')
        trends_30d = pytrends.interest_over_time()

        if trends_30d.empty:
            logging.warning(f"No Google Trends data found for {symbol}")
            return data

        # Get the column (should be the search term)
        col = search_terms[0]
        if col not in trends_30d.columns:
            logging.warning(f"Unexpected Google Trends response for {symbol}")
            return data

        volume_data = trends_30d[col]

        # Current search volume (latest value, 0-100 scale)
        data['search_volume_index'] = int(volume_data.iloc[-1]) if len(volume_data) > 0 else None

        # 7-day trend
        if len(volume_data) >= 7:
            week_ago_avg = volume_data.iloc[-7:-0].mean()
            current_avg = volume_data.iloc[-3:].mean()
            if week_ago_avg > 0:
                data['search_trend_7d'] = float((current_avg - week_ago_avg) / week_ago_avg)

        # 30-day trend
        if len(volume_data) >= 14:
            month_avg = volume_data.mean()
            recent_avg = volume_data.iloc[-7:].mean()
            if month_avg > 0:
                data['search_trend_30d'] = float((recent_avg - month_avg) / month_avg)

        logging.info(f"✓ Got REAL Google Trends for {symbol}: volume={data['search_volume_index']}, 7d={data['search_trend_7d']:.3f}, 30d={data['search_trend_30d']:.3f}")
        time.sleep(2)  # Respect API rate limits

    except Exception as e:
        logging.error(f"❌ Error fetching Google Trends for {symbol}: {e}")
        # Return None values instead of random fake data

    return data

# ============================================================================
# REAL DATA: Reddit Sentiment Implementation
# ============================================================================

def get_reddit_sentiment_real(symbol: str, reddit_client=None) -> Dict:
    """
    Get REAL Reddit sentiment data for a stock symbol

    Returns:
    - reddit_mention_count: Actual mention count from search
    - reddit_sentiment_score: Real sentiment from comments (-1 to 1)
    - subreddits: Which subreddits mentioned the stock
    """
    data = {
        'symbol': symbol,
        'date': date.today(),
        'reddit_mention_count': 0,
        'reddit_sentiment_score': None,
        'reddit_positive_ratio': None,
        'subreddits_mentioned': [],
        'data_source': 'reddit'
    }

    if not PRAW_AVAILABLE or reddit_client is None:
        logging.warning(f"Reddit API not available - cannot fetch real Reddit data for {symbol}")
        return data

    try:
        logging.info(f"📱 Fetching REAL Reddit data for {symbol}...")

        # Search major investment subreddits
        target_subreddits = ['stocks', 'wallstreetbets', 'investing', 'options']
        all_sentiments = []
        total_mentions = 0

        for subreddit_name in target_subreddits:
            try:
                subreddit = reddit_client.subreddit(subreddit_name)

                # Search for symbol mentions
                submissions = subreddit.search(symbol, time_filter='week', limit=30)

                mention_count = 0
                sentiments = []

                for submission in submissions:
                    mention_count += 1

                    # Get sentiment from submission title + top comments
                    texts = [submission.title]

                    # Get top comments
                    submission.comments.list(limit=5)
                    for comment in submission.comments[:5]:
                        if hasattr(comment, 'body'):
                            texts.append(comment.body)

                    # Calculate sentiment using TextBlob
                    if TEXTBLOB_AVAILABLE:
                        full_text = " ".join(texts)
                        blob = TextBlob(full_text)
                        polarity = blob.sentiment.polarity  # -1 to 1
                        sentiments.append(polarity)

                if mention_count > 0:
                    total_mentions += mention_count
                    all_sentiments.extend(sentiments)
                    data['subreddits_mentioned'].append(subreddit_name)
                    logging.info(f"  r/{subreddit_name}: {mention_count} mentions")

            except Exception as e:
                logging.warning(f"Error fetching from r/{subreddit_name}: {e}")
                continue

            time.sleep(1)  # Respect rate limits

        # Aggregate results
        data['reddit_mention_count'] = total_mentions

        if all_sentiments:
            avg_sentiment = sum(all_sentiments) / len(all_sentiments)
            data['reddit_sentiment_score'] = float(avg_sentiment)

            positive = sum(1 for s in all_sentiments if s > 0.1)
            data['reddit_positive_ratio'] = float(positive / len(all_sentiments))

            logging.info(f"✓ Got REAL Reddit data for {symbol}: {total_mentions} mentions, sentiment={avg_sentiment:.3f}")
        else:
            logging.warning(f"No Reddit mentions found for {symbol}")

    except Exception as e:
        logging.error(f"❌ Error fetching Reddit data for {symbol}: {e}")
        # Return incomplete data instead of random fake data

    return data

# ============================================================================
# Setup Reddit Client
# ============================================================================

def get_reddit_client():
    """
    Get Reddit API client with credentials from Secrets Manager

    Requires credentials in AWS Secrets Manager:
    {
        "reddit_client_id": "...",
        "reddit_client_secret": "...",
        "reddit_user_agent": "StocksApp/1.0"
    }
    """
    try:
        import boto3

        secret_arn = os.environ.get("REDDIT_SECRET_ARN")
        if not secret_arn:
            logging.warning("⚠️  REDDIT_SECRET_ARN not set - Reddit sentiment will be unavailable")
            return None

        secret_str = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)["SecretString"]
        secrets = json.loads(secret_str)

        reddit = praw.Reddit(
            client_id=secrets.get('reddit_client_id'),
            client_secret=secrets.get('reddit_client_secret'),
            user_agent=secrets.get('reddit_user_agent', 'StocksApp/1.0')
        )

        logging.info("✓ Connected to Reddit API")
        return reddit

    except Exception as e:
        logging.error(f"❌ Failed to initialize Reddit client: {e}")
        logging.error("Set up Reddit app at: https://www.reddit.com/prefs/apps")
        return None

# ============================================================================
# Database Functions
# ============================================================================

def get_db_config():
    """Get database configuration from Secrets Manager or environment"""
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
            "dbname": sec["dbname"]
        }
    except Exception:
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

def save_sentiment_data(conn, data: Dict):
    """Save sentiment data to database"""
    try:
        cursor = conn.cursor()

        # Insert Google Trends data
        if data.get('google_trends'):
            gt = data['google_trends']
            cursor.execute("""
                INSERT INTO sentiment (symbol, date, search_volume_index, search_trend_7d, search_trend_30d)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    search_volume_index = EXCLUDED.search_volume_index,
                    search_trend_7d = EXCLUDED.search_trend_7d,
                    search_trend_30d = EXCLUDED.search_trend_30d
            """, (gt['symbol'], gt['date'], gt['search_volume_index'], gt['search_trend_7d'], gt['search_trend_30d']))

        # Insert Reddit data
        if data.get('reddit'):
            rd = data['reddit']
            cursor.execute("""
                INSERT INTO sentiment (symbol, date, reddit_mention_count, reddit_sentiment_score)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    reddit_mention_count = EXCLUDED.reddit_mention_count,
                    reddit_sentiment_score = EXCLUDED.reddit_sentiment_score
            """, (rd['symbol'], rd['date'], rd['reddit_mention_count'], rd['reddit_sentiment_score']))

        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Database error: {e}")
        conn.rollback()
        return False

# ============================================================================
# Main Execution
# ============================================================================

def main():
    logging.info("=" * 80)
    logging.info("🚀 Starting Sentiment Data Loader - REAL DATA SOURCES")
    logging.info("=" * 80)
    logging.info("")

    # Get database connection
    cfg = get_db_config()
    try:
        conn = psycopg2.connect(**cfg)
        logging.info("✓ Connected to database")
    except Exception as e:
        logging.error(f"❌ Failed to connect to database: {e}")
        return

    # Get Reddit client (optional)
    reddit_client = None
    if PRAW_AVAILABLE:
        reddit_client = get_reddit_client()

    # List of stocks to fetch sentiment for
    stocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'JPM', 'V', 'WMT']

    for symbol in stocks:
        logging.info(f"\n📈 Processing {symbol}...")

        sentiment_data = {'symbol': symbol}

        # Get REAL Google Trends data
        sentiment_data['google_trends'] = get_google_trends_real(symbol)

        # Get REAL Reddit sentiment (if client available)
        if reddit_client:
            sentiment_data['reddit'] = get_reddit_sentiment_real(symbol, reddit_client)
        else:
            sentiment_data['reddit'] = {'symbol': symbol, 'date': date.today(), 'reddit_mention_count': None}

        # Save to database
        if save_sentiment_data(conn, sentiment_data):
            logging.info(f"✓ Saved sentiment data for {symbol}")
        else:
            logging.error(f"❌ Failed to save sentiment data for {symbol}")

    conn.close()
    logging.info("\n" + "=" * 80)
    logging.info("✓ Sentiment data load complete")
    logging.info("=" * 80)

if __name__ == "__main__":
    main()
