# All Remaining CloudFormation & Deployment Issues

## CRITICAL (Deployment Blockers)

### 1. **API Gateway Routes Missing Authorization** (template-webapp.yml)
- **Issue**: All API Gateway routes (/{proxy+} and /) have NO Auth
- **Risk**: Any unauthenticated user can access all endpoints
- **Current**: ApiProxy and ApiRoot defined without Auth property
- **Fix**: Add Cognito authorizer to all routes
  ```yaml
  Properties:
    Auth:
      DefaultAuthorizer: CognitoAuth
      AddApiKeyRequiredHeader: true
  ```

### 2. **EventBridge Rules Missing DeadLetterConfig** (template-algo.yml, template-core.yml)
- **Issue**: If EventBridge rule fails, event is silently dropped
- **Risk**: Silent failures in scheduled tasks (e.g., algo orchestrator doesn't run)
- **Current**: BastionStopRule and EventBridge rules have no DeadLetterConfig
- **Fix**: Add SQS queue as DLQ
  ```yaml
  DeadLetterConfig:
    Arn: !GetAtt EventFailureQueue.Arn
  ```

### 3. **ECS Tasks Using "latest" Image Tag** (template-loader-tasks.yml)
- **Issue**: 10 ECS task definitions use `!Join [":", [!ImportValue, "latest"]]`
- **Risk**: Deployments will pull unpredictable image; same hash can have different code
- **Current**: All loaders using "latest"
- **Fix**: Use commit SHA or version tags
  ```yaml
  Image: !Sub "${ContainerUri}:v1.0.0"  # or git-${GIT_SHA}
  ```

### 4. **Lambda Missing ReservedConcurrentExecutions** (template-core.yml:296 BastionStopFunction)
- **Issue**: BastionStopFunction has no concurrency limit or timeout
- **Risk**: Could throttle or hang when scaling
- **Fix**: Add ReservedConcurrentExecutions and explicit Timeout

### 5. **S3 Buckets Missing Bucket Policies** (template-core.yml, template-data-infrastructure.yml)
- **Issue**: 5 S3 buckets (CodeBucket, CfTemplatesBucket, AlgoArtifactsBucket, DataLoadingBucket, LogArchiveBucket) have no bucket policies
- **Risk**: Could cause access denied or inadvertent public access
- **Fix**: Add BucketPolicy resources with explicit allow/deny

## HIGH PRIORITY (Will Cause Issues)

### 6. **State Machine Without Error Handling** (template-loader-tasks.yml)
- **Issue**: LoaderOrchestrationStateMachine has no Catch/Retry clauses
- **Risk**: If any loader fails, entire orchestration stops without retry
- **Fix**: Add error handling:
  ```yaml
  Catch:
    - ErrorEquals: ["States.ALL"]
      Next: NotifyFailure
  ```

### 7. **Exports Missing Descriptions** (template-core.yml outputs)
- **Issue**: All 20+ outputs in template-core.yml missing Description field
- **Risk**: CloudFormation best practice violation; makes it hard to understand exports
- **Example**: VpcId, PublicSubnet1Id, etc. have no Description
- **Fix**: Add Description to each output

### 8. **Hardcoded Log Group Names** (template-data-infrastructure.yml, template-loader-tasks.yml)
- **Issue**: Log groups use hardcoded names like `/aws/ecs/stock-scores-loader`
- **Risk**: Naming conflicts if multiple stacks deployed; hard to track by stack
- **Fix**: Use stack name in log group names
  ```yaml
  LogGroupName: !Sub '/aws/ecs/${AWS::StackName}-stock-scores'
  ```

### 9. **RDS Database Without Backups** (template-data-infrastructure.yml)
- **Issue**: Added BackupRetentionPeriod: 7 but need to verify it's configured correctly
- **Risk**: No disaster recovery option
- **Note**: ALREADY PARTIALLY FIXED but verify implementation

### 10. **Lambda Permission Missing SourceArn** (template-algo.yml, template-core.yml)
- **Issue**: Lambda permissions have Principal but missing SourceArn
- **Risk**: Any EventBridge/Lambda in account could invoke these functions
- **Current**: Events principals without SourceArn constraint
- **Fix**: Add SourceArn for each trigger

## MEDIUM PRIORITY (Performance/Cost)

### 11. **No Provisioned Concurrency for Burs Workloads** (template-algo.yml)
- **Issue**: Algo orchestrator Lambda can experience cold starts
- **Risk**: First execution of orchestrator has 1-5s delay
- **Current**: ProvisionedConcurrency commented out
- **Fix**: Enable for prod (costs ~$5/month but eliminates cold starts)

### 12. **CloudWatch Logs Not Archived to Glacier** (template-data-infrastructure.yml)
- **Issue**: Logs retained 7 days then deleted; no long-term archive
- **Risk**: Can't audit historical data after 7 days
- **Fix**: Archive to S3 Glacier via Lambda (setup log->S3 pipeline)

### 13. **No VPC Endpoint for RDS-like Outbound** 
- **Issue**: Data loaders must use public internet to reach RDS (should be VPC private)
- **Risk**: Network latency, not following least-privilege
- **Current**: RDS in private subnet but loaders in public network path
- **Fix**: Deploy NAT Gateway for private outbound

### 14. **No CloudWatch Alarms for API Errors** (template-webapp.yml)
- **Issue**: API Lambda has no error rate alarm
- **Risk**: Silent failures; errors not detected until user reports
- **Fix**: Add CloudWatch alarm for Lambda errors > 1%

## LOW PRIORITY (Best Practices)

### 15. **No Environment-Specific Naming** (template-webapp.yml)
- **Issue**: Globals and exports don't consistently use EnvironmentName parameter
- **Risk**: Hard to support multiple environments (dev/staging/prod)
- **Note**: Some resources DO use EnvironmentName, others don't

### 16. **No Input Validation on Parameters** (all templates)
- **Issue**: Parameters like RDSUsername, NotificationEmail not validated
- **Risk**: Invalid input passes through silently
- **Fix**: Add AllowedPattern where applicable

### 17. **SNS Topic Subscription Missing Confirmation Wait** (template-data-infrastructure.yml)
- **Issue**: If AlertTopicArn provided but SNS subscription fails, deployment continues
- **Risk**: Alarms created but notifications never sent
- **Fix**: Add SNS subscription with manual confirmation requirement

### 18. **Auto-Scaling Group Missing Tags** (template-core.yml)
- **Issue**: BastionAutoScalingGroup has tags but doesn't propagate them to EC2 instances properly
- **Risk**: Instances may not have tracking/billing tags
- **Check**: Verify PropagateAtLaunch is set on all ASG tags

---

## Summary by Template

| Template | Issues | Severity |
|----------|--------|----------|
| template-webapp.yml | 1,4,14 | CRITICAL, CRITICAL, MEDIUM |
| template-algo.yml | 2,10 | CRITICAL, MEDIUM |
| template-core.yml | 2,5,7,10,18 | CRITICAL, CRITICAL, HIGH, MEDIUM, LOW |
| template-data-infrastructure.yml | 5,8 | CRITICAL, HIGH |
| template-loader-tasks.yml | 3,6,8 | CRITICAL, HIGH, HIGH |
| template-loader-lambda.yml | 3 | CRITICAL |

