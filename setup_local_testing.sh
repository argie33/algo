#!/bin/bash
set -e

cd /mnt/c/Users/arger/code/algo

echo "=========================================="
echo "SETUP: Local Algo Testing Environment"
echo "=========================================="
echo ""

# Create and activate venv
echo "1️⃣ Creating Python virtual environment..."
python3 -m venv venv_test
source venv_test/bin/activate

echo "✅ Venv activated"
echo ""

# Install requirements
echo "2️⃣ Installing Python dependencies..."
pip install -q psycopg2-binary requests pandas numpy scipy scikit-learn 2>&1 | grep -v "already satisfied" || true

echo "✅ Dependencies installed"
echo ""

# Set environment variables for local testing
echo "3️⃣ Configuring environment..."
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=stocks
export DB_USER=stocks
export DB_PASSWORD=postgres
export ENVIRONMENT=local
export EXECUTION_MODE=paper
export DRY_RUN=true
export ORCHESTRATOR_LOG_LEVEL=info

echo "✅ Environment configured"
echo ""

# Load comprehensive test data
echo "4️⃣ Loading comprehensive test data into PostgreSQL..."
cat << 'EOSQL' | docker exec -i stocks_db psql -U stocks -d stocks > /dev/null

-- Load sample data from CSV
COPY stock_symbols (symbol, security_name, exchange, market_category)
FROM STDIN WITH (FORMAT csv, DELIMITER '|', HEADER false)
SELECT symbol, security_name, exchange, market_category
FROM (VALUES
  ('AAPL','Apple Inc','NASDAQ','stocks'),
  ('MSFT','Microsoft Corp','NASDAQ','stocks'),
  ('GOOGL','Alphabet Inc','NASDAQ','stocks'),
  ('AMZN','Amazon Com','NASDAQ','stocks'),
  ('TSLA','Tesla Inc','NASDAQ','stocks'),
  ('NVDA','NVIDIA Corp','NASDAQ','stocks'),
  ('META','Meta Platforms','NASDAQ','stocks'),
  ('JPM','JPMorgan Chase','NYSE','stocks'),
  ('V','Visa Inc','NYSE','stocks'),
  ('JNJ','Johnson Johnson','NYSE','stocks'),
  ('PG','Procter Gamble','NYSE','stocks'),
  ('KO','Coca Cola','NYSE','stocks'),
  ('DIS','Disney Inc','NYSE','stocks'),
  ('NFLX','Netflix Inc','NASDAQ','stocks'),
  ('UBER','Uber Tech','NYSE','stocks')
) AS t(symbol, security_name, exchange, market_category)
WHERE NOT EXISTS (SELECT 1 FROM stock_symbols WHERE symbol = t.symbol);

-- Load stock scores
INSERT INTO stock_scores (symbol, composite_score, momentum_score, quality_score, value_score)
SELECT symbol,
  70.0 + (random() * 20),
  65.0 + (random() * 25),
  70.0 + (random() * 20),
  68.0 + (random() * 22)
FROM stock_symbols
ON CONFLICT (symbol) DO NOTHING;

EOSQL

echo "✅ Test data loaded"
echo ""

# Show loaded data
echo "5️⃣ Verifying data..."
docker exec stocks_db psql -U stocks -d stocks << 'EOSQL'
SELECT
  (SELECT COUNT(*) FROM stock_symbols) as symbols,
  (SELECT COUNT(*) FROM stock_scores) as scores,
  (SELECT COUNT(*) FROM price_daily) as prices,
  (SELECT COUNT(*) FROM algo_positions) as positions,
  (SELECT COUNT(*) FROM algo_trades) as trades;
EOSQL

echo ""
echo "=========================================="
echo "✅ LOCAL TESTING ENVIRONMENT READY"
echo "=========================================="
echo ""
echo "Environment set:"
echo "  DB_HOST: $DB_HOST:$DB_PORT"
echo "  DB: $DB_NAME"
echo "  MODE: $EXECUTION_MODE (DRY_RUN=$DRY_RUN)"
echo ""
echo "Next steps:"
echo "  source venv_test/bin/activate"
echo "  python3 -c 'from algo_orchestrator import run_orchestrator; print(run_orchestrator())'"
echo ""
