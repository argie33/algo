// Web App Database Initialization Script
// Creates webapp-specific tables not covered by loader scripts
// Loader scripts create market data tables and take precedence

const { query } = require('./utils/database');

/**
 * Initialize webapp-specific database tables
 * Only creates tables not handled by data loaders
 */
async function initializeWebappTables() {
  console.log("🚀 Initializing webapp-specific database tables...");

  try {
    // Fix/create loader tables that need schema updates
    await fixLoaderTableSchemas();

    // User Management Tables
    await createUserTables();

    // Portfolio Management Tables
    await createPortfolioTables();

    // Watchlist Management Tables
    await createWatchlistTables();

    // Trading Strategy Tables
    await createTradingTables();

    // Alert Management Tables
    await createAlertTables();

    // Screener Tables
    await createScreenerTables();

    // Risk Management Tables
    await createRiskTables();

    // Audit and Activity Tables
    await createAuditTables();

    // Create indexes for performance
    await createIndexes();

    // Add update triggers
    await createTriggers();

    console.log("✅ Database schema creation completed - no data insertion in init script");

    console.log("✅ Webapp database initialization completed successfully!");
    return true;

  } catch (error) {
    console.error("❌ Webapp database initialization error:", error);
    throw error;
  }
}

async function fixLoaderTableSchemas() {
  console.log("🔧 Fixing loader table schemas to match loader scripts...");

  try {
    // Fix earnings_metrics table - recreate to match loadearningsmetrics.py schema
    console.log("  📊 Fixing earnings_metrics table schema...");

    // Drop and recreate to ensure correct schema
    await query("DROP TABLE IF EXISTS earnings_metrics CASCADE;");

    await query(`
      CREATE TABLE earnings_metrics (
        symbol VARCHAR(20) NOT NULL,
        report_date DATE NOT NULL,
        eps_qoq_growth DOUBLE PRECISION,
        eps_yoy_growth DOUBLE PRECISION,
        revenue_yoy_growth DOUBLE PRECISION,
        earnings_surprise_pct DOUBLE PRECISION,
        earnings_quality_score DOUBLE PRECISION,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, report_date)
      );
    `);

    await query("CREATE INDEX IF NOT EXISTS idx_earnings_metrics_symbol ON earnings_metrics(symbol);");
    await query("CREATE INDEX IF NOT EXISTS idx_earnings_metrics_quality_score ON earnings_metrics(earnings_quality_score DESC);");
    await query("CREATE INDEX IF NOT EXISTS idx_earnings_metrics_date ON earnings_metrics(report_date DESC);");

    console.log("  ✅ earnings_metrics table schema fixed");

  } catch (error) {
    console.error("  ❌ Loader table schema fix error:", error);
    // Don't throw - allow other tables to be created
  }
}

async function createUserTables() {
  console.log("📝 Creating user management tables...");

  const tables = [
    {
      name: "user_profiles",
      sql: `CREATE TABLE IF NOT EXISTS user_profiles (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        username VARCHAR(100),
        first_name VARCHAR(100),
        last_name VARCHAR(100),
        phone VARCHAR(20),
        country VARCHAR(50) DEFAULT 'US',
        timezone VARCHAR(50) DEFAULT 'America/New_York',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        is_active BOOLEAN DEFAULT TRUE
      )`
    },
    {
      name: "user_dashboard_settings",
      sql: `CREATE TABLE IF NOT EXISTS user_dashboard_settings (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) UNIQUE NOT NULL,
        theme VARCHAR(20) DEFAULT 'light',
        default_watchlist_id INTEGER,
        dashboard_layout JSONB,
        chart_preferences JSONB,
        notification_settings JSONB,
        risk_tolerance VARCHAR(20) DEFAULT 'moderate',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )`
    },
    {
      name: "user_2fa_secrets",
      sql: `CREATE TABLE IF NOT EXISTS user_2fa_secrets (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) UNIQUE NOT NULL,
        secret_encrypted TEXT NOT NULL,
        backup_codes_encrypted TEXT[],
        is_enabled BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP
      )`
    }
  ];

  for (const table of tables) {
    await query(table.sql);
    console.log(`  ✅ Created table: ${table.name}`);
  }
}

