# Credentials Setup Guide

Complete instructions for configuring Alpaca API credentials and Cognito authentication.

---

## Part 1: Alpaca API Credentials

### Current Issue
- Phase 9 reconciliation fails with HTTP 401 Unauthorized
- Alpaca API credentials missing from AWS Secrets Manager
- Position reconciliation cannot fetch live broker data

### Step 1: Generate Alpaca API Key

**For Paper Trading (Development):**
1. Log into https://app.alpaca.markets
2. Navigate to **Settings → Integrations → API Keys**
3. Create new API key
4. Copy **API Key** and **Secret Key**
5. Ensure key has: `account:read`, `positions:read`

**For Live Trading (Production):**
⚠️ Use live API key, ensure account is funded, test carefully

### Step 2: Create AWS Secret

**AWS CLI (Fastest):**
```bash
aws secretsmanager create-secret \
  --name alpaca-credentials \
  --secret-string '{
    "api_key": "PKxxxxxxxxxxxxxxxx",
    "secret_key": "xxxxxxxxxxxxxxxxxxx",
    "base_url": "https://paper-api.alpaca.markets"
  }' \
  --region us-east-1
```

**AWS Console:**
1. Secrets Manager → Create Secret
2. Type: Other
3. Name: `alpaca-credentials`
4. Value: JSON with api_key, secret_key, base_url
5. Store

**Update Existing:**
```bash
aws secretsmanager update-secret \
  --secret-id alpaca-credentials \
  --secret-string '{"api_key":"...", "secret_key":"...", "base_url":"..."}'
```

### Step 3: Verify Credentials

**Test Connectivity:**
```bash
export ALPACA_API_KEY="PKxxxxxxxxxxxxxxxx"
export ALPACA_SECRET_KEY="xxxxxxxxxxxxxxxxxxx"
export ALPACA_BASE_URL="https://paper-api.alpaca.markets"

curl -X GET \
  -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_SECRET_KEY" \
  "$ALPACA_BASE_URL/v2/account"
```

**Python Verification:**
```python
from alpaca.trading.client import TradingClient
import json, boto3

secret = json.loads(boto3.client('secretsmanager').get_secret_value(SecretId='alpaca-credentials')['SecretString'])
tc = TradingClient(api_key=secret['api_key'], secret_key=secret['secret_key'], base_url=secret['base_url'])
account = tc.get_account()
print(f"Account {account.account_number}: ${account.portfolio_value:,.2f}")
```

### Step 4: Test in Orchestrator

```bash
export ORCHESTRATOR_DRY_RUN=true
python3 -m algo.orchestrator.run --dry-run --verbose
# Look for: [PHASE 9] ✓ Reconciliation completed
```

---

## Part 2: Cognito Authentication

### Current Issue
- Dashboard API JWT validation fails with 401 Unauthorized
- Cognito user pool/client not configured
- Users cannot authenticate to dashboard

### Step 1: Create Cognito User Pool

**AWS CLI:**
```bash
aws cognito-idp create-user-pool \
  --pool-name algo-dashboard-pool \
  --policies '{"PasswordPolicy": {"MinimumLength": 12}}' \
  --region us-east-1
```

**AWS Console:**
1. Cognito → Create User Pool
2. Name: `algo-dashboard-pool`
3. Sign-in: Email
4. Password Policy: Default (12+ chars, mixed case, numbers, symbols)
5. Create

**Save the User Pool ID** (e.g., `us-east-1_abc123def456`)

### Step 2: Create App Client

**AWS CLI:**
```bash
aws cognito-idp create-user-pool-client \
  --user-pool-id us-east-1_abc123def456 \
  --client-name algo-dashboard-web \
  --explicit-auth-flows \
    ALLOW_USER_PASSWORD_AUTH \
    ALLOW_REFRESH_TOKEN_AUTH \
    ALLOW_USER_SRP_AUTH \
  --region us-east-1
```

