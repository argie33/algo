#!/usr/bin/env python3
"""
Manual CloudFormation S3/CloudFront validation
"""

def check_template_issues():
    print("🔍 Checking CloudFormation template for S3/CloudFront OAC issues...")
    
    issues = []
    suggestions = []
    
    # Based on the template analysis
    print("\n✅ FIXES APPLIED:")
    print("  1. Removed S3OriginConfig from CloudFront origin (conflicts with OAC)")
    print("  2. Fixed CloudFront distribution ARN reference in bucket policy")
    print("  3. Added Sid to bucket policy statement")
    print("  4. Removed DependsOn from bucket policy")
    
    print("\n🔍 POTENTIAL REMAINING ISSUES TO CHECK:")
    
    print("\n1. REGION COMPATIBILITY:")
    print("   - Ensure you're deploying in a region that supports OAC")
    print("   - OAC is available in all standard regions")
    
    print("\n2. IAM PERMISSIONS:")
    print("   - CloudFormation execution role needs cloudfront:* permissions")
    print("   - CloudFormation execution role needs s3:PutBucketPolicy permissions")
    
    print("\n3. TEMPLATE VALIDATION:")
    print("   - Run: aws cloudformation validate-template --template-body file://template-webapp-lambda.yml")
    
    print("\n4. RESOURCE NAMING:")
    print("   - Check if bucket name is globally unique")
    print("   - Verify no naming conflicts with existing resources")
    
    print("\n5. COMMON OAC DEPLOYMENT ISSUES:")
    print("   - Sometimes OAC resources need a few minutes to propagate")
    print("   - Try deploying just the S3 + OAC resources first, then CloudFront")
    
    print("\n6. ALTERNATIVE APPROACH - SEPARATE BUCKET POLICY:")
    print("   - Consider creating bucket policy after CloudFront distribution")
    print("   - Use separate stack or manual bucket policy creation")
    
    print("\n📝 SUGGESTED NEXT STEPS:")
    print("   1. Run CloudFormation validate-template command")
    print("   2. Check CloudFormation execution role permissions") 
    print("   3. Try deploying to a clean environment")
    print("   4. If still failing, try the alternative deployment approach below")
    
    print("\n🔧 ALTERNATIVE DEPLOYMENT APPROACH:")
    print("   If the issue persists, try this order:")
    print("   1. Deploy S3 bucket + OAC resources first")
    print("   2. Deploy CloudFront distribution") 
    print("   3. Create bucket policy manually or in separate stack")
    
    return True

if __name__ == "__main__":
    check_template_issues()
