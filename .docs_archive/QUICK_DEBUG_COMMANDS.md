# Quick Debug Commands - Copy & Paste for Fast Issue Resolution

**When something breaks, run these commands to diagnose the problem in seconds.**

## Immediate Actions

### 1. Get the Error
```bash
# Copy FULL error from GitHub Actions workflow logs
# Include: Error type, resource name, full stack trace
```

### 2. Check AWS Credentials
```bash
aws sts get-caller-identity
# Should show:
# - Account: 626216981288
# - User: reader (or your user)
# If fails: credentials are wrong/expired
```

### 3. List What Exists in AWS
```bash
# VPCs
aws ec2 describe-vpcs --region us-east-1 --query 'Vpcs[?Tags[?Key==`ManagedBy` && Value==`terraform`]].{Id:VpcId,CIDR:CidrBlock}'

# RDS
aws rds describe-db-instances --region us-east-1 --query 'DBInstances[?contains(DBInstanceIdentifier, `stocks`)].{Id:DBInstanceIdentifier,Status:DBInstanceStatus}'

# ECS
aws ecs describe-clusters --region us-east-1 --query 'clusters[*].{Name:clusterName,Status:status}'

# ECR
aws ecr describe-repositories --region us-east-1 --query 'repositories[*].repositoryName'

# S3
aws s3 ls | grep stocks

# Secrets Manager
aws secretsmanager list-secrets --region us-east-1 --query 'SecretList[*].Name'
```

### 4. Check Terraform State
```bash
cd terraform

# What does terraform think exists?
terraform state list | grep -i "vpc\|rds\|ecs"

# Full details on one resource
terraform state show aws_vpc.main

# Refresh state with AWS reality
terraform refresh
```

---

## Issue Categories & Commands

### "Resource doesn't exist" Error

```bash
# Is it really missing?
aws ec2 describe-vpcs --region us-east-1 --query 'Vpcs[*].VpcId' | grep vpc-12345678

# If found, import it
terraform import aws_vpc.main vpc-12345678

# If not found, delete from state
terraform state rm aws_vpc.main
```

### "Resource already exists" Error

```bash
# Find it in AWS
aws ec2 describe-vpcs --region us-east-1 --query 'Vpcs' | grep 10.0.0.0/16

# Check what's in state
terraform state list | grep vpc
terraform state show aws_vpc.main

# Option 1: Delete in AWS Console, retry
# Option 2: Import into state
terraform import aws_vpc.main vpc-xxxxxxxxx

# Option 3: Remove from state and recreate
terraform state rm aws_vpc.main
terraform apply -target=aws_vpc.main
```

### "Access Denied" / "Not Authorized" Error

```bash
# What action failed? (look in error message)
# Example: User not authorized to perform: ec2:CreateVpc

# Check current IAM user
aws iam get-user

# Check inline policies
aws iam list-user-policies --user-name YOUR_USER

# Check attached policies
aws iam list-attached-user-policies --user-name YOUR_USER

# View specific policy
aws iam get-user-policy --user-name YOUR_USER --policy-name POLICY_NAME

# SOLUTION: Add missing action to IAM policy
# Or: Use different IAM user with broader permissions
```

### "Module reference failed" Error

```bash
# Which module referenced what?
grep -n "module.XXX\[0\].YYY" terraform/main.tf

# Does the output exist?
grep -n "output \"YYY\"" terraform/modules/XXX/outputs.tf

# Does the variable exist?
grep -n "variable \"YYY\"" terraform/modules/XXX/variables.tf

# Check the type matches
grep -A2 "variable \"YYY\"" terraform/modules/XXX/variables.tf
```

### "Timeout" / "Slow Deployment" Error

```bash
# Check if RDS is creating (takes 15+ minutes)
aws rds describe-db-instances --region us-east-1 --query 'DBInstances[*].[DBInstanceIdentifier, DBInstanceStatus]'
# Status will be: creating → available

# Don't interrupt. It's working. Check in 10 minutes.

# If truly stuck for 30+ minutes:
aws rds delete-db-instance --db-instance-identifier stocks-db --skip-final-snapshot --region us-east-1
# Then retry terraform apply
```

### "Variable type mismatch" Error

```bash
# What type was expected?
grep -A1 "variable \"db_password\"" terraform/modules/data_infrastructure/variables.tf

# What type is being passed?
grep "TF_VAR_db_password" .github/workflows/deploy-terraform.yml

# If secrets, they're always strings. If numbers, use tonumber()
```

---

## Module Debugging

### Bootstrap Module Issues

```bash
# Did OIDC provider get created?
aws iam list-open-id-connect-providers

# Did role get created?
aws iam get-role --role-name stocks-github-actions-deploy

# Check role's assume policy
aws iam get-role-policy --role-name stocks-github-actions-deploy --policy-name ???
# (policy name varies)
```

### Core Module Issues

```bash
# VPC
aws ec2 describe-vpcs --region us-east-1 --query 'Vpcs[?Tags[?Value==`stocks-vpc`]]'

# Subnets
aws ec2 describe-subnets --region us-east-1 --query 'Subnets[?Tags[?Value==`stocks-*`]]'

# Security Groups
aws ec2 describe-security-groups --region us-east-1 --query 'SecurityGroups[?Tags[?Value==`stocks-*`]]'

# S3 Buckets
aws s3 ls | grep "stocks-\|algo-"

# ECR
aws ecr describe-repositories --region us-east-1
```

