/**
 * Database schema validation utility
 * Provides comprehensive validation for database operations and schema integrity
 */

const { query } = require('./database');
const logger = require('./logger');

/**
 * Schema definitions for database tables
 */
const tableSchemas = {
  stocks: {
    required: ['symbol', 'name'],
    columns: {
      symbol: { type: 'VARCHAR', maxLength: 10, unique: true },
      name: { type: 'VARCHAR', maxLength: 200 },
      sector: { type: 'VARCHAR', maxLength: 100 },
      industry: { type: 'VARCHAR', maxLength: 100 },
      market_cap: { type: 'BIGINT', min: 0 },
      price: { type: 'DECIMAL', precision: 10, scale: 2, min: 0 },
      volume: { type: 'BIGINT', min: 0 },
      pe_ratio: { type: 'DECIMAL', precision: 8, scale: 2 },
      eps: { type: 'DECIMAL', precision: 8, scale: 2 },
      dividend_yield: { type: 'DECIMAL', precision: 5, scale: 4 },
      beta: { type: 'DECIMAL', precision: 6, scale: 3 },
      exchange: { type: 'VARCHAR', maxLength: 20 },
      country: { type: 'VARCHAR', maxLength: 50 },
      currency: { type: 'VARCHAR', maxLength: 3 },
      is_active: { type: 'BOOLEAN', default: true },
      last_updated: { type: 'TIMESTAMP' }
    }
  },
  
  stock_prices: {
    required: ['symbol', 'date', 'close'],
    columns: {
      symbol: { type: 'VARCHAR', maxLength: 10 },
      date: { type: 'DATE' },
      open: { type: 'DECIMAL', precision: 10, scale: 2, min: 0 },
      high: { type: 'DECIMAL', precision: 10, scale: 2, min: 0 },
      low: { type: 'DECIMAL', precision: 10, scale: 2, min: 0 },
      close: { type: 'DECIMAL', precision: 10, scale: 2, min: 0 },
      volume: { type: 'BIGINT', min: 0 },
      adjusted_close: { type: 'DECIMAL', precision: 10, scale: 2, min: 0 }
    },
    indexes: ['symbol', 'date'],
    primaryKey: ['symbol', 'date']
  },
  
  user_api_keys: {
    required: ['user_id', 'provider', 'encrypted_data'],
    columns: {
      user_id: { type: 'VARCHAR', maxLength: 50 },
      provider: { type: 'VARCHAR', maxLength: 50 },
      encrypted_data: { type: 'TEXT' },
      user_salt: { type: 'VARCHAR', maxLength: 100 },
      created_at: { type: 'TIMESTAMP', default: 'NOW()' },
      updated_at: { type: 'TIMESTAMP', default: 'NOW()' }
    },
    indexes: ['user_id', 'provider'],
    primaryKey: ['user_id', 'provider']
  },
  
  watchlists: {
    required: ['user_id', 'name'],
    columns: {
      id: { type: 'SERIAL', primaryKey: true },
      user_id: { type: 'VARCHAR', maxLength: 50 },
      name: { type: 'VARCHAR', maxLength: 100 },
      description: { type: 'TEXT' },
      is_public: { type: 'BOOLEAN', default: false },
      created_at: { type: 'TIMESTAMP', default: 'NOW()' },
      updated_at: { type: 'TIMESTAMP', default: 'NOW()' }
    },
    indexes: ['user_id']
  },
  
  watchlist_items: {
    required: ['watchlist_id', 'symbol'],
    columns: {
      id: { type: 'SERIAL', primaryKey: true },
      watchlist_id: { type: 'INTEGER' },
      symbol: { type: 'VARCHAR', maxLength: 10 },
      added_at: { type: 'TIMESTAMP', default: 'NOW()' },
      notes: { type: 'TEXT' }
    },
    indexes: ['watchlist_id', 'symbol'],
    foreignKeys: {
      watchlist_id: { table: 'watchlists', column: 'id' }
    }
  },
  
  technical_indicators: {
    required: ['symbol', 'date'],
    columns: {
      symbol: { type: 'VARCHAR', maxLength: 10 },
      date: { type: 'DATE' },
      sma_20: { type: 'DECIMAL', precision: 10, scale: 2 },
      sma_50: { type: 'DECIMAL', precision: 10, scale: 2 },
      sma_200: { type: 'DECIMAL', precision: 10, scale: 2 },
      ema_12: { type: 'DECIMAL', precision: 10, scale: 2 },
      ema_26: { type: 'DECIMAL', precision: 10, scale: 2 },
      macd: { type: 'DECIMAL', precision: 10, scale: 4 },
      macd_signal: { type: 'DECIMAL', precision: 10, scale: 4 },
      macd_histogram: { type: 'DECIMAL', precision: 10, scale: 4 },
      rsi: { type: 'DECIMAL', precision: 5, scale: 2 },
      bollinger_upper: { type: 'DECIMAL', precision: 10, scale: 2 },
      bollinger_middle: { type: 'DECIMAL', precision: 10, scale: 2 },
      bollinger_lower: { type: 'DECIMAL', precision: 10, scale: 2 },
      stochastic_k: { type: 'DECIMAL', precision: 5, scale: 2 },
      stochastic_d: { type: 'DECIMAL', precision: 5, scale: 2 },
      williams_r: { type: 'DECIMAL', precision: 6, scale: 2 },
      atr: { type: 'DECIMAL', precision: 10, scale: 4 },
      obv: { type: 'BIGINT' }
    },
    indexes: ['symbol', 'date'],
    primaryKey: ['symbol', 'date']
  },
  
  earnings_reports: {
    required: ['symbol', 'report_date'],
    columns: {
      symbol: { type: 'VARCHAR', maxLength: 10 },
      report_date: { type: 'DATE' },
      quarter: { type: 'INTEGER', min: 1, max: 4 },
      year: { type: 'INTEGER', min: 1900 },
      revenue: { type: 'BIGINT' },
      net_income: { type: 'BIGINT' },
      eps_reported: { type: 'DECIMAL', precision: 8, scale: 2 },
      eps_estimate: { type: 'DECIMAL', precision: 8, scale: 2 },
      surprise_percent: { type: 'DECIMAL', precision: 6, scale: 2 }
    },
    indexes: ['symbol', 'report_date'],
    primaryKey: ['symbol', 'report_date']
  }
};

