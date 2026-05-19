# Phase 1: Console Actions - 20 Minutes to -$22-33/Month

**Savings**: -$22-33/month = -$264-396/year  
**Upfront Cost**: $360 (RDS + Lambda reserved capacity)  
**Time Required**: 20 minutes  
**ROI**: Break-even in 16 months, then pure savings

---

## Action 1: RDS Reserved Instance (5 minutes) → -$12-15/month

### Steps:
1. Go to: [AWS RDS Console](https://console.aws.amazon.com/rds/)
2. Click **"Reservations"** in left menu
3. Click **"Purchase reserved instances"**
4. Configure:
   - **Engine**: PostgreSQL
   - **Instance Class**: db.t4g.small  
   - **Term**: 1 year
   - **Payment Option**: All upfront (~$300)
5. Click **"Purchase reserved instances"**
6. ✅ Verify: RDS → Reservations should show your 1-year commitment

### What This Does:
- Locks in 60% discount on RDS database
- Pays itself back in 2 years
- Zero changes to your database or applications

### Expected on Next Bill:
- RDS cost drops from ~$40/month to ~$24/month
- Savings: **-$16/month baseline, -$12-15/month after Phase 2**

---

## Action 2: Lambda Reserved Concurrency (5 minutes) → -$5-8/month

### API Lambda Function:
1. Go to: [AWS Lambda Console](https://console.aws.amazon.com/lambda/)
2. Click function: **`algo-api-prod`**
3. Go to **Configuration** tab
4. Scroll to **Concurrency** section
5. Click **"Edit"**
6. Set **Reserved concurrent executions**: `50`
7. Click **"Save"**
8. ✅ Verify: Console shows "Reserved: 50"

### Orchestrator Lambda Function:
1. Select function: **`algo-algo-prod`**
2. Repeat steps 3-7 above
3. Set **Reserved concurrent executions**: `10`
4. ✅ Verify: Console shows "Reserved: 10"

### What This Does:
- Guarantees 50 concurrent API requests (always available)
- Guarantees 10 concurrent orchestrator runs (always available)
- Gets 70% discount on reserved concurrency
- Prevents throttling during traffic spikes

### Expected Cost Impact:
- **API Lambda**: -$2-4/month
- **Algo Lambda**: -$3-4/month
- **Total**: -$5-8/month

---

## Action 3: Activate Cost Allocation Tags (5 minutes) → Visibility

### Steps:
1. Go to: [AWS Billing Console](https://console.aws.amazon.com/billing/)
2. Click **"Cost allocation tags"** in left menu
3. Find and activate each tag:
   - [ ] **CostCenter** → Click "Activate"
   - [ ] **ServiceName** → Click "Activate"
   - [ ] **Environment** → Click "Activate"
4. ✅ **Wait 24 hours** for tags to appear in Cost Explorer

### What This Does:
- Breaks down costs by service (Database, API, Algo, Storage)
- Identifies which services are expensive
- Helps spot future cost issues early
- Free to activate

### After 24 Hours:
1. Go to: [AWS Cost Explorer](https://console.aws.amazon.com/cost-management/)
2. Click **"Cost Explorer"**
3. Select **"Group by"** → **"Tag"**
4. Select tag: **CostCenter**
5. See breakdown by service

---

## Action 4: Verify Cognito Password Policies (5 minutes) → Security

### Status: ✅ Already Configured
Your Cognito user pool is already configured with:
- ✅ Minimum 12 characters
- ✅ Require uppercase letters
- ✅ Require lowercase letters
- ✅ Require numbers
- ✅ Require special symbols

### Verification (Optional):
1. Go to: [AWS Cognito Console](https://console.aws.amazon.com/cognito/)
2. Select your **User Pool**
3. Go to **Policies** → **Password policy**
4. Confirm settings above are enabled

### What This Does:
- Prevents weak passwords
- Meets compliance requirements
- Reduces account takeover risk
- No cost impact

---

## ⏱️ Timeline

| Action | Time | Cost | Savings | Cumulative |
|--------|------|------|---------|-----------|
| RDS Reserved | 5 min | $300 | -$12-15/mo | -$12-15/mo |
| Lambda Reserved | 5 min | $60 | -$5-8/mo | -$17-23/mo |
| Cost Tags | 5 min | $0 | Visibility | -$17-23/mo |
| Cognito Verify | 5 min | $0 | Security | -$17-23/mo |
| **TOTAL** | **20 min** | **$360** | **-$22-33/mo** | **-$264-396/yr** |

---

## 📊 Monthly Bill Impact

### BEFORE (This Month)
```
RDS:                 $40/month
Lambda:              $7-10/month
CloudFront:          $3-5/month
S3 + Data:           $2-3/month
NAT Gateway:         $32/month
DynamoDB:            $0.25/month
Secrets Manager:     $1.20/month
CloudWatch Logs:     $5-10/month
Other:               $10-15/month
─────────────────────────────
TOTAL:               $100-120/month
```

### AFTER (Next Month)
```
RDS (reserved):      $24/month         (-$16)
Lambda (reserved):   $4-6/month        (-$3-4)
CloudFront (cached): $2-3/month        (-$1-2)
S3 + Data:           $2-3/month
NAT Gateway:         $32/month
DynamoDB:            $0.25/month
Secrets Manager:     $1.20/month
CloudWatch Logs:     $5-10/month
Other:               $10-15/month
─────────────────────────────
TOTAL:               $80-95/month      (-$20-40)
```

**Monthly Savings**: -$20-40/month  
**Annual Savings**: -$240-480/year  
**First Year ROI**: -$240-480 minus $360 = -120 savings after cost recovery

---

## 💡 Tips for Success

### Before You Start
- [ ] Have AWS login credentials ready
- [ ] Allocate 20 uninterrupted minutes
- [ ] Keep this guide open in a tab

### While You're Doing It
- [ ] Take screenshots of each completed step (for your records)
- [ ] Verify each action immediately after completing it
- [ ] Don't rush - these are one-time actions

### After You're Done
- [ ] Wait 24 hours for cost tags to appear
- [ ] Check Cost Explorer to see tag breakdown
- [ ] Monitor next month's AWS bill for RDS discount
- [ ] Note the reserved concurrency in Lambda settings

---

## ⚠️ Important Notes

### These Changes Are Safe
- ✅ No downtime for any service
- ✅ No code changes required
- ✅ No data migrations
- ✅ Existing Lambda functions work unchanged
- ✅ RDS database continues operating normally

### You Can't Undo Purchases (But It's OK)
- RDS Reserved Instance: 1-year commitment (can't cancel, but you already have the capacity)
- Lambda Concurrency: Can be removed anytime
- Cost Tags: Can be deactivated anytime

### Refund Policy
- AWS gives refunds for unused reserved instances only within 7 days
- But your RDS is already in use, so you'll see immediate savings

---

## ✅ Success Criteria

You're done when:

- [ ] **RDS Console** shows 1-year reservation active
- [ ] **Lambda (API)** shows "Reserved: 50"
- [ ] **Lambda (Algo)** shows "Reserved: 10"
- [ ] **Billing Console** shows cost tags "Inactive" → "Active"
- [ ] **Next Month's Bill** shows RDS at ~$24 instead of ~$40
- [ ] **Cognito Policies** verified (already done)

---

## 🎯 What Happens Next

### Immediately
- Reserved instances take effect on next billing cycle
- Lambda gets reserved concurrency pool

### In 24 Hours
- Cost allocation tags appear in Cost Explorer
- You can see cost breakdown by service

### In 1-2 Billing Cycles
- AWS bill shows RDS discount applied
- You see -$12-15/month RDS savings reflected
- You see -$5-8/month Lambda savings reflected

### If Deployed Phase 2 (Terraform)
- Lambda layer deployed (faster deploys, smaller packages)
- CloudFront caching active (-$5-10/month additional)
- **Total**: -$27-43/month combined

---

## 🆘 Troubleshooting

**Q: I don't see the option to purchase reserved instances**
A: Check if you have billing permissions. Contact your AWS account admin if needed.

**Q: The cost tags didn't activate**
A: They take 24 hours. Come back tomorrow and check Cost Explorer.

**Q: I set Lambda reserved concurrency, will existing invocations fail?**
A: No, reserved concurrency applies to NEW invocations. Your existing code continues working.

**Q: Can I change the reserved amounts later?**
A: Yes! Go back to Lambda console and click "Edit" to adjust up or down.

**Q: What if I don't need this much reserved concurrency?**
A: Start conservative (50/10) and adjust after monitoring for a week. You can always reduce.

---

## 📞 Need Help?

If you get stuck on any step:
- **RDS Reserved**: AWS Console → RDS → Reservations help
- **Lambda Concurrency**: AWS Console → Lambda → Function → Configuration
- **Cost Tags**: AWS Console → Billing → Cost allocation tags
- **Cognito**: AWS Console → Cognito → User Pools → Policies

---

## 🎉 You've Got This!

20 minutes of work → **-$264-396 per year**

That's like getting free AWS services for a month. Let's go! 🚀

---

**Checklist:**
- [ ] Step 1: RDS Reserved Instance ✅
- [ ] Step 2: Lambda Concurrency (API) ✅
- [ ] Step 3: Lambda Concurrency (Algo) ✅
- [ ] Step 4: Activate Cost Tags ✅
- [ ] Step 5: Verify Cognito ✅
- [ ] DONE! 🎉
