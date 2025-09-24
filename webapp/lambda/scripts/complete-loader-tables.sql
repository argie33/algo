-- Complete database schema matching ALL Python loader scripts exactly
-- Based on: loadstocksymbols.py, loadfundamentalmetrics.py, loadpricedaily.py, loadpositioning.py, loadsentiment.py, loadnews.py, loadmarket.py

-- Stock symbols table (from loadstocksymbols.py)
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol            VARCHAR(50),
    exchange          VARCHAR(100),
    security_name     TEXT,
    cqs_symbol        VARCHAR(50),
    market_category   VARCHAR(50),
    test_issue        CHAR(1),
    financial_status  VARCHAR(50),
    round_lot_size    INT,
    etf               CHAR(1),
    secondary_symbol  VARCHAR(50)
);

-- ETF symbols table (from loadstocksymbols.py)
CREATE TABLE IF NOT EXISTS etf_symbols (
    symbol            VARCHAR(50),
    exchange          VARCHAR(100),
    security_name     TEXT,
    cqs_symbol        VARCHAR(50),
    market_category   VARCHAR(50),
    test_issue        CHAR(1),
    financial_status  VARCHAR(50),
    round_lot_size    INT,
    etf               CHAR(1),
    secondary_symbol  VARCHAR(50)
);

-- Price daily table (from loadpricedaily.py)
CREATE TABLE IF NOT EXISTS price_daily (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(10) NOT NULL,
    date         DATE         NOT NULL,
    open         DOUBLE PRECISION,
    high         DOUBLE PRECISION,
    low          DOUBLE PRECISION,
    close        DOUBLE PRECISION,
    adj_close    DOUBLE PRECISION,
    volume       BIGINT,
    dividends    DOUBLE PRECISION,
    splits       DOUBLE PRECISION,
    fetched_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ETF price daily table (from loadpricedaily.py)
CREATE TABLE IF NOT EXISTS etf_price_daily (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(10) NOT NULL,
    date         DATE         NOT NULL,
    open         DOUBLE PRECISION,
    high         DOUBLE PRECISION,
    low          DOUBLE PRECISION,
    close        DOUBLE PRECISION,
    adj_close    DOUBLE PRECISION,
    volume       BIGINT,
    dividends    DOUBLE PRECISION,
    splits       DOUBLE PRECISION,
    fetched_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Fundamental metrics table (from loadfundamentalmetrics.py)
CREATE TABLE IF NOT EXISTS fundamental_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    market_cap BIGINT,
    pe_ratio DECIMAL(10,2),
    forward_pe DECIMAL(10,2),
    peg_ratio DECIMAL(10,2),
    price_to_book DECIMAL(10,2),
    price_to_sales DECIMAL(10,2),
    price_to_cash_flow DECIMAL(10,2),
    dividend_yield DECIMAL(8,4),
    dividend_rate DECIMAL(10,2),
    beta DECIMAL(8,4),
    fifty_two_week_high DECIMAL(10,2),
    fifty_two_week_low DECIMAL(10,2),
    revenue_per_share DECIMAL(10,2),
    revenue BIGINT,
    quarterly_revenue_growth DECIMAL(8,4),
    gross_profit BIGINT,
    ebitda BIGINT,
    operating_income BIGINT,
    net_income BIGINT,
    earnings_per_share DECIMAL(10,2),
    quarterly_earnings_growth DECIMAL(8,4),
    return_on_equity DECIMAL(8,4),
    return_on_assets DECIMAL(8,4),
    debt_to_equity DECIMAL(10,2),
    current_ratio DECIMAL(8,4),
    quick_ratio DECIMAL(8,4),
    book_value DECIMAL(10,2),
    shares_outstanding BIGINT,
    float_shares BIGINT,
    short_ratio DECIMAL(8,2),
    short_interest BIGINT,
    enterprise_value BIGINT,
    enterprise_to_revenue DECIMAL(10,2),
    enterprise_to_ebitda DECIMAL(10,2),
    sector VARCHAR(100),
    industry VARCHAR(200),
    full_time_employees INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol)
);

