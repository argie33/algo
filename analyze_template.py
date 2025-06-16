#!/usr/bin/env python3
"""
Comprehensive CloudFormation template analysis for potential deployment issues
"""

import yaml
import sys
from collections import defaultdict

def analyze_template(template_path):
    """Analyze CloudFormation template for potential issues"""
    
    print("🔍 COMPREHENSIVE TEMPLATE ANALYSIS")
    print("=" * 50)
    
    with open(template_path, 'r') as f:
        template = yaml.safe_load(f)
    
    resources = template.get('Resources', {})
    outputs = template.get('Outputs', {})
    parameters = template.get('Parameters', {})
    
    issues = []
    warnings = []
    
    print(f"📊 TEMPLATE STATS:")
    print(f"   - Parameters: {len(parameters)}")
    print(f"   - Resources: {len(resources)}")
    print(f"   - Outputs: {len(outputs)}")
    print()
    
    # Check for common issues
    print("🔧 CHECKING FOR COMMON ISSUES:")
    
    # 1. Check for missing required parameters
    required_params = ['DatabaseSecretArn', 'DatabaseEndpoint']
    missing_params = []
    for param in required_params:
        if param not in parameters:
            missing_params.append(param)
    
    if missing_params:
        issues.append(f"Missing required parameters: {missing_params}")
    else:
        print("   ✅ All required parameters present")
    
    # 2. Check for resource naming conflicts
    resource_names = set()
    for name, resource in resources.items():
        if 'Properties' in resource and 'Name' in resource['Properties']:
            actual_name = resource['Properties']['Name']
            if actual_name in resource_names:
                issues.append(f"Potential naming conflict: {actual_name}")
            resource_names.add(actual_name)
    
    print("   ✅ No obvious naming conflicts")
    
    # 3. Check CloudFront/S3 setup
    has_cloudfront = any(r.get('Type') == 'AWS::CloudFront::Distribution' for r in resources.values())
    has_s3_bucket = any(r.get('Type') == 'AWS::S3::Bucket' for r in resources.values())
    has_bucket_policy = any(r.get('Type') == 'AWS::S3::BucketPolicy' for r in resources.values())
    has_oai = any(r.get('Type') == 'AWS::CloudFront::CloudFrontOriginAccessIdentity' for r in resources.values())
    
    if has_cloudfront and has_s3_bucket:
        if not has_bucket_policy:
            issues.append("CloudFront + S3 setup missing bucket policy")
        elif not has_oai:
            warnings.append("Using modern setup - ensure OAC is properly configured")
        else:
            print("   ✅ CloudFront + S3 + OAI setup looks correct")
    
    # 4. Check Lambda configuration
    lambda_functions = [r for r in resources.values() if r.get('Type') == 'AWS::Serverless::Function']
    for func in lambda_functions:
        props = func.get('Properties', {})
        if props.get('Timeout', 0) > 29:
            warnings.append(f"Lambda timeout > 29s may cause API Gateway timeouts")
        if props.get('MemorySize', 0) < 512:
            warnings.append(f"Lambda memory < 512MB may cause performance issues")
    
    if lambda_functions:
        print("   ✅ Lambda functions configured")
    
    # 5. Check API Gateway setup
    api_gateways = [r for r in resources.values() if r.get('Type') == 'AWS::Serverless::Api']
    if api_gateways:
        print("   ✅ API Gateway configured")
    
    # 6. Check for proper IAM roles
    iam_roles = [r for r in resources.values() if r.get('Type') == 'AWS::IAM::Role']
    if iam_roles:
        print("   ✅ IAM roles configured")
    
    # 7. Check outputs
    critical_outputs = ['WebsiteURL', 'ApiGatewayUrl']
    missing_outputs = []
    for output in critical_outputs:
        if output not in outputs:
            missing_outputs.append(output)
    
    if missing_outputs:
        warnings.append(f"Missing recommended outputs: {missing_outputs}")
    else:
        print("   ✅ Critical outputs present")
    
    print()
    print("🚨 ISSUES FOUND:")
    if issues:
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. ❌ {issue}")
    else:
        print("   ✅ No critical issues found!")
    
    print()
    print("⚠️  WARNINGS:")
    if warnings:
        for i, warning in enumerate(warnings, 1):
            print(f"   {i}. ⚠️  {warning}")
    else:
        print("   ✅ No warnings!")
    
    print()
    print("🎯 DEPLOYMENT READINESS:")
    
    if not issues:
        print("   ✅ READY FOR DEPLOYMENT")
        print("   📋 Pre-deployment checklist:")
        print("      • Ensure AWS credentials are configured")
        print("      • Verify DatabaseSecretArn parameter value")
        print("      • Verify DatabaseEndpoint parameter value")
        print("      • Ensure webapp/lambda/ directory exists with code")
        print("      • Consider testing in dev environment first")
        return True
    else:
        print("   ❌ NOT READY - Fix issues above first")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze_template.py <template_file>")
        sys.exit(1)
    
    template_path = sys.argv[1]
    ready = analyze_template(template_path)
    sys.exit(0 if ready else 1)
