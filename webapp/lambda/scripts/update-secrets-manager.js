/**
 * Update AWS Secrets Manager with new database user credentials
 * This script updates the database secrets to use the webapp_user instead of master user
 */

const { SecretsManagerClient, UpdateSecretCommand, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

const region = process.env.AWS_REGION || 'us-east-1';
const secretArn = 'arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-credentials-dev';

const client = new SecretsManagerClient({ region });

async function updateDatabaseCredentials() {
    try {
        console.log('📡 Fetching current database credentials...');
        
        // Get current secret
        const getCommand = new GetSecretValueCommand({ SecretId: secretArn });
        const currentSecret = await client.send(getCommand);
        const currentCreds = JSON.parse(currentSecret.SecretString);
        
        console.log('✅ Current credentials retrieved');
        console.log('🏗️ Current host:', currentCreds.host);
        console.log('👤 Current user:', currentCreds.username);
        
        // Create new credentials with webapp_user
        const newCredentials = {
            ...currentCreds,
            username: 'webapp_user',
            user: 'webapp_user', // Some configs use 'user' instead of 'username'
            password: 'webapp_secure_password_2025'
        };
        
        console.log('🔄 Updating credentials to use webapp_user...');
        
        // Update the secret
        const updateCommand = new UpdateSecretCommand({
            SecretId: secretArn,
            SecretString: JSON.stringify(newCredentials, null, 2)
        });
        
        await client.send(updateCommand);
        
        console.log('✅ Database credentials updated successfully!');
        console.log('🔐 New username: webapp_user');
        console.log('📝 New credentials stored in AWS Secrets Manager');
        
        return true;
    } catch (error) {
        console.error('❌ Failed to update database credentials:', error);
        throw error;
    }
}

// Only run if called directly
if (require.main === module) {
    updateDatabaseCredentials()
        .then(() => {
            console.log('🎉 Database credentials update completed');
            process.exit(0);
        })
        .catch((error) => {
            console.error('💥 Database credentials update failed:', error);
            process.exit(1);
        });
}

module.exports = { updateDatabaseCredentials };