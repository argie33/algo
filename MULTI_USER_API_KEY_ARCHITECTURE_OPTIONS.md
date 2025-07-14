# Multi-User API Key Architecture Options

## 🎯 **Requirements for Supporting Many Users**

- **Scalability**: Handle thousands of users without bottlenecks
- **Security**: Each user's API keys completely isolated 
- **Performance**: Fast encryption/decryption for concurrent users
- **Reliability**: No single point of failure
- **Cost**: Efficient use of AWS resources

## 🏗️ **Architecture Options Analysis**

### **Option 1: Shared Master Key (Current Design)**
```
One encryption secret → All user keys encrypted with user-specific salts
```

**Pros:**
- ✅ Simple infrastructure (one secret)
- ✅ Fast - no additional AWS calls per user
- ✅ Cost effective - minimal AWS resource usage
- ✅ Proven pattern used by major platforms

**Cons:**
- ⚠️ Single secret compromise affects all users (but keys still need individual salts)
- ⚠️ Key rotation requires re-encrypting all user data

**Current Implementation:**
```javascript
// Master secret (shared)
const masterSecret = process.env.API_KEY_ENCRYPTION_SECRET;

// Per-user salt (unique)
const userSalt = crypto.randomBytes(16).toString('hex');

// Per-user encryption key (derived)
const userKey = crypto.scryptSync(masterSecret, userSalt, 32);
```

---

### **Option 2: Per-User Secrets in Secrets Manager**
```
Each user gets their own secret: "user-{userId}-api-encryption"
```

**Pros:**
- ✅ Complete user isolation
- ✅ Individual key rotation
- ✅ Compromise only affects one user

**Cons:**
- ❌ **MAJOR**: AWS Secrets Manager costs $0.40/month per secret
- ❌ **MAJOR**: 10,000 users = $4,000/month just for secrets
- ❌ Performance impact - AWS API call per user operation
- ❌ Complex secret lifecycle management
- ❌ Rate limiting issues with Secrets Manager

---

### **Option 3: Hybrid - User-Specific Encryption with KMS**
```
AWS KMS per-user data keys + local key derivation
```

**Pros:**
- ✅ Strong user isolation via AWS KMS
- ✅ No per-user secret storage costs
- ✅ Hardware security module backing

**Cons:**
- ❌ KMS API calls cost ($0.03 per 10,000 calls)
- ❌ More complex implementation
- ❌ Potential latency for every operation

---

### **Option 4: Enhanced Shared Key with User Context**
```
Master key + user ID + context for key derivation
```

**Implementation:**
```javascript
// Derive user-specific key from master + user context
const userKey = crypto.scryptSync(
  masterSecret, 
  `${userId}:${userSalt}:api-keys`, 
  32
);
```

**Pros:**
- ✅ Strong user isolation 
- ✅ Single secret to manage
- ✅ No additional AWS costs
- ✅ Fast performance
- ✅ Industry standard approach

**Cons:**
- ⚠️ Still relies on master secret security

---

### **Option 5: Client-Side Encryption**
```
Users provide their own encryption password
```

**Pros:**
- ✅ Zero server-side secret management
- ✅ Maximum user privacy

**Cons:**
- ❌ Poor user experience (users must remember passwords)
- ❌ Key recovery complexity
- ❌ Not suitable for background portfolio sync

---

## 📊 **Recommendation: Enhanced Shared Key (Option 4)**

### **Why This is Best for Multi-User:**

#### **1. Industry Standard**
- Used by AWS, Google Cloud, Azure for customer data encryption
- Proven pattern in Stripe, PayPal, major fintech platforms
- NIST approved key derivation approach

#### **2. Cost Efficiency**
```
1 secret:     $0.40/month
10,000 users: $0.40/month (same cost!)
vs.
Per-user secrets: $4,000/month for 10,000 users
```

#### **3. Performance at Scale**
```
Shared Key:    0 additional AWS API calls
Per-User KMS:  10,000 KMS calls for 10,000 users
Per-User SM:   10,000 Secrets Manager calls
```

#### **4. Security Analysis**
Even with shared master key:
- ✅ Each user gets unique salt
- ✅ Key derivation includes user ID  
- ✅ User A cannot decrypt User B's data
- ✅ Compromise requires both master key AND specific user salt

### **Enhanced Implementation**
```javascript
class UserApiKeyService {
  constructor() {
    this.masterSecret = process.env.API_KEY_ENCRYPTION_SECRET;
    this.keyCache = new Map(); // Cache derived keys
  }

  getUserEncryptionKey(userId, userSalt) {
    const keyId = `${userId}:${userSalt}`;
    
    if (this.keyCache.has(keyId)) {
      return this.keyCache.get(keyId);
    }

    // Derive user-specific key with multiple contexts
    const userKey = crypto.scryptSync(
      this.masterSecret,
      `${userId}:${userSalt}:api-encryption:v1`,
      32
    );

    this.keyCache.set(keyId, userKey);
    return userKey;
  }

  encryptUserApiKey(userId, apiKey, userSalt) {
    const userKey = this.getUserEncryptionKey(userId, userSalt);
    // ... AES-256-GCM encryption with user key
  }
}
```

### **Additional Security Layers**
1. **User ID in key derivation** - prevents cross-user attacks
2. **Version in context** - enables key rotation strategies  
3. **Purpose-specific derivation** - separate keys for different data types
4. **Key caching** - performance optimization

---

## 🛠️ **Implementation Plan**

### **Phase 1: Fix Current Issue (Immediate)**
```bash
1. Create single encryption secret in AWS Secrets Manager
2. Redeploy Lambda to load secret
3. Verify basic functionality works
```

### **Phase 2: Enhance Security (Short Term)**
```javascript
1. Update key derivation to include user ID in context
2. Add key caching for performance
3. Implement proper key rotation strategy
```

### **Phase 3: Production Hardening (Medium Term)**  
```javascript
1. Add monitoring for encryption operations
2. Implement rate limiting and abuse detection
3. Add backup/recovery procedures
4. Performance optimization for high user load
```

---

## 🎯 **Conclusion**

**For supporting many users efficiently:**

✅ **Use Enhanced Shared Key approach (Option 4)**
- Industry proven pattern
- Cost effective ($0.40/month vs $4,000/month)
- High performance 
- Strong security with proper implementation

❌ **Avoid per-user secrets in Secrets Manager**  
- Cost prohibitive at scale
- Performance bottlenecks
- Complex management overhead

**The current architecture is fundamentally sound for multi-user - we just need to create the missing master secret and enhance the key derivation.**