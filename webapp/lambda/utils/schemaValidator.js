/**
 * Database Schema Validator
 * Provides table existence validation and schema checking before executing queries
 */

const { query } = require('./database');

class SchemaValidator {
  constructor() {
    // Cache for table existence and schema information
    this.tableCache = new Map();
    this.cacheExpiry = 5 * 60 * 1000; // 5 minutes
    
    // Expected table schemas for the financial application
    this.expectedTables = {
      // Core symbol and company data
      'stock_symbols': {
        required: true,
        category: 'core',
        expectedColumns: ['symbol', 'security_name', 'exchange', 'market_category'],
        description: 'Master list of tradeable symbols'
      },
      'company_profiles': {
        required: false,
        category: 'core',
        expectedColumns: ['symbol', 'company_name', 'description', 'sector', 'industry'],
        description: 'Company profile information'
      },
      'symbols': {
        required: false,
        category: 'core',
        expectedColumns: ['symbol', 'name', 'description'],
        description: 'Alternative symbols table'
      },
      
      // Price data
      'price_daily': {
        required: true,
        category: 'price',
        expectedColumns: ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume'],
        description: 'Daily price data'
      },
      'latest_prices': {
        required: false,
        category: 'price',
        expectedColumns: ['symbol', 'price', 'last_updated'],
        description: 'Latest price information'
      },
      
      // Technical analysis
      'technicals_daily': {
        required: false,
        category: 'technical',
        expectedColumns: ['symbol', 'date', 'rsi', 'macd', 'sma_20', 'sma_50'],
        description: 'Daily technical indicators'
      },
      'latest_technicals': {
        required: false,
        category: 'technical',
        expectedColumns: ['symbol', 'rsi', 'macd', 'last_updated'],
        description: 'Latest technical indicators'
      },
      
      // User and portfolio data
      'user_api_keys': {
        required: true,
        category: 'user',
        expectedColumns: ['user_id', 'provider', 'api_key_encrypted', 'api_secret_encrypted', 'status'],
        description: 'User API credentials'
      },
      'portfolio_holdings': {
        required: false,
        category: 'portfolio',
        expectedColumns: ['user_id', 'symbol', 'quantity', 'avg_cost', 'last_updated'],
        description: 'User portfolio holdings'
      },
      
      // Trading and analytics
      'trades': {
        required: false,
        category: 'trading',
        expectedColumns: ['user_id', 'symbol', 'quantity', 'price', 'side', 'executed_at'],
        description: 'Trade execution records'
      },
      'buy_sell_daily': {
        required: false,
        category: 'analytics',
        expectedColumns: ['symbol', 'date', 'buy_signal', 'sell_signal', 'confidence'],
        description: 'Daily buy/sell signals'
      },
      
      // System tables
      'health_status': {
        required: false,
        category: 'system',
        expectedColumns: ['table_name', 'record_count', 'status', 'last_updated'],
        description: 'System health monitoring'
      },
      'last_updated': {
        required: false,
        category: 'system',
        expectedColumns: ['table_name', 'last_updated', 'record_count'],
        description: 'Data freshness tracking'
      }
    };
  }

  /**
   * Validate table existence before executing a query
   */
  async validateTableExists(tableName, options = {}) {
    const { 
      required = false, 
      throwOnMissing = false,
      useCache = true 
    } = options;

    const cacheKey = `exists_${tableName}`;
    
    // Check cache first
    if (useCache && this.tableCache.has(cacheKey)) {
      const cached = this.tableCache.get(cacheKey);
      if (Date.now() - cached.timestamp < this.cacheExpiry) {
        return cached.exists;
      }
    }

    try {
      const result = await query(`
        SELECT COUNT(*) as exists 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = $1
      `, [tableName], 3000);

      const exists = parseInt(result.rows[0].exists) > 0;
      
      // Cache result
      this.tableCache.set(cacheKey, {
        exists,
        timestamp: Date.now()
      });

      if (required && !exists && throwOnMissing) {
        throw new Error(`Required table '${tableName}' does not exist`);
      }

      return exists;
    } catch (error) {
      console.error(`Error checking table existence for '${tableName}':`, error.message);
      
      if (throwOnMissing) {
        throw error;
      }
      
      return false;
    }
  }