class SchemaValidator {
  constructor() {
    this.schemas = tableSchemas;
  }

  /**
   * Validate data against table schema
   */
  validateData(tableName, data) {
    const schema = this.schemas[tableName];
    if (!schema) {
      throw new Error(`No schema defined for table: ${tableName}`);
    }

    const errors = [];
    const validatedData = {};

    // Check required fields
    for (const requiredField of schema.required) {
      if (data[requiredField] === undefined || data[requiredField] === null) {
        errors.push({
          field: requiredField,
          message: `Required field '${requiredField}' is missing`,
          code: 'REQUIRED_FIELD_MISSING'
        });
      }
    }

    // Validate each field
    for (const [fieldName, fieldValue] of Object.entries(data)) {
      const columnDef = schema.columns[fieldName];
      if (!columnDef) {
        errors.push({
          field: fieldName,
          message: `Unknown field '${fieldName}' for table '${tableName}'`,
          code: 'UNKNOWN_FIELD'
        });
        continue;
      }

      const fieldErrors = this.validateField(fieldName, fieldValue, columnDef);
      errors.push(...fieldErrors);

      if (fieldErrors.length === 0) {
        validatedData[fieldName] = this.sanitizeFieldValue(fieldValue, columnDef);
      }
    }

    return {
      valid: errors.length === 0,
      errors: errors,
      data: validatedData
    };
  }

