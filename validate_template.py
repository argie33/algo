#!/usr/bin/env python3
"""
CloudFormation Template Validator for S3/CloudFront OAC Setup
This script validates the template for common issues that cause deployment failures.
"""

import yaml
import json
import sys
import re
from typing import Dict, List, Any

def validate_template(template_path: str) -> List[str]:
    """Validate CloudFormation template for common issues."""
    issues = []
    
    try:
        with open(template_path, 'r') as f:
            template = yaml.safe_load(f)
    except Exception as e:
        issues.append(f"Failed to parse template: {e}")
        return issues
    
    resources = template.get('Resources', {})
    
    # Check for CloudFront distribution
    cf_dist = None
    for name, resource in resources.items():
        if resource.get('Type') == 'AWS::CloudFront::Distribution':
            cf_dist = name
            break
    
    if not cf_dist:
        issues.append("No CloudFront distribution found")
        return issues
    
    # Check CloudFront distribution configuration
    cf_config = resources[cf_dist].get('Properties', {}).get('DistributionConfig', {})
    origins = cf_config.get('Origins', [])
    
    s3_origin = None
    for origin in origins:
        if 'OriginAccessControlId' in origin:
            s3_origin = origin
            break
    
    if not s3_origin:
        issues.append("No S3 origin with OriginAccessControlId found in CloudFront distribution")
    
    # Check for S3OriginConfig (should not exist with OAC)
    for origin in origins:
        if 'S3OriginConfig' in origin:
            issues.append("S3OriginConfig found in origin - this conflicts with OAC setup")
    
    # Check for Origin Access Control resource
    oac_resource = None
    for name, resource in resources.items():
        if resource.get('Type') == 'AWS::CloudFront::OriginAccessControl':
            oac_resource = name
            break
    
    if not oac_resource:
        issues.append("No Origin Access Control resource found")
    
    # Check S3 bucket policy
    bucket_policy = None
    for name, resource in resources.items():
        if resource.get('Type') == 'AWS::S3::BucketPolicy':
            bucket_policy = resource
            break
    
    if bucket_policy:
        policy_doc = bucket_policy.get('Properties', {}).get('PolicyDocument', {})
        statements = policy_doc.get('Statement', [])
        
        for stmt in statements:
            # Check for correct principal
            principal = stmt.get('Principal', {})
            if principal.get('Service') != 'cloudfront.amazonaws.com':
                issues.append("S3 bucket policy should have Principal.Service: cloudfront.amazonaws.com")
            
            # Check for condition
            condition = stmt.get('Condition', {})
            if 'StringEquals' not in condition:
                issues.append("S3 bucket policy should have StringEquals condition")
            else:
                string_equals = condition['StringEquals']
                if 'AWS:SourceArn' not in string_equals:
                    issues.append("S3 bucket policy should have AWS:SourceArn in StringEquals condition")
    else:
        issues.append("No S3 bucket policy found")
    
    # Check for circular dependencies
    depends_on = {}
    for name, resource in resources.items():
        deps = resource.get('DependsOn', [])
        if isinstance(deps, str):
            deps = [deps]
        depends_on[name] = deps
    
    # Simple circular dependency check
    def has_circular_dep(resource, visited, path):
        if resource in visited:
            return resource in path
        visited.add(resource)
        path.append(resource)
        
        for dep in depends_on.get(resource, []):
            if has_circular_dep(dep, visited, path):
                return True
        
        path.pop()
        return False
    
    for resource in depends_on:
        if has_circular_dep(resource, set(), []):
            issues.append(f"Circular dependency detected involving {resource}")
    
    return issues

def main():
    if len(sys.argv) != 2:
        print("Usage: python validate_template.py <template_file>")
        sys.exit(1)
    
    template_path = sys.argv[1]
    issues = validate_template(template_path)
    
    if issues:
        print("❌ Template validation issues found:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        sys.exit(1)
    else:
        print("✅ Template validation passed")
        sys.exit(0)

if __name__ == "__main__":
    main()
