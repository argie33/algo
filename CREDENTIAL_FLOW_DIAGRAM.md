# Credential Flow Architecture

## 1. LOCAL DEVELOPMENT
```
User sets credentials in AWS Secrets Manager (one-time setup)
  ↓
credential_manager.get_credential_manager()
  ↓
boto3.client('secretsmanager').get_secret_value()
  ↓
Returns: {host, port, username, password, dbname}
  ↓
credential_helper.get_db_config() uses values
```

## 2. GITHUB ACTIONS CI
```
GitHub Secrets (RDS_PASSWORD, etc)
  ↓
Environment Variables: DB_PASSWORD=<secret>, others default or env-set
  ↓
credential_helper.get_db_config()
  ↓
Returns merged config from:
  - os.getenv('DB_PASSWORD')
  - os.getenv('DB_HOST', DEFAULT_HOST)
  - etc.
```

## 3. TERRAFORM DEPLOYMENT
```
GitHub Actions passes secrets.RDS_PASSWORD
  ↓
TF_VAR_db_master_password environment variable
  ↓
Terraform: aws_secretsmanager_secret.rds_credentials
  ↓
Stores in AWS Secrets Manager with name: ${project}-rds-credentials-${env}
```

## 4. AWS LAMBDA (Orchestrator)
```
Lambda invoked by EventBridge
  ↓
Environment variables (from Terraform):
  - EXECUTION_MODE
  - DATABASE_SECRET_ARN (from secrets store)
  ↓
lambda_function.py calls prepare_database_credentials()
  ↓
get_db_config() retrieves from:
  1. credential_manager (tries AWS Secrets Manager using DATABASE_SECRET_ARN)
  2. Environment variables (DB_PASSWORD fallback)
  ↓
Returns: {host, port, user, password, database}
  ↓
Orchestrator runs with credentials
```

## 5. AWS RDS PROXY
```
Lambda → RDS Proxy (uses IAM auth or secrets)
  ↓
Secrets Manager: aws_secretsmanager_secret.rds_credentials
  ↓
→ RDS database
```

## Critical Path Check
✓ Credentials defined in utils.defaults.py (local fallbacks)
✓ All code uses config.credential_helper.get_db_config()
✓ GitHub Actions passes RDS_PASSWORD
✓ Terraform stores in AWS Secrets Manager
✓ Lambda has DATABASE_SECRET_ARN env var
✓ credential_manager reads from Secrets Manager
✓ No hardcoded values in production code