### Data Infrastructure Issues

```bash
# RDS Instance
aws rds describe-db-instances --region us-east-1 --db-instance-identifier stocks-db

# RDS Secrets
aws secretsmanager get-secret-value --secret-id stocks-db-secret --region us-east-1

# ECS Cluster
aws ecs describe-clusters --region us-east-1 --clusters stocks-cluster

# CloudWatch Alarms
aws cloudwatch describe-alarms --region us-east-1 --alarm-name-prefix stocks
```

---

## State Management Commands

### If You Need to Reset

```bash
# Backup current state
cp terraform.tfstate terraform.tfstate.backup

# See what Terraform thinks exists
terraform state list

# See what AWS actually has
aws ec2 describe-instances --region us-east-1
aws ec2 describe-vpcs --region us-east-1
aws rds describe-db-instances --region us-east-1

# Sync state with reality
terraform refresh

# Remove something from state (without deleting from AWS)
terraform state rm aws_vpc.main

# Remove a whole module's state
terraform state rm 'module.core'

# Restore from backup if you messed up
cp terraform.tfstate.backup terraform.tfstate
terraform refresh
```

---

## Emergency Commands

### Complete Reset (Nuclear Option)

```bash
# Destroy everything
terraform destroy -auto-approve

# Wait for RDS deletion (takes 5-10 minutes)
# Check:
aws rds describe-db-instances --region us-east-1 | grep stocks

# Once RDS gone, delete VPC
aws ec2 delete-vpc --vpc-id vpc-xxxxxxxx --region us-east-1

# Then re-deploy
terraform init
terraform apply
```

### Force Update Module

```bash
# If one module is stuck, just update it
terraform apply -target=module.data_infrastructure

# Or redeploy from scratch
terraform destroy -target=module.core
terraform apply -target=module.core
```

---

## Git/Push Recovery

### If Workflow Keeps Failing

```bash
# View last N commits
git log --oneline -10

# Revert last commit
git revert HEAD

# Or: Reset to specific commit (DESTRUCTIVE)
git reset --hard abc123def

# Push fix
git push origin main

# Workflow re-runs automatically
```

---

## Validation Commands

### Before Pushing

```bash
cd terraform

# Syntax check
terraform validate

# Format check
terraform fmt -recursive

# Dry run (plan)
terraform plan -out=tfplan

# See what will be created
terraform show tfplan
```

---

## Info Gathering

### For Debugging Reports

```bash
# AWS Info
aws sts get-caller-identity
aws ec2 describe-regions --region-names us-east-1 --query 'Regions[*].[RegionName, Endpoint]'

# Terraform Info
terraform version
terraform state list | wc -l

# GitHub Secrets Check (lists names only, not values)
gh secret list --repo argeropolos/algo

# Recent Commits
git log --oneline -5

# Uncommitted Changes
git status
git diff terraform/
```

---

## One-Liners for Common Issues

```bash
# "Can't find VPC"
aws ec2 describe-vpcs --region us-east-1 --query 'Vpcs' | grep stocks

# "RDS not created yet"
aws rds describe-db-instances --region us-east-1 | grep stocks-db -A5

# "Security group missing"
aws ec2 describe-security-groups --region us-east-1 | grep stocks

# "Secrets Manager empty"
aws secretsmanager list-secrets --region us-east-1

# "ECR repo not found"
aws ecr describe-repositories --region us-east-1 | grep stocks

# "Module reference broken"
grep "module\.\w*\[0\]\.\w*" terraform/main.tf

# "Variable not defined"
grep "var\.\w*" terraform/modules/*/main.tf | grep -v "variable \"" terraform/modules/*/variables.tf

# "Terraform state corrupt"
terraform state list | wc -l  # Count resources in state
```

---

## When to Use Each Command

| Symptom | Command | What It Shows |
|---------|---------|---------------|
| "VPC not found" | `aws ec2 describe-vpcs` | Whether VPC exists in AWS |
| "Error in state" | `terraform state list` | What Terraform thinks exists |
| "Permission denied" | `aws iam get-user-policy` | IAM permissions |
| "Resource already exists" | `aws ec2 describe-vpcs ... grep CIDR` | If resource is truly there |
| "Module ref failed" | `grep "module\.X\[0\]\.Y"` | If reference syntax is right |
| "Slow deployment" | `aws rds describe-db-instances` | If RDS is still creating |
| "Secrets missing" | `aws secretsmanager list-secrets` | If Secrets Manager has it |
| "Everything broken" | `terraform destroy -auto-approve` | Full reset |

---

## Template: Debugging Report

When something breaks, gather:

```bash
# 1. Error message (copy from GitHub Actions logs)
# 2. AWS state
aws ec2 describe-vpcs --region us-east-1
aws rds describe-db-instances --region us-east-1
aws ecs describe-clusters --region us-east-1

# 3. Terraform state
cd terraform
terraform state list

# 4. Module reference check
grep "module\." terraform/main.tf | head -5

# 5. Recent commits
git log --oneline -3

# Share all this with the debugging team
```

---

**Last Updated:** 2026-05-06
**Use When:** Something breaks
**Time to Diagnosis:** < 2 minutes with these commands
