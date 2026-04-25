require('dotenv').config({ path: '.env.local' });
const pg = require('pg');

const config = {
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  user: process.env.DB_USER || 'stocks',
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME || 'stocks'
};

const client = new pg.Client(config);

(async () => {
  try {
    await client.connect();
    
    // Find all financial-related tables
    const tables = await client.query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      AND table_name LIKE '%balance%' 
      OR table_name LIKE '%income%' 
      OR table_name LIKE '%cash%'
      OR table_name LIKE '%financial%'
      ORDER BY table_name
    `);
    
    console.log('\n=== FINANCIAL TABLES IN DATABASE ===\n');
    
    for (const row of tables.rows) {
      const tableName = row.table_name;
      
      // Get row count
      const countResult = await client.query(`SELECT COUNT(*) as cnt FROM ${tableName}`);
      const rowCount = countResult.rows[0].cnt;
      
      // Get column count
      const colResult = await client.query(`
        SELECT COUNT(*) as cnt FROM information_schema.columns 
        WHERE table_name = $1
      `, [tableName]);
      const colCount = colResult.rows[0].cnt;
      
      // Get sample data
      const sampleResult = await client.query(`SELECT * FROM ${tableName} LIMIT 1`);
      const hasSampleData = sampleResult.rows.length > 0;
      
      console.log(`${tableName}:`);
      console.log(`  - Rows: ${rowCount}`);
      console.log(`  - Columns: ${colCount}`);
      console.log(`  - Has data: ${hasSampleData ? 'YES' : 'NO'}`);
      
      if (hasSampleData && rowCount > 0) {
        const sample = sampleResult.rows[0];
        const keys = Object.keys(sample);
        console.log(`  - Sample columns: ${keys.slice(0, 10).join(', ')}...`);
      }
      console.log();
    }
    
    // Check what the API endpoints are querying
    console.log('\n=== API ENDPOINT CONFIGURATION ===\n');
    console.log('Checking webapp/lambda/routes/financials.js for table references...');
    
    await client.end();
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
})();