  /**
   * Validate individual field
   */
  validateField(fieldName, value, columnDef) {
    const errors = [];

    // Skip validation for null values unless required
    if (value === null || value === undefined) {
      return errors;
    }

    // Type validation
    switch (columnDef.type) {
      case 'VARCHAR':
        if (typeof value !== 'string') {
          errors.push({
            field: fieldName,
            message: `Field '${fieldName}' must be a string`,
            code: 'INVALID_TYPE'
          });
        } else if (columnDef.maxLength && value.length > columnDef.maxLength) {
          errors.push({
            field: fieldName,
            message: `Field '${fieldName}' exceeds maximum length of ${columnDef.maxLength}`,
            code: 'EXCEEDS_MAX_LENGTH'
          });
        }
        break;

      case 'INTEGER':
      case 'SERIAL':
        if (!Number.isInteger(Number(value))) {
          errors.push({
            field: fieldName,
            message: `Field '${fieldName}' must be an integer`,
            code: 'INVALID_TYPE'
          });
        } else {
          const numValue = Number(value);
          if (columnDef.min !== undefined && numValue < columnDef.min) {
            errors.push({
              field: fieldName,
              message: `Field '${fieldName}' must be at least ${columnDef.min}`,
              code: 'BELOW_MINIMUM'
            });
          }
          if (columnDef.max !== undefined && numValue > columnDef.max) {
            errors.push({
              field: fieldName,
              message: `Field '${fieldName}' must be at most ${columnDef.max}`,
              code: 'ABOVE_MAXIMUM'
            });
          }
        }
        break;

      case 'BIGINT':
        if (!Number.isInteger(Number(value))) {
          errors.push({
            field: fieldName,
            message: `Field '${fieldName}' must be a big integer`,
            code: 'INVALID_TYPE'
          });
        } else if (columnDef.min !== undefined && Number(value) < columnDef.min) {
          errors.push({
            field: fieldName,
            message: `Field '${fieldName}' must be at least ${columnDef.min}`,
            code: 'BELOW_MINIMUM'
          });
        }
        break;

      case 'DECIMAL':
        if (isNaN(Number(value))) {
          errors.push({
            field: fieldName,
            message: `Field '${fieldName}' must be a number`,
            code: 'INVALID_TYPE'
          });
        } else {
          const numValue = Number(value);
          if (columnDef.min !== undefined && numValue < columnDef.min) {
            errors.push({
              field: fieldName,
              message: `Field '${fieldName}' must be at least ${columnDef.min}`,
              code: 'BELOW_MINIMUM'
            });
          }
          if (columnDef.max !== undefined && numValue > columnDef.max) {
            errors.push({
              field: fieldName,
              message: `Field '${fieldName}' must be at most ${columnDef.max}`,
              code: 'ABOVE_MAXIMUM'
            });
          }
        }
        break;

      case 'BOOLEAN':
        if (typeof value !== 'boolean' && value !== 'true' && value !== 'false' && value !== 1 && value !== 0) {
          errors.push({
            field: fieldName,
            message: `Field '${fieldName}' must be a boolean`,
            code: 'INVALID_TYPE'
          });
        }
        break;

      case 'DATE':
        if (isNaN(Date.parse(value))) {
          errors.push({
            field: fieldName,
            message: `Field '${fieldName}' must be a valid date`,
            code: 'INVALID_DATE'
          });
        }
        break;

      case 'TIMESTAMP':
        if (isNaN(Date.parse(value))) {
          errors.push({
            field: fieldName,
            message: `Field '${fieldName}' must be a valid timestamp`,
            code: 'INVALID_TIMESTAMP'
          });
        }
        break;

      case 'TEXT':
        if (typeof value !== 'string') {
          errors.push({
            field: fieldName,
            message: `Field '${fieldName}' must be a string`,
            code: 'INVALID_TYPE'
          });
        }
        break;
    }

    return errors;
  }

  /**
   * Sanitize field value according to column definition
   */
  sanitizeFieldValue(value, columnDef) {
    if (value === null || value === undefined) {
      return null;
    }

    switch (columnDef.type) {
      case 'VARCHAR':
      case 'TEXT':
        return String(value).trim();

      case 'INTEGER':
      case 'SERIAL':
      case 'BIGINT':
        return Number(value);

      case 'DECIMAL':
        return parseFloat(value);

      case 'BOOLEAN':
        if (typeof value === 'boolean') return value;
        if (value === 'true' || value === 1) return true;
        if (value === 'false' || value === 0) return false;
        return Boolean(value);

      case 'DATE':
      case 'TIMESTAMP':
        return new Date(value).toISOString();

      default:
        return value;
    }
  }

