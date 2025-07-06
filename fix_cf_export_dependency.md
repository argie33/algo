# CloudFormation Export Dependency Fix

## Problem
Error: "Cannot update export StocksApp-DBEndpoint as it is in use by stocks-ecs-tasks-stack"

## Root Cause
The `template-app-stocks.yml` exports `StocksApp-DBEndpoint` which is imported by `template-app-ecs-tasks.yml`. CloudFormation prevents changing exports when they're being imported by other stacks.

## Solution Options

### Option 1: Update Both Stacks Together (Recommended)
1. First, update the importing stack to remove the dependency temporarily
2. Then update the exporting stack
3. Finally, update the importing stack again to use the new export

### Option 2: Use Parameters Instead of Exports
Replace the export/import pattern with parameters passed between stacks.

### Option 3: Change Export Name
Create a new export with a different name and gradually migrate.

## Implementation (Option 1)

### Step 1: Modify template-app-ecs-tasks.yml to use parameters
Add parameters section:
```yaml
Parameters:
  DBEndpoint:
    Type: String
    Description: Database endpoint address
  DBPort:
    Type: String
    Description: Database port
  DBName:
    Type: String
    Description: Database name
```

Replace all `!ImportValue StocksApp-DBEndpoint` with `!Ref DBEndpoint`
Replace all `!ImportValue StocksApp-DBPort` with `!Ref DBPort`
Replace all `!ImportValue StocksApp-DBName` with `!Ref DBName`

### Step 2: Update the ECS tasks stack first
```bash
aws cloudformation update-stack \
  --stack-name stocks-ecs-tasks-stack \
  --template-body file://template-app-ecs-tasks.yml \
  --parameters \
    ParameterKey=DBEndpoint,ParameterValue=$(aws cloudformation describe-stacks --stack-name stocks-app-stack --query "Stacks[0].Outputs[?OutputKey=='DBEndpoint'].OutputValue" --output text) \
    ParameterKey=DBPort,ParameterValue=$(aws cloudformation describe-stacks --stack-name stocks-app-stack --query "Stacks[0].Outputs[?OutputKey=='DBPort'].OutputValue" --output text) \
    ParameterKey=DBName,ParameterValue=stocks \
  --capabilities CAPABILITY_IAM
```

### Step 3: Update the app stocks stack (remove exports)
```bash
aws cloudformation update-stack \
  --stack-name stocks-app-stack \
  --template-body file://template-app-stocks.yml \
  --capabilities CAPABILITY_IAM
```

### Step 4: Update ECS tasks stack to use direct references
Optionally, you can now modify the ECS tasks stack to get the values directly via CloudFormation functions instead of parameters.

## Quick Fix Implementation
Run the commands in sequence:
1. Update ECS stack with parameters
2. Update App stack (remove exports)
3. Verify both stacks are working

This will break the circular dependency and allow future updates to proceed normally.