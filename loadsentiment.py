#!/usr/bin/env python3
"""
Sentiment Data Loader Script - Auth deployment trigger v4 - Empty database population

This script loads comprehensive sentiment analysis data including:
- Analyst sentiment (recommendations, price targets, revisions)
- Social sentiment (Reddit mentions, news sentiment)
- Market sentiment indicators (put/call ratios, options flow)
- Google Trends data for search interest
Updated: 2025-07-15 - Trigger deployment for sentiment analysis data

Data Sources:
- Primary: yfinance for analyst recommendations
- Reddit: PRAW (Python Reddit API Wrapper) for social sentiment
- News: NewsAPI or Alpha Vantage for news sentiment
- Google Trends: pytrends for search volume data
- Options: yfinance options data

Author: Financial Dashboard System
"""

import sys
import time
import logging
import json
import os
import gc
import resource
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Sentiment analysis imports
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    logging.warning("TextBlob not available - sentiment analysis will be limited")

try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False
    logging.warning("PyTrends not available - Google Trends data will be unavailable")

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False
    logging.warning("⚠️  PRAW not installed - Reddit sentiment will be unavailable. Install with: pip install praw")

# Script configuration
SCRIPT_NAME = "loadsentiment.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def log_mem(stage: str):
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mb = usage / 1024 if sys.platform.startswith("linux") else usage / (1024 * 1024)
    logging.info(f"[MEM] {stage}: {mb:.1f} MB RSS")

def get_db_config():
    """Get database configuration"""
    try:
        import boto3
        secret_str = boto3.client("secretsmanager") \
                         .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
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
    if not PRAW_AVAILABLE:
        logging.warning("⚠️  PRAW not available - Reddit sentiment will be unavailable")
        return None

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
        logging.warning(f"⚠️  Failed to initialize Reddit client: {e}")
        logging.warning("Set up Reddit app at: https://www.reddit.com/prefs/apps")
        return None

def safe_float(value, default=None):
    """Convert to float safely"""
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def calculate_sentiment_score(text: str) -> float:
    """Calculate sentiment score from text using TextBlob. Returns None if unavailable."""
    if not TEXTBLOB_AVAILABLE or not text:
        return None  # No real sentiment data available

    try:
        blob = TextBlob(text)
        # TextBlob polarity ranges from -1 (negative) to 1 (positive)
        return blob.sentiment.polarity
    except Exception:
        return None  # Error - return None instead of fake 0.0

