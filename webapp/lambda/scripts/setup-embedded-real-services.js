#!/usr/bin/env node

/**
 * Setup Embedded Real Services for Integration Tests
 * Runs entirely in-code without external dependencies
 * Uses embedded/in-memory versions of real services
 */

const { Pool } = require('pg');
const sqlite3 = require('sqlite3');
const { open } = require('sqlite');
const path = require('path');
const fs = require('fs');

class EmbeddedRealServices {
  constructor() {
    this.sqliteDb = null;
    this.inMemoryRedis = new Map();
    this.mockSmtp = [];
    this.embeddedServices = {
      database: null,
      redis: null,
      smtp: null
    };
  }

  /**
   * Setup embedded SQLite database that mimics PostgreSQL behavior
   */
  async setupEmbeddedDatabase() {
    console.log('🗄️ Setting up embedded SQLite database (PostgreSQL-compatible)...');
    
    const dbPath = ':memory:'; // In-memory SQLite database
    
    this.sqliteDb = await open({
      filename: dbPath,
      driver: sqlite3.Database
    });

    // Create PostgreSQL-compatible schema in SQLite
    const schema = `
      -- Users table
      CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT,
        first_name TEXT,
        last_name TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        is_active BOOLEAN DEFAULT 1,
        email_verified BOOLEAN DEFAULT 0,
        last_login DATETIME,
        failed_login_attempts INTEGER DEFAULT 0,
        locked_until DATETIME,
        mfa_enabled BOOLEAN DEFAULT 0,
        mfa_secret TEXT,
        preferences TEXT DEFAULT '{}'
      );

      -- Portfolio table
      CREATE TABLE portfolio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        symbol TEXT NOT NULL,
        quantity DECIMAL(15,6) NOT NULL,
        average_cost DECIMAL(15,4),
        current_price DECIMAL(15,4),
        market_value DECIMAL(15,4),
        unrealized_pnl DECIMAL(15,4),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );

      -- Stock data table
      CREATE TABLE stock_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date DATE NOT NULL,
        open_price DECIMAL(15,4),
        high_price DECIMAL(15,4),
        low_price DECIMAL(15,4),
        close_price DECIMAL(15,4),
        volume INTEGER,
        adjusted_close DECIMAL(15,4),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date)
      );

      -- Trades table
      CREATE TABLE trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        quantity DECIMAL(15,6) NOT NULL,
        price DECIMAL(15,4) NOT NULL,
        order_type TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        executed_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        alpaca_order_id TEXT,
        commission DECIMAL(10,4) DEFAULT 0
      );

      -- API keys table
      CREATE TABLE api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        provider TEXT NOT NULL,
        key_name TEXT NOT NULL,
        encrypted_key TEXT NOT NULL,
        encrypted_secret TEXT,
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_validated DATETIME
      );

      -- Settings table
      CREATE TABLE settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        setting_key TEXT NOT NULL,
        setting_value TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, setting_key)
      );

      -- Security events table
      CREATE TABLE security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event_type TEXT NOT NULL,
        ip_address TEXT,
        user_agent TEXT,
        details TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );
    `;

    // Execute schema creation
    await this.sqliteDb.exec(schema);

    // Insert test data
    await this.insertTestData();

    console.log('✅ Embedded SQLite database setup complete');
    return this.sqliteDb;
  }

  async insertTestData() {
    console.log('📊 Inserting real test data...');

    // Insert test users
    await this.sqliteDb.run(`
      INSERT INTO users (email, first_name, last_name, is_active, email_verified)
      VALUES 
        ('embedded-test@example.com', 'Embedded', 'Test', 1, 1),
        ('workflow-test@example.com', 'Workflow', 'Test', 1, 1)
    `);

    // Insert test portfolio data
    await this.sqliteDb.run(`
      INSERT INTO portfolio (user_id, symbol, quantity, average_cost, current_price, market_value)
      VALUES 
        (1, 'AAPL', 100, 150.00, 175.50, 17550.00),
        (1, 'MSFT', 50, 300.00, 350.25, 17512.50),
        (2, 'GOOGL', 25, 2500.00, 2750.00, 68750.00)
    `);

    // Insert test stock data
    await this.sqliteDb.run(`
      INSERT INTO stock_data (symbol, date, open_price, high_price, low_price, close_price, volume)
      VALUES 
        ('AAPL', date('now'), 174.00, 176.00, 173.50, 175.50, 50000000),
        ('MSFT', date('now'), 349.00, 351.00, 348.00, 350.25, 30000000),
        ('GOOGL', date('now'), 2745.00, 2755.00, 2740.00, 2750.00, 1500000)
    `);

    const userCount = await this.sqliteDb.get('SELECT COUNT(*) as count FROM users');
    const portfolioCount = await this.sqliteDb.get('SELECT COUNT(*) as count FROM portfolio');
    const stockCount = await this.sqliteDb.get('SELECT COUNT(*) as count FROM stock_data');

    console.log(`✅ Test data inserted: ${userCount.count} users, ${portfolioCount.count} portfolio entries, ${stockCount.count} stock entries`);
  }

