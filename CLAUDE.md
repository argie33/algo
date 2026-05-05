# Stock Analytics Platform

See `DOCUMENTATION.md` for all guides and references.

---

## AWS Infrastructure Architecture

### Stack Deployment Order (CRITICAL - Must follow this sequence)

```
[1] stocks-oidc (bootstrap)
    ├─ Creates: GitHub OIDC provider, GitHubActionsDeployRole
    ├─ Exports: StocksOidc-WebIdentityProviderArn, GitHubActionsDeployRoleArn
    └─ Deploy: One-time only, manually run .github/workflows/bootstrap-oidc.yml

[2] stocks-core (foundation)
    ├─ Creates: VPC, subnets, bastion, ECR, S3 buckets, VPC endpoints
    ├─ Exports: StocksCore-VpcId, -PublicSubnet1Id, -PublicSubnet2Id
    │           StocksCore-ContainerRepositoryUri, StocksCore-CfTemplatesBucketName
    │           StocksCore-AlgoArtifactsBucketName
    ├─ Imports: None (foundation layer)
    └─ Deploy: .github/workflows/deploy-core.yml

[3] stocks-data (data infrastructure)
    ├─ Creates: RDS PostgreSQL, ECS cluster, Secrets Manager, log groups
    ├─ Exports: StocksApp-DBEndpoint, StocksApp-DBPort, StocksApp-DBName
    │           StocksApp-SecretArn, StocksApp-ClusterArn, StocksApp-EcsTasksSecurityGroupId
    ├─ Imports: StocksCore-VpcId, -PublicSubnet*, -ContainerRepositoryUri
    └─ Deploy: .github/workflows/deploy-data-infrastructure.yml

[4a] stocks-loaders (loader task definitions)
    ├─ Creates: 63 ECS task definitions (data loaders), 4 EventBridge schedule rules
    ├─ Exports: StocksLoaders-StockSymbolsTaskDefArn, -EconDataTaskDefArn, ... (63 total)
    ├─ Imports: StocksCore-ContainerRepositoryUri, StocksApp-DBEndpoint, -SecretArn, -ClusterArn
    └─ Deploy: .github/workflows/deploy-loaders.yml (not yet created)

[4b] stocks-webapp-dev (frontend & API)
    ├─ Creates: Lambda API, API Gateway, CloudFront, Cognito, S3 frontend bucket
    ├─ Exports: ${AWS::StackName}-ApiUrl, -WebsiteURL, -CloudFrontDistributionId
    ├─ Imports: StocksApp-DBEndpoint, -SecretArn
    └─ Deploy: .github/workflows/deploy-webapp.yml

[4c] stocks-algo-dev (trading orchestrator)
    ├─ Creates: Algo Lambda, EventBridge scheduler, SNS alerts
    ├─ Exports: ${AWS::StackName}-LambdaFunctionArn, -ScheduleArn
    ├─ Imports: StocksApp-SecretArn, StocksCore-AlgoArtifactsBucketName
    └─ Deploy: .github/workflows/deploy-algo.yml (not yet created)
```

### Quick Deploy from Fresh AWS Account

**Prerequisites:**
- AWS account with permissions to create CloudFormation stacks, IAM roles, RDS, ECS, Lambda
- GitHub repository with secrets configured: `AWS_ACCOUNT_ID`, `RDS_USERNAME`, `RDS_PASSWORD`, `FRED_API_KEY`, `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`

**Steps:**
```bash
# Step 1: Bootstrap OIDC provider (one-time only)
# Go to Actions → Workflows → bootstrap-oidc.yml → Run workflow
# Wait 2-3 minutes

# Step 2: Deploy foundation
# Run deploy-core.yml manually
# Wait 10-15 minutes for VPC, subnets, ECR, bastion, S3 buckets

# Step 3: Deploy data layer
# Run deploy-data-infrastructure.yml
# Wait 15-20 minutes for RDS, ECS cluster, Secrets Manager

# Step 4: Deploy services (parallel)
# Run deploy-webapp.yml → wait for CloudFront and Lambda (3-5 min)
# Run deploy-loaders.yml → wait for ECS tasks and EventBridge (5-10 min)
# Run deploy-algo.yml → wait for Algo Lambda and scheduler (2-3 min)

# Or: Run deploy-all-infrastructure.yml for fully automated orchestration
```

### CloudFormation Export/Import Chain

All cross-stack dependencies use `!ImportValue` pattern. If a deploy fails with "ResourceExistenceCheck failed":

1. Check the CloudFormation console for the importing stack
2. Look for error: "Template error: instance of Fn::ImportValue references undefined export"
3. Verify the source stack exists and is in `*_COMPLETE` state
4. Re-run the source stack deploy, then retry the dependent stack

**Critical exports by layer:**
- Foundation: `StocksCore-VpcId`, `StocksCore-ContainerRepositoryUri`, `StocksCore-CfTemplatesBucketName`, `StocksCore-AlgoArtifactsBucketName`
- Data: `StocksApp-DBEndpoint`, `StocksApp-SecretArn`, `StocksApp-ClusterArn`
- Services: Each exports `${AWS::StackName}-*` (webapp, algo)

### Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "Stack does not exist" | Previous deploy failed | Check CloudFormation console for failed stack, delete it |
| "ResourceExistenceCheck failed" | Missing export from dependency | Run dependency workflow first (e.g., deploy-core before deploy-webapp) |
| "ModuleNotFoundError: optimal_loader" | ECR image out of date | Re-run deploy-loaders.yml to rebuild image |
| "Stack stuck in ROLLBACK_COMPLETE" | Deployment failed, cleanup incomplete | Delete stack manually in CloudFormation console, retry deploy |
| "Cognito callback URL mismatch" | Placeholder CloudFront domain | Workflow post-deploy step should update automatically |

---
