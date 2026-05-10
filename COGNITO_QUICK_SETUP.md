# ⚡ COGNITO QUICK SETUP (AWS Console - 20 minutes)

**Your AWS user is "reader" (read-only) - use AWS Console instead of CLI**

---

## 🚀 Step 1: Create User Pool (5 min)

1. **Open** → https://console.aws.amazon.com/cognito/v2/idp/user-pools?region=us-east-1
2. **Click** → "Create user pool"
3. **Configure**:
   - Sign-in options: ✅ Email
   - Password policy: ✅ Require uppercase, lowercase, numbers (keep defaults)
   - **Pool name**: `stocks-trading-pool-dev`
4. **Click** → "Create user pool"
5. **Wait** → Page shows your pool ID

**Copy this:** User Pool ID (looks like: `us-east-1_XXXXXXXXX`)

---

## 🚀 Step 2: Create App Client (3 min)

1. **In your new user pool**, go to **"App integration"** → **"App clients and analytics"**
2. **Click** → "Create app client"
3. **Configure**:
   - App client name: `stocks-web-app-dev`
   - ✅ User password-based authentication (ALLOW_USER_PASSWORD_AUTH)
   - ✅ Refresh token based authentication (ALLOW_REFRESH_TOKEN_AUTH)
   - Callback URL: `http://localhost:5173/`
   - Allowed OAuth scopes: openid, profile, email
4. **Click** → "Create app client"

**Copy this:** Client ID (looks like: `a1b2c3d4e5f6g7h8i9j0k1l2`)

---

## 🚀 Step 3: Create Cognito Domain (5 min)

1. **In your user pool**, go to **"App integration"** → **"Domain"**
2. **Click** → "Create Cognito domain"
3. **Enter domain** (must be globally unique - add timestamp):
   - `stocks-dev-trading-20260509` ← use this pattern
4. **Click** → "Create Cognito domain"
5. **Wait** → Domain created, shows full URL

**Copy this:** Full domain URL (looks like: `https://stocks-dev-trading-20260509.auth.us-east-1.amazoncognito.com`)

---

## 🚀 Step 4: Create Test User (3 min)

1. **In your user pool**, go to **"Users"**
2. **Click** → "Create user"
3. **Fill in**:
   - Username: `testuser`
   - Password: `TestPassword123!`
   - ✅ Mark email as verified
4. **Click** → "Create user"
5. **Verify** → User appears in list

**Test credentials**:
- Username: `testuser`
- Password: `TestPassword123!`

---

## 🚀 Step 5: Update .env.local (1 min)

**Add these lines to `.C:\Users\arger\code\algo\.env.local`:**

```bash
# ================================================================
# COGNITO CONFIGURATION
# ================================================================
VITE_COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
VITE_COGNITO_CLIENT_ID=a1b2c3d4e5f6g7h8i9j0k1l2
VITE_COGNITO_DOMAIN=https://stocks-dev-trading-20260509.auth.us-east-1.amazoncognito.com
VITE_AWS_REGION=us-east-1
```

**Replace with YOUR values from Steps 1-3**

---

## 🚀 Step 6: Restart Frontend (1 min)

```bash
# If running, stop it (Ctrl+C)
cd webapp/frontend
npm run dev
```

---

## ✅ Test It Works

1. Open http://localhost:5173
2. Click **"Sign In"**
3. Enter:
   - Username: `testuser`
   - Password: `TestPassword123!`
4. **Should see**: Logged in dashboard instead of login form

**Success!** You now have real Cognito authentication! 🎉

---

## 🎯 Direct AWS Links

**Copy-paste these into your browser:**

- **Create User Pool**: https://console.aws.amazon.com/cognito/v2/idp/user-pools/create/spa?region=us-east-1

- **Your Pools**: https://console.aws.amazon.com/cognito/v2/idp/user-pools?region=us-east-1

---

## 💡 What to do if something goes wrong

| Problem | Solution |
|---------|----------|
| "Callback URL mismatch" | Go to app client → OAuth 2.0 URLs → Add `http://localhost:5173/` to Callback URLs |
| "Domain already exists" | Use a different domain name (add more numbers/letters) |
| Still using dev auth | Check that env vars are in `.env.local` (restart frontend after editing) |
| "Invalid credentials" | Check username/password entered correctly |

---

## 🏁 TOTAL TIME: 20 minutes

**That's it! You now have production-ready authentication.** 🚀