**AWS Console:**
1. User Pool → App Integration → App Clients
2. Create App Client
3. Name: `algo-dashboard-web`
4. Type: Public Client
5. Auth flows: PASSWORD, REFRESH_TOKEN, USER_SRP
6. Create

**Save the Client ID** (e.g., `3l0abc123def456xyz789`)

### Step 3: Create Test User

**AWS CLI:**
```bash
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_abc123def456 \
  --username algo-admin \
  --user-attributes Name=email,Value=argeropolos@gmail.com \
  --temporary-password TempPassword123! \
  --region us-east-1

aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_abc123def456 \
  --username algo-admin \
  --password "SecurePassword123!" \
  --permanent \
  --region us-east-1
```

**AWS Console:**
1. User Pool → Users → Create User
2. Username: `algo-admin`
3. Email: `argeropolos@gmail.com`
4. Temporary password: (auto)
5. Send invitation: Yes

### Step 4: Configure Environment Variables

**In Lambda Function:**
1. Lambda Console → Configuration → Environment Variables
2. Add:
   - `COGNITO_POOL_ID`: `us-east-1_abc123def456`
   - `COGNITO_CLIENT_ID`: `3l0abc123def456xyz789`
   - `COGNITO_REGION`: `us-east-1`
   - `COGNITO_JWKS_URL`: `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_abc123def456/.well-known/jwks.json`

**In ECS Task Definition:**
```json
"environment": [
  {"name": "COGNITO_POOL_ID", "value": "us-east-1_abc123def456"},
  {"name": "COGNITO_CLIENT_ID", "value": "3l0abc123def456xyz789"},
  {"name": "COGNITO_REGION", "value": "us-east-1"},
  {"name": "COGNITO_JWKS_URL", "value": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_abc123def456/.well-known/jwks.json"}
]
```

### Step 5: Test Authentication

**Generate JWT Token:**
```bash
python3 << 'EOF'
import json, boto3
from botocore.exceptions import ClientError

client = boto3.client('cognito-idp', region_name='us-east-1')
try:
    response = client.admin_initiate_auth(
        UserPoolId='us-east-1_abc123def456',
        ClientId='3l0abc123def456xyz789',
        AuthFlow='ADMIN_NO_SRP_AUTH',
        AuthParameters={'USERNAME': 'algo-admin', 'PASSWORD': 'SecurePassword123!'}
    )
    token = response['AuthenticationResult']['IdToken']
    print(token)
except ClientError as e:
    print(f"Error: {e.response['Error']['Code']}")
EOF
```

**Test API Call:**
```bash
JWT_TOKEN=$(python3 scripts/generate-cognito-token.py)
curl -H "Authorization: Bearer $JWT_TOKEN" \
  https://api.example.com/api/algo/portfolio
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` (Alpaca) | Invalid API key/secret | Regenerate key in Alpaca dashboard, update secret |
| `401 Unauthorized` (JWT) | Invalid/missing token | Regenerate with `generate-cognito-token.py` |
| `403 Forbidden` | Valid token but missing permissions | Add user to admin group (see below) |
| `Connection refused` | Wrong base URL | Check paper vs live URL |
| `Secret not found` | Wrong secret name | Verify secret is `alpaca-credentials` |
| `JWKS unreachable` | Wrong pool ID/region | Verify COGNITO_JWKS_URL environment variable |

---

## Admin Functions

**Add User to Admin Group:**
```bash
aws cognito-idp create-group \
  --group-name admin \
  --user-pool-id us-east-1_abc123def456 \
  --description "Dashboard admins" \
  --region us-east-1

aws cognito-idp admin-add-user-to-group \
  --user-pool-id us-east-1_abc123def456 \
  --username algo-admin \
  --group-name admin \
  --region us-east-1
```

---

## References
- Alpaca API: https://docs.alpaca.markets
- Cognito: https://docs.aws.amazon.com/cognito/
- Related code: `algo/orchestrator/phase9_reconciliation.py`, `utils/validation.py`
