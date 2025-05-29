-- Create tables needed for stock symbols
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(20) PRIMARY KEY,
    name VARCHAR(255),
    exchange VARCHAR(20),
    asset_type VARCHAR(20),
    ipo_date DATE,
    delisting_date DATE,
    status VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS etf_symbols (
    symbol VARCHAR(20) PRIMARY KEY,
    name VARCHAR(255),
    exchange VARCHAR(20),
    asset_type VARCHAR(20),
    ipo_date DATE,
    delisting_date DATE,
    status VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS price_daily (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(18,4),
    high DECIMAL(18,4),
    low DECIMAL(18,4),
    close DECIMAL(18,4),
    adj_close DECIMAL(18,4),
    volume BIGINT,
    dividends DECIMAL(18,4),
    stock_splits DECIMAL(18,4),
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS etf_price_daily (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(18,4),
    high DECIMAL(18,4),
    low DECIMAL(18,4),
    close DECIMAL(18,4),
    adj_close DECIMAL(18,4),
    volume BIGINT,
    dividends DECIMAL(18,4),
    stock_splits DECIMAL(18,4),
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(100) PRIMARY KEY,
    last_run TIMESTAMP NOT NULL
);
