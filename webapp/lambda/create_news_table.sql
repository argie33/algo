-- Create comprehensive news table for news routes
-- This table has the proper schema that news routes expect

CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(255) UNIQUE,
    symbol VARCHAR(10),
    headline TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    source VARCHAR(255),
    author VARCHAR(255),
    published_at TIMESTAMP,
    category VARCHAR(100),
    sentiment DECIMAL(3,2) DEFAULT 0,
    sentiment_confidence DECIMAL(3,2) DEFAULT 0.5,
    relevance_score DECIMAL(3,2) DEFAULT 0.5,
    keywords JSONB,
    content TEXT,
    impact_score DECIMAL(3,2) DEFAULT 0.5,
    thumbnail TEXT,
    related_tickers JSONB,
    news_type VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    fetched_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_news_symbol ON news(symbol);
CREATE INDEX IF NOT EXISTS idx_news_published_at ON news(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_uuid ON news(uuid);
CREATE INDEX IF NOT EXISTS idx_news_source ON news(source);
CREATE INDEX IF NOT EXISTS idx_news_category ON news(category);
CREATE INDEX IF NOT EXISTS idx_news_sentiment ON news(sentiment);

-- Create a view to bridge between stock_news and news tables
CREATE OR REPLACE VIEW news_unified AS
SELECT 
    sn.id,
    sn.uuid,
    sn.ticker as symbol,
    sn.title as headline,
    sn.title as summary,
    sn.link as url,
    sn.publisher as source,
    null as author,
    sn.publish_time as published_at,
    'general' as category,
    0 as sentiment,
    0.5 as sentiment_confidence,
    0.5 as relevance_score,
    null as keywords,
    sn.title as content,
    0.5 as impact_score,
    sn.thumbnail,
    sn.related_tickers,
    sn.news_type,
    sn.created_at,
    sn.created_at as fetched_at
FROM stock_news sn
UNION ALL
SELECT 
    n.id,
    n.uuid,
    n.symbol,
    n.headline,
    n.summary,
    n.url,
    n.source,
    n.author,
    n.published_at,
    n.category,
    n.sentiment,
    n.sentiment_confidence,
    n.relevance_score,
    n.keywords,
    n.content,
    n.impact_score,
    n.thumbnail,
    n.related_tickers,
    n.news_type,
    n.created_at,
    n.fetched_at
FROM news n;

COMMIT;