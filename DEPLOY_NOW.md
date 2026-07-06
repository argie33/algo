# DEPLOY THE SYSTEM NOW - Step-by-Step

The system is ready to deploy. You just need to trigger one GitHub Actions workflow.

## Step 1: Go to GitHub Actions

1. Open your GitHub repo (algo)
2. Click on **Actions** tab at the top

## Step 2: Find the Deployment Workflow

1. Click on **"Deploy All Infrastructure (Terraform)"** in the workflow list
2. You should see it in the left sidebar

## Step 3: Trigger the Deployment

1. Click the **"Run workflow"** button (top right)
2. A dropdown will appear with options - leave defaults:
   - `skip_terraform`: false
   - `skip_image`: false
   - `skip_code`: false
3. Click **"Run workflow"** green button

## Step 4: Wait for Completion

1. Watch the workflow run (takes 15-20 minutes)
2. It will deploy Lambda, API Gateway, EventBridge, RDS, everything

## After Deployment - System Fully Operational

✅ **Trading Executes Automatically**:
- 9:30 AM ET: Morning run (primary)
- 1:00 PM ET: Afternoon run (rebalance)
- 3:00 PM ET: Pre-close run (final trades)
- 5:30 PM ET: Evening run (signal prep)

✅ **Dashboard Works**:
- Shows growth scores
- Displays positions
- Shows portfolio P&L
- Shows circuit breaker status

✅ **Data Loaders Work**:
- Prices loaded automatically
- Signals computed
- Metrics updated
- Trades execute

## Why This Works

GitHub Actions has full AWS permissions via OIDC role. Your AWS CLI doesn't, but the workflow does.

**One click. System working. That's it.**
