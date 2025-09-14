#!/usr/bin/env python3
"""
Enhanced News Data Loader
Loads news data with sentiment analysis and categorization
"""
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta

import psycopg2
import yfinance as yf
from psycopg2.extras import RealDictCursor, execute_values

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def get_db_config():
    """Get database configuration"""
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "password"),
        "dbname": os.environ.get("DB_NAME", "stocks"),
    }

def simple_sentiment_analysis(text):
    """
    Simple sentiment analysis based on keyword matching
    Returns (sentiment_score, confidence)
    """
    if not text:
        return 0.0, 0.0
    
    text_lower = text.lower()
    
    positive_words = [
        'positive', 'good', 'great', 'excellent', 'strong', 'growth', 'profit', 'gain',
        'up', 'rise', 'increase', 'beat', 'exceed', 'surpass', 'outperform', 'upgrade',
        'bullish', 'optimistic', 'confident', 'success', 'achievement', 'milestone',
        'breakthrough', 'innovation', 'partnership', 'acquisition', 'expansion'
    ]
    
    negative_words = [
        'negative', 'bad', 'poor', 'weak', 'decline', 'loss', 'fall', 'drop',
        'down', 'decrease', 'miss', 'disappoint', 'underperform', 'downgrade',
        'bearish', 'pessimistic', 'concern', 'worry', 'risk', 'threat', 'challenge',
        'problem', 'issue', 'crisis', 'lawsuit', 'investigation', 'bankruptcy'
    ]
    
    neutral_words = [
        'neutral', 'stable', 'maintain', 'hold', 'unchanged', 'steady', 'consistent',
        'regular', 'standard', 'normal', 'expected', 'planned', 'routine'
    ]
    
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    neutral_count = sum(1 for word in neutral_words if word in text_lower)
    
    total_sentiment_words = positive_count + negative_count + neutral_count
    
    if total_sentiment_words == 0:
        return 0.0, 0.0
    
    # Calculate sentiment score (-1 to +1)
    sentiment_score = (positive_count - negative_count) / max(total_sentiment_words, 1)
    
    # Calculate confidence based on total sentiment words found
    confidence = min(total_sentiment_words / 10.0, 1.0)  # Cap at 1.0
    
    return sentiment_score, confidence

def categorize_news(title, content=""):
    """
    Categorize news based on title and content
    """
    text = (title + " " + content).lower()
    
    categories = {
        'earnings': ['earnings', 'quarterly', 'revenue', 'profit', 'eps', 'guidance', 'results'],
        'market': ['market', 'trading', 'price', 'stock', 'shares', 'volume', 'rally', 'sell-off'],
        'economy': ['economic', 'gdp', 'inflation', 'federal', 'fed', 'interest rate', 'unemployment'],
        'technology': ['technology', 'tech', 'ai', 'artificial intelligence', 'software', 'hardware', 'innovation'],
        'crypto': ['bitcoin', 'crypto', 'cryptocurrency', 'blockchain', 'ethereum', 'digital currency'],
        'politics': ['political', 'government', 'regulation', 'policy', 'congress', 'senate', 'president'],
        'global': ['global', 'international', 'china', 'europe', 'trade', 'tariff', 'geopolitical'],
        'merger': ['merger', 'acquisition', 'deal', 'buyout', 'takeover', 'partnership'],
        'ipo': ['ipo', 'public offering', 'debut', 'listing', 'first day']
    }
    
    for category, keywords in categories.items():
        if any(keyword in text for keyword in keywords):
            return category
    
    return 'general'

def extract_keywords(title, content=""):
    """
    Extract relevant keywords from news content
    """
    text = (title + " " + content).lower()
    
    # Common financial keywords
    financial_keywords = [
        'revenue', 'profit', 'earnings', 'eps', 'guidance', 'growth', 'margin',
        'acquisition', 'merger', 'ipo', 'dividend', 'buyback', 'debt', 'cash',
        'market share', 'competition', 'regulation', 'lawsuit', 'fda approval',
        'clinical trial', 'patent', 'product launch', 'expansion', 'restructuring'
    ]
    
    found_keywords = []
    for keyword in financial_keywords:
        if keyword in text:
            found_keywords.append(keyword)
    
    # Extract stock symbols (simple regex)
    symbols = re.findall(r'\b[A-Z]{1,5}\b', title + " " + content)
    symbols = [s for s in symbols if len(s) >= 2 and len(s) <= 5]
    
    return found_keywords + symbols[:5]  # Limit to avoid clutter

def calculate_relevance_score(title, symbol, keywords):
    """
    Calculate relevance score based on various factors
    """
    score = 0.5  # Base score
    
    # Check if symbol is mentioned in title
    if symbol and symbol.upper() in title.upper():
        score += 0.3
    
    # Check for high-impact keywords
    high_impact_keywords = ['earnings', 'acquisition', 'merger', 'fda', 'lawsuit', 'bankruptcy']
    for keyword in keywords:
        if keyword.lower() in high_impact_keywords:
            score += 0.1
    
    # Cap at 1.0
    return min(score, 1.0)

