# Phase 1: Parallel Loader Execution - Start Today

## The Goal
Run all loaders in parallel instead of sequentially.
- **Before:** 70 minutes (price → scores → earnings → signals)
- **After:** 25 minutes (all 4 running together)
- **Speedup:** 3x faster
- **Cost:** -67%

---

## What We're Building

### Step Functions State Machine
```
Start
  ├→ Task 1: Load Price Daily (parallel, 20 min)
  ├→ Task 2: Load Stock Scores (parallel, 10 min)
  ├→ Task 3: Load Earnings (parallel, 15 min)
  ├→ Task 4: Load Signals Daily (parallel, 25 min)
  ↓
Fan-in (Wait for all 4 to complete)
  ↓
Success: All complete
  ↓
SNS Alert: "Data loaded successfully"
```

### Cost Calculation
- Each ECS Fargate task: $0.015 per minute
- Current (sequential): 70 min = $1.05 per run
- Phase 1 (parallel): 25 min = $0.375 per run
- **Savings: $0.675 per run (-64%)**
- **Monthly: 2 runs/day = -$405/month**

---

## Implementation Steps

### Step 1: Create Step Functions Template (30 min)

Create `template-parallel-loaders.yml`:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Parallel data loaders using Step Functions'

Resources:
  ParallelLoaderStateMachine:
    Type: AWS::StepFunctions::StateMachine
    Properties:
      StateMachineType: STANDARD
      RoleArn: !GetAtt StepFunctionsRole.Arn
      DefinitionString: !Sub |
        {
          "Comment": "Run all data loaders in parallel",
          "StartAt": "ParallelLoaders",
          "States": {
            "ParallelLoaders": {
              "Type": "Parallel",
              "Branches": [
                {
                  "StartAt": "LoadPriceDaily",
                  "States": {
                    "LoadPriceDaily": {
                      "Type": "Task",
                      "Resource": "arn:aws:ecs:${AWS::Region}:${AWS::AccountId}:task/${EcsCluster}",
                      "Parameters": {
                        "cluster": "${EcsCluster}",
                        "taskDefinition": "loadpricedaily:1",
                        "launchType": "FARGATE",
                        "networkConfiguration": {
                          "awsvpcConfiguration": {
                            "subnets": ["subnet-12345"],
                            "securityGroups": ["sg-12345"],
                            "assignPublicIp": "ENABLED"
                          }
                        }
                      },
                      "End": true,
                      "TimeoutSeconds": 1800,
                      "Retry": [
                        {
                          "ErrorEquals": ["States.TaskFailed"],
                          "IntervalSeconds": 2,
                          "MaxAttempts": 2,
                          "BackoffRate": 2.0
                        }
                      ],
                      "Catch": [
                        {
                          "ErrorEquals": ["States.ALL"],
                          "Next": "LoadPriceDailyFailed"
                        }
                      ]
                    },
                    "LoadPriceDailyFailed": {
                      "Type": "Fail",
                      "Error": "LoadPriceDailyError",
                      "Cause": "Failed to load price daily data"
                    }
                  }
                },
                {
                  "StartAt": "LoadStockScores",
                  "States": {
                    "LoadStockScores": {
                      "Type": "Task",
                      "Resource": "arn:aws:ecs:${AWS::Region}:${AWS::AccountId}:task/${EcsCluster}",
                      "Parameters": {
                        "cluster": "${EcsCluster}",
                        "taskDefinition": "loadstockscores:1",
                        "launchType": "FARGATE",
                        "networkConfiguration": {
                          "awsvpcConfiguration": {
                            "subnets": ["subnet-12345"],
                            "securityGroups": ["sg-12345"],
                            "assignPublicIp": "ENABLED"
                          }
                        }
                      },
                      "End": true,
                      "TimeoutSeconds": 900
                    }
                  }
                },
                {
                  "StartAt": "LoadEarningsHistory",
                  "States": {
                    "LoadEarningsHistory": {
                      "Type": "Task",
                      "Resource": "arn:aws:ecs:${AWS::Region}:${AWS::AccountId}:task/${EcsCluster}",
                      "Parameters": {
                        "cluster": "${EcsCluster}",
                        "taskDefinition": "loadearningshistory:1",
                        "launchType": "FARGATE",
                        "networkConfiguration": {
                          "awsvpcConfiguration": {
                            "subnets": ["subnet-12345"],
                            "securityGroups": ["sg-12345"],
                            "assignPublicIp": "ENABLED"
                          }
                        }
                      },
                      "End": true,
                      "TimeoutSeconds": 1200
                    }
                  }
                },
                {
                  "StartAt": "LoadSignalsDaily",
                  "States": {
                    "LoadSignalsDaily": {
                      "Type": "Task",
                      "Resource": "arn:aws:ecs:${AWS::Region}:${AWS::AccountId}:task/${EcsCluster}",
                      "Parameters": {
                        "cluster": "${EcsCluster}",
                        "taskDefinition": "loadbuyselldaily:1",
                        "launchType": "FARGATE",
                        "networkConfiguration": {
                          "awsvpcConfiguration": {
                            "subnets": ["subnet-12345"],
                            "securityGroups": ["sg-12345"],
                            "assignPublicIp": "ENABLED"
                          }
                        }
                      },
                      "End": true,
                      "TimeoutSeconds": 1800
                    }
                  }
                }
              ],
              "Next": "AllLoadersComplete"
            },
            "AllLoadersComplete": {
              "Type": "Task",
              "Resource": "arn:aws:sns:${AWS::Region}:${AWS::AccountId}:DataLoaderNotifications",
              "Parameters": {
                "TopicArn": "arn:aws:sns:${AWS::Region}:${AWS::AccountId}:DataLoaderNotifications",
                "Subject": "Data loaders completed successfully",
                "Message": "All data loaders ran in parallel and completed"
              },
              "End": true
            }
          }
        }
