# Latest Buy/Sell Signal Scripts - Incremental Processing

## Overview
These scripts generate buy/sell signals incrementally, processing only symbols that have new/changed technical indicators data. They are designed to run after the latest technical indicators scripts to maintain data consistency and optimize processing time.

## Scripts Created

### 1. Latest Buy/Sell Daily (`loadlatestbuyselldaily.py`)
- **Purpose**: Processes daily buy/sell signals for symbols with new technical indicators
- **Dependency**: Runs after `loadlatesttechnicalsdaily.py`
- **Lookback**: 7 days for identification, 200 periods for signal calculation
- **Tables**: Uses `price_daily`, `technical_data_daily`, outputs to `buy_sell_daily`

### 2. Latest Buy/Sell Weekly (`loadlatestbuysellweekly.py`)
- **Purpose**: Processes weekly buy/sell signals for symbols with new technical indicators
- **Dependency**: Runs after `loadlatesttechnicalsweekly.py`
- **Lookback**: 4 weeks for identification, 100 periods for signal calculation
- **Tables**: Uses `price_weekly`, `technical_data_weekly`, outputs to `buy_sell_weekly`

### 3. Latest Buy/Sell Monthly (`loadlatestbuysellmonthly.py`)
- **Purpose**: Processes monthly buy/sell signals for symbols with new technical indicators
- **Dependency**: Runs after `loadlatesttechnicalsmonthly.py`
- **Lookback**: 6 months for identification, 60 periods for signal calculation
- **Tables**: Uses `price_monthly`, `technical_data_monthly`, outputs to `buy_sell_monthly`

## Key Features

### Incremental Processing Logic
- **Smart Delta Detection**: Identifies symbols where technical indicators are newer than buy/sell signals
- **Efficient Updates**: Only processes symbols that actually need updates
- **Conflict Handling**: Uses ON CONFLICT DO UPDATE for database upserts
- **Data Cleanup**: Deletes existing data for date ranges being updated

### Signal Generation Algorithm
Uses the same proven algorithm as the full buy/sell scripts:

1. **Trend Analysis**: Price vs 50-period SMA
2. **RSI Signals**: 
   - Buy: RSI crosses above 50 in uptrend
   - Sell: RSI crosses below 50
3. **Breakout Signals**:
   - Buy: High breaks above pivot high
   - Sell: Low breaks below pivot low minus ATR buffer
4. **ADX Filter**: Optional strength filter (default >25)
5. **Position Tracking**: Maintains in/out position state

### Performance Optimizations
- **Ultra-fast NumPy vectorization** for signal calculations
- **Parallel processing** with ThreadPoolExecutor (2 workers)
- **Memory optimization** with float32/int32 data types
- **Bulk database operations** using execute_values
- **Connection pooling** and performance parameter tuning

### Database Schema
All scripts output to their respective `buy_sell_*` tables with schema:
```sql
CREATE TABLE buy_sell_daily (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20)    NOT NULL,
    timeframe    VARCHAR(10)    NOT NULL, 
    date         DATE           NOT NULL,
    signal       VARCHAR(10),     -- 'Buy', 'Sell', 'None'
    buylevel     REAL,           -- Breakout buy level
    stoplevel    REAL,           -- Stop loss level
    inposition   BOOLEAN,        -- Position state
    UNIQUE(symbol, timeframe, date)
);
```

## Dependencies

### Requirements (`requirements-latestbuysell.txt`)
```
psycopg2-binary==2.9.9
boto3==1.35.36
requests==2.32.3
pandas==2.2.2
numpy==1.26.4
psutil==6.0.0
```

### Environment Variables
- `DB_SECRET_ARN`: AWS Secrets Manager ARN for database credentials
- `FRED_API_KEY`: Federal Reserve Economic Data API key for risk-free rate

## Docker Configuration

### Dockerfiles
- `Dockerfile.latestbuyselldaily`
- `Dockerfile.latestbuysellweekly` 
- `Dockerfile.latestbuysellmonthly`

All use the same requirements file and follow identical build patterns.

## Execution Flow

### Recommended Pipeline Order
1. `loadlatestpricedaily.py` → loads new price data
2. `loadlatesttechnicalsdaily.py` → calculates technical indicators for new price data
3. `loadlatestbuyselldaily.py` → generates buy/sell signals for new technical data

### Parallel Processing
- **2 concurrent workers** for database stability
- **Per-symbol processing** with individual database connections
- **Progress tracking** with ETA calculations
- **Graceful error handling** with retry logic

### Memory Management
- **Aggressive garbage collection** every 10 symbols
- **Memory monitoring** with psutil RSS tracking
- **Optimized DataFrames** with proper data types
- **Connection cleanup** on completion/failure

## Error Handling

### Database Resilience
- **Connection timeouts** with retry logic
- **Statement timeouts** (300s default)
- **Lock timeouts** (60s) to prevent deadlocks
- **Graceful degradation** on failures

### Logging
- **Comprehensive progress tracking** with timing information
- **Memory usage monitoring** throughout execution
- **Error details** with stack traces for debugging
- **Performance metrics** (symbols/minute, records/second)

## Output
Each script produces detailed logs showing:
- Symbols requiring updates
- Processing progress with ETA
- Database insertion statistics
- Memory usage throughout execution
- Final success/failure summary

The scripts are designed to be highly efficient, processing only the minimal set of symbols that need updates while maintaining full signal accuracy through sufficient lookback periods for proper technical analysis.