def load_news_with_analysis(symbols, cur, conn):
    """
    Load news data with sentiment analysis and categorization
    """
    total = len(symbols)
    processed = 0
    failed = []
    
    logging.info(f"Loading enhanced news for {total} symbols")
    
    for symbol in symbols:
        try:
            logging.info(f"Fetching news for {symbol}")
            
            ticker = yf.Ticker(symbol)
            news_data = ticker.news
            
            if not news_data:
                logging.warning(f"No news data found for {symbol}")
                continue
            
            news_items = []
            for news_item in news_data:
                # Extract basic data
                uuid = news_item.get("uuid")
                title = news_item.get("title", "")
                link = news_item.get("link", "")
                publisher = news_item.get("publisher", "")
                publish_time = news_item.get("providerPublishTime")
                news_type = news_item.get("type", "")
                
                # Convert timestamp
                publish_datetime = None
                if publish_time:
                    try:
                        publish_datetime = datetime.fromtimestamp(publish_time)
                    except (ValueError, TypeError):
                        logging.warning(f"Invalid timestamp for {symbol}: {publish_time}")
                
                # Skip old news (older than 30 days)
                if publish_datetime and publish_datetime < datetime.now() - timedelta(days=30):
                    continue
                
                # Get thumbnail
                thumbnail = None
                if "thumbnail" in news_item and "resolutions" in news_item["thumbnail"]:
                    thumbnails = news_item["thumbnail"]["resolutions"]
                    if thumbnails:
                        thumbnail = thumbnails[0].get("url")
                
                # Get related tickers
                related_tickers = []
                if "relatedTickers" in news_item:
                    related_tickers = [t for t in news_item["relatedTickers"] if t]
                
                # Perform sentiment analysis
                sentiment_score, sentiment_confidence = simple_sentiment_analysis(title)
                
                # Categorize news
                category = categorize_news(title)
                
                # Extract keywords
                keywords = extract_keywords(title)
                
                # Calculate relevance score
                relevance_score = calculate_relevance_score(title, symbol, keywords)
                
                # Calculate impact score (similar to relevance but considering sentiment)
                impact_score = relevance_score * (1 + abs(sentiment_score)) / 2
                
                news_items.append((
                    uuid,
                    symbol,
                    title,
                    title,  # summary (same as title for now)
                    link,
                    publisher,
                    None,  # author
                    publish_datetime,
                    category,
                    sentiment_score,
                    sentiment_confidence,
                    relevance_score,
                    json.dumps(keywords) if keywords else None,
                    title,  # content (same as title for now)
                    impact_score,
                    thumbnail,
                    json.dumps(related_tickers) if related_tickers else None,
                    news_type
                ))
            
            # Insert news items
            if news_items:
                execute_values(
                    cur,
                    """
                    INSERT INTO news (
                        uuid, symbol, headline, summary, url, source, author,
                        published_at, category, sentiment, sentiment_confidence,
                        relevance_score, keywords, content, impact_score,
                        thumbnail, related_tickers, news_type
                    ) VALUES %s
                    ON CONFLICT (uuid) DO UPDATE SET
                        headline = EXCLUDED.headline,
                        summary = EXCLUDED.summary,
                        url = EXCLUDED.url,
                        source = EXCLUDED.source,
                        published_at = EXCLUDED.published_at,
                        category = EXCLUDED.category,
                        sentiment = EXCLUDED.sentiment,
                        sentiment_confidence = EXCLUDED.sentiment_confidence,
                        relevance_score = EXCLUDED.relevance_score,
                        keywords = EXCLUDED.keywords,
                        content = EXCLUDED.content,
                        impact_score = EXCLUDED.impact_score,
                        thumbnail = EXCLUDED.thumbnail,
                        related_tickers = EXCLUDED.related_tickers,
                        news_type = EXCLUDED.news_type
                    """,
                    news_items,
                )
                
                logging.info(f"Inserted {len(news_items)} enhanced news items for {symbol}")
            
            conn.commit()
            processed += 1
            
        except Exception as e:
            logging.error(f"Failed to process news for {symbol}: {str(e)}")
            failed.append(symbol)
            conn.rollback()
    
    return total, processed, failed

if __name__ == "__main__":
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
    
    # Create news table if it doesn't exist
    with open('/home/stocks/algo/webapp/lambda/create_news_table.sql', 'r') as f:
        cur.execute(f.read())
    conn.commit()
    
    # Get sample symbols for testing
    cur.execute("SELECT symbol FROM stock_symbols WHERE symbol IN ('AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'SPY', 'QQQ') ORDER BY symbol;")
    symbols = [r["symbol"] for r in cur.fetchall()]
    
    if not symbols:
        # Fallback to hardcoded symbols if no stock_symbols table
        symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX']
        logging.info("Using fallback symbols")
    
    total, processed, failed = load_news_with_analysis(symbols, cur, conn)
    
    # Clean up old news (keep only last 30 days)
    logging.info("Cleaning up old news data...")
    cleanup_date = datetime.now() - timedelta(days=30)
    cur.execute(
        "DELETE FROM news WHERE published_at < %s OR published_at IS NULL",
        (cleanup_date,)
    )
    deleted_count = cur.rowcount
    logging.info(f"Deleted {deleted_count} old news items")
    
    conn.commit()
    cur.close()
    conn.close()
    
    logging.info(f"Enhanced news loading complete. Total: {total}, Processed: {processed}, Failed: {len(failed)}")
    if failed:
        logging.warning(f"Failed symbols: {failed}")