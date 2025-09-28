
const { initializeDatabase, query, closeDatabase } = require('./utils/database');

async function fixOrdersSchema() {
  try {
    console.log('🔧 Fixing orders database schema...');

    await initializeDatabase();

    // Add missing status column to orders/trades tables
    const schemaFixes = [
      {
        name: 'Add status column to trades table',
        sql: `ALTER TABLE trades ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'completed'`
      },
      {
        name: 'Add status column to orders table (if exists)',
        sql: `ALTER TABLE orders ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'completed'`
      },
      {
        name: 'Add missing columns to trades for orders compatibility',
        sql: `
          ALTER TABLE trades
          ADD COLUMN IF NOT EXISTS order_type VARCHAR(20) DEFAULT 'market',
          ADD COLUMN IF NOT EXISTS order_status VARCHAR(20) DEFAULT 'filled',
          ADD COLUMN IF NOT EXISTS filled_qty DECIMAL(15,6),
          ADD COLUMN IF NOT EXISTS avg_fill_price DECIMAL(15,2)
        `
      }
    ];

    for (const fix of schemaFixes) {
      console.log(`📝 ${fix.name}...`);
      try {
        await query(fix.sql);
        console.log(`✅ ${fix.name} - SUCCESS`);
      } catch (error) {
        console.log(`⚠️  ${fix.name} - ${error.message}`);
      }
    }

    console.log('🎉 Orders schema fixes completed!');

  } catch (error) {
    console.error('❌ Error fixing orders schema:', error);
  } finally {
    await closeDatabase();
  }
}

fixOrdersSchema();