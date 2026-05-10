const fs = require('fs');
const path = require('path');
const { getPool } = require('./utils/database');

/**
 * Initialize webapp database tables from migration files
 * Runs all .sql files in the migrations directory in alphabetical order
 */
async function initializeWebappTables() {
  try {
    const pool = getPool();
    const migrationsDir = path.join(__dirname, 'migrations');

    // Check if migrations directory exists
    if (!fs.existsSync(migrationsDir)) {
      console.log('No migrations directory found, skipping migrations');
      return true;
    }

    // Read all migration files
    const migrationFiles = fs.readdirSync(migrationsDir)
      .filter(file => file.endsWith('.sql'))
      .sort();

    if (migrationFiles.length === 0) {
      console.log('No migration files found');
      return true;
    }

    console.log(`Found ${migrationFiles.length} migration files to execute`);

    // Execute each migration
    for (const migrationFile of migrationFiles) {
      const filePath = path.join(migrationsDir, migrationFile);
      const sql = fs.readFileSync(filePath, 'utf8');

      try {
        console.log(`Executing migration: ${migrationFile}`);
        const client = await pool.connect();
        try {
          await client.query(sql);
          console.log(`✅ Migration completed: ${migrationFile}`);
        } finally {
          client.release();
        }
      } catch (error) {
        // Some migrations might fail if tables already exist or other conditions
        // We log the error but continue with other migrations
        if (error.message.includes('already exists') ||
            error.message.includes('duplicate key')) {
          console.log(`⚠️ Migration ${migrationFile} skipped (already applied or duplicate): ${error.message}`);
        } else {
          console.error(`❌ Migration ${migrationFile} failed:`, error.message);
        }
      }
    }

    console.log('✅ Webapp tables initialization completed');
    return true;
  } catch (error) {
    console.error('Webapp table initialization error:', error.message);
    // Don't throw - let the application continue with existing tables
    return false;
  }
}

module.exports = {
  initializeWebappTables,
};
