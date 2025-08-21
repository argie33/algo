const {
  SecretsManagerClient,
  GetSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");
const { Pool } = require("pg");

/**
 * Comprehensive Database Connectivity Test
 * Tests database connection, AWS Secrets Manager integration, and error handling
 */

class DatabaseConnectivityTest {
  constructor() {
    this.secretsManager = new SecretsManagerClient({
      region:
        process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || "us-east-1",
    });

    this.results = {
      timestamp: new Date().toISOString(),
      environment: process.env.NODE_ENV || "development",
      tests: [],
      summary: {
        passed: 0,
        failed: 0,
        warnings: 0,
      },
    };
  }

  /**
   * Log test result
   */
  logResult(testName, success, message, data = null) {
    const result = {
      test: testName,
      success: success,
      message: message,
      data: data,
      timestamp: new Date().toISOString(),
    };

    this.results.tests.push(result);

    if (success) {
      this.results.summary.passed++;
      console.log(`✅ ${testName}: ${message}`);
    } else {
      this.results.summary.failed++;
      console.error(`❌ ${testName}: ${message}`);
    }

    if (data) {
      console.log(`   Data:`, JSON.stringify(data, null, 2));
    }
  }

  /**
   * Test environment variables
   */
  testEnvironmentVariables() {
    console.log("\n🧪 Testing Environment Variables...");

    const requiredVars = [
      "DB_SECRET_ARN",
      "API_KEY_ENCRYPTION_SECRET_ARN",
      "WEBAPP_AWS_REGION",
      "NODE_ENV",
    ];

    const envVars = {};
    let allPresent = true;

    for (const varName of requiredVars) {
      const value = process.env[varName];
      envVars[varName] = value ? `${value.substring(0, 20)}...` : "NOT_SET";

      if (!value) {
        allPresent = false;
        console.warn(`⚠️  ${varName} is not set`);
      }
    }

    this.logResult(
      "Environment Variables",
      allPresent,
      allPresent
        ? "All required environment variables are set"
        : "Some environment variables are missing",
      envVars
    );

    return allPresent;
  }

  /**
   * Test AWS Secrets Manager connection
   */
  async testSecretsManager() {
    console.log("\n🧪 Testing AWS Secrets Manager...");

    const secretArn = process.env.DB_SECRET_ARN;
    if (!secretArn) {
      this.logResult("AWS Secrets Manager", false, "DB_SECRET_ARN not set");
      return null;
    }

    try {
      const command = new GetSecretValueCommand({ SecretId: secretArn });
      const result = await this.secretsManager.send(command);

      const diagnostics = {
        secretType: typeof result.SecretString,
        secretLength: result.SecretString?.length,
        secretPreview: result.SecretString?.substring(0, 50) + "...",
        hasSecretString: !!result.SecretString,
        hasSecretBinary: !!result.SecretBinary,
      };

      // Test JSON parsing
      let secret = null;
      let parseError = null;

      try {
        if (typeof result.SecretString === "string") {
          secret = JSON.parse(result.SecretString);
          diagnostics.parseAttempt = "SUCCESS";
          diagnostics.parsedKeys = Object.keys(secret);
        } else if (typeof result.SecretString === "object") {
          secret = result.SecretString;
          diagnostics.parseAttempt = "ALREADY_PARSED";
          diagnostics.parsedKeys = Object.keys(secret);
        } else {
          throw new Error("SecretString is neither string nor object");
        }
      } catch (error) {
        parseError = error.message;
        diagnostics.parseAttempt = "FAILED";
        diagnostics.parseError = parseError;
      }

      const success = !parseError && secret && Object.keys(secret).length > 0;

      this.logResult(
        "AWS Secrets Manager",
        success,
        success
          ? "Secret retrieved and parsed successfully"
          : `Failed to parse secret: ${parseError}`,
        diagnostics
      );

      return secret;
    } catch (error) {
      this.logResult(
        "AWS Secrets Manager",
        false,
        `Failed to retrieve secret: ${error.message}`,
        { error: error.name, code: error.Code }
      );
      return null;
    }
  }

  /**
   * Test database connection configuration
   */
  async testDatabaseConfig(secret) {
    console.log("\n🧪 Testing Database Configuration...");

    if (!secret) {
      this.logResult("Database Config", false, "No database secret available");
      return null;
    }

    const requiredFields = ["host", "port", "database", "username", "password"];
    const config = {};
    let allFieldsPresent = true;

    for (const field of requiredFields) {
      const value = secret[field];
      config[field] = value
        ? field === "password"
          ? "***HIDDEN***"
          : value
        : "MISSING";

      if (!value) {
        allFieldsPresent = false;
        console.warn(`⚠️  Database ${field} is missing`);
      }
    }

    this.logResult(
      "Database Config",
      allFieldsPresent,
      allFieldsPresent
        ? "All database configuration fields present"
        : "Some database configuration fields missing",
      config
    );

    return allFieldsPresent ? secret : null;
  }

  /**
   * Test database connection
   */
  async testDatabaseConnection(secret) {
    console.log("\n🧪 Testing Database Connection...");

    if (!secret) {
      this.logResult(
        "Database Connection",
        false,
        "No database configuration available"
      );
      return null;
    }

    // Test different SSL configurations
    const sslConfigs = [
      { ssl: false, description: "No SSL (recommended for RDS in VPC)" },
      {
        ssl: { rejectUnauthorized: false },
        description: "SSL without certificate validation",
      },
      { ssl: true, description: "SSL with certificate validation" },
    ];

    for (const sslConfig of sslConfigs) {
      console.log(`\n   Testing ${sslConfig.description}...`);

      const config = {
        host: secret.host,
        port: secret.port,
        database: secret.database,
        user: secret.username,
        password: secret.password,
        ...(sslConfig.ssl !== undefined ? { ssl: sslConfig.ssl } : {}),
        connectionTimeoutMillis: 10000,
        idleTimeoutMillis: 30000,
        max: 1, // Single connection for test
        statement_timeout: 10000,
      };

      let pool = null;
      let client = null;

      try {
        pool = new Pool(config);
        client = await pool.connect();

        // Test basic query
        const result = await client.query(
          "SELECT NOW() as current_time, version() as db_version"
        );
        const row = result.rows[0];

        // Test table access
        const tableTest = await client.query(`
          SELECT COUNT(*) as table_count 
          FROM information_schema.tables 
          WHERE table_schema = 'public'
        `);

        const testData = {
          ssl: sslConfig.ssl,
          connectionTime: row.current_time,
          dbVersion: row.db_version.substring(0, 50) + "...",
          tableCount: tableTest.rows[0].table_count,
          config: {
            host: config.host,
            port: config.port,
            database: config.database,
            ssl: config.ssl,
          },
        };

        this.logResult(
          `Database Connection (${sslConfig.description})`,
          true,
          "Database connection successful",
          testData
        );

        return { pool, client, config: testData };
      } catch (error) {
        this.logResult(
          `Database Connection (${sslConfig.description})`,
          false,
          `Connection failed: ${error.message}`,
          {
            error: error.name,
            code: error.code,
            ssl: sslConfig.ssl,
          }
        );

        // Continue to next SSL config
        continue;
      } finally {
        if (client) {
          try {
            client.release();
          } catch (e) {
            // Ignore cleanup errors
          }
        }
        if (pool) {
          try {
            await pool.end();
          } catch (e) {
            // Ignore cleanup errors
          }
        }
      }
    }

    return null;
  }

  /**
   * Test database tables and schema
   */
  async testDatabaseSchema(connectionInfo) {
    console.log("\n🧪 Testing Database Schema...");

    if (!connectionInfo) {
      this.logResult(
        "Database Schema",
        false,
        "No database connection available"
      );
      return;
    }

    const { pool } = connectionInfo;
    let client = null;

    try {
      client = await pool.connect();

      // Test critical tables
      const criticalTables = [
        "user_api_keys",
        "stock_symbols",
        "stock_prices",
        "technical_indicators",
      ];

      const tableResults = {};

      for (const tableName of criticalTables) {
        try {
          const result = await client.query(
            `
            SELECT COUNT(*) as row_count 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = $1
          `,
            [tableName]
          );

          const exists = result.rows[0].row_count > 0;
          tableResults[tableName] = { exists };

          if (exists) {
            const countResult = await client.query(
              `SELECT COUNT(*) as count FROM ${tableName}`
            );
            tableResults[tableName].rowCount = countResult.rows[0].count;
          }
        } catch (error) {
          tableResults[tableName] = { exists: false, error: error.message };
        }
      }

      const allTablesExist = Object.values(tableResults).every((t) => t.exists);

      this.logResult(
        "Database Schema",
        allTablesExist,
        allTablesExist
          ? "All critical tables exist"
          : "Some critical tables missing",
        tableResults
      );
    } catch (error) {
      this.logResult(
        "Database Schema",
        false,
        `Schema test failed: ${error.message}`,
        { error: error.name, code: error.code }
      );
    } finally {
      if (client) {
        try {
          client.release();
        } catch (e) {
          // Ignore cleanup errors
        }
      }
    }
  }

  /**
   * Test API key encryption secret
   */
  async testApiKeyEncryption() {
    console.log("\n🧪 Testing API Key Encryption...");

    const secretArn = process.env.API_KEY_ENCRYPTION_SECRET_ARN;
    if (!secretArn) {
      // Try environment variable fallback
      const envSecret = process.env.API_KEY_ENCRYPTION_SECRET;
      if (envSecret) {
        this.logResult(
          "API Key Encryption",
          true,
          "Using environment variable encryption key",
          { source: "environment", length: envSecret.length }
        );
        return;
      }

      this.logResult(
        "API Key Encryption",
        false,
        "No encryption secret available"
      );
      return;
    }

    try {
      const command = new GetSecretValueCommand({ SecretId: secretArn });
      const result = await this.secretsManager.send(command);

      let secret = null;
      if (typeof result.SecretString === "string") {
        secret = JSON.parse(result.SecretString);
      } else {
        secret = result.SecretString;
      }

      const hasEncryptionKey =
        secret && (secret.encryptionKey || secret.API_KEY_ENCRYPTION_SECRET);

      this.logResult(
        "API Key Encryption",
        hasEncryptionKey,
        hasEncryptionKey
          ? "API key encryption secret available"
          : "API key encryption secret missing",
        {
          source: "secrets-manager",
          hasEncryptionKey: hasEncryptionKey,
          secretKeys: secret ? Object.keys(secret) : [],
        }
      );
    } catch (error) {
      this.logResult(
        "API Key Encryption",
        false,
        `Failed to retrieve encryption secret: ${error.message}`,
        { error: error.name, code: error.Code }
      );
    }
  }

  /**
   * Run all tests
   */
  async runAllTests() {
    console.log("🚀 Starting Database Connectivity Tests...");
    console.log("=".repeat(60));

    // Test environment variables
    const _envOk = this.testEnvironmentVariables();

    // Test AWS Secrets Manager
    const secret = await this.testSecretsManager();

    // Test database configuration
    const dbConfig = await this.testDatabaseConfig(secret);

    // Test database connection
    const connectionInfo = await this.testDatabaseConnection(dbConfig);

    // Test database schema
    await this.testDatabaseSchema(connectionInfo);

    // Test API key encryption
    await this.testApiKeyEncryption();

    // Print summary
    console.log("\n" + "=".repeat(60));
    console.log("🏁 Test Results Summary:");
    console.log(`✅ Passed: ${this.results.summary.passed}`);
    console.log(`❌ Failed: ${this.results.summary.failed}`);
    console.log(`⚠️  Warnings: ${this.results.summary.warnings}`);
    console.log(`📊 Total Tests: ${this.results.tests.length}`);

    const overallSuccess = this.results.summary.failed === 0;
    console.log(
      `\n🎯 Overall Result: ${overallSuccess ? "✅ PASS" : "❌ FAIL"}`
    );

    return this.results;
  }

  /**
   * Generate detailed report
   */
  generateReport() {
    return {
      ...this.results,
      recommendations: this.generateRecommendations(),
    };
  }

  /**
   * Generate recommendations based on test results
   */
  generateRecommendations() {
    const recommendations = [];

    for (const test of this.results.tests) {
      if (!test.success) {
        switch (test.test) {
          case "Environment Variables":
            recommendations.push({
              priority: "HIGH",
              category: "Configuration",
              issue: "Missing environment variables",
              solution:
                "Set all required environment variables in your deployment configuration",
            });
            break;

          case "AWS Secrets Manager":
            recommendations.push({
              priority: "HIGH",
              category: "Security",
              issue: "Cannot access AWS Secrets Manager",
              solution: "Verify IAM permissions and secret ARN configuration",
            });
            break;

          case "Database Connection":
            recommendations.push({
              priority: "CRITICAL",
              category: "Infrastructure",
              issue: "Database connection failed",
              solution:
                "Check database configuration, network connectivity, and SSL settings",
            });
            break;

          case "Database Schema":
            recommendations.push({
              priority: "HIGH",
              category: "Database",
              issue: "Missing database tables",
              solution:
                "Run database initialization scripts to create required tables",
            });
            break;
        }
      }
    }

    return recommendations;
  }
}

// Export for use in other modules
module.exports = DatabaseConnectivityTest;

// Run tests if called directly
if (require.main === module) {
  const test = new DatabaseConnectivityTest();

  test
    .runAllTests()
    .then((results) => {
      const report = test.generateReport();

      // Save report to file
      const fs = require("fs");
      const reportPath = `database-connectivity-report-${Date.now()}.json`;
      fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

      console.log(`\n📄 Detailed report saved to: ${reportPath}`);

      // Exit with appropriate code
      process.exit(results.summary.failed === 0 ? 0 : 1);
    })
    .catch((error) => {
      console.error("Test execution failed:", error);
      process.exit(1);
    });
}
