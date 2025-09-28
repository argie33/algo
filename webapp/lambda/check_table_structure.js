
// Script to check current table structures
process.env.NODE_ENV = "test";
process.env.DB_HOST = "localhost";
process.env.DB_USER = "postgres";
process.env.DB_PASSWORD = "password";
process.env.DB_NAME = "stocks";
process.env.DB_PORT = "5432";
process.env.DB_SSL = "false";

async function checkTableStructure(tableName) {
  const { query } = require('./utils/database');

  try {
    console.log(`\n🔍 Checking structure of ${tableName} table...`);

    // Check if table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = $1
      );
    `, [tableName]);

    if (!tableExists.rows[0].exists) {
      console.log(`❌ Table ${tableName} does not exist`);
      return;
    }

    // Get column information
    const columns = await query(`
      SELECT column_name, data_type, is_nullable, column_default
      FROM information_schema.columns
      WHERE table_name = $1
      ORDER BY ordinal_position;
    `, [tableName]);

    console.log(`✅ Table ${tableName} exists with ${columns.rows.length} columns:`);
    columns.rows.forEach(col => {
      console.log(`  - ${col.column_name}: ${col.data_type} ${col.is_nullable === 'NO' ? '(NOT NULL)' : '(NULLABLE)'}`);
    });

  } catch (error) {
    console.error(`❌ Error checking table ${tableName}:`, error.message);
  }
}

async function main() {
  try {
    await checkTableStructure('portfolio_transactions');
    await checkTableStructure('trade_history');
    await checkTableStructure('portfolio_holdings');
  } catch (error) {
    console.error('💥 Check failed:', error);
    process.exit(1);
  }
}

main();