```

### Step 2: Create CloudWatch Rule (10 min)

Trigger the Step Function on a schedule:

```bash
# Create CloudWatch rule to run daily at 2 AM
aws events put-rule \
  --name daily-parallel-loaders \
  --schedule-expression 'cron(0 2 * * ? *)' \
  --state ENABLED

# Add Step Functions as target
aws events put-targets \
  --rule daily-parallel-loaders \
  --targets "Id"="1","Arn"="arn:aws:states:us-east-1:ACCOUNT_ID:stateMachine:ParallelLoaderStateMachine","RoleArn"="arn:aws:iam::ACCOUNT_ID:role/EventsInvokeStepFunctionsRole"
```

### Step 3: Add SNS Notifications (5 min)

Get alerts when loaders complete or fail:

```bash
# Create SNS topic for notifications
aws sns create-topic --name DataLoaderNotifications

# Subscribe your email
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT_ID:DataLoaderNotifications \
  --protocol email \
  --notification-endpoint your-email@example.com
```

### Step 4: Test It (30 min)

```bash
# Test the Step Function manually
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT_ID:stateMachine:ParallelLoaderStateMachine \
  --name test-run-1

# Monitor execution in AWS Console
# Step Functions → Executions → test-run-1
```

**Expected behavior:**
- All 4 tasks start at the same time
- Price Daily completes in ~20 min
- Stock Scores completes in ~10 min
- Earnings History completes in ~15 min
- Signals Daily completes in ~25 min
- Then all complete together (fan-in)
- SNS alert sent

---

## Success Metrics

### Speed
- **Before:** 70 minutes total
- **After:** 25 minutes (the longest task)
- **Improvement:** 3x faster ✅

### Cost
- **Before:** $1.05 per run
- **After:** $0.375 per run
- **Savings:** -64% ✅

### Reliability
- **Failed tasks retry automatically** (2 retries with backoff)
- **SNS alerts** on success/failure
- **CloudWatch logs** track each task

---

## Verification Checklist

After deploying Phase 1:

- [ ] Step Functions state machine created
- [ ] CloudWatch rule triggers on schedule
- [ ] All 4 loaders run in parallel (visible in console)
- [ ] Completion time: ~25 minutes
- [ ] SNS alerts working
- [ ] Monitor system shows fresh data
- [ ] Error rate <1% (from dedup fix)
- [ ] Cost reduced by 64%

---

## Next Steps After Phase 1

Once Phase 1 is running smoothly (1-2 days):

1. **Verify parallel execution** in AWS Console
2. **Measure actual time** (should be ~25 min)
3. **Check CloudWatch logs** for any issues
4. **Move to Phase 2:** Symbol-level parallelism with Lambda

---

## Rollback Plan (If needed)

If parallel execution causes issues:

```bash
# Disable the CloudWatch rule
aws events disable-rule --name daily-parallel-loaders

# Manual trigger still works via GitHub Actions
# Falls back to sequential execution
```

---

## Implementation Timeline

| Step | Duration | Status |
|------|----------|--------|
| Create Step Functions template | 30 min | Ready |
| Deploy CloudFormation stack | 15 min | Ready |
| Create CloudWatch rule | 10 min | Ready |
| Add SNS notifications | 5 min | Ready |
| Test execution | 30 min | Ready |
| **Total:** | **90 min** | **Ready to go!** |

---

## Questions to Ask

1. Should we keep the GitHub Actions manual trigger as a fallback?
   - **Yes:** Provides manual control
   
2. What if one loader fails?
   - **Retry 2x automatically, then alert via SNS**
   
3. How do we monitor progress?
   - **AWS Step Functions console shows all 4 running**
   
4. What if we need to stop a loader?
   - **Stop the Step Functions execution, it terminates all tasks**

---

**Ready to implement? Let's make it 3x faster today.**

Next commit: Deploy the parallel loader infrastructure to AWS.