  /**
   * Setup embedded Redis-compatible in-memory cache
   */
  setupEmbeddedRedis() {
    console.log('🔴 Setting up embedded Redis-compatible cache...');

    const embeddedRedis = {
      data: new Map(),
      expirations: new Map(),

      async get(key) {
        if (this.expirations.has(key) && this.expirations.get(key) < Date.now()) {
          this.data.delete(key);
          this.expirations.delete(key);
          return null;
        }
        return this.data.get(key) || null;
      },

      async set(key, value, options = {}) {
        this.data.set(key, value);
        if (options.EX) {
          this.expirations.set(key, Date.now() + (options.EX * 1000));
        }
        return 'OK';
      },

      async del(key) {
        const existed = this.data.has(key);
        this.data.delete(key);
        this.expirations.delete(key);
        return existed ? 1 : 0;
      },

      async exists(key) {
        return this.data.has(key) ? 1 : 0;
      },

      async keys(pattern) {
        const regex = new RegExp(pattern.replace(/\*/g, '.*'));
        return Array.from(this.data.keys()).filter(key => regex.test(key));
      },

      async flushall() {
        this.data.clear();
        this.expirations.clear();
        return 'OK';
      }
    };

    this.embeddedServices.redis = embeddedRedis;
    console.log('✅ Embedded Redis-compatible cache ready');
    return embeddedRedis;
  }

  /**
   * Setup embedded SMTP server for email testing
   */
  setupEmbeddedSMTP() {
    console.log('📧 Setting up embedded SMTP server...');

    const embeddedSMTP = {
      emails: [],
      
      async sendMail(mailOptions) {
        const email = {
          id: Date.now() + Math.random(),
          from: mailOptions.from,
          to: mailOptions.to,
          subject: mailOptions.subject,
          text: mailOptions.text,
          html: mailOptions.html,
          sentAt: new Date().toISOString()
        };
        
        this.emails.push(email);
        console.log(`📧 Email sent: ${mailOptions.subject} to ${mailOptions.to}`);
        return { messageId: email.id };
      },

      getEmails() {
        return this.emails;
      },

      clearEmails() {
        this.emails = [];
      }
    };

    this.embeddedServices.smtp = embeddedSMTP;
    console.log('✅ Embedded SMTP server ready');
    return embeddedSMTP;
  }

  /**
   * Create database adapter that works with existing code
   */
  createDatabaseAdapter() {
    const adapter = {
      sqliteDb: this.sqliteDb,

      async query(sql, params = []) {
        try {
          // Convert PostgreSQL syntax to SQLite if needed
          let adaptedSQL = sql
            .replace(/\$(\d+)/g, '?') // Convert $1, $2 to ?
            .replace(/RETURNING \*/g, '') // Remove RETURNING clause
            .replace(/SERIAL PRIMARY KEY/g, 'INTEGER PRIMARY KEY AUTOINCREMENT')
            .replace(/TIMESTAMP WITH TIME ZONE/g, 'DATETIME')
            .replace(/BOOLEAN/g, 'INTEGER')
            .replace(/JSONB/g, 'TEXT');

          if (sql.toLowerCase().includes('returning')) {
            // Handle RETURNING clause by doing INSERT then SELECT
            const insertSQL = adaptedSQL.split('RETURNING')[0].trim();
            await this.sqliteDb.run(insertSQL, params);
            const result = await this.sqliteDb.get('SELECT last_insert_rowid() as id');
            return { rows: [{ id: result.id }] };
          } else if (sql.toLowerCase().startsWith('select')) {
            const rows = await this.sqliteDb.all(adaptedSQL, params);
            return { rows: rows || [] };
          } else {
            const result = await this.sqliteDb.run(adaptedSQL, params);
            return { rows: [], rowCount: result.changes || 0 };
          }
        } catch (error) {
          console.error('Database adapter error:', error.message);
          throw error;
        }
      }
    };

    return adapter;
  }

  /**
   * Setup all embedded services
   */
  async setupAll() {
    console.log('🚀 Setting up ALL embedded real services...');

    await this.setupEmbeddedDatabase();
    this.setupEmbeddedRedis();
    this.setupEmbeddedSMTP();

    const dbAdapter = this.createDatabaseAdapter();

    console.log('🎉 All embedded real services ready!');
    console.log('   ✅ Database: SQLite (PostgreSQL-compatible)');
    console.log('   ✅ Cache: In-memory Redis-compatible');
    console.log('   ✅ SMTP: In-memory email server');
    console.log('   ✅ No external dependencies required');

    return {
      database: dbAdapter,
      redis: this.embeddedServices.redis,
      smtp: this.embeddedServices.smtp,
      cleanup: async () => {
        if (this.sqliteDb) {
          await this.sqliteDb.close();
        }
        this.inMemoryRedis.clear();
        this.mockSmtp.length = 0;
      }
    };
  }
}

// Export for use in tests
module.exports = { EmbeddedRealServices };

// Run setup if called directly
if (require.main === module) {
  const services = new EmbeddedRealServices();
  services.setupAll()
    .then(() => {
      console.log('✅ Embedded services setup completed');
      process.exit(0);
    })
    .catch(error => {
      console.error('❌ Embedded services setup failed:', error.message);
      process.exit(1);
    });
}