-- Positioning metrics table (from loadpositioning.py)
CREATE TABLE IF NOT EXISTS positioning_metrics (
    symbol VARCHAR(20),
    date DATE,

    -- Institutional Holdings
    institutional_ownership_pct DECIMAL(6,4) DEFAULT 0,
    institutional_holders_count INTEGER DEFAULT 0,
    top_10_institutions_pct DECIMAL(6,4) DEFAULT 0,
    institutional_concentration DECIMAL(8,6) DEFAULT 0,
    recent_institutional_buying DECIMAL(8,6) DEFAULT 0,
    recent_institutional_selling DECIMAL(8,6) DEFAULT 0,
    net_institutional_flow DECIMAL(8,6) DEFAULT 0,
    institutional_momentum DECIMAL(8,6) DEFAULT 0,
    smart_money_score DECIMAL(6,4) DEFAULT 0,
    institutional_quality_score DECIMAL(6,4) DEFAULT 0,

    -- Insider Trading
    insider_ownership_pct DECIMAL(6,4) DEFAULT 0,
    recent_insider_buys INTEGER DEFAULT 0,
    recent_insider_sells INTEGER DEFAULT 0,
    insider_buy_value DECIMAL(15,2) DEFAULT 0,
    insider_sell_value DECIMAL(15,2) DEFAULT 0,
    net_insider_trading DECIMAL(15,2) DEFAULT 0,
    insider_sentiment_score DECIMAL(6,4) DEFAULT 0,
    ceo_trading_activity DECIMAL(6,4) DEFAULT 0,
    director_trading_activity DECIMAL(6,4) DEFAULT 0,
    insider_concentration DECIMAL(8,6) DEFAULT 0,

    -- Options Flow
    put_call_ratio DECIMAL(8,4) DEFAULT 0,
    options_volume INTEGER DEFAULT 0,
    unusual_options_activity DECIMAL(8,4) DEFAULT 0,
    gamma_exposure DECIMAL(12,2) DEFAULT 0,
    options_sentiment DECIMAL(6,4) DEFAULT 0,
    large_options_trades INTEGER DEFAULT 0,
    options_skew DECIMAL(8,4) DEFAULT 0,
    max_pain_level DECIMAL(12,4) DEFAULT 0,

    -- Short Interest
    short_interest_pct DECIMAL(6,4) DEFAULT 0,
    short_ratio DECIMAL(8,4) DEFAULT 0,
    days_to_cover DECIMAL(8,4) DEFAULT 0,
    short_squeeze_score DECIMAL(6,4) DEFAULT 0,
    borrow_rate DECIMAL(6,4) DEFAULT 0,
    short_availability DECIMAL(6,4) DEFAULT 0,

    -- Composite Score
    composite_positioning_score DECIMAL(6,4) DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Analyst sentiment analysis table (from loadsentiment.py)
CREATE TABLE IF NOT EXISTS analyst_sentiment_analysis (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    analyst_count INTEGER DEFAULT 0,
    strong_buy_count INTEGER DEFAULT 0,
    buy_count INTEGER DEFAULT 0,
    hold_count INTEGER DEFAULT 0,
    sell_count INTEGER DEFAULT 0,
    strong_sell_count INTEGER DEFAULT 0,
    average_rating DECIMAL(4,2) DEFAULT 0,
    target_price DECIMAL(12,4) DEFAULT 0,
    target_high DECIMAL(12,4) DEFAULT 0,
    target_low DECIMAL(12,4) DEFAULT 0,
    target_mean DECIMAL(12,4) DEFAULT 0,
    target_median DECIMAL(12,4) DEFAULT 0,
    recommendation_trend VARCHAR(20) DEFAULT 'NEUTRAL',
    upgrade_downgrade_history JSONB,
    price_target_changes JSONB,
    earnings_revisions JSONB,
    sentiment_score DECIMAL(6,4) DEFAULT 0,
    confidence_level DECIMAL(6,4) DEFAULT 0,
    analyst_coverage_quality DECIMAL(6,4) DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Social sentiment analysis table (from loadsentiment.py)
CREATE TABLE IF NOT EXISTS social_sentiment_analysis (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    platform VARCHAR(50) NOT NULL,
    mention_count INTEGER DEFAULT 0,
    positive_mentions INTEGER DEFAULT 0,
    negative_mentions INTEGER DEFAULT 0,
    neutral_mentions INTEGER DEFAULT 0,
    engagement_score DECIMAL(10,2) DEFAULT 0,
    reach_score DECIMAL(10,2) DEFAULT 0,
    influence_score DECIMAL(8,4) DEFAULT 0,
    sentiment_score DECIMAL(6,4) DEFAULT 0,
    trending_score DECIMAL(8,4) DEFAULT 0,
    volume_score DECIMAL(8,4) DEFAULT 0,
    bullish_keywords JSONB,
    bearish_keywords JSONB,
    top_posts JSONB,
    influencer_sentiment JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, platform)
);

-- Retail sentiment table (from loadsentiment.py)
CREATE TABLE IF NOT EXISTS retail_sentiment (
    symbol VARCHAR(20),
    date DATE,
    bullish_percentage DECIMAL(6,2) DEFAULT 0,
    bearish_percentage DECIMAL(6,2) DEFAULT 0,
    neutral_percentage DECIMAL(6,2) DEFAULT 0,
    net_sentiment DECIMAL(6,2) DEFAULT 0,
    sentiment_change DECIMAL(6,2) DEFAULT 0,
    source VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date, source)
);