class AnalystSentimentCollector:
    """Collect analyst sentiment data from various sources"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.ticker = yf.Ticker(symbol)
    
    def get_analyst_recommendations(self) -> Dict:
        """Get analyst recommendations and price targets"""
        data = {
            'symbol': self.symbol,
            'date': date.today(),
            'strong_buy_count': 0,
            'buy_count': 0,
            'hold_count': 0,
            'sell_count': 0,
            'strong_sell_count': 0,
            'total_analysts': 0,
            'avg_price_target': None,
            'high_price_target': None,
            'low_price_target': None,
            'price_target_vs_current': None,
            'recommendation_mean': None
        }
        
        try:
            # Get recommendation data
            recommendations = self.ticker.recommendations
            if recommendations is not None and not recommendations.empty:
                try:
                    # Get latest recommendations (last 90 days)
                    recent_date = datetime.now() - timedelta(days=90)
                    # Try datetime comparison first
                    try:
                        rec_index = pd.to_datetime(recommendations.index)
                        mask = rec_index >= pd.Timestamp(recent_date)
                        recent_recs = recommendations[mask]
                    except (TypeError, ValueError):
                        # If index isn't datetime, use last 90 rows as proxy
                        recent_recs = recommendations.tail(90)
                except Exception as e:
                    logging.warning(f"Error filtering recommendations for {self.symbol}: {e}")
                    recent_recs = recommendations.tail(90)  # Fallback
                
                if not recent_recs.empty:
                    # Aggregate recommendation counts
                    rec_counts = recent_recs.groupby('To Grade').size()
                    
                    # Map different recommendation formats
                    strong_buy_terms = ['Strong Buy', 'Buy', 'Outperform', 'Overweight']
                    buy_terms = ['Buy', 'Positive', 'Add']
                    hold_terms = ['Hold', 'Neutral', 'Equal-Weight', 'Market Perform']
                    sell_terms = ['Sell', 'Negative', 'Reduce']
                    strong_sell_terms = ['Strong Sell', 'Underperform', 'Underweight']
                    
                    for grade, count in rec_counts.items():
                        grade_upper = str(grade).upper()
                        if any(term.upper() in grade_upper for term in strong_buy_terms):
                            data['strong_buy_count'] += count
                        elif any(term.upper() in grade_upper for term in buy_terms):
                            data['buy_count'] += count
                        elif any(term.upper() in grade_upper for term in hold_terms):
                            data['hold_count'] += count
                        elif any(term.upper() in grade_upper for term in sell_terms):
                            data['sell_count'] += count
                        elif any(term.upper() in grade_upper for term in strong_sell_terms):
                            data['strong_sell_count'] += count
                        else:
                            data['hold_count'] += count  # Default to hold
                    
                    data['total_analysts'] = sum([
                        data['strong_buy_count'], data['buy_count'], data['hold_count'],
                        data['sell_count'], data['strong_sell_count']
                    ])
            
            # Get price targets from info
            info = self.ticker.info
            if info:
                data['avg_price_target'] = safe_float(info.get('targetMeanPrice'))
                data['high_price_target'] = safe_float(info.get('targetHighPrice'))
                data['low_price_target'] = safe_float(info.get('targetLowPrice'))
                data['recommendation_mean'] = safe_float(info.get('recommendationMean'))
                
                current_price = safe_float(info.get('currentPrice'))
                if current_price and data['avg_price_target']:
                    data['price_target_vs_current'] = (data['avg_price_target'] - current_price) / current_price
        
        except Exception as e:
            logging.warning(f"Error collecting analyst data for {self.symbol}: {e}")
        
        return data
    
    def get_analyst_revisions(self) -> Dict:
        """Get recent analyst estimate revisions"""
        data = {
            'symbol': self.symbol,
            'date': date.today(),
            'eps_revisions_up_last_30d': 0,
            'eps_revisions_down_last_30d': 0,
            'revenue_revisions_up_last_30d': 0,
            'revenue_revisions_down_last_30d': 0,
            'upgrades_last_30d': 0,
            'downgrades_last_30d': 0,
            'initiations_last_30d': 0
        }
        
        try:
            # Get upgrades/downgrades from recommendations
            recommendations = self.ticker.recommendations
            if recommendations is not None and not recommendations.empty:
                try:
                    # Get last 30 days of recommendations
                    # The recommendations df may have different index types, so handle gracefully
                    recent_date = datetime.now() - timedelta(days=30)

                    # Try to filter by date if index is datetime, otherwise just take last rows
                    try:
                        # Assume index is datetime-like
                        rec_index = pd.to_datetime(recommendations.index)
                        mask = rec_index >= pd.Timestamp(recent_date)
                        recent_recs = recommendations[mask]
                    except (TypeError, ValueError):
                        # If index isn't datetime, just use the last 30 rows as proxy for 30 days
                        recent_recs = recommendations.tail(30)

                    if not recent_recs.empty:
                        # Simple count of recommendations in last 30 days as proxy for activity
                        data['initiations_last_30d'] = len(recent_recs)

                        # Could enhance this with more sophisticated upgrade/downgrade detection
                        # For now, use simple heuristics
                        if 'To Grade' in recent_recs.columns:
                            try:
                                positive_actions = recent_recs[recent_recs['To Grade'].str.contains('Buy|Outperform|Overweight', case=False, na=False)]
                                negative_actions = recent_recs[recent_recs['To Grade'].str.contains('Sell|Underperform|Underweight', case=False, na=False)]

                                data['upgrades_last_30d'] = len(positive_actions)
                                data['downgrades_last_30d'] = len(negative_actions)
                            except Exception as e:
                                logging.warning(f"Error parsing analyst grades for {self.symbol}: {e}")
                except Exception as e:
                    logging.warning(f"Error filtering recommendations for {self.symbol}: {e}")
        
        except Exception as e:
            logging.warning(f"Error collecting analyst revisions for {self.symbol}: {e}")
        
        return data

class SocialSentimentCollector:
    """Collect social sentiment data from various sources"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
    
    def get_reddit_sentiment(self, reddit_client=None) -> Dict:
        """Get REAL Reddit sentiment from actual discussions - NO FAKE DATA"""
        data = {
            'symbol': self.symbol,
            'date': date.today(),
            'reddit_mention_count': None,
            'reddit_sentiment_score': None,
            'reddit_volume_normalized_sentiment': None
        }

        # If no Reddit client available, return NULL values
        if reddit_client is None:
            logging.warning(f"⚠️  Reddit sentiment unavailable for {self.symbol} - API not configured. Returning NULL.")
            return data

        try:
            logging.info(f"📱 Fetching REAL Reddit data for {self.symbol}...")

            # Search major investment subreddits
            target_subreddits = ['stocks', 'wallstreetbets', 'investing', 'options', 'SecurityAnalysis']
            all_sentiments = []
            total_mentions = 0

            for subreddit_name in target_subreddits:
                try:
                    subreddit = reddit_client.subreddit(subreddit_name)

                    # Search for symbol mentions in recent posts
                    submissions = subreddit.search(self.symbol, time_filter='week', limit=25)

                    mention_count = 0
                    sentiments = []

                    for submission in submissions:
                        mention_count += 1

                        # Get sentiment from submission title
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
                        logging.info(f"  r/{subreddit_name}: {mention_count} mentions")

                except Exception as e:
                    logging.warning(f"Error fetching from r/{subreddit_name}: {e}")
                    continue

                time.sleep(1)  # Respect rate limits

            # Aggregate results
            data['reddit_mention_count'] = total_mentions if total_mentions > 0 else None

            if all_sentiments:
                avg_sentiment = sum(all_sentiments) / len(all_sentiments)
                data['reddit_sentiment_score'] = float(avg_sentiment)
                data['reddit_volume_normalized_sentiment'] = float(avg_sentiment)
                logging.info(f"✓ Got REAL Reddit data for {self.symbol}: {total_mentions} mentions, sentiment={avg_sentiment:.3f}")
            else:
                logging.warning(f"No Reddit mentions found for {self.symbol}")

        except Exception as e:
            logging.error(f"❌ Error fetching Reddit data for {self.symbol}: {e}")
            # Return None values instead of fake data

        return data
    
    def get_google_trends(self) -> Dict:
        """Get REAL Google Trends search data - NO FAKE DATA"""
        data = {
            'symbol': self.symbol,
            'date': date.today(),
            'search_volume_index': None,
            'search_trend_7d': None,
            'search_trend_30d': None
        }

        try:
            if PYTRENDS_AVAILABLE:
                pytrends = TrendReq(hl='en-US', tz=360)

                # Build search terms
                search_terms = [f"{self.symbol} stock", self.symbol]

                # Get trends for last 30 days
                pytrends.build_payload(search_terms[:1], cat=0, timeframe='today 1-m', geo='US', gprop='')
                trends_data = pytrends.interest_over_time()

                if not trends_data.empty and f"{self.symbol} stock" in trends_data.columns:
                    volume_data = trends_data[f"{self.symbol} stock"]

                    # Current search volume (latest value)
                    data['search_volume_index'] = int(volume_data.iloc[-1]) if len(volume_data) > 0 else None

                    # Calculate trends
                    if len(volume_data) >= 7:
                        week_ago_avg = volume_data.iloc[-7:].mean()
                        current_avg = volume_data.iloc[-3:].mean()
                        if week_ago_avg > 0:
                            data['search_trend_7d'] = (current_avg - week_ago_avg) / week_ago_avg

                    if len(volume_data) >= 30:
                        month_avg = volume_data.mean()
                        recent_avg = volume_data.iloc[-7:].mean()
                        if month_avg > 0:
                            data['search_trend_30d'] = (recent_avg - month_avg) / month_avg

                # Small delay to respect API limits
                time.sleep(1)
            else:
                # Return NULL instead of fake data if pytrends not available
                logging.warning(f"⚠️  PyTrends not available - Google Trends data unavailable for {self.symbol}")

        except Exception as e:
            logging.warning(f"Error collecting Google Trends for {self.symbol}: {e}")
            # Return NULL values instead of generating fake data

        return data
    
    def get_news_sentiment(self) -> Dict:
        """Get REAL news sentiment analysis - return NULL if unavailable"""
        data = {
            'symbol': self.symbol,
            'date': date.today(),
            'news_article_count': None,
            'news_sentiment_score': None,
            'news_source_quality_weight': None
        }
        
        try:
            # Get recent news from yfinance
            ticker = yf.Ticker(self.symbol)
            news = ticker.news
            
            if news and len(news) > 0:
                # Analyze recent news (last 7 days)
                recent_date = datetime.now() - timedelta(days=7)
                recent_news = []
                
                for article in news:
                    try:
                        # Parse article timestamp
                        article_time = datetime.fromtimestamp(article.get('providerPublishTime', 0))
                        if article_time >= recent_date:
                            recent_news.append(article)
                    except Exception:
                        continue
                
                data['news_article_count'] = len(recent_news)
                
                if recent_news:
                    # Calculate sentiment from titles and summaries
                    sentiments = []
                    quality_weights = []
                    
                    for article in recent_news:
                        title = article.get('title', '')
                        summary = article.get('summary', '')
                        publisher = article.get('publisher', '')
                        
                        # Combine title and summary for sentiment analysis
                        text = f"{title} {summary}"
                        sentiment = calculate_sentiment_score(text)
                        sentiments.append(sentiment)
                        
                        # Simple quality weighting based on publisher
                        quality_weight = 1.0
                        trusted_sources = ['Reuters', 'Bloomberg', 'Associated Press', 'MarketWatch', 'Yahoo Finance', 'CNBC']
                        if any(source.lower() in publisher.lower() for source in trusted_sources):
                            quality_weight = 1.5
                        quality_weights.append(quality_weight)
                    
                    # Calculate weighted sentiment
                    if sentiments:
                        total_weight = sum(quality_weights)
                        weighted_sentiment = sum(s * w for s, w in zip(sentiments, quality_weights)) / total_weight
                        data['news_sentiment_score'] = max(-1.0, min(1.0, weighted_sentiment))
                        data['news_source_quality_weight'] = total_weight / len(quality_weights)
        
        except Exception as e:
            logging.warning(f"Error collecting news sentiment for {self.symbol}: {e}")
        
        return data