  /**
   * Validate table exists and has correct structure
   */
  async validateTableStructure(tableName) {
    try {
      const schema = this.schemas[tableName];
      if (!schema) {
        throw new Error(`No schema defined for table: ${tableName}`);
      }

      // Check if table exists
      const tableExists = await query(`
        SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = $1
        )
      `, [tableName]);

      if (!tableExists.rows[0].exists) {
        return {
          valid: false,
          errors: [`Table '${tableName}' does not exist`]
        };
      }

      // Get actual table structure
      const columns = await query(`
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
      `, [tableName]);

      const actualColumns = new Set(columns.rows.map(col => col.column_name));
      const expectedColumns = new Set(Object.keys(schema.columns));

      const errors = [];

      // Check for missing columns
      for (const expectedCol of expectedColumns) {
        if (!actualColumns.has(expectedCol)) {
          errors.push(`Missing column '${expectedCol}' in table '${tableName}'`);
        }
      }

      // Check for extra columns (warning only)
      for (const actualCol of actualColumns) {
        if (!expectedColumns.has(actualCol) && actualCol !== 'id') {
          logger.warn(`Extra column '${actualCol}' found in table '${tableName}'`);
        }
      }

      return {
        valid: errors.length === 0,
        errors: errors,
        actualColumns: Array.from(actualColumns),
        expectedColumns: Array.from(expectedColumns)
      };

    } catch (error) {
      logger.error('Schema validation error', { error, tableName });
      return {
        valid: false,
        errors: [`Schema validation failed: ${error.message}`]
      };
    }
  }

  /**
   * Validate database integrity
   */
  async validateDatabaseIntegrity() {
    const results = {};
    const overallErrors = [];

    for (const tableName of Object.keys(this.schemas)) {
      try {
        const validation = await this.validateTableStructure(tableName);
        results[tableName] = validation;

        if (!validation.valid) {
          overallErrors.push(...validation.errors);
        }
      } catch (error) {
        results[tableName] = {
          valid: false,
          errors: [error.message]
        };
        overallErrors.push(`Table '${tableName}': ${error.message}`);
      }
    }

    return {
      valid: overallErrors.length === 0,
      errors: overallErrors,
      tableResults: results,
      checkedAt: new Date().toISOString()
    };
  }

  /**
   * Generate CREATE TABLE statement from schema
   */
  generateCreateTableSQL(tableName) {
    const schema = this.schemas[tableName];
    if (!schema) {
      throw new Error(`No schema defined for table: ${tableName}`);
    }

    let sql = `CREATE TABLE IF NOT EXISTS ${tableName} (\n`;
    const columnDefinitions = [];

    for (const [columnName, columnDef] of Object.entries(schema.columns)) {
      let definition = `  ${columnName} ${columnDef.type}`;

      if (columnDef.type === 'VARCHAR' && columnDef.maxLength) {
        definition += `(${columnDef.maxLength})`;
      }

      if (columnDef.type === 'DECIMAL' && columnDef.precision) {
        definition += `(${columnDef.precision}${columnDef.scale ? ',' + columnDef.scale : ''})`;
      }

      if (columnDef.primaryKey) {
        definition += ' PRIMARY KEY';
      }

      if (!columnDef.nullable && columnDef.type !== 'SERIAL') {
        definition += ' NOT NULL';
      }

      if (columnDef.unique) {
        definition += ' UNIQUE';
      }

      if (columnDef.default) {
        definition += ` DEFAULT ${columnDef.default}`;
      }

      columnDefinitions.push(definition);
    }

    sql += columnDefinitions.join(',\n');

    // Add primary key constraint if defined
    if (schema.primaryKey && Array.isArray(schema.primaryKey)) {
      sql += `,\n  PRIMARY KEY (${schema.primaryKey.join(', ')})`;
    }

    sql += '\n);';

    // Add indexes
    if (schema.indexes) {
      for (const index of schema.indexes) {
        const indexColumns = Array.isArray(index) ? index.join(', ') : index;
        sql += `\n\nCREATE INDEX IF NOT EXISTS idx_${tableName}_${indexColumns.replace(/[^a-zA-Z0-9]/g, '_')} ON ${tableName} (${indexColumns});`;
      }
    }

    return sql;
  }

  /**
   * Get schema definition for a table
   */
  getTableSchema(tableName) {
    return this.schemas[tableName] || null;
  }

  /**
   * List all available table schemas
   */
  listTables() {
    return Object.keys(this.schemas);
  }
}

// Export singleton instance
const schemaValidator = new SchemaValidator();

module.exports = {
  validateData: (tableName, data) => schemaValidator.validateData(tableName, data),
  validateTableStructure: (tableName) => schemaValidator.validateTableStructure(tableName),
  validateDatabaseIntegrity: () => schemaValidator.validateDatabaseIntegrity(),
  generateCreateTableSQL: (tableName) => schemaValidator.generateCreateTableSQL(tableName),
  getTableSchema: (tableName) => schemaValidator.getTableSchema(tableName),
  listTables: () => schemaValidator.listTables(),
  schemas: tableSchemas
};