  /**
   * Validate multiple tables exist
   */
  async validateTablesExist(tableNames, options = {}) {
    const results = {};
    
    for (const tableName of tableNames) {
      results[tableName] = await this.validateTableExists(tableName, options);
    }
    
    return results;
  }

  /**
   * Get table schema information
   */
  async getTableSchema(tableName, options = {}) {
    const { useCache = true } = options;
    const cacheKey = `schema_${tableName}`;
    
    // Check cache first
    if (useCache && this.tableCache.has(cacheKey)) {
      const cached = this.tableCache.get(cacheKey);
      if (Date.now() - cached.timestamp < this.cacheExpiry) {
        return cached.schema;
      }
    }

    try {
      const result = await query(`
        SELECT 
          column_name,
          data_type,
          is_nullable,
          column_default,
          character_maximum_length
        FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
      `, [tableName], 5000);

      const schema = {
        exists: result.rows.length > 0,
        columns: result.rows.map(row => ({
          name: row.column_name,
          type: row.data_type,
          nullable: row.is_nullable === 'YES',
          default: row.column_default,
          maxLength: row.character_maximum_length
        })),
        columnNames: result.rows.map(row => row.column_name)
      };
      
      // Cache result
      this.tableCache.set(cacheKey, {
        schema,
        timestamp: Date.now()
      });

      return schema;
    } catch (error) {
      console.error(`Error getting schema for table '${tableName}':`, error.message);
      return {
        exists: false,
        columns: [],
        columnNames: [],
        error: error.message
      };
    }
  }

  /**
   * Validate table schema against expected schema
   */
  async validateTableSchema(tableName, options = {}) {
    const { strict = false } = options;
    
    const expectedSchema = this.expectedTables[tableName];
    if (!expectedSchema) {
      return {
        valid: true,
        message: `No expected schema defined for table '${tableName}'`,
        missing: [],
        extra: []
      };
    }

    const actualSchema = await this.getTableSchema(tableName);
    
    if (!actualSchema.exists) {
      return {
        valid: false,
        message: `Table '${tableName}' does not exist`,
        expected: expectedSchema,
        missing: expectedSchema.expectedColumns,
        extra: []
      };
    }

    // Check for missing required columns
    const missing = expectedSchema.expectedColumns.filter(
      col => !actualSchema.columnNames.includes(col)
    );

    // Check for extra columns (if strict mode)
    const extra = strict 
      ? actualSchema.columnNames.filter(
          col => !expectedSchema.expectedColumns.includes(col)
        )
      : [];

    const valid = missing.length === 0 && (strict ? extra.length === 0 : true);

    return {
      valid,
      message: valid 
        ? `Table '${tableName}' schema is valid`
        : `Table '${tableName}' schema validation failed`,
      expected: expectedSchema,
      actual: actualSchema,
      missing,
      extra
    };
  }

  /**
   * Safe query wrapper that validates table existence first
   */
  async safeQuery(queryText, params = [], options = {}) {
    const {
      timeout = 5000,
      validateTables = true,
      throwOnMissingTable = false
    } = options;

    if (validateTables) {
      // Extract table names from query
      const tableNames = this.extractTableNames(queryText);
      
      for (const tableName of tableNames) {
        const exists = await this.validateTableExists(tableName, {
          throwOnMissing: throwOnMissingTable
        });
        
        if (!exists) {
          const expectedTable = this.expectedTables[tableName];
          const fallbackMessage = expectedTable 
            ? `Table '${tableName}' (${expectedTable.description}) does not exist`
            : `Table '${tableName}' does not exist`;
            
          if (throwOnMissingTable) {
            throw new Error(fallbackMessage);
          } else {
            console.warn(`⚠️ ${fallbackMessage} - query may fail`);
          }
        }
      }
    }

    // Execute the query with the database utility
    return await query(queryText, params, timeout);
  }

