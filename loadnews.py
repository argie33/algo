#!/usr/bin/env python3  
# DEPLOY: Data population phase - News and sentiment data loading for frontend features
import sys
import time
import logging
import json
import os
import gc
import resource
import math
import hashlib
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

import boto3
import yfinance as yf
import requests
import feedparser
from textblob import TextBlob

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadnews.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES = 3
RETRY_DELAY = 0.2  # seconds between download retries

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"]
    secret_json = json.loads(secret_str)
    return {
        "host": secret_json["host"],
        "port": secret_json["port"],
        "user": secret_json.get("user", secret_json.get("username")),
        "password": secret_json["password"],
        "dbname": secret_json["dbname"]
    }

# -------------------------------
# Environment
# -------------------------------
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "30"))
PAUSE = float(os.environ.get("PAUSE", "0.5"))
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN", "loadfundamentals-secrets")

# -------------------------------
# News Analysis Classes
# -------------------------------
class NewsCollector:
    def __init__(self):
        self.sources = {
            'Reuters': 'https://feeds.reuters.com/reuters/businessNews',
            'MarketWatch': 'https://feeds.marketwatch.com/marketwatch/realtimeheadlines/',
            'Yahoo Finance': 'https://feeds.finance.yahoo.com/rss/2.0/headline',
            'Seeking Alpha': 'https://seekingalpha.com/market_currents.xml',
            'Benzinga': 'https://www.benzinga.com/feed'
        }
        
        self.categories = {
            'earnings': ['earnings', 'quarterly', 'revenue', 'profit', 'eps', 'guidance'],
            'merger': ['merger', 'acquisition', 'takeover', 'buyout', 'deal', 'purchase'],
            'regulatory': ['regulatory', 'sec', 'fda', 'government', 'policy', 'regulation'],
            'analyst': ['analyst', 'rating', 'upgrade', 'downgrade', 'target', 'recommendation'],
            'economic': ['economic', 'gdp', 'inflation', 'fed', 'interest', 'employment'],
            'technology': ['technology', 'tech', 'software', 'hardware', 'ai', 'innovation'],
            'healthcare': ['healthcare', 'pharma', 'drug', 'medical', 'biotech', 'clinical'],
            'energy': ['energy', 'oil', 'gas', 'renewable', 'solar', 'petroleum'],
            'finance': ['bank', 'financial', 'credit', 'loan', 'mortgage', 'banking'],
            'retail': ['retail', 'consumer', 'sales', 'store', 'shopping', 'ecommerce']
        }

    def collect_news_from_rss(self) -> List[Dict[str, Any]]:
        """Collect news from RSS feeds."""
        all_news = []
        
        for source, url in self.sources.items():
            try:
                logging.info(f"Fetching news from {source}")
                feed = feedparser.parse(url)
                
                if feed.bozo:
                    logging.warning(f"Feed parsing issues for {source}: {feed.bozo_exception}")
                    continue
                
                for entry in feed.entries:
                    try:
                        news_item = self.process_rss_entry(entry, source)
                        if news_item:
                            all_news.append(news_item)
                    except Exception as e:
                        logging.error(f"Error processing entry from {source}: {e}")
                        continue
                
                logging.info(f"Collected {len(feed.entries)} articles from {source}")
                
            except Exception as e:
                logging.error(f"Error fetching from {source}: {e}")
                continue
        
        return all_news

    def process_rss_entry(self, entry, source: str) -> Optional[Dict[str, Any]]:
        """Process a single RSS entry."""
        try:
            title = entry.title if hasattr(entry, 'title') else ''
            description = entry.description if hasattr(entry, 'description') else ''
            
            # Clean HTML tags
            description = re.sub(r'<[^>]+>', '', description)
            
            # Get publication date
            published = entry.published if hasattr(entry, 'published') else ''
            if published:
                try:
                    published_dt = datetime.strptime(published, '%a, %d %b %Y %H:%M:%S %z')
                except:
                    try:
                        published_dt = datetime.strptime(published, '%a, %d %b %Y %H:%M:%S %Z')
                    except:
                        published_dt = datetime.now()
            else:
                published_dt = datetime.now()
            
            url = entry.link if hasattr(entry, 'link') else ''
            author = entry.author if hasattr(entry, 'author') else source
            
            full_text = f"{title} {description}"
            
            # Create unique ID
            content_hash = hashlib.md5(f"{title}{url}".encode()).hexdigest()[:16]
            
            return {
                'id': content_hash,
                'title': title,
                'content': description,
                'source': source,
                'author': author,
                'published_at': published_dt.isoformat(),
                'url': url,
                'category': self.categorize_news(full_text),
                'symbol': self.extract_stock_symbol(full_text),
                'keywords': self.extract_keywords(full_text),
                'summary': description[:200] + '...' if len(description) > 200 else description,
                'full_text': full_text
            }
            
        except Exception as e:
            logging.error(f"Error processing RSS entry: {e}")
            return None

    def categorize_news(self, text: str) -> str:
        """Categorize news based on content."""
        text_lower = text.lower()
        
        category_scores = {}
        for category, keywords in self.categories.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            if score > 0:
                category_scores[category] = score
        
        if category_scores:
            return max(category_scores, key=category_scores.get)
        
        return 'general'

    def extract_stock_symbol(self, text: str) -> Optional[str]:
        """Extract stock symbol from text."""
        patterns = [
            r'\(([A-Z]{1,5})\)',  # (AAPL)
            r'\$([A-Z]{1,5})\b',  # $AAPL
            r'\b([A-Z]{2,5})\b'   # AAPL (standalone)
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                common_words = {'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS', 'HIM', 'HIS', 'HOW', 'ITS', 'NEW', 'NOW', 'OLD', 'SEE', 'TWO', 'WHO', 'BOY', 'DID', 'LET', 'PUT', 'SAY', 'SHE', 'TOO', 'USE', 'CEO', 'CFO', 'IPO', 'SEC', 'FDA', 'API', 'CTO', 'NYSE', 'NASDAQ'}
                for match in matches:
                    if match not in common_words and len(match) <= 5:
                        return match
        
        return None

    def extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        words = re.findall(r'\b\w+\b', text.lower())
        
        stop_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'new', 'now', 'old', 'see', 'two', 'who', 'boy', 'did', 'let', 'put', 'say', 'she', 'too', 'use', 'this', 'that', 'with', 'have', 'will', 'been', 'from', 'they', 'know', 'want', 'good', 'much', 'some', 'time', 'very', 'when', 'come', 'here', 'just', 'like', 'long', 'make', 'many', 'over', 'such', 'take', 'than', 'them', 'well', 'were'}
        
        filtered_words = [word for word in words if len(word) > 3 and word not in stop_words]
        
        word_freq = {}
        for word in filtered_words:
            word_freq[word] = word_freq.get(word, 0) + 1
        
        return sorted(word_freq.keys(), key=word_freq.get, reverse=True)[:10]

