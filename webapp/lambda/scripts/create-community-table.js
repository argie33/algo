#!/usr/bin/env node

/**
 * Script to create community_signups table
 * Run with: node scripts/create-community-table.js
 */

const { initializeDatabase, query } = require('../utils/database');
const fs = require('fs');
const path = require('path');

async function createCommunityTable() {
  try {
    console.log('🔄 Initializing database...');
    await initializeDatabase();

    console.log('📝 Creating community_signups table...');

    const sql = fs.readFileSync(path.join(__dirname, '../migrations/001-create-community-signups.sql'), 'utf8');

    // Split SQL statements by semicolon and execute each one
    const statements = sql.split(';').filter(s => s.trim());

    for (const statement of statements) {
      if (statement.trim()) {
        console.log(`  Executing: ${statement.trim().substring(0, 60)}...`);
        await query(statement);
      }
    }

    console.log('✅ Community signups table created successfully!');

    // Verify table exists
    const result = await query(
      `SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'community_signups'
      )`
    );

    if (result.rows[0].exists) {
      console.log('✅ Table verification successful!');

      // Show table structure
      const structure = await query(
        `SELECT column_name, data_type, is_nullable
         FROM information_schema.columns
         WHERE table_name = 'community_signups'
         ORDER BY ordinal_position`
      );

      console.log('\n📊 Table structure:');
      structure.rows.forEach(col => {
        const nullable = col.is_nullable === 'YES' ? 'nullable' : 'NOT NULL';
        console.log(`   ${col.column_name.padEnd(25)} ${col.data_type.padEnd(20)} ${nullable}`);
      });
    } else {
      console.log('❌ Table verification failed!');
      process.exit(1);
    }

  } catch (error) {
    console.error('❌ Error creating table:', error.message);
    console.error(error);
    process.exit(1);
  }
}

createCommunityTable();