  /**
   * Extract table names from SQL query
   */
  extractTableNames(queryText) {
    const tableNames = new Set();
    
    // Simple regex to extract table names - this is basic and may need enhancement
    const patterns = [
      /FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)/gi,
      /UPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)/gi,
      /INSERT INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)/gi,
      /DELETE FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)/gi,
      /JOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)/gi
    ];

    patterns.forEach(pattern => {
      let match;
      while ((match = pattern.exec(queryText)) !== null) {
        tableNames.add(match[1].toLowerCase());
      }
    });

    return Array.from(tableNames);
  }

  /**
   * Get comprehensive schema validation report
   */
  async getSchemaValidationReport(options = {}) {
    const { includeOptional = true, strict = false } = options;
    
    const report = {
      timestamp: new Date().toISOString(),
      summary: {
        totalTables: 0,
        requiredTables: 0,
        existingTables: 0,
        validSchemas: 0,
        invalidSchemas: 0,
        missingRequired: 0
      },
      tables: {},
      issues: [],
      recommendations: []
    };

    const tablesToCheck = Object.keys(this.expectedTables).filter(
      tableName => includeOptional || this.expectedTables[tableName].required
    );

    report.summary.totalTables = tablesToCheck.length;
    report.summary.requiredTables = tablesToCheck.filter(
      name => this.expectedTables[name].required
    ).length;

    for (const tableName of tablesToCheck) {
      const tableInfo = this.expectedTables[tableName];
      const validation = await this.validateTableSchema(tableName, { strict });
      
      report.tables[tableName] = {
        ...tableInfo,
        validation,
        exists: validation.actual?.exists || false
      };

      if (validation.actual?.exists) {
        report.summary.existingTables++;
      }

      if (validation.valid) {
        report.summary.validSchemas++;
      } else {
        report.summary.invalidSchemas++;
        
        if (tableInfo.required) {
          report.summary.missingRequired++;
        }

        // Add issues
        if (!validation.actual?.exists) {
          report.issues.push({
            table: tableName,
            type: 'missing_table',
            severity: tableInfo.required ? 'high' : 'medium',
            message: `Table '${tableName}' does not exist`,
            recommendation: `Create table '${tableName}' with columns: ${tableInfo.expectedColumns.join(', ')}`
          });
        } else if (validation.missing.length > 0) {
          report.issues.push({
            table: tableName,
            type: 'missing_columns',
            severity: 'medium',
            message: `Table '${tableName}' is missing columns: ${validation.missing.join(', ')}`,
            recommendation: `Add missing columns to table '${tableName}'`
          });
        }
      }
    }

    // Generate recommendations
    if (report.summary.missingRequired > 0) {
      report.recommendations.push({
        priority: 'high',
        action: 'create_required_tables',
        message: `${report.summary.missingRequired} required tables are missing. Run database initialization scripts.`
      });
    }

    if (report.summary.invalidSchemas > 0) {
      report.recommendations.push({
        priority: 'medium',
        action: 'fix_schemas',
        message: `${report.summary.invalidSchemas} tables have schema issues. Review and update table structures.`
      });
    }

    if (report.issues.length === 0) {
      report.recommendations.push({
        priority: 'info',
        action: 'none',
        message: 'All validated tables have correct schemas.'
      });
    }

    return report;
  }

  /**
   * Clear validation cache
   */
  clearCache() {
    this.tableCache.clear();
  }

  /**
   * Get cache status
   */
  getCacheStatus() {
    const entries = Array.from(this.tableCache.entries());
    return {
      size: this.tableCache.size,
      entries: entries.map(([key, value]) => ({
        key,
        age: Date.now() - value.timestamp,
        expired: Date.now() - value.timestamp > this.cacheExpiry
      }))
    };
  }
}

// Export singleton instance
module.exports = new SchemaValidator();