class SentimentAnalyzer:
    def __init__(self):
        self.positive_words = [
            'growth', 'profit', 'gain', 'rise', 'surge', 'boost', 'strong', 'beat',
            'exceed', 'outperform', 'upgrade', 'buy', 'bullish', 'positive', 'good',
            'excellent', 'success', 'recovery', 'momentum', 'breakthrough'
        ]
        
        self.negative_words = [
            'loss', 'decline', 'fall', 'drop', 'plunge', 'crash', 'weak', 'miss',
            'underperform', 'downgrade', 'sell', 'bearish', 'negative', 'bad',
            'terrible', 'concern', 'warning', 'risk', 'problem', 'struggle'
        ]

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment using TextBlob."""
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity  # -1 to 1
            subjectivity = blob.sentiment.subjectivity  # 0 to 1
            
            # Determine label
            if polarity > 0.1:
                label = 'positive'
            elif polarity < -0.1:
                label = 'negative'
            else:
                label = 'neutral'
            
            confidence = 1 - subjectivity
            
            return {
                'score': polarity,
                'label': label,
                'confidence': confidence
            }
            
        except Exception as e:
            logging.error(f"Error in sentiment analysis: {e}")
            return {
                'score': 0.0,
                'label': 'neutral',
                'confidence': 0.5
            }

    def calculate_impact_score(self, title: str, content: str, category: str, symbol: Optional[str]) -> float:
        """Calculate impact score for news."""
        score = 0.5
        
        category_weights = {
            'earnings': 0.9, 'merger': 0.8, 'regulatory': 0.7, 'analyst': 0.6,
            'economic': 0.8, 'technology': 0.6, 'healthcare': 0.7, 'energy': 0.6,
            'finance': 0.7, 'retail': 0.5
        }
        
        score += category_weights.get(category, 0.5) * 0.3
        
        if symbol:
            score += 0.2
        
        title_lower = title.lower()
        impact_keywords = ['earnings', 'merger', 'acquisition', 'bankruptcy', 'lawsuit', 'fda', 'approval', 'breakthrough', 'crisis']
        keyword_count = sum(1 for keyword in impact_keywords if keyword in title_lower)
        score += min(keyword_count * 0.1, 0.2)
        
        return min(score, 1.0)

    def calculate_relevance_score(self, title: str, content: str, category: str) -> float:
        """Calculate relevance score for news."""
        score = 0.5
        
        category_relevance = {
            'earnings': 0.9, 'analyst': 0.8, 'merger': 0.7, 'regulatory': 0.6,
            'economic': 0.7, 'technology': 0.6, 'healthcare': 0.6, 'energy': 0.5,
            'finance': 0.6, 'retail': 0.5
        }
        
        score += category_relevance.get(category, 0.5) * 0.3
        
        title_lower = title.lower()
        relevant_keywords = ['stock', 'market', 'trading', 'investor', 'price', 'shares', 'financial']
        keyword_count = sum(1 for keyword in relevant_keywords if keyword in title_lower)
        score += min(keyword_count * 0.1, 0.2)
        
        return min(score, 1.0)

# -------------------------------
# News loading
# -------------------------------
def load_news_data(symbols, cur, conn):
    """
    Load news data for given symbols using yfinance.
    Returns (total, processed, failed).
    """
    total = len(symbols)
    processed = 0
    failed = []
    
    # Calculate batch count
    num_batches = math.ceil(total / BATCH_SIZE)
    
    logging.info(f"Loading news for {total} symbols in {num_batches} batches of {BATCH_SIZE}")
    
    for batch_idx in range(num_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total)
        batch = symbols[start_idx:end_idx]
        
        log_mem(f"Batch {batch_idx+1} start")
        logging.info(f"Processing batch {batch_idx+1}/{num_batches}: symbols {start_idx+1}-{end_idx}")
        
        for symbol in batch:
            orig_sym = symbol
            try:
                logging.info(f"Fetching news for {orig_sym}")
                
                # Get ticker object
                ticker = yf.Ticker(orig_sym)
                
                # Get news data
                news_data = ticker.news
                
                if not news_data:
                    logging.warning(f"No news data found for {orig_sym}")
                    continue
                
                # Process each news item
                news_items = []
                for news_item in news_data:
                    # Extract news data
                    uuid = news_item.get('uuid')
                    title = news_item.get('title', '')
                    publisher = news_item.get('publisher', '')
                    link = news_item.get('link', '')
                    publish_time = news_item.get('providerPublishTime')
                    news_type = news_item.get('type', '')
                    
                    # Convert timestamp to datetime
                    publish_datetime = None
                    if publish_time:
                        try:
                            publish_datetime = datetime.fromtimestamp(publish_time)
                        except (ValueError, TypeError):
                            logging.warning(f"Invalid timestamp for {orig_sym}: {publish_time}")
                    
                    # Get thumbnail and related tickers
                    thumbnail = None
                    if 'thumbnail' in news_item and 'resolutions' in news_item['thumbnail']:
                        thumbnails = news_item['thumbnail']['resolutions']
                        if thumbnails:
                            thumbnail = thumbnails[0].get('url')
                    
                    related_tickers = []
                    if 'relatedTickers' in news_item:
                        related_tickers = [ticker for ticker in news_item['relatedTickers'] if ticker]
                    
                    news_items.append((
                        uuid,
                        orig_sym,
                        title,
                        publisher,
                        link,
                        publish_datetime,
                        news_type,
                        thumbnail,
                        json.dumps(related_tickers) if related_tickers else None
                    ))
                
                # Insert news items
                if news_items:
                    execute_values(
                        cur,
                        """
                        INSERT INTO stock_news (
                            uuid, ticker, title, publisher, link, 
                            publish_time, news_type, thumbnail, related_tickers
                        ) VALUES %s
                        ON CONFLICT (uuid) DO UPDATE SET
                            title = EXCLUDED.title,
                            publisher = EXCLUDED.publisher,
                            link = EXCLUDED.link,
                            publish_time = EXCLUDED.publish_time,
                            news_type = EXCLUDED.news_type,
                            thumbnail = EXCLUDED.thumbnail,
                            related_tickers = EXCLUDED.related_tickers
                        """,
                        news_items
                    )
                    
                    logging.info(f"Inserted {len(news_items)} news items for {orig_sym}")
                
                conn.commit()
                processed += 1
                logging.info(f"Successfully processed news for {orig_sym}")
                
            except Exception as e:
                logging.error(f"Failed to process news for {orig_sym}: {str(e)}")
                failed.append(orig_sym)
                conn.rollback()
        
        del batch
        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")
        time.sleep(PAUSE)
    
    return total, processed, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")
    
    # Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create news tables
    logging.info("Creating news tables...")
    
    # Original stock_news table for yfinance data
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_news (
            id SERIAL PRIMARY KEY,
            uuid VARCHAR(255) UNIQUE NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            title TEXT NOT NULL,
            publisher VARCHAR(255),
            link TEXT,
            publish_time TIMESTAMP,
            news_type VARCHAR(100),
            thumbnail TEXT,
            related_tickers JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # Enhanced news_articles table for RSS feeds and sentiment analysis
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news_articles (
            id VARCHAR(50) PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT,
            source VARCHAR(100) NOT NULL,
            author VARCHAR(100),
            published_at TIMESTAMP WITH TIME ZONE NOT NULL,
            url TEXT,
            category VARCHAR(50),
            symbol VARCHAR(10),
            keywords TEXT[],
            summary TEXT,
            sentiment_score DECIMAL(3,2),
            sentiment_label VARCHAR(20),
            sentiment_confidence DECIMAL(3,2),
            impact_score DECIMAL(3,2),
            relevance_score DECIMAL(3,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Create indexes for better performance
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_news_ticker ON stock_news(ticker);
        CREATE INDEX IF NOT EXISTS idx_stock_news_publish_time ON stock_news(publish_time DESC);
        CREATE INDEX IF NOT EXISTS idx_stock_news_uuid ON stock_news(uuid);
        CREATE INDEX IF NOT EXISTS idx_stock_news_publisher ON stock_news(publisher);
        
        CREATE INDEX IF NOT EXISTS idx_news_published_at ON news_articles(published_at);
        CREATE INDEX IF NOT EXISTS idx_news_symbol ON news_articles(symbol);
        CREATE INDEX IF NOT EXISTS idx_news_category ON news_articles(category);
        CREATE INDEX IF NOT EXISTS idx_news_sentiment ON news_articles(sentiment_label);
        CREATE INDEX IF NOT EXISTS idx_news_source ON news_articles(source);
    """)
    
    conn.commit()
    
    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_news_data(stock_syms, cur, conn)
    
    # Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols ORDER BY symbol;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, p_e, f_e = load_news_data(etf_syms, cur, conn)
    
    # Load RSS news feeds with sentiment analysis
    logging.info("Loading RSS news feeds...")
    news_collector = NewsCollector()
    sentiment_analyzer = SentimentAnalyzer()
    
    try:
        # Collect news from RSS feeds
        rss_news = news_collector.collect_news_from_rss()
        
        # Process each news item
        for news_item in rss_news:
            try:
                # Analyze sentiment
                sentiment = sentiment_analyzer.analyze_sentiment(news_item['full_text'])
                
                # Calculate scores
                impact_score = sentiment_analyzer.calculate_impact_score(
                    news_item['title'], 
                    news_item['content'], 
                    news_item['category'], 
                    news_item['symbol']
                )
                
                relevance_score = sentiment_analyzer.calculate_relevance_score(
                    news_item['title'], 
                    news_item['content'], 
                    news_item['category']
                )
                
                # Insert into news_articles table
                cur.execute("""
                    INSERT INTO news_articles (
                        id, title, content, source, author, published_at, url,
                        category, symbol, keywords, summary, sentiment_score,
                        sentiment_label, sentiment_confidence, impact_score,
                        relevance_score, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        sentiment_score = EXCLUDED.sentiment_score,
                        sentiment_label = EXCLUDED.sentiment_label,
                        sentiment_confidence = EXCLUDED.sentiment_confidence,
                        impact_score = EXCLUDED.impact_score,
                        relevance_score = EXCLUDED.relevance_score,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    news_item['id'],
                    news_item['title'],
                    news_item['content'],
                    news_item['source'],
                    news_item['author'],
                    news_item['published_at'],
                    news_item['url'],
                    news_item['category'],
                    news_item['symbol'],
                    news_item['keywords'],
                    news_item['summary'],
                    sentiment['score'],
                    sentiment['label'],
                    sentiment['confidence'],
                    impact_score,
                    relevance_score
                ))
                
            except Exception as e:
                logging.error(f"Error processing RSS news item {news_item['id']}: {e}")
                continue
        
        conn.commit()
        logging.info(f"Processed {len(rss_news)} RSS news articles")
        
    except Exception as e:
        logging.error(f"Error loading RSS news: {e}")
        conn.rollback()
    
    # Clean up old news (keep only last 30 days)
    logging.info("Cleaning up old news data...")
    cleanup_date = datetime.now() - timedelta(days=30)
    
    # Clean stock_news table
    cur.execute("""
        DELETE FROM stock_news 
        WHERE publish_time < %s OR publish_time IS NULL
    """, (cleanup_date,))
    
    deleted_stock_news = cur.rowcount
    logging.info(f"Deleted {deleted_stock_news} old stock news items")
    
    # Clean news_articles table
    cur.execute("""
        DELETE FROM news_articles 
        WHERE published_at < %s
    """, (cleanup_date,))
    
    deleted_rss_news = cur.rowcount
    logging.info(f"Deleted {deleted_rss_news} old RSS news items")
    
    # Record last run
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()
    
    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Stocks — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")
    logging.info(f"ETFs   — total: {t_e}, processed: {p_e}, failed: {len(f_e)}")
    
    if f_s:
        logging.warning(f"Failed stock symbols: {f_s[:10]}{'...' if len(f_s) > 10 else ''}")
    if f_e:
        logging.warning(f"Failed ETF symbols: {f_e[:10]}{'...' if len(f_e) > 10 else ''}")
    
    cur.close()
    conn.close()
    logging.info("News loading complete.")