async function createPortfolioTables() {
  console.log("💼 Creating portfolio management tables...");

  const tables = [
    {
      name: "portfolio_transactions",
      sql: `CREATE TABLE IF NOT EXISTS portfolio_transactions (
        transaction_id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        transaction_type VARCHAR(20) NOT NULL,
        quantity DECIMAL(15,4) NOT NULL,
        price DECIMAL(15,4) NOT NULL,
        total_amount DECIMAL(15,4) NOT NULL,
        commission DECIMAL(10,4) DEFAULT 0.00,
        transaction_date TIMESTAMP NOT NULL,
        settlement_date TIMESTAMP,
        notes TEXT,
        user_id VARCHAR(50) NOT NULL,
        broker VARCHAR(50) DEFAULT 'manual',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )`
    },
    {
      name: "portfolio_holdings",
      sql: `CREATE TABLE IF NOT EXISTS portfolio_holdings (
        holding_id SERIAL PRIMARY KEY,
        user_id VARCHAR(50) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        quantity DECIMAL(15,4) NOT NULL,
        average_cost DECIMAL(15,4) NOT NULL,
        current_price DECIMAL(15,4) DEFAULT 0,
        market_value DECIMAL(15,4) DEFAULT 0,
        unrealized_pnl DECIMAL(15,4) DEFAULT 0,
        unrealized_pnl_percent DECIMAL(10,4) DEFAULT 0,
        sector VARCHAR(100),
        cost_basis DECIMAL(15,4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, symbol)
      )`
    },
    {
      name: "portfolio_performance",
      sql: `CREATE TABLE IF NOT EXISTS portfolio_performance (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        date DATE,
        total_value DECIMAL(15,2),
        total_cost DECIMAL(15,2),
        cash_balance DECIMAL(15,2) DEFAULT 0,
        day_change DECIMAL(15,2),
        day_change_percent DECIMAL(8,4),
        total_return DECIMAL(15,2),
        total_return_percent DECIMAL(8,4),
        daily_pnl DECIMAL(15,2),
        daily_pnl_percent DECIMAL(8,4),
        broker VARCHAR(50) DEFAULT 'combined',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, date)
      )`
    }
  ];

  for (const table of tables) {
    await query(table.sql);
    console.log(`  ✅ Created table: ${table.name}`);
  }
}

async function createWatchlistTables() {
  console.log("👀 Creating watchlist management tables...");

  const tables = [
    {
      name: "watchlists",
      sql: `CREATE TABLE IF NOT EXISTS watchlists (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        name VARCHAR(100) NOT NULL,
        description TEXT,
        is_default BOOLEAN DEFAULT FALSE,
        is_public BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name)
      )`
    },
    {
      name: "watchlist_items",
      sql: `CREATE TABLE IF NOT EXISTS watchlist_items (
        id SERIAL PRIMARY KEY,
        watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
        symbol VARCHAR(20) NOT NULL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        notes TEXT,
        target_price DECIMAL(15,4),
        alert_enabled BOOLEAN DEFAULT FALSE,
        sort_order INTEGER DEFAULT 0,
        UNIQUE(watchlist_id, symbol)
      )`
    },
    {
      name: "watchlist_performance",
      sql: `CREATE TABLE IF NOT EXISTS watchlist_performance (
        id SERIAL PRIMARY KEY,
        watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        total_value DECIMAL(15,2),
        day_change DECIMAL(15,2),
        day_change_percent DECIMAL(8,4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(watchlist_id, date)
      )`
    }
  ];

  for (const table of tables) {
    await query(table.sql);
    console.log(`  ✅ Created table: ${table.name}`);
  }
}