-- Stock news table (from loadnews.py)
CREATE TABLE IF NOT EXISTS stock_news (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    publish_time TIMESTAMP,
    provider VARCHAR(100),
    related_tickers JSONB,
    sentiment_score DECIMAL(3,2),
    category VARCHAR(50),
    source_quality DECIMAL(4,2) DEFAULT 0,
    relevance_score DECIMAL(4,2) DEFAULT 0,
    impact_score DECIMAL(4,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Market data table (from loadmarket.py)
CREATE TABLE IF NOT EXISTS market_data (
    ticker VARCHAR(10) PRIMARY KEY,
    previous_close NUMERIC,
    regular_market_previous_close NUMERIC,
    open_price NUMERIC,
    regular_market_open NUMERIC,
    day_low NUMERIC,
    regular_market_day_low NUMERIC,
    day_high NUMERIC,
    regular_market_day_high NUMERIC,
    regular_market_price NUMERIC,
    current_price NUMERIC,
    post_market_price NUMERIC,
    post_market_change NUMERIC,
    post_market_change_pct NUMERIC,
    volume BIGINT,
    regular_market_volume BIGINT,
    average_volume BIGINT,
    avg_volume_10d BIGINT,
    avg_daily_volume_10d BIGINT,
    avg_daily_volume_3m BIGINT,
    bid_price NUMERIC,
    ask_price NUMERIC,
    bid_size INT,
    ask_size INT,
    market_state VARCHAR(20),
    fifty_two_week_low NUMERIC,
    fifty_two_week_high NUMERIC,
    fifty_two_week_range VARCHAR(50),
    fifty_two_week_low_change NUMERIC,
    fifty_two_week_low_change_pct NUMERIC,
    fifty_two_week_high_change NUMERIC,
    fifty_two_week_high_change_pct NUMERIC,
    fifty_two_week_change_pct NUMERIC,
    fifty_day_avg NUMERIC,
    two_hundred_day_avg NUMERIC,
    fifty_day_avg_change NUMERIC,
    fifty_day_avg_change_pct NUMERIC,
    two_hundred_day_avg_change NUMERIC,
    two_hundred_day_avg_change_pct NUMERIC,
    source_interval_sec INT,
    market_cap BIGINT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Last updated tracking table (from all loaders)
CREATE TABLE IF NOT EXISTS last_updated (
    script_name   VARCHAR(255) PRIMARY KEY,
    last_run      TIMESTAMP WITH TIME ZONE
);

-- Create all performance indexes
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_symbol ON fundamental_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_sector ON fundamental_metrics(sector);
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_industry ON fundamental_metrics(industry);
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_updated ON fundamental_metrics(updated_at);

CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_etf_price_daily_symbol_date ON etf_price_daily(symbol, date);

CREATE INDEX IF NOT EXISTS idx_positioning_symbol ON positioning_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_positioning_date ON positioning_metrics(date DESC);
CREATE INDEX IF NOT EXISTS idx_positioning_composite ON positioning_metrics(composite_positioning_score DESC);
CREATE INDEX IF NOT EXISTS idx_positioning_institutional ON positioning_metrics(institutional_ownership_pct DESC);
CREATE INDEX IF NOT EXISTS idx_positioning_insider ON positioning_metrics(insider_sentiment_score DESC);
CREATE INDEX IF NOT EXISTS idx_positioning_options ON positioning_metrics(unusual_options_activity DESC);
CREATE INDEX IF NOT EXISTS idx_positioning_short ON positioning_metrics(short_squeeze_score DESC);
CREATE INDEX IF NOT EXISTS idx_positioning_smart_money ON positioning_metrics(smart_money_score DESC);

CREATE INDEX IF NOT EXISTS idx_analyst_sentiment_symbol ON analyst_sentiment_analysis(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_sentiment_date ON analyst_sentiment_analysis(date DESC);
CREATE INDEX IF NOT EXISTS idx_analyst_sentiment_score ON analyst_sentiment_analysis(sentiment_score DESC);

CREATE INDEX IF NOT EXISTS idx_social_sentiment_symbol ON social_sentiment_analysis(symbol);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_date ON social_sentiment_analysis(date DESC);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_platform ON social_sentiment_analysis(platform);

CREATE INDEX IF NOT EXISTS idx_retail_sentiment_symbol ON retail_sentiment(symbol);
CREATE INDEX IF NOT EXISTS idx_retail_sentiment_date ON retail_sentiment(date DESC);

CREATE INDEX IF NOT EXISTS idx_stock_news_ticker ON stock_news(ticker);
CREATE INDEX IF NOT EXISTS idx_stock_news_publish_time ON stock_news(publish_time);
CREATE INDEX IF NOT EXISTS idx_stock_news_sentiment ON stock_news(sentiment_score);

CREATE INDEX IF NOT EXISTS idx_market_data_ticker ON market_data(ticker);
CREATE INDEX IF NOT EXISTS idx_market_data_updated ON market_data(updated_at);