def calculate_rsi(prices, period=14):
    """Calculate RSI (Relative Strength Index) from prices"""
    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 1
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Convert RSI to sentiment: RSI > 70 = overbought (negative), RSI < 30 = oversold (positive)
    # Neutral at 50 (RSI of 50 = 0.0 sentiment)
    # Returns value between -1.0 and 1.0
    sentiment = (50 - rsi) / 50.0  # Maps RSI to -1 to 1 range
    return max(-1.0, min(1.0, sentiment))

def calculate_macd_sentiment(prices):
    """Calculate MACD-based sentiment from prices"""
    if len(prices) < 26:
        return None

    prices_array = np.array(prices, dtype=float)

    # Calculate EMAs
    ema_12 = pd.Series(prices_array).ewm(span=12, adjust=False).mean().values
    ema_26 = pd.Series(prices_array).ewm(span=26, adjust=False).mean().values

    # MACD = EMA12 - EMA26
    macd = ema_12 - ema_26

    # Get the latest MACD value and the previous one
    current_macd = float(macd[-1])
    prev_macd = float(macd[-2]) if len(macd) > 1 else current_macd

    # Momentum: positive if MACD is increasing, negative if decreasing
    macd_momentum = current_macd - prev_macd

    # Convert to sentiment between -1 and 1
    # Normalize based on typical MACD ranges
    sentiment = float(np.tanh(current_macd / 0.5))  # Tanh keeps output in -1 to 1 range
    return max(-1.0, min(1.0, sentiment))