async function createTradingTables() {
  console.log("📈 Creating trading strategy tables...");

  const tables = [
    {
      name: "trading_strategies",
      sql: `CREATE TABLE IF NOT EXISTS trading_strategies (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        name VARCHAR(100) NOT NULL,
        description TEXT,
        strategy_type VARCHAR(50),
        conditions JSONB NOT NULL,
        actions JSONB NOT NULL,
        risk_parameters JSONB,
        is_active BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_executed TIMESTAMP,
        UNIQUE(user_id, name)
      )`
    },
    {
      name: "orders",
      sql: `CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(20) NOT NULL,
        order_type VARCHAR(20) NOT NULL,
        side VARCHAR(10) NOT NULL,
        quantity DECIMAL(15,8) NOT NULL,
        price DECIMAL(15,4),
        stop_price DECIMAL(15,4),
        time_in_force VARCHAR(10) DEFAULT 'DAY',
        status VARCHAR(20) DEFAULT 'pending',
        broker VARCHAR(50) DEFAULT 'manual',
        broker_order_id VARCHAR(100),
        filled_quantity DECIMAL(15,8) DEFAULT 0,
        avg_fill_price DECIMAL(15,4),
        commission DECIMAL(10,2) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        filled_at TIMESTAMP,
        cancelled_at TIMESTAMP,
        notes TEXT
      )`
    },
    {
      name: "trades",
      sql: `CREATE TABLE IF NOT EXISTS trades (
        id SERIAL PRIMARY KEY,
        trade_id VARCHAR(100) UNIQUE NOT NULL,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(20) NOT NULL,
        side VARCHAR(10) NOT NULL,
        quantity DECIMAL(15,8) NOT NULL,
        price DECIMAL(15,4) NOT NULL,
        total_amount DECIMAL(15,2) NOT NULL,
        commission DECIMAL(10,2) DEFAULT 0,
        realized_pnl DECIMAL(15,2),
        status VARCHAR(20) DEFAULT 'completed',
        trade_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        settlement_date DATE,
        broker VARCHAR(50) DEFAULT 'manual',
        broker_trade_id VARCHAR(100),
        order_id INTEGER REFERENCES orders(id),
        strategy_id INTEGER REFERENCES trading_strategies(id),
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )`
    }
  ];

  for (const table of tables) {
    await query(table.sql);
    console.log(`  ✅ Created table: ${table.name}`);
  }
}

async function createAlertTables() {
  console.log("🚨 Creating alert management tables...");

  const tables = [
    {
      name: "price_alerts",
      sql: `CREATE TABLE IF NOT EXISTS price_alerts (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(20) NOT NULL,
        alert_type VARCHAR(20) NOT NULL,
        target_value DECIMAL(15,4) NOT NULL,
        current_value DECIMAL(15,4),
        is_triggered BOOLEAN DEFAULT FALSE,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        triggered_at TIMESTAMP,
        message TEXT
      )`
    },
    {
      name: "risk_alerts",
      sql: `CREATE TABLE IF NOT EXISTS risk_alerts (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        alert_type VARCHAR(50) NOT NULL,
        threshold_value DECIMAL(15,4) NOT NULL,
        current_value DECIMAL(15,4),
        is_triggered BOOLEAN DEFAULT FALSE,
        is_active BOOLEAN DEFAULT TRUE,
        symbol VARCHAR(20),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        triggered_at TIMESTAMP,
        message TEXT
      )`
    },
    {
      name: "alert_settings",
      sql: `CREATE TABLE IF NOT EXISTS alert_settings (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL UNIQUE,
        notification_preferences JSONB DEFAULT '{}',
        delivery_settings JSONB DEFAULT '{}',
        alert_categories JSONB DEFAULT '{}',
        watchlist_settings JSONB DEFAULT '{}',
        advanced_settings JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )`
    },
    {
      name: "trading_alerts",
      sql: `CREATE TABLE IF NOT EXISTS trading_alerts (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        alert_type VARCHAR(50) NOT NULL,
        title VARCHAR(255),
        description TEXT,
        trigger_price DECIMAL(12,4),
        current_price DECIMAL(12,4),
        trigger_condition VARCHAR(20),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        triggered_at TIMESTAMP NULL,
        expires_at TIMESTAMP NULL,
        acknowledged_at TIMESTAMP NULL
      )`
    }
  ];

  for (const table of tables) {
    await query(table.sql);
    console.log(`  ✅ Created table: ${table.name}`);
  }
}

async function createScreenerTables() {
  console.log("🔍 Creating screener tables...");

  const tables = [
    {
      name: "saved_screens",
      sql: `CREATE TABLE IF NOT EXISTS saved_screens (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        name VARCHAR(100) NOT NULL,
        description TEXT,
        filters JSONB NOT NULL,
        sort_by VARCHAR(50),
        sort_direction VARCHAR(10) DEFAULT 'DESC',
        is_public BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name)
      )`
    }
  ];

  for (const table of tables) {
    await query(table.sql);
    console.log(`  ✅ Created table: ${table.name}`);
  }
}

