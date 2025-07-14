# User API Key Architecture & Current Issues

## 🏗️ **Designed Architecture (Per-User API Keys)**

### Database Structure
```sql
user_api_keys table:
- user_id (UUID) - Unique per user
- provider (e.g., 'alpaca', 'td_ameritrade')  
- encrypted_api_key (AES-256-GCM encrypted)
- encrypted_api_secret (AES-256-GCM encrypted)
- user_salt (unique salt per user)
- Constraint: UNIQUE(user_id, provider)
```

### User Isolation Design
- ✅ **Each user** has their own API keys
- ✅ **Encryption salts** are unique per user
- ✅ **Database queries** filter by `user_id` 
- ✅ **JWT authentication** ensures users only access their own keys

### Per-User Workflow
1. **User A** stores Alpaca API key → encrypted with User A's salt
2. **User B** stores Alpaca API key → encrypted with User B's salt  
3. **User A** retrieves portfolio → uses User A's decrypted Alpaca key
4. **User B** retrieves portfolio → uses User B's decrypted Alpaca key

## 🚨 **Current Problem: Service-Level Failure**

### Root Cause
The **encryption service itself** is down, affecting ALL users:

```javascript
// In apiKeyService.js
if (!process.env.API_KEY_ENCRYPTION_SECRET) {
  this.isEnabled = false;  // ← BLOCKS ALL USERS
}
```

### Impact on All Users
- ❌ **No user** can store API keys (503 errors)
- ❌ **No user** can retrieve API keys (503 errors)  
- ❌ **All users** fall back to demo data
- ❌ **Entire API key system** non-functional

### Error Flow
```
User tries to add API key → 
POST /settings/api-keys → 
apiKeyService.isEnabled = false → 
503 "service unavailable" →
Frontend shows error
```

## 🛠️ **Fix Required (Infrastructure Level)**

### Step 1: Create Missing Secret
```bash
AWS Secrets Manager → Create:
Name: "stocks-app/api-key-encryption"  
Value: { "API_KEY_ENCRYPTION_SECRET": "random-64-char-string" }
```

### Step 2: Restart Service
```bash
Redeploy Lambda → Loads secret → apiKeyService.isEnabled = true
```

### Step 3: Verify Per-User Functionality
```bash
User A: POST /settings/api-keys → Encrypted with User A salt → Stored
User B: POST /settings/api-keys → Encrypted with User B salt → Stored
User A: GET /settings/api-keys → Returns only User A's keys
User B: GET /settings/api-keys → Returns only User B's keys
```

## 📊 **User Separation is Already Implemented**

### Authentication Layer
```javascript
// All API key endpoints use this:
router.use(authenticateToken);

// Extracts user ID from JWT:
const userId = req.user?.sub;

// All queries include user isolation:
SELECT * FROM user_api_keys WHERE user_id = $1
```

### Encryption Layer
```javascript
// Each user gets unique salt:
const userSalt = crypto.randomBytes(16).toString('hex');

// Encryption key derived from master secret + user salt:
const key = crypto.scryptSync(masterSecret, userSalt, 32);
```

### Database Constraints
```sql
-- Ensures each user can have one key per provider:
UNIQUE(user_id, provider, provider_account_id)

-- All queries filtered by user:
WHERE user_id = $1 AND provider = $2
```

## ✅ **Once Fixed, User Separation Works**

After creating the encryption secret:

### User A Workflow
1. Login → JWT contains User A's ID
2. Add Alpaca key → Encrypted with User A's salt → Stored in DB
3. View portfolio → Retrieves User A's Alpaca key → Fetches User A's portfolio
4. GET /settings/api-keys → Returns only User A's keys

### User B Workflow  
1. Login → JWT contains User B's ID
2. Add Alpaca key → Encrypted with User B's salt → Stored in DB
3. View portfolio → Retrieves User B's Alpaca key → Fetches User B's portfolio
4. GET /settings/api-keys → Returns only User B's keys

### Security Guarantees
- ✅ User A cannot see User B's API keys
- ✅ User A cannot use User B's API keys
- ✅ Each user's keys encrypted with different salts
- ✅ Database enforces user isolation

---

## 🎯 **Current Status**

**The user separation architecture is complete and correct.**

**The issue is infrastructure-level: missing encryption secret prevents the service from starting.**

**Fix: Create the encryption secret → All users can then store/use their individual API keys securely.**