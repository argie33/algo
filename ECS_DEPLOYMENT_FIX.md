# ECS Deployment Fix: Missing Docker Images

## Problem Summary

The ECS task `technicalsdaily-loader` is failing with:
```
CannotPullContainerError: pull image manifest has been retried 1 time(s): 
failed to resolve ref ***.dkr.ecr.us-east-1.amazonaws.com/stocks-app-registry-***:technicalsdaily-34683c0631c3cffa537e577e707abc79e7c653aa: not found
```

## Root Cause

The GitHub Actions workflow is trying to run an ECS task, but the required Docker image was never built and pushed to ECR. This happens because:

1. **Missing Build Step**: The workflow assumes the Docker image exists in ECR
2. **No Build Pipeline**: There's no automated process to build and push images when code changes
3. **Tag Mismatch**: The expected tag format includes the commit hash, but no build process creates it

## Immediate Solutions

### Option 1: Emergency Fix (Fastest)
```bash
# Run the emergency fix script
./emergency-fix-ecs.sh
```

This creates a minimal working image with the exact tag that's failing.

### Option 2: Proper Build and Push
```bash
# Run the comprehensive fix script
./fix-technicalsdaily-deployment.sh
```

This builds the actual image from the proper Dockerfile and pushes it to ECR.

### Option 3: Manual Build (If you have Docker and AWS CLI)
```bash
# 1. Get ECR login
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# 2. Build image
docker build -f Dockerfile.technicalsdaily -t technicalsdaily-34683c0631c3cffa537e577e707abc79e7c653aa .

# 3. Tag for ECR
docker tag technicalsdaily-34683c0631c3cffa537e577e707abc79e7c653aa ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/stocks-app-registry:technicalsdaily-34683c0631c3cffa537e577e707abc79e7c653aa

# 4. Push to ECR
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/stocks-app-registry:technicalsdaily-34683c0631c3cffa537e577e707abc79e7c653aa
```

## Long-Term Solution

### 1. GitHub Actions Workflow
I've created `.github/workflows/deploy-ecs-tasks.yml` that:
- Automatically builds Docker images when Dockerfiles change
- Pushes images to ECR with proper tagging
- Runs ECS tasks with the newly built images
- Handles cleanup of old images

### 2. CloudFormation Integration
The workflow integrates with your existing CloudFormation templates and:
- Uses existing task definitions
- Overrides container images with newly built ones
- Maintains proper networking and security configurations

### 3. Error Handling
The new workflow includes:
- Proper error handling and logging
- Task completion monitoring
- Cleanup of old images to save storage costs

## Prevention Measures

1. **Always Build Before Deploy**: Never run ECS tasks without ensuring images exist
2. **Automated Builds**: Use the GitHub Actions workflow for consistent builds
3. **Image Tagging**: Use consistent tagging strategy (task-name + commit hash)
4. **ECR Repository Management**: Ensure ECR repositories exist before pushing
5. **Health Checks**: Include container health checks in task definitions

## Testing the Fix

After applying any solution:

1. **Verify Image Exists**:
```bash
aws ecr describe-images --repository-name stocks-app-registry --image-ids imageTag=technicalsdaily-34683c0631c3cffa537e577e707abc79e7c653aa
```

2. **Test ECS Task**:
```bash
aws ecs run-task --cluster stocks-cluster --task-definition technicalsdaily-loader --launch-type FARGATE
```

3. **Check Logs**:
```bash
aws logs filter-log-events --log-group-name "/ecs/technicalsdaily-loader" --start-time $(date -d '1 hour ago' +%s)000
```

## Files Created

- `emergency-fix-ecs.sh` - Quick emergency fix
- `fix-technicalsdaily-deployment.sh` - Comprehensive fix
- `.github/workflows/deploy-ecs-tasks.yml` - Automated build/deploy workflow
- `ECS_DEPLOYMENT_FIX.md` - This documentation

## Next Steps

1. Run one of the fix scripts to resolve the immediate issue
2. Set up the GitHub Actions workflow for future deployments
3. Update your deployment process to always build images first
4. Consider implementing automated testing of containers before deployment

## Related Issues

This same issue could affect other ECS tasks with similar Docker image requirements:
- `pricedaily-loader`
- `buysell-loader`
- `stocksymbols-loader`
- Any other ECS tasks expecting Docker images

The provided solutions work for all these tasks by changing the task name parameter.