async function createRiskTables() {
  console.log("⚠️ Creating risk management tables...");

  const tables = [
    {
      name: "user_risk_limits",
      sql: `CREATE TABLE IF NOT EXISTS user_risk_limits (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) UNIQUE NOT NULL,
        max_position_size_percent DECIMAL(5,2) DEFAULT 10.00,
        max_sector_allocation_percent DECIMAL(5,2) DEFAULT 25.00,
        max_daily_loss_percent DECIMAL(5,2) DEFAULT 5.00,
        max_portfolio_var DECIMAL(5,2) DEFAULT 10.00,
        stop_loss_percent DECIMAL(5,2) DEFAULT 10.00,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )`
    }
  ];

  for (const table of tables) {
    await query(table.sql);
    console.log(`  ✅ Created table: ${table.name}`);
  }
}

async function createAuditTables() {
  console.log("📋 Creating audit and activity tables...");

  const tables = [
    {
      name: "user_activity_log",
      sql: `CREATE TABLE IF NOT EXISTS user_activity_log (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        action VARCHAR(100) NOT NULL,
        details JSONB,
        ip_address INET,
        user_agent TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )`
    }
  ];

  for (const table of tables) {
    await query(table.sql);
    console.log(`  ✅ Created table: ${table.name}`);
  }
}

async function createIndexes() {
  console.log("🔧 Creating performance indexes...");

  const indexes = [
    "CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email)",
    "CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_user ON portfolio_transactions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_symbol ON portfolio_transactions(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user ON portfolio_holdings(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_portfolio_performance_user_date ON portfolio_performance(user_id, date)",
    "CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_items_symbol ON watchlist_items(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_price_alerts_user_id ON price_alerts(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_price_alerts_symbol ON price_alerts(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_price_alerts_active ON price_alerts(is_active) WHERE is_active = TRUE",
    "CREATE INDEX IF NOT EXISTS idx_risk_alerts_user_id ON risk_alerts(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_trading_strategies_user_id ON trading_strategies(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_trading_strategies_active ON trading_strategies(is_active) WHERE is_active = TRUE",
    "CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_trades_trade_date ON trades(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_trades_trade_id ON trades(trade_id)",
    "CREATE INDEX IF NOT EXISTS idx_alert_settings_user_id ON alert_settings(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_trading_alerts_user_id ON trading_alerts(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_trading_alerts_symbol ON trading_alerts(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_trading_alerts_active ON trading_alerts(is_active) WHERE is_active = TRUE",
    "CREATE INDEX IF NOT EXISTS idx_user_activity_log_user_id ON user_activity_log(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_activity_log_created_at ON user_activity_log(created_at)"
  ];

  for (const indexSql of indexes) {
    try {
      await query(indexSql);
    } catch (error) {
      console.warn(`  ⚠️ Index creation warning: ${error.message}`);
    }
  }
  console.log(`  ✅ Created ${indexes.length} performance indexes`);
}

async function createTriggers() {
  console.log("⚡ Creating update triggers...");

  try {
    // Create update function
    await query(`
      CREATE OR REPLACE FUNCTION update_updated_at_column()
      RETURNS TRIGGER AS $$
      BEGIN
          NEW.updated_at = CURRENT_TIMESTAMP;
          RETURN NEW;
      END;
      $$ language 'plpgsql'
    `);

    // Create triggers
    const triggers = [
      "CREATE TRIGGER update_user_profiles_updated_at BEFORE UPDATE ON user_profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
      "CREATE TRIGGER update_user_dashboard_settings_updated_at BEFORE UPDATE ON user_dashboard_settings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
      "CREATE TRIGGER update_portfolio_holdings_updated_at BEFORE UPDATE ON portfolio_holdings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
      "CREATE TRIGGER update_watchlists_updated_at BEFORE UPDATE ON watchlists FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
      "CREATE TRIGGER update_trading_strategies_updated_at BEFORE UPDATE ON trading_strategies FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
      "CREATE TRIGGER update_saved_screens_updated_at BEFORE UPDATE ON saved_screens FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
      "CREATE TRIGGER update_user_risk_limits_updated_at BEFORE UPDATE ON user_risk_limits FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
      "CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
      "CREATE TRIGGER update_alert_settings_updated_at BEFORE UPDATE ON alert_settings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
    ];

    for (const triggerSql of triggers) {
      try {
        await query(triggerSql);
      } catch (error) {
        if (!error.message.includes('already exists')) {
          console.warn(`  ⚠️ Trigger creation warning: ${error.message}`);
        }
      }
    }
    console.log(`  ✅ Created update triggers`);
  } catch (error) {
    console.warn(`  ⚠️ Trigger setup warning: ${error.message}`);
  }
}


module.exports = {
  initializeWebappTables
};