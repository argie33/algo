const { query } = require('./utils/database');

async function checkScoresTable() {
  try {
    console.log('🔍 Checking scores-related tables...\n');

    // Check if stock_scores table exists and its structure
    try {
      const result = await query(`
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'stock_scores'
        ORDER BY ordinal_position;
      `);

      if (result.rows.length > 0) {
        console.log('✅ stock_scores table columns:');
        result.rows.forEach(row => {
          console.log(`   • ${row.column_name} (${row.data_type})`);
        });
      } else {
        console.log('❌ stock_scores table not found');
      }
    } catch (err) {
      console.log('❌ Error checking stock_scores table:', err.message);
    }

    console.log('\n🔍 Checking for other score-related tables...\n');

    // Check for other scoring tables
    const tables = await query(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
        AND table_name LIKE '%score%'
      ORDER BY table_name;
    `);

    if (tables.rows.length > 0) {
      console.log('📊 Found score-related tables:');
      for (const table of tables.rows) {
        console.log(`\n   📋 ${table.table_name}:`);
        try {
          const cols = await query(`
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = $1
            ORDER BY ordinal_position;
          `, [table.table_name]);

          cols.rows.forEach(col => {
            console.log(`      • ${col.column_name} (${col.data_type})`);
          });
        } catch (err) {
          console.log(`      ❌ Error: ${err.message}`);
        }
      }
    } else {
      console.log('❌ No score-related tables found');
    }

    // Check for data in any existing tables
    console.log('\n🔍 Checking for actual data...\n');
    try {
      const dataCheck = await query('SELECT COUNT(*) as count FROM stock_scores LIMIT 1');
      console.log(`📊 stock_scores table has ${dataCheck.rows[0]?.count || 0} records`);
    } catch (err) {
      console.log('❌ No data in stock_scores or table does not exist');
    }

  } catch (error) {
    console.error('❌ Database connection error:', error.message);
  } finally {
    process.exit(0);
  }
}

checkScoresTable();