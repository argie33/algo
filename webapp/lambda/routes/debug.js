/**
 * Debug Routes for Database Schema Management
 * DEVELOPMENT USE ONLY - NOT FOR PRODUCTION
 */

const express = require('express');
const { query } = require('../utils/database');
const fs = require('fs');
const path = require('path');
const router = express.Router();

/**
 * Fix Financial Database Schema
 * POST /api/debug/fix-financial-schema
 */
router.post('/fix-financial-schema', async (req, res) => {
  try {
    console.log('🔧 [DEBUG] Starting financial schema fix...');

    // Read the SQL fix file
    const sqlFile = path.join(__dirname, '..', 'fix_financial_schema.sql');
    if (!fs.existsSync(sqlFile)) {
      return res.status(404).json({
        success: false,
        error: 'Schema fix file not found'
      });
    }

    const sqlCommands = fs.readFileSync(sqlFile, 'utf8');

    // Split into individual commands and execute
    // Handle multi-line SQL commands properly - parse complete statements
    const commands = [];
    let currentCommand = '';
    let inStatement = false;
    let parenCount = 0;

    const lines = sqlCommands.split('\n');
    for (const line of lines) {
      const trimmedLine = line.trim();
      if (trimmedLine.length === 0 || trimmedLine.startsWith('--')) {
        continue;
      }

      currentCommand += ' ' + trimmedLine;

      // Count parentheses to handle multi-line CREATE TABLE statements
      for (const char of trimmedLine) {
        if (char === '(') parenCount++;
        if (char === ')') parenCount--;
      }

      // If we hit a semicolon and we're not inside parentheses, we have a complete command
      if (trimmedLine.endsWith(';') && parenCount === 0) {
        const finalCommand = currentCommand.trim().replace(/\s+/g, ' ');
        if (!finalCommand.toUpperCase().includes('COMMIT')) {
          commands.push(finalCommand);
        }
        currentCommand = '';
      }
    }

    console.log(`🔄 [DEBUG] Executing ${commands.length} SQL commands...`);

    // Log all commands for debugging
    commands.forEach((cmd, index) => {
      console.log(`Command ${index + 1}: ${cmd.substring(0, 100)}...`);
    });

    const results = [];
    let successCount = 0;
    let errorCount = 0;

    for (let i = 0; i < commands.length; i++) {
      const command = commands[i];
      if (command.trim()) {
        try {
          await query(command);

          let action = 'Unknown';
          let target = '';

          if (command.toUpperCase().includes('DROP TABLE')) {
            action = 'DROPPED';
            target = command.match(/DROP TABLE.*?(\w+)/i)?.[1] || 'table';
          } else if (command.toUpperCase().includes('CREATE TABLE')) {
            action = 'CREATED';
            target = command.match(/CREATE TABLE (\w+)/i)?.[1] || 'table';
          } else if (command.toUpperCase().includes('CREATE INDEX')) {
            action = 'CREATED';
            target = command.match(/CREATE INDEX (\w+)/i)?.[1] || 'index';
          } else if (command.toUpperCase().includes('INSERT INTO')) {
            action = 'INSERTED';
            target = command.match(/INSERT INTO (\w+)/i)?.[1] || 'table';
          }

          results.push({ command: i + 1, action, target, status: 'SUCCESS' });
          successCount++;

        } catch (error) {
          console.log(`⚠️ [DEBUG] Warning on command ${i + 1}: ${error.message}`);
          results.push({
            command: i + 1,
            status: 'WARNING',
            error: error.message,
            sql: command.substring(0, 50) + '...'
          });
          errorCount++;
        }
      }
    }

    // Verify tables exist
    console.log('🔍 [DEBUG] Verifying financial tables...');
    const tables = [
      'annual_balance_sheet',
      'annual_income_statement',
      'annual_cash_flow',
      'quarterly_balance_sheet',
      'quarterly_income_statement',
      'quarterly_cash_flow'
    ];

    const verification = {};
    for (const table of tables) {
      try {
        const result = await query(`SELECT COUNT(*) as count FROM ${table}`);
        const count = parseInt(result.rows[0].count);
        verification[table] = { status: 'EXISTS', count };
        console.log(`✅ [DEBUG] ${table}: ${count} rows`);
      } catch (error) {
        verification[table] = { status: 'ERROR', error: error.message };
        console.log(`❌ [DEBUG] ${table}: ${error.message}`);
      }
    }

    console.log('🎉 [DEBUG] Financial schema fix completed!');

    res.json({
      success: true,
      message: 'Financial schema fix completed',
      results: {
        commands_executed: commands.length,
        successful: successCount,
        warnings: errorCount,
        details: results,
        verification
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('❌ [DEBUG] Schema fix error:', error);
    res.status(500).json({
      success: false,
      error: 'Schema fix failed',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Check Financial Schema Status
 * GET /api/debug/financial-schema-status
 */
router.get('/financial-schema-status', async (req, res) => {
  try {
    console.log('🔍 [DEBUG] Checking financial schema status...');

    const tables = [
      'annual_balance_sheet',
      'annual_income_statement',
      'annual_cash_flow',
      'quarterly_balance_sheet',
      'quarterly_income_statement',
      'quarterly_cash_flow'
    ];

    const status = {};

    for (const table of tables) {
      try {
        // Check if table exists and get schema
        const schemaResult = await query(`
          SELECT column_name, data_type
          FROM information_schema.columns
          WHERE table_name = $1
          ORDER BY ordinal_position
        `, [table]);

        const countResult = await query(`SELECT COUNT(*) as count FROM ${table}`);
        const count = parseInt(countResult.rows[0].count);

        status[table] = {
          exists: true,
          count,
          schema: schemaResult.rows,
          has_correct_columns: schemaResult.rows.some(col => col.column_name === 'symbol') &&
                               schemaResult.rows.some(col => col.column_name === 'date') &&
                               schemaResult.rows.some(col => col.column_name === 'item_name') &&
                               schemaResult.rows.some(col => col.column_name === 'value')
        };

      } catch (error) {
        status[table] = {
          exists: false,
          error: error.message
        };
      }
    }

    res.json({
      success: true,
      tables: status,
      summary: {
        total_tables: tables.length,
        existing_tables: Object.values(status).filter(t => t.exists).length,
        tables_with_correct_schema: Object.values(status).filter(t => t.has_correct_columns).length
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('❌ [DEBUG] Schema status error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to check schema status',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;