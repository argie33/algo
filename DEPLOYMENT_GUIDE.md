# Deployment Guide: GitHub Actions + Terraform IaC Only

**TL;DR:** All deployment happens via GitHub Actions. Make code changes → commit to main → GitHub auto-deploys. Watch progress at https://github.com/argie33/algo/actions

---

## ✅ Current Status

**The system is FULLY DEPLOYED and RUNNING.**

- ✅ API Lambda: https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com
- ✅ Frontend: https://d5j1h4wzrkvw7.cloudfront.net
- ✅ RDS Database: PostgreSQL 14, healthy
- ✅ EventBridge Scheduler: Daily data loaders (3:30am–10:25pm ET)
- ✅ Algo Orchestrator: Ready to trade (5:30pm ET weekdays)
- ✅ Last deployment: 2026-05-12 ✓ All jobs passed

**Nothing needs deployment — system is live and trading.**

---

## 🔄 How Deployment Works

### Automatic (Every Commit to main)

1. You push code to main
2. GitHub Actions auto-triggers deploy-all-infrastructure.yml
3. Workflow runs 6 jobs:
   - Terraform Apply (infrastructure)
   - Build Docker image (ECS loaders)
   - Deploy Algo Lambda
   - Deploy API Lambda
   - Build & deploy frontend
   - Initialize database schema
4. All changes go live in ~20-30 minutes

### Manual (If Needed)

1. Go to: https://github.com/argie33/algo/actions
2. Click "Deploy All Infrastructure (Terraform)"
3. Click "Run workflow" button
4. Click "Run workflow" again

---

## 🛑 GOLDEN RULE

**NEVER manually change AWS resources via the console.**

- ❌ No manual Lambda edits
- ❌ No manual RDS changes
- ❌ No manual S3 uploads
- ❌ No manual anything

**All infrastructure lives in:** 	erraform/ directory

**Always:** Edit code → Commit → Push to main → GitHub deploys via Terraform

---

## 📋 Deployment Checklist

- ✅ Secrets configured (already done)
- ✅ AWS credentials set via OIDC (already done)
- ✅ GitHub Actions enabled (already done)
- ✅ Code ready to push (your job)
- ✅ Just commit and push

---

## ⏱️ Deployment Times

- Terraform: 12-15 min
- Docker: 3-5 min
- Lambdas: 4 min
- Frontend: 5 min
- **Total: ~20-30 min**

---

## 🔍 Watch Deployment

https://github.com/argie33/algo/actions → Click latest run → See status

All jobs in green = success

---

## 🎯 That's It

- **System is deployed** ✓
- **Secrets configured** ✓
- **Secrets already set** ✓
- **Ready to go** ✓

Write code → git push origin main → GitHub deploys everything automatically.

---

See STATUS.md for full infrastructure details.
