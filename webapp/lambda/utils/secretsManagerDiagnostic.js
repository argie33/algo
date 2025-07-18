/**
 * AWS Secrets Manager Diagnostic Tool
 * Comprehensive debugging for JSON parsing errors
 */

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

class SecretsManagerDiagnostic {
    constructor() {
        this.client = new SecretsManagerClient({
            region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
        });
    }

    /**
     * Comprehensive secret retrieval with detailed logging
     */
    async diagnoseSecret(secretArn) {
        const diagnosisId = Math.random().toString(36).substr(2, 9);
        console.log(`🔍 [${diagnosisId}] Starting AWS Secrets Manager diagnostic`);
        console.log(`🔍 [${diagnosisId}] Secret ARN: ${secretArn}`);
        console.log(`🔍 [${diagnosisId}] Region: ${this.client.config.region}`);

        try {
            // Step 1: Get the raw secret response
            console.log(`🔍 [${diagnosisId}] Calling AWS Secrets Manager...`);
            const command = new GetSecretValueCommand({ SecretId: secretArn });
            const response = await this.client.send(command);
            
            console.log(`✅ [${diagnosisId}] Raw response received`);
            console.log(`🔍 [${diagnosisId}] Response keys:`, Object.keys(response || {}));
            
            // Step 2: Analyze the SecretString property
            const secretString = response.SecretString;
            console.log(`🔍 [${diagnosisId}] SecretString type:`, typeof secretString);
            console.log(`🔍 [${diagnosisId}] SecretString length:`, secretString?.length || 0);
            console.log(`🔍 [${diagnosisId}] SecretString first 200 chars: [REDACTED]`);
            
            // Step 3: Check if it's actually an object that needs stringifying
            if (typeof secretString === 'object') {
                console.log(`⚠️ [${diagnosisId}] SecretString is an object, not a string!`);
                console.log(`🔍 [${diagnosisId}] Object keys:`, Object.keys(secretString));
                console.log(`🔍 [${diagnosisId}] Object values: [REDACTED]`);
                
                // Try to use the object directly
                return {
                    success: true,
                    method: 'direct_object',
                    config: secretString,
                    diagnosticId: diagnosisId
                };
            }
            
            // Step 4: Try to parse as JSON
            if (typeof secretString === 'string') {
                console.log(`🔍 [${diagnosisId}] Attempting JSON.parse on string...`);
                
                try {
                    const parsed = JSON.parse(secretString);
                    console.log(`✅ [${diagnosisId}] JSON parsing successful`);
                    console.log(`🔍 [${diagnosisId}] Parsed keys:`, Object.keys(parsed));
                    
                    return {
                        success: true,
                        method: 'json_parse',
                        config: parsed,
                        diagnosticId: diagnosisId
                    };
                } catch (parseError) {
                    console.error(`❌ [${diagnosisId}] JSON parsing failed:`, parseError.message);
                    
                    // Step 5: Try to fix common JSON issues
                    console.log(`🔧 [${diagnosisId}] Attempting to fix JSON issues...`);
                    
                    // Remove potential BOM and invisible characters
                    const cleanString = secretString.replace(/^\uFEFF/, '').trim();
                    console.log(`🔍 [${diagnosisId}] Cleaned string length:`, cleanString.length);
                    console.log(`🔍 [${diagnosisId}] Cleaned string first 200 chars: [REDACTED]`);
                    
                    try {
                        const parsed = JSON.parse(cleanString);
                        console.log(`✅ [${diagnosisId}] JSON parsing successful after cleaning`);
                        return {
                            success: true,
                            method: 'json_parse_cleaned',
                            config: parsed,
                            diagnosticId: diagnosisId
                        };
                    } catch (cleanParseError) {
                        console.error(`❌ [${diagnosisId}] JSON parsing still failed after cleaning:`, cleanParseError.message);
                        
                        // Step 6: Character-by-character analysis
                        console.log(`🔍 [${diagnosisId}] Character analysis: [REDACTED - Logging characters would expose sensitive data]`);
                        // Character-by-character analysis removed for security
                        
                        throw new Error(`Unable to parse secret after all attempts: ${cleanParseError.message}`);
                    }
                }
            }
            
            // Step 7: Handle binary secrets
            if (response.SecretBinary) {
                console.log(`🔍 [${diagnosisId}] Secret is binary, attempting to decode...`);
                const binaryString = Buffer.from(response.SecretBinary).toString('utf8');
                console.log(`🔍 [${diagnosisId}] Binary decoded length:`, binaryString.length);
                console.log(`🔍 [${diagnosisId}] Binary decoded first 200 chars:`, binaryString.substring(0, 200));
                
                try {
                    const parsed = JSON.parse(binaryString);
                    return {
                        success: true,
                        method: 'binary_decode',
                        config: parsed,
                        diagnosticId: diagnosisId
                    };
                } catch (binaryParseError) {
                    console.error(`❌ [${diagnosisId}] Binary JSON parsing failed:`, binaryParseError.message);
                    throw binaryParseError;
                }
            }
            
            throw new Error('No valid secret found in SecretString or SecretBinary');
            
        } catch (error) {
            console.error(`❌ [${diagnosisId}] Secrets Manager diagnostic failed:`, {
                message: error.message,
                code: error.code,
                statusCode: error.$metadata?.httpStatusCode,
                requestId: error.$metadata?.requestId
            });
            
            return {
                success: false,
                error: error.message,
                diagnosticId: diagnosisId
            };
        }
    }

    /**
     * Test database configuration from secrets
     */
    async testDatabaseConfig(secretArn) {
        console.log(`🧪 Testing database configuration from secret: ${secretArn}`);
        
        const diagnosis = await this.diagnoseSecret(secretArn);
        
        if (!diagnosis.success) {
            throw new Error(`Secret diagnosis failed: ${diagnosis.error}`);
        }
        
        const config = diagnosis.config;
        console.log(`✅ Secret retrieved using method: ${diagnosis.method}`);
        
        // Validate required database fields
        const requiredFields = ['host', 'username', 'password', 'dbname'];
        const missingFields = requiredFields.filter(field => !config[field]);
        
        if (missingFields.length > 0) {
            throw new Error(`Missing required database fields: ${missingFields.join(', ')}`);
        }
        
        console.log(`✅ Database configuration validated:`, {
            host: config.host,
            port: config.port || 5432,
            database: config.dbname,
            username: config.username,
            hasPassword: !!config.password
        });
        
        return {
            host: config.host,
            port: parseInt(config.port) || 5432,
            database: config.dbname,
            user: config.username,
            password: config.password,
            ssl: false // Match working ECS configuration
        };
    }

    /**
     * Create a fixed database configuration getter
     */
    createFixedDbConfigGetter(secretArn) {
        return async () => {
            try {
                return await this.testDatabaseConfig(secretArn);
            } catch (error) {
                console.error('❌ Fixed database config getter failed:', error.message);
                throw error;
            }
        };
    }
}

module.exports = SecretsManagerDiagnostic;