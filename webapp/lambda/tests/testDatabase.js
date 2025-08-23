const { newDb } = require("pg-mem");

// Create in-memory PostgreSQL database for testing
const createTestDatabase = () => {
  const db = newDb();

  // Create test schema
  db.public.none(`
    CREATE TABLE user_portfolio (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      symbol VARCHAR(10) NOT NULL,
      quantity REAL NOT NULL DEFAULT 0,
      avg_cost REAL NOT NULL DEFAULT 0,
      last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE user_api_keys (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      provider VARCHAR(50) NOT NULL,
      encrypted_data TEXT,
      user_salt TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      last_used TIMESTAMP DEFAULT NULL,
      UNIQUE(user_id, provider)
    );

    CREATE TABLE stock_prices (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      price REAL NOT NULL,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      volume INTEGER DEFAULT 0
    );

    CREATE TABLE risk_alerts (
      id VARCHAR(50) PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      alert_type VARCHAR(50) NOT NULL,
      message TEXT,
      severity VARCHAR(20) DEFAULT 'medium',
      status VARCHAR(20) DEFAULT 'active',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      acknowledged_at TIMESTAMP NULL
    );
  `);

  const adapter = db.adapters.createPg();

  // pg-mem returns an object with Pool and Client, we need to create a client
  const client = new adapter.Client();
  return client;
};

module.exports = { createTestDatabase };