def get_fallback_sentiment(symbol: str) -> Dict:
    """Get technical sentiment based on recent price movement - NO external API calls"""
    try:
        # Fetch recent price data (last 90 days)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="90d")

        if hist.empty or len(hist) < 14:
            logging.warning(f"Insufficient historical data for {symbol}")
            return {'price_change_sentiment': None}

        # Get closing prices
        prices = hist['Close'].values

        # Calculate RSI-based sentiment
        rsi_sentiment = calculate_rsi(prices, period=14)

        # Calculate MACD-based sentiment
        macd_sentiment = calculate_macd_sentiment(prices)

        # Calculate price momentum (% change over last 5, 10, 20 days)
        recent_price = prices[-1]
        price_5d_ago = prices[-6] if len(prices) >= 6 else prices[0]
        price_10d_ago = prices[-11] if len(prices) >= 11 else prices[0]
        price_20d_ago = prices[-21] if len(prices) >= 21 else prices[0]

        momentum_5d = (recent_price - price_5d_ago) / price_5d_ago if price_5d_ago > 0 else 0
        momentum_10d = (recent_price - price_10d_ago) / price_10d_ago if price_10d_ago > 0 else 0
        momentum_20d = (recent_price - price_20d_ago) / price_20d_ago if price_20d_ago > 0 else 0

        # Normalize momentum to -1 to 1 range (assume ±10% is extreme)
        momentum_sentiment = np.tanh(momentum_10d * 2.5)

        # Combine all sentiments (weighted average)
        sentiments = []
        if rsi_sentiment is not None:
            sentiments.append(rsi_sentiment * 0.4)  # RSI: 40% weight
        if macd_sentiment is not None:
            sentiments.append(macd_sentiment * 0.3)  # MACD: 30% weight
        if momentum_sentiment is not None:
            sentiments.append(momentum_sentiment * 0.3)  # Momentum: 30% weight

        if sentiments:
            technical_sentiment = sum(sentiments)
            return {
                'price_change_sentiment': float(technical_sentiment),
                'rsi_sentiment': rsi_sentiment,
                'macd_sentiment': macd_sentiment,
                'momentum_10d': momentum_sentiment
            }
        else:
            return {'price_change_sentiment': None}

    except Exception as e:
        logging.warning(f"Could not calculate technical sentiment for {symbol}: {e}")
        return {'price_change_sentiment': None}

