# 🚀 Deploy Cognito with Terraform (IaC Ready)

**Status**: Terraform code ready to deploy  
**Time**: 5 minutes to deploy + 20 minutes to configure frontend  
**Prerequisites**: AWS user with write permissions (not "reader")

---

## 📋 What This Deploys

When you run the Terraform commands below, it will automatically create:

- ✅ **Cognito User Pool** (`stocks-trading-pool-dev`)
- ✅ **App Client** (`stocks-web-app-dev`)
- ✅ **OAuth Domain** (globally unique, auto-generated)
- ✅ **Test User** (testuser / TestPassword123!)

---

## 🚀 Deploy Cognito (5 minutes)

### Step 1: Initialize Terraform

```bash
cd terraform
terraform init
```

### Step 2: Deploy Cognito

```bash
# Deploy to development environment
terraform apply -var="environment=dev"
```

When prompted, type: `yes`

### Step 3: Get Output Values

```bash
# Display the Cognito credentials
terraform output

# Or individual values:
terraform output cognito_user_pool_id
terraform output cognito_user_pool_client_id
terraform output cognito_domain_url
```

---

## 🔧 Configure Frontend (5 minutes)

### Step 1: Copy Environment Variables

From the `terraform output` above, you'll get three values. Add them to `.env.local`:

```bash
# From: terraform output cognito_user_pool_id
VITE_COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX

# From: terraform output cognito_user_pool_client_id
VITE_COGNITO_CLIENT_ID=a1b2c3d4e5f6g7h8i9j0k1l2

# From: terraform output cognito_domain_url
VITE_COGNITO_DOMAIN=https://stocks-trading-dev-626216981288.auth.us-east-1.amazoncognito.com

# AWS Region
VITE_AWS_REGION=us-east-1
```

**Location**: `C:\Users\arger\code\algo\.env.local`

### Step 2: Restart Frontend

```bash
# Stop frontend if running (Ctrl+C)
cd webapp/frontend
npm run dev
```

---

## ✅ Test It Works (5 minutes)

1. **Open** → http://localhost:5173
2. **Click** → "Sign In" button
3. **Enter**:
   - Username: `testuser`
   - Password: `TestPassword123!`
4. **Expected**: Logged-in dashboard appears

---

## 📊 Terraform Files

| File | Purpose |
|------|---------|
| `terraform/cognito.tf` | Root module for Cognito |
| `terraform/modules/cognito/main.tf` | Cognito resources (user pool, client, domain) |
| `terraform/modules/cognito/variables.tf` | Variable definitions |

---

## 🔄 Useful Terraform Commands

```bash
# Plan changes without applying
terraform plan -var="environment=dev"

# Apply with auto-approval (no "yes" prompt)
terraform apply -var="environment=dev" -auto-approve

# Destroy Cognito (delete everything - be careful!)
terraform destroy -var="environment=dev"

# Get specific output
terraform output cognito_user_pool_id

# Format code
terraform fmt -recursive
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| "Access Denied" | User doesn't have write permissions. Ask account owner to deploy. |
| "Domain already exists" | Domain names are globally unique. Try again later or change region. |
| "Module not found" | Run `terraform init` first |
| "Still using dev auth?" | Check `terraform output` values match `.env.local` exactly |

---

## 🔐 Security Notes

- ✅ Test user is created only in `dev` environment
- ✅ Password policy requires: uppercase, lowercase, numbers (12 chars min)
- ✅ No secrets in frontend code (client ID is public)
- ✅ Uses AWS Cognito defaults (no extra configuration needed)

---

## 📝 Next Steps After Deployment

1. ✅ Deploy Cognito (this step)
2. ✅ Configure frontend (5 min)
3. Test login works (5 min)
4. Deploy to production (update terraform vars)
5. Wire real user management if needed

---

## 💡 Production Deployment

To deploy to production:

```bash
# Deploy prod Cognito
terraform apply \
  -var="environment=prod" \
  -var="domain_name=yourdomain.com"

# This creates:
# - Larger user pool
# - Production security settings
# - Callback URLs for your domain
```

---

## ✨ Summary

| Step | Time | Status |
|------|------|--------|
| Deploy Cognito | 5 min | **Ready** (needs write IAM) |
| Update .env.local | 2 min | **Manual** |
| Restart frontend | 1 min | **Manual** |
| Test login | 5 min | **Manual** |
| **Total** | **13 min** | **Ready to go!** |

**Everything is ready. Just run the commands above!** 🚀
