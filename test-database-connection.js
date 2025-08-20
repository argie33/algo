#!/usr/bin/env node

/**
 * Database Connection Diagnostic Tool
 * Tests database connectivity and identifies configuration issues
 */

require("dotenv").config();
const {
  SecretsManagerClient,
  GetSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");
const { Pool } = require("pg");

const secretsManager = new SecretsManagerClient({
  region: process.env.AWS_REGION || "us-east-1",
});

async function testSecretsManager() {
  console.log("\n🔍 Testing AWS Secrets Manager...");

  const secretArn = process.env.DB_SECRET_ARN;
  console.log("Secret ARN:", secretArn);

  if (!secretArn) {
    console.log("❌ DB_SECRET_ARN not set");
    return null;
  }

  try {
    const command = new GetSecretValueCommand({ SecretId: secretArn });
    const result = await secretsManager.send(command);

    console.log("✅ Successfully retrieved secret from AWS");
    console.log("Secret type:", typeof result.SecretString);
    console.log(
      "Secret preview:",
      result.SecretString?.substring(0, 50) + "..."
    );

    // Try to parse the secret
    try {
      const secret = JSON.parse(result.SecretString);
      console.log("✅ Successfully parsed secret as JSON");
      console.log("Secret keys:", Object.keys(secret));

      return {
        host: secret.host || secret.hostname,
        port: parseInt(secret.port) || 5432,
        user: secret.username || secret.user,
        password: secret.password,
        database: secret.dbname || secret.database,
      };
    } catch (parseError) {
      console.log("❌ Failed to parse secret as JSON:", parseError.message);
      console.log("Raw secret:", result.SecretString);
      return null;
    }
  } catch (error) {
    console.log("❌ Failed to retrieve secret:", error.message);
    return null;
  }
}

async function testEnvironmentVariables() {
  console.log("\n🔍 Testing Environment Variables...");

  const envVars = {
    DB_HOST: process.env.DB_HOST,
    DB_ENDPOINT: process.env.DB_ENDPOINT,
    DB_PORT: process.env.DB_PORT,
    DB_USER: process.env.DB_USER,
    DB_USERNAME: process.env.DB_USERNAME,
    DB_PASSWORD: process.env.DB_PASSWORD ? "[REDACTED]" : undefined,
    DB_NAME: process.env.DB_NAME,
    DB_DATABASE: process.env.DB_DATABASE,
    DB_SSL: process.env.DB_SSL,
  };

  console.log("Environment variables:", envVars);

  const host = process.env.DB_HOST || process.env.DB_ENDPOINT;
  const user = process.env.DB_USER || process.env.DB_USERNAME;
  const database = process.env.DB_NAME || process.env.DB_DATABASE;

  if (host && user && process.env.DB_PASSWORD && database) {
    console.log("✅ Complete environment configuration found");
    return {
      host,
      port: parseInt(process.env.DB_PORT) || 5432,
      user,
      password: process.env.DB_PASSWORD,
      database,
    };
  } else {
    console.log("❌ Incomplete environment configuration");
    return null;
  }
}

async function testConnection(config) {
  if (!config) {
    console.log("❌ No configuration to test");
    return false;
  }

  console.log("\n🔍 Testing Database Connection...");
  console.log(
    `Connecting to: ${config.host}:${config.port}/${config.database} as ${config.user}`
  );

  const pool = new Pool({
    ...config,
    max: 1,
    connectionTimeoutMillis: 10000,
    ssl: config.ssl !== false ? { rejectUnauthorized: false } : false,
  });

  try {
    const client = await pool.connect();
    console.log("✅ Successfully connected to database");

    // Test a simple query
    const result = await client.query(
      "SELECT NOW() as current_time, version() as pg_version"
    );
    console.log("✅ Query successful:", result.rows[0]);

    client.release();
    await pool.end();

    return true;
  } catch (error) {
    console.log("❌ Database connection failed:", error.message);
    await pool.end();
    return false;
  }
}

async function testLambdaContext() {
  console.log("\n🔍 Testing Lambda Environment...");

  const lambdaVars = {
    AWS_REGION: process.env.AWS_REGION,
    AWS_LAMBDA_FUNCTION_NAME: process.env.AWS_LAMBDA_FUNCTION_NAME,
    NODE_ENV: process.env.NODE_ENV,
    DB_SECRET_ARN: process.env.DB_SECRET_ARN ? "[SET]" : "[NOT SET]",
  };

  console.log("Lambda environment:", lambdaVars);

  if (process.env.AWS_LAMBDA_FUNCTION_NAME) {
    console.log("✅ Running in Lambda environment");
  } else {
    console.log("ℹ️ Running in local environment");
  }
}

async function main() {
  console.log("🧪 Database Connection Diagnostic Tool");
  console.log("=====================================");

  await testLambdaContext();

  // Test both configuration methods
  const secretConfig = await testSecretsManager();
  const envConfig = await testEnvironmentVariables();

  // Test connections
  if (secretConfig) {
    console.log("\n📡 Testing Secrets Manager configuration...");
    await testConnection(secretConfig);
  }

  if (envConfig) {
    console.log("\n📡 Testing Environment Variables configuration...");
    await testConnection(envConfig);
  }

  if (!secretConfig && !envConfig) {
    console.log("\n❌ No valid database configuration found");
    console.log(
      "Set either DB_SECRET_ARN or DB_HOST/DB_USER/DB_PASSWORD/DB_NAME"
    );
  }

  console.log("\n🏁 Diagnostic complete");
}

main().catch(console.error);
