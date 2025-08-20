require("dotenv").config();
console.log("Environment check:");
console.log(
  "DB_SECRET_ARN:",
  process.env.DB_SECRET_ARN ? "[SET]" : "[NOT SET]"
);
console.log("AWS_REGION:", process.env.AWS_REGION || "[NOT SET]");
console.log("NODE_ENV:", process.env.NODE_ENV || "[NOT SET]");

const {
  SecretsManagerClient,
  GetSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");

async function test() {
  if (process.env.DB_SECRET_ARN) {
    const client = new SecretsManagerClient({ region: "us-east-1" });
    try {
      const result = await client.send(
        new GetSecretValueCommand({ SecretId: process.env.DB_SECRET_ARN })
      );
      console.log("Secret retrieved, type:", typeof result.SecretString);
      console.log("Secret preview:", result.SecretString?.substring(0, 50));

      const parsed = JSON.parse(result.SecretString);
      console.log("Parsed successfully, keys:", Object.keys(parsed));
    } catch (error) {
      console.error("Error:", error.message);
    }
  }
}

test();
