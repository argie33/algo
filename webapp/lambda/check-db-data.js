// Direct database check script
const { Client } = require('pg');
require('dotenv').config();

async function checkDatabase() {
  // Try AWS RDS configuration first (matching .env)
  let clientConfig;
  
  if (process.env.USE_AWS_SECRETS === 'true') {
    console.log('🔐 Attempting AWS RDS connection...');
    // We'll need to get the secret, but for now try the RDS endpoint directly
    clientConfig = {
      host: 'stocks-db-dev.ch7hvtpgibhf.us-east-1.rds.amazonaws.com',
      port: 5432,
      database: 'stocks',
      user: 'stocks_admin', // typical RDS setup
      password: process.env.DB_PASSWORD || 'password', // fallback
      ssl: { rejectUnauthorized: false }
    };
  } else {
    console.log('🏠 Attempting local database connection...');
    clientConfig = {
      host: 'localhost',
      port: 5432,
      database: 'stocks',
      user: 'postgres',
      password: 'postgres'
    };
  }
  
  const client = new Client(clientConfig);

  try {
    await client.connect();
    console.log('✅ Connected to database');

    // Check tables
    const tables = await client.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      ORDER BY table_name
    `);
    console.log('📊 Available tables:', tables.rows.map(r => r.table_name));

    // Check stock_symbols data
    if (tables.rows.some(r => r.table_name === 'stock_symbols')) {
      const count = await client.query('SELECT COUNT(*) as count FROM stock_symbols');
      console.log('📈 Total stocks in stock_symbols:', count.rows[0].count);
      
      const activeCount = await client.query('SELECT COUNT(*) as count FROM stock_symbols WHERE is_active = true');
      console.log('📈 Active stocks:', activeCount.rows[0].count);

      // Sample data
      const sample = await client.query('SELECT symbol, name, sector, exchange FROM stock_symbols WHERE is_active = true LIMIT 5');
      console.log('📋 Sample stocks:', sample.rows);
    }

    // Check price_daily data
    if (tables.rows.some(r => r.table_name === 'price_daily')) {
      const priceCount = await client.query('SELECT COUNT(*) as count FROM price_daily');
      console.log('📈 Price records:', priceCount.rows[0].count);
      
      const recentPrices = await client.query(`
        SELECT symbol, date, close 
        FROM price_daily 
        ORDER BY date DESC 
        LIMIT 5
      `);
      console.log('📋 Recent prices:', recentPrices.rows);
    }

  } catch (error) {
    console.error('❌ Database error:', error.message);
  } finally {
    await client.end();
  }
}

checkDatabase();