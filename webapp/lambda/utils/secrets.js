const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

const secretsManager = new SecretsManagerClient({
    region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
});

/**
 * Get database credentials from AWS Secrets Manager
 */
async function getDbCredentials() {
    try {
        const secretArn = process.env.DB_SECRET_ARN;
        
        if (!secretArn) {
            throw new Error('DB_SECRET_ARN environment variable not set');
        }
        
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const result = await secretsManager.send(command);
        const secret = JSON.parse(result.SecretString);
        
        return {
            host: secret.host || process.env.DB_ENDPOINT,
            port: parseInt(secret.port) || 5432,
            user: secret.username,
            password: secret.password,
            database: secret.dbname
        };
    } catch (error) {
        console.error('Error getting DB credentials:', error);
        throw error;
    }
}

module.exports = {
    getDbCredentials
};