def process_symbol_sentiment(symbol: str, reddit_client=None) -> Optional[Dict]:
    """Process comprehensive sentiment data for a symbol"""
    try:
        # Collect analyst sentiment
        analyst_collector = AnalystSentimentCollector(symbol)
        analyst_data = analyst_collector.get_analyst_recommendations()
        analyst_revisions = analyst_collector.get_analyst_revisions()

        # Collect social sentiment (Reddit + Google Trends only, NO news)
        social_collector = SocialSentimentCollector(symbol)
        reddit_data = social_collector.get_reddit_sentiment(reddit_client)
        trends_data = social_collector.get_google_trends()

        # Always try fallback sentiment - it's our most reliable source
        fallback_data = get_fallback_sentiment(symbol)

        # Combine all data (analyst, reddit, trends, technical fallback)
        result = {
            'symbol': symbol,
            'date': date.today(),
            'analyst_sentiment': {**analyst_data, **analyst_revisions},
            'social_sentiment': {**reddit_data, **trends_data, **fallback_data}
        }

        return result

    except Exception as e:
        logging.error(f"Error processing sentiment for {symbol}: {e}")
        return None

def create_sentiment_tables(cur, conn):
    """Create sentiment analysis tables"""
    logging.info("Creating sentiment analysis tables...")
    
    # Analyst sentiment table
    analyst_sql = """
    CREATE TABLE IF NOT EXISTS analyst_sentiment_analysis (
        symbol VARCHAR(20),
        date DATE,
        strong_buy_count INTEGER DEFAULT 0,
        buy_count INTEGER DEFAULT 0,
        hold_count INTEGER DEFAULT 0,
        sell_count INTEGER DEFAULT 0,
        strong_sell_count INTEGER DEFAULT 0,
        total_analysts INTEGER DEFAULT 0,
        upgrades_last_30d INTEGER DEFAULT 0,
        downgrades_last_30d INTEGER DEFAULT 0,
        initiations_last_30d INTEGER DEFAULT 0,
        avg_price_target DECIMAL(10,4),
        high_price_target DECIMAL(10,4),
        low_price_target DECIMAL(10,4),
        price_target_vs_current DECIMAL(8,4),
        eps_revisions_up_last_30d INTEGER DEFAULT 0,
        eps_revisions_down_last_30d INTEGER DEFAULT 0,
        revenue_revisions_up_last_30d INTEGER DEFAULT 0,
        revenue_revisions_down_last_30d INTEGER DEFAULT 0,
        recommendation_mean DECIMAL(4,2),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """
    
    # Social sentiment table
    social_sql = """
    CREATE TABLE IF NOT EXISTS social_sentiment_analysis (
        symbol VARCHAR(20),
        date DATE,
        reddit_mention_count INTEGER DEFAULT 0,
        reddit_sentiment_score DECIMAL(6,4) DEFAULT 0,
        reddit_volume_normalized_sentiment DECIMAL(6,4) DEFAULT 0,
        search_volume_index INTEGER DEFAULT 0,
        search_trend_7d DECIMAL(8,4) DEFAULT 0,
        search_trend_30d DECIMAL(8,4) DEFAULT 0,
        news_article_count INTEGER DEFAULT 0,
        news_sentiment_score DECIMAL(6,4) DEFAULT 0,
        news_source_quality_weight DECIMAL(5,2) DEFAULT 0,
        social_media_volume INTEGER DEFAULT 0,
        viral_score DECIMAL(5,2) DEFAULT 0,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """

    # Main sentiment table (used by API)
    sentiment_sql = """
    CREATE TABLE IF NOT EXISTS sentiment (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        sentiment_score DOUBLE PRECISION,
        positive_mentions INTEGER,
        negative_mentions INTEGER,
        neutral_mentions INTEGER,
        total_mentions INTEGER,
        source VARCHAR(50),
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date, source)
    );
    """

    # Execute table creation
    cur.execute(analyst_sql)
    cur.execute(social_sql)
    cur.execute(sentiment_sql)
    
    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_analyst_sentiment_symbol ON analyst_sentiment_analysis(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_analyst_sentiment_date ON analyst_sentiment_analysis(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_analyst_sentiment_mean ON analyst_sentiment_analysis(recommendation_mean);",
        "CREATE INDEX IF NOT EXISTS idx_analyst_sentiment_target ON analyst_sentiment_analysis(price_target_vs_current DESC);",
        
        "CREATE INDEX IF NOT EXISTS idx_social_sentiment_symbol ON social_sentiment_analysis(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_social_sentiment_date ON social_sentiment_analysis(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_social_sentiment_reddit ON social_sentiment_analysis(reddit_sentiment_score DESC);",
        "CREATE INDEX IF NOT EXISTS idx_social_sentiment_news ON social_sentiment_analysis(news_sentiment_score DESC);",
        "CREATE INDEX IF NOT EXISTS idx_social_sentiment_volume ON social_sentiment_analysis(search_volume_index DESC);"
    ]
    
    for index_sql in indexes:
        cur.execute(index_sql)
    
    conn.commit()
    logging.info("Sentiment analysis tables created successfully")

def load_sentiment_batch(symbols: List[str], conn, cur, batch_size: int = 10) -> Tuple[int, int]:
    """Load sentiment data in batches"""
    total_processed = 0
    total_inserted = 0
    failed_symbols = []

    # Initialize Reddit client once for all symbols
    reddit_client = get_reddit_client()
    if reddit_client is None:
        logging.warning("⚠️  Reddit API not configured - Reddit sentiment will be NULL for all symbols")
    else:
        logging.info("✓ Reddit API initialized for sentiment collection")

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        logging.info(f"Processing sentiment batch {batch_num}/{total_batches}: {len(batch)} symbols")
        log_mem(f"Sentiment batch {batch_num} start")

        # Process symbols sequentially for sentiment (to respect API limits)
        sentiment_data = []
        for symbol in batch:
            try:
                data = process_symbol_sentiment(symbol, reddit_client)
                if data:
                    sentiment_data.append(data)
                else:
                    failed_symbols.append(symbol)
                total_processed += 1
                
                # Add delay between symbols to respect API limits
                time.sleep(1)
                
            except Exception as e:
                failed_symbols.append(symbol)
                logging.error(f"Exception processing sentiment for {symbol}: {e}")
                total_processed += 1
        
        # Insert to database
        if sentiment_data:
            try:
                analyst_data = []
                social_data = []
                
                for item in sentiment_data:
                    symbol = item['symbol']
                    date_val = item['date']
                    
                    # Analyst sentiment data
                    analyst = item['analyst_sentiment']
                    analyst_data.append((
                        symbol, date_val,
                        analyst.get('strong_buy_count', 0),
                        analyst.get('buy_count', 0),
                        analyst.get('hold_count', 0),
                        analyst.get('sell_count', 0),
                        analyst.get('strong_sell_count', 0),
                        analyst.get('total_analysts', 0),
                        analyst.get('upgrades_last_30d', 0),
                        analyst.get('downgrades_last_30d', 0),
                        analyst.get('initiations_last_30d', 0),
                        analyst.get('avg_price_target'),
                        analyst.get('high_price_target'),
                        analyst.get('low_price_target'),
                        analyst.get('price_target_vs_current'),
                        analyst.get('eps_revisions_up_last_30d', 0),
                        analyst.get('eps_revisions_down_last_30d', 0),
                        analyst.get('revenue_revisions_up_last_30d', 0),
                        analyst.get('revenue_revisions_down_last_30d', 0),
                        analyst.get('recommendation_mean')
                    ))
                    
                    # Social sentiment data
                    social = item['social_sentiment']
                    social_data.append((
                        symbol, date_val,
                        social.get('reddit_mention_count', 0),
                        social.get('reddit_sentiment_score', 0.0),
                        social.get('reddit_volume_normalized_sentiment', 0.0),
                        social.get('search_volume_index', 0),
                        social.get('search_trend_7d', 0.0),
                        social.get('search_trend_30d', 0.0),
                        social.get('news_article_count', 0),
                        social.get('news_sentiment_score', 0.0),
                        social.get('news_source_quality_weight', 0.0),
                        0,  # social_media_volume (placeholder)
                        0.0  # viral_score (placeholder)
                    ))
                
                # Execute batch inserts for analyst data
                if analyst_data:
                    analyst_insert = """
                        INSERT INTO analyst_sentiment_analysis
                        (symbol, date, strong_buy_count, buy_count, hold_count, sell_count,
                         strong_sell_count, total_analysts, upgrades_last_30d, downgrades_last_30d, initiations_last_30d,
                         avg_price_target, high_price_target, low_price_target,
                         price_target_vs_current, eps_revisions_up_last_30d, eps_revisions_down_last_30d,
                         revenue_revisions_up_last_30d, revenue_revisions_down_last_30d,
                         recommendation_mean, analyst_count)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            strong_buy_count = EXCLUDED.strong_buy_count,
                            buy_count = EXCLUDED.buy_count,
                            hold_count = EXCLUDED.hold_count,
                            sell_count = EXCLUDED.sell_count,
                            strong_sell_count = EXCLUDED.strong_sell_count,
                            total_analysts = EXCLUDED.total_analysts,
                            upgrades_last_30d = EXCLUDED.upgrades_last_30d,
                            downgrades_last_30d = EXCLUDED.downgrades_last_30d,
                            initiations_last_30d = EXCLUDED.initiations_last_30d,
                            avg_price_target = EXCLUDED.avg_price_target,
                            high_price_target = EXCLUDED.high_price_target,
                            low_price_target = EXCLUDED.low_price_target,
                            price_target_vs_current = EXCLUDED.price_target_vs_current,
                            eps_revisions_up_last_30d = EXCLUDED.eps_revisions_up_last_30d,
                            eps_revisions_down_last_30d = EXCLUDED.eps_revisions_down_last_30d,
                            revenue_revisions_up_last_30d = EXCLUDED.revenue_revisions_up_last_30d,
                            revenue_revisions_down_last_30d = EXCLUDED.revenue_revisions_down_last_30d,
                            recommendation_mean = EXCLUDED.recommendation_mean,
                            analyst_count = EXCLUDED.analyst_count
                    """
                    for analyst_tuple in analyst_data:
                        try:
                            # analyst_tuple is (symbol, date, strong_buy, buy, hold, sell, strong_sell,
                            #                   total, upgrades, downgrades, initiations, avg_target, high_target,
                            #                   low_target, price_vs_current, eps_up, eps_down, rev_up, rev_down, rec_mean)
                            symbol = analyst_tuple[0]
                            date_val = analyst_tuple[1]
                            strong_buy = analyst_tuple[2]
                            buy = analyst_tuple[3]
                            hold = analyst_tuple[4]
                            sell = analyst_tuple[5]
                            strong_sell = analyst_tuple[6]
                            total = analyst_tuple[7]
                            upgrades = analyst_tuple[8]
                            downgrades = analyst_tuple[9]
                            initiations = analyst_tuple[10]
                            avg_target = analyst_tuple[11]
                            high_target = analyst_tuple[12]
                            low_target = analyst_tuple[13]
                            price_vs_current = analyst_tuple[14]
                            eps_up = analyst_tuple[15]
                            eps_down = analyst_tuple[16]
                            rev_up = analyst_tuple[17]
                            rev_down = analyst_tuple[18]
                            rec_mean = analyst_tuple[19]

                            cur.execute(analyst_insert, (
                                symbol, date_val, strong_buy, buy, hold, sell, strong_sell,
                                total, upgrades, downgrades, initiations,
                                avg_target, high_target, low_target,
                                price_vs_current, eps_up, eps_down, rev_up, rev_down,
                                rec_mean, total
                            ))
                            logging.debug(f"✓ Inserted analyst data for {symbol}: {total} analysts")
                        except Exception as e:
                            logging.debug(f"Could not insert analyst data for {symbol}: {e}")

                if social_data:
                    social_insert = """
                        INSERT INTO social_sentiment_analysis
                        (symbol, date, reddit_sentiment_score, search_volume_index, news_sentiment_score, news_article_count)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            reddit_sentiment_score = EXCLUDED.reddit_sentiment_score,
                            search_volume_index = EXCLUDED.search_volume_index,
                            news_sentiment_score = EXCLUDED.news_sentiment_score,
                            news_article_count = EXCLUDED.news_article_count
                    """
                    for social_tuple in social_data:
                        try:
                            # social_tuple is (symbol, date, reddit_mention_count, reddit_sentiment, reddit_volume_norm,
                            #                  search_volume, search_7d, search_30d, news_count, news_sentiment, news_quality,
                            #                  social_media_volume, viral_score)
                            symbol = social_tuple[0]
                            date_val = social_tuple[1]
                            reddit_mention_count = social_tuple[2]
                            reddit_sentiment = social_tuple[3]
                            reddit_volume_norm = social_tuple[4]
                            search_volume = social_tuple[5]
                            # search_7d = social_tuple[6]  # not used in table
                            # search_30d = social_tuple[7]  # not used in table
                            news_count = social_tuple[8]
                            news_sentiment = social_tuple[9]
                            # news_quality = social_tuple[10]  # not used in table
                            # social_media_volume = social_tuple[11]  # not used in table
                            # viral_score = social_tuple[12]  # not used in table

                            cur.execute(social_insert, (
                                symbol, date_val, reddit_sentiment, search_volume, news_sentiment, news_count
                            ))
                            logging.debug(f"✓ Inserted social data for {symbol}: reddit={reddit_sentiment}, search_vol={search_volume}")
                        except Exception as e:
                            logging.debug(f"Could not insert social data for {symbol}: {e}")

                # Always insert into sentiment table (the one the API queries)
                # Map data from sentiment_data which has the actual sentiment info
                if sentiment_data:
                    sentiment_insert_direct = """
                        INSERT INTO sentiment (symbol, date, sentiment_score, source)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (symbol, date, source) DO UPDATE SET
                            sentiment_score = EXCLUDED.sentiment_score,
                            fetched_at = CURRENT_TIMESTAMP
                    """
                    for item in sentiment_data:
                        try:
                            symbol = item.get('symbol')
                            date_val = item.get('date')
                            # Get sentiment data - try multiple sources in priority order
                            social = item.get('social_sentiment', {})

                            # Try to get sentiment score from multiple sources in order of preference:
                            # 1. News sentiment (from yfinance news articles) - most reliable
                            # 2. Google Trends (if available) - provides search interest
                            # 3. Technical sentiment (RSI + MACD + momentum) - ALWAYS available as fallback
                            # Always use technical sentiment as final fallback since it works for every symbol
                            sentiment_score = (
                                social.get('news_sentiment_score') or  # News sentiment priority
                                social.get('google_trends_score') or   # Then Google Trends
                                social.get('price_change_sentiment')   # Technical sentiment ALWAYS works
                            )

                            # Always insert - technical sentiment ensures we have data
                            if sentiment_score is not None:
                                source = 'technical'  # Default to technical
                                if social.get('news_sentiment_score'):
                                    source = 'news'
                                elif social.get('google_trends_score'):
                                    source = 'trends'

                                cur.execute(sentiment_insert_direct, (symbol, date_val, sentiment_score, source))
                                logging.debug(f"✓ Inserted sentiment for {symbol}: {sentiment_score:.3f} ({source})")
                            else:
                                logging.warning(f"⚠️  No sentiment data collected for {symbol} - even technical sentiment failed")
                        except Exception as e:
                            logging.warning(f"Could not insert sentiment for {item.get('symbol')}: {e}")

                conn.commit()
                total_inserted += len(sentiment_data)
                logging.info(f"Sentiment batch {batch_num} inserted {len(sentiment_data)} symbols successfully")
                
            except Exception as e:
                logging.error(f"Database insert error for sentiment batch {batch_num}: {e}")
                conn.rollback()
        
        # Cleanup
        del sentiment_data
        gc.collect()
        log_mem(f"Sentiment batch {batch_num} end")
        time.sleep(5)  # Longer pause for sentiment due to API limits
    
    if failed_symbols:
        logging.warning(f"Failed to process sentiment data for {len(failed_symbols)} symbols: {failed_symbols[:5]}...")
    
    return total_processed, total_inserted

if __name__ == "__main__":
    log_mem("startup")
    
    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create tables
    create_sentiment_tables(cur, conn)
    
    # Get symbols to process
    cur.execute("""
        SELECT symbol FROM stock_symbols_enhanced
        ORDER BY symbol
    """)
    symbols = [row['symbol'] for row in cur.fetchall()]
    
    if not symbols:
        logging.warning("No symbols found in stock_symbols_enhanced table. Run loadsymbols.py first.")
        sys.exit(1)
    
    logging.info(f"Loading sentiment data for {len(symbols)} symbols")
    
    # Load sentiment data
    start_time = time.time()
    processed, inserted = load_sentiment_batch(symbols, conn, cur)
    end_time = time.time()
    
    # Final statistics
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM analyst_sentiment_analysis")
    total_analyst = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM social_sentiment_analysis")
    total_social = cur.fetchone()[0]
    
    logging.info("=" * 60)
    logging.info("SENTIMENT DATA LOADING COMPLETE")
    logging.info("=" * 60)
    logging.info(f"Symbols processed: {processed}")
    logging.info(f"Symbols with sentiment data: {inserted}")
    logging.info(f"Symbols in analyst sentiment table: {total_analyst}")
    logging.info(f"Symbols in social sentiment table: {total_social}")
    logging.info(f"Processing time: {(end_time - start_time):.1f} seconds")
    log_mem("completion")
    
    # Sample results
    cur.execute("""
        SELECT a.symbol, se.company_name, 
               a.total_analysts, a.recommendation_mean, a.price_target_vs_current,
               s.reddit_mention_count, s.news_sentiment_score, s.search_volume_index
        FROM analyst_sentiment_analysis a
        JOIN stock_symbols_enhanced se ON a.symbol = se.symbol
        LEFT JOIN social_sentiment_analysis s ON a.symbol = s.symbol AND a.date = s.date
        WHERE a.total_analysts > 0
        ORDER BY a.price_target_vs_current DESC NULLS LAST
        LIMIT 10
    """)
    
    logging.info("\nTop 10 Stocks by Analyst Price Target Upside:")
    for row in cur.fetchall():
        upside = row['price_target_vs_current'] or 0
        logging.info(f"  {row['symbol']} ({row['company_name'][:25]}): "
                    f"Upside={upside:.1%}, Analysts={row['total_analysts']}, "
                    f"Reddit={row['reddit_mention_count']}, News Sentiment={row['news_sentiment_score']:.2f}")
    
    cur.close()
    conn.close()
    logging.info("Database connection closed")