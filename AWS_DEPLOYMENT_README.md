# AWS Deployment - Complete Guide

## Current Status

✅ **Local Development**: Fully functional and tested
- Backend running on `http://localhost:3001`
- Frontend running on `http://localhost:5173`
- Database: PostgreSQL (13GB with all data)
- All 145 industries loading with real performance data
- Charts and metrics displaying correctly

📦 **Database Dump**: Ready (13GB)
- Location: `/tmp/stocks_database.sql`
- Contains: All tables, indices, and data
- Size: 13 GB

🚧 **AWS Deployment**: Blocked by permissions

## The Issue: Limited AWS Permissions

Your AWS account currently has **"reader" permissions only**:
```
User ARN: arn:aws:iam::626216981288:user/reader
```

This means you can **view** resources but **cannot create or modify** them.

### Required Permissions for Deployment:
- ✅ RDS (create, modify, delete database instances)
- ✅ EC2 (create, modify, delete instances)
- ✅ S3 (create buckets, upload files)
- ✅ CloudFront (create distributions)
- ✅ IAM (create roles for services)
- ✅ Lambda (create, deploy functions)

## Solution: Request Elevated Permissions

Contact your AWS account administrator and request:

> **Permission Request**: I need elevated IAM permissions to deploy a web application to AWS. Specifically, I need:
> - RDS: Full access (create/modify/delete PostgreSQL instances)
> - S3: Full access (create buckets, manage objects)
> - EC2: Full access (create/modify/delete instances)
> - CloudFront: Full access (create distributions)
> - Lambda: Full access (create/deploy functions)
> - IAM: Limited access (create service roles)
>
> Account ID: 626216981288
> Preferred role name: `deployment-admin` or similar

### Permission Policy (IAM JSON):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "rds:*",
        "s3:*",
        "ec2:*",
        "cloudfront:*",
        "lambda:*",
        "apigateway:*",
        "iam:CreateRole",
        "iam:PutRolePolicy",
        "iam:PassRole"
      ],
      "Resource": "*"
    }
  ]
}
```

## Deployment Files Ready

Three files have been created to automate deployment once you have permissions:

### 1. **AWS_DEPLOYMENT_GUIDE.md**
Complete manual deployment guide with step-by-step instructions:
- Creating RDS instance
- Creating S3 buckets
- Restoring database
- Deploying backend
- Deploying frontend
- Setting up CloudFront

### 2. **deploy-to-aws.sh** (Automated Script)
Executable bash script that automates most deployment steps:
```bash
# Once you have elevated permissions, run:
bash /home/stocks/algo/deploy-to-aws.sh
```

The script will:
- ✅ Verify AWS credentials and permissions
- ✅ Create RDS PostgreSQL instance
- ✅ Create S3 buckets for backups and frontend
- ✅ Upload database dump to S3
- ✅ Prompt for manual database restoration
- ✅ Build frontend for production
- ✅ Deploy frontend to S3
- ✅ Provide deployment summary

### 3. **Deployment Architecture**
```
┌─────────────────────────────────────────────────┐
│                   AWS Cloud                      │
├─────────────────────────────────────────────────┤
│                                                   │
│  ┌─────────────┐    ┌──────────────┐             │
│  │  CloudFront │───→│  S3 Bucket   │             │
│  │  + SSL      │    │  (Frontend)  │             │
│  └─────────────┘    └──────────────┘             │
│         ↑                                         │
│         │                                         │
│  ┌──────────────────┐    ┌─────────────────┐    │
│  │  API Gateway /   │───→│  RDS            │    │
│  │  Lambda / EC2    │    │  PostgreSQL     │    │
│  │  (Backend)       │    │  (13GB Database)│    │
│  └──────────────────┘    └─────────────────┘    │
│                                                   │
└─────────────────────────────────────────────────┘
```

## Estimated Costs

After deployment, monthly AWS costs will be approximately:

| Service | Instance Type | Monthly Cost |
|---------|---------------|--------------|
| RDS | db.t3.medium (500GB storage) | $60-80 |
| Lambda | (if used) | $5-20 |
| EC2 | t3.medium (if used) | $25-35 |
| S3 | 15GB storage + transfer | $5-10 |
| CloudFront | ~10GB transfer | $20-30 |
| **Total** | | **$115-175/month** |

💡 **Cost Optimization Tips**:
- Use RDS "db.t3.micro" for testing ($15/month)
- Use spot instances for EC2 (70% discount)
- Enable S3 intelligent-tiering
- Set CloudFront caching aggressively

## What's Ready to Deploy

### Backend
- ✅ Node.js Express server with all routes
- ✅ Database queries optimized
- ✅ All 12 API endpoints tested and working
- ✅ Data loaders prepared

### Frontend
- ✅ React application fully built
- ✅ All 145 industries loading
- ✅ Charts and visualizations working
- ✅ Real-time performance metrics
- ✅ Responsive design

### Data
- ✅ 13GB PostgreSQL database dump
- ✅ All sectors and industries
- ✅ All price data loaded
- ✅ All performance metrics calculated
- ✅ Ready to restore to RDS

## Next Steps

### Option 1: Request Permissions (Recommended)
1. Send the permission request to your AWS admin
2. Wait for approval (usually 1-2 hours)
3. Run the deployment script
4. Verify everything works

### Option 2: Have Admin Deploy
1. Share this guide with your AWS admin
2. Have them run the deployment script
3. They can grant you temporary access to test

### Option 3: Use Different AWS Account
If you have another AWS account with full permissions:
1. Configure AWS CLI: `aws configure`
2. Run the deployment script
3. Share the deployed URLs with your team

## Deployment Checklist

Once you have elevated permissions:

- [ ] Run `bash /home/stocks/algo/deploy-to-aws.sh`
- [ ] Wait for RDS instance to be created (10-15 min)
- [ ] Manually restore database (see guide)
- [ ] Build and deploy frontend (script handles this)
- [ ] Deploy backend to Lambda/EC2
- [ ] Update frontend API URLs to point to backend
- [ ] Test all endpoints
- [ ] Test frontend from CloudFront URL
- [ ] Verify all 145 industries load
- [ ] Check performance metrics display correctly
- [ ] Load and verify sector performance data

## Testing Deployed Application

Once deployed, test these endpoints:

```bash
# Sectors endpoint
curl https://your-api-endpoint/api/sectors/sectors-with-history

# Industries endpoint
curl https://your-api-endpoint/api/sectors/industries-with-history

# Market overview
curl https://your-api-endpoint/api/market/overview
```

Expected results:
- Sectors return with performance data (1D%, 5D%, 20D%)
- All 145 industries load
- Performance values are realistic (-5% to +5% range)
- Timestamps are current

## Support Resources

- **AWS Documentation**: https://docs.aws.amazon.com
- **RDS Setup**: https://docs.aws.amazon.com/rds/latest/UserGuide/USER_CreateDBInstance.html
- **S3 Deployment**: https://docs.aws.amazon.com/AmazonS3/latest/userguide/WebsiteHosting.html
- **CloudFront**: https://docs.aws.amazon.com/cloudfront/latest/developerguide/Introduction.html

## Questions?

Refer to:
1. AWS_DEPLOYMENT_GUIDE.md for detailed steps
2. deploy-to-aws.sh for automated deployment
3. README.md in project root for general setup

---

**Status**: Ready for AWS deployment pending permission approval ⏳
