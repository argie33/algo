#!/usr/bin/env python3
"""
Local CloudFormation Template Validator
Validates templates locally without AWS API calls for maximum speed
"""

import json
import yaml
import sys
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

class LocalTemplateValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
    
    def validate_template_file(self, template_path: str) -> Dict:
        """Main validation function"""
        print(f"🔍 Local validation: {template_path}")
        
        self.errors = []
        self.warnings = []
        self.info = []
        
        # 1. File format validation
        template = self._load_template(template_path)
        if not template:
            return self._create_result(False)
        
        # 2. Structure validation
        self._validate_structure(template)
        
        # 3. Resource validation
        self._validate_resources(template)
        
        # 4. Parameter validation
        self._validate_parameters(template)
        
        # 5. Output validation
        self._validate_outputs(template)
        
        # 6. Reference validation
        self._validate_references(template)
        
        # 7. Best practices
        self._check_best_practices(template)
        
        return self._create_result(len(self.errors) == 0)
    
    def _load_template(self, template_path: str) -> Dict:
        """Load and parse template file"""
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Try JSON first
            if template_path.endswith('.json'):
                template = json.loads(content)
                self.info.append("✅ Valid JSON format")
            else:
                # Try YAML
                template = yaml.safe_load(content)
                self.info.append("✅ Valid YAML format")
            
            return template
            
        except json.JSONDecodeError as e:
            self.errors.append(f"❌ JSON parsing error: {str(e)}")
            return None
        except yaml.YAMLError as e:
            self.errors.append(f"❌ YAML parsing error: {str(e)}")
            return None
        except FileNotFoundError:
            self.errors.append(f"❌ Template file not found: {template_path}")
            return None
        except Exception as e:
            self.errors.append(f"❌ File reading error: {str(e)}")
            return None
    
    def _validate_structure(self, template: Dict):
        """Validate basic CloudFormation structure"""
        required_keys = ['Resources']
        optional_keys = ['AWSTemplateFormatVersion', 'Description', 'Parameters', 
                        'Mappings', 'Conditions', 'Outputs', 'Transform', 'Metadata']
        
        # Check required sections
        for key in required_keys:
            if key not in template:
                self.errors.append(f"❌ Missing required section: {key}")
        
        # Check for unknown top-level keys
        valid_keys = required_keys + optional_keys
        for key in template.keys():
            if key not in valid_keys:
                self.warnings.append(f"⚠️  Unknown top-level key: {key}")
        
        # Validate version
        if 'AWSTemplateFormatVersion' in template:
            version = template['AWSTemplateFormatVersion']
            if version != '2010-09-09':
                self.warnings.append(f"⚠️  Unusual template version: {version}")
        
        self.info.append(f"✅ Template structure valid")
    
    def _validate_resources(self, template: Dict):
        """Validate resources section"""
        resources = template.get('Resources', {})
        
        if not resources:
            self.errors.append("❌ No resources defined")
            return
        
        resource_types = set()
        logical_ids = set()
        
        for logical_id, resource in resources.items():
            logical_ids.add(logical_id)
            
            # Validate resource structure
            if not isinstance(resource, dict):
                self.errors.append(f"❌ Resource {logical_id} is not a dictionary")
                continue
            
            # Check required properties
            if 'Type' not in resource:
                self.errors.append(f"❌ Resource {logical_id} missing Type")
                continue
            
            resource_type = resource['Type']
            resource_types.add(resource_type)
            
            # Validate resource type format
            if not re.match(r'^[A-Za-z0-9]+::[A-Za-z0-9]+::[A-Za-z0-9]+$', resource_type):
                self.warnings.append(f"⚠️  Resource {logical_id} has unusual type format: {resource_type}")
            
            # Check for common issues
            properties = resource.get('Properties', {})
            
            # S3 bucket validation
            if resource_type == 'AWS::S3::Bucket':
                self._validate_s3_bucket(logical_id, properties)
            
            # CloudFront validation
            elif resource_type == 'AWS::CloudFront::Distribution':
                self._validate_cloudfront(logical_id, properties)
                self.warnings.append(f"⚠️  {logical_id}: CloudFront deployment takes 10-15 minutes")
            
            # Lambda validation
            elif resource_type == 'AWS::Lambda::Function':
                self._validate_lambda(logical_id, properties)
            
            # API Gateway validation
            elif resource_type == 'AWS::ApiGateway::RestApi':
                self._validate_api_gateway(logical_id, properties)
        
        self.info.append(f"✅ {len(resources)} resources validated")
        self.info.append(f"📊 Resource types: {len(resource_types)}")
        
        # Check for potential naming conflicts
        self._check_naming_conflicts(logical_ids)
    
    def _validate_s3_bucket(self, logical_id: str, properties: Dict):
        """Validate S3 bucket specific properties"""
        if 'BucketName' in properties:
            bucket_name = properties['BucketName']
            if isinstance(bucket_name, str):
                # Check bucket naming rules
                if not re.match(r'^[a-z0-9.\-]+$', bucket_name):
                    self.errors.append(f"❌ {logical_id}: Invalid bucket name format")
                elif len(bucket_name) < 3 or len(bucket_name) > 63:
                    self.errors.append(f"❌ {logical_id}: Bucket name length must be 3-63 characters")
        
        # Check for public access
        public_access = properties.get('PublicAccessBlockConfiguration')
        if not public_access:
            self.warnings.append(f"⚠️  {logical_id}: No PublicAccessBlockConfiguration specified")
    
    def _validate_cloudfront(self, logical_id: str, properties: Dict):
        """Validate CloudFront distribution"""
        dist_config = properties.get('DistributionConfig', {})
        
        if 'Origins' not in dist_config:
            self.errors.append(f"❌ {logical_id}: Missing Origins in DistributionConfig")
        
        if 'DefaultCacheBehavior' not in dist_config:
            self.errors.append(f"❌ {logical_id}: Missing DefaultCacheBehavior")
        
        # Check for common performance settings
        default_behavior = dist_config.get('DefaultCacheBehavior', {})
        if 'ViewerProtocolPolicy' not in default_behavior:
            self.warnings.append(f"⚠️  {logical_id}: ViewerProtocolPolicy not specified")
    
    def _validate_lambda(self, logical_id: str, properties: Dict):
        """Validate Lambda function"""
        if 'Runtime' not in properties:
            self.errors.append(f"❌ {logical_id}: Missing Runtime")
        
        if 'Handler' not in properties:
            self.errors.append(f"❌ {logical_id}: Missing Handler")
        
        if 'Code' not in properties:
            self.errors.append(f"❌ {logical_id}: Missing Code")
        
        # Check runtime deprecation
        runtime = properties.get('Runtime', '')
        deprecated_runtimes = ['python3.6', 'python3.7', 'nodejs12.x', 'nodejs14.x']
        if runtime in deprecated_runtimes:
            self.warnings.append(f"⚠️  {logical_id}: Runtime {runtime} is deprecated")
    
    def _validate_api_gateway(self, logical_id: str, properties: Dict):
        """Validate API Gateway"""
        if 'Name' in properties:
            # Check for logging configuration
            if 'Description' not in properties:
                self.warnings.append(f"⚠️  {logical_id}: Consider adding Description")
    
    def _validate_parameters(self, template: Dict):
        """Validate parameters section"""
        parameters = template.get('Parameters', {})
        
        if not parameters:
            self.info.append("ℹ️  No parameters defined")
            return
        
        for param_name, param_def in parameters.items():
            if 'Type' not in param_def:
                self.errors.append(f"❌ Parameter {param_name}: Missing Type")
            
            # Check for default values on sensitive parameters
            param_type = param_def.get('Type', '')
            if 'NoEcho' in param_def and param_def['NoEcho'] and 'Default' in param_def:
                self.warnings.append(f"⚠️  Parameter {param_name}: NoEcho parameter has default value")
        
        self.info.append(f"✅ {len(parameters)} parameters validated")
    
    def _validate_outputs(self, template: Dict):
        """Validate outputs section"""
        outputs = template.get('Outputs', {})
        
        if not outputs:
            self.warnings.append("⚠️  No outputs defined - consider adding key outputs")
            return
        
        for output_name, output_def in outputs.items():
            if 'Value' not in output_def:
                self.errors.append(f"❌ Output {output_name}: Missing Value")
            
            if 'Description' not in output_def:
                self.warnings.append(f"⚠️  Output {output_name}: Missing Description")
        
        self.info.append(f"✅ {len(outputs)} outputs validated")
    
    def _validate_references(self, template: Dict):
        """Validate Ref and GetAtt references"""
        resources = template.get('Resources', {})
        parameters = template.get('Parameters', {})
        
        # Find all references in the template
        template_str = json.dumps(template)
        
        # Find Ref functions
        ref_pattern = r'"Ref":\s*"([^"]+)"'
        refs = re.findall(ref_pattern, template_str)
        
        # Find GetAtt functions
        getatt_pattern = r'"Fn::GetAtt":\s*\[\s*"([^"]+)"'
        getatts = re.findall(getatt_pattern, template_str)
        
        # Also check for !Ref and !GetAtt in YAML
        ref_yaml_pattern = r'!Ref\s+(\w+)'
        getatt_yaml_pattern = r'!GetAtt\s+(\w+)'
        refs.extend(re.findall(ref_yaml_pattern, template_str))
        getatts.extend(re.findall(getatt_yaml_pattern, template_str))
        
        # Validate references
        valid_refs = set(resources.keys()) | set(parameters.keys()) | {'AWS::Region', 'AWS::AccountId', 'AWS::StackName'}
        
        invalid_refs = []
        for ref in refs:
            if ref not in valid_refs:
                invalid_refs.append(ref)
        
        invalid_getatts = []
        for getatt in getatts:
            if getatt not in resources:
                invalid_getatts.append(getatt)
        
        if invalid_refs:
            for ref in invalid_refs:
                self.errors.append(f"❌ Invalid Ref: {ref}")
        
        if invalid_getatts:
            for getatt in invalid_getatts:
                self.errors.append(f"❌ Invalid GetAtt: {getatt}")
        
        if not invalid_refs and not invalid_getatts:
            self.info.append("✅ All references valid")
    
    def _check_best_practices(self, template: Dict):
        """Check CloudFormation best practices"""
        # Check for hardcoded values
        template_str = json.dumps(template)
        
        # Look for hardcoded account IDs
        account_pattern = r'\b\d{12}\b'
        if re.search(account_pattern, template_str):
            self.warnings.append("⚠️  Possible hardcoded AWS Account ID detected")
        
        # Check for tags
        resources = template.get('Resources', {})
        untagged_resources = []
        
        for logical_id, resource in resources.items():
            resource_type = resource.get('Type', '')
            properties = resource.get('Properties', {})
            
            # Resources that should be tagged
            taggable_types = [
                'AWS::S3::Bucket',
                'AWS::Lambda::Function',
                'AWS::ApiGateway::RestApi',
                'AWS::EC2::Instance',
                'AWS::RDS::DBInstance'
            ]
            
            if resource_type in taggable_types and 'Tags' not in properties:
                untagged_resources.append(logical_id)
        
        if untagged_resources:
            self.warnings.append(f"⚠️  Untagged resources: {', '.join(untagged_resources[:3])}")
        
        # Check for description
        if 'Description' not in template:
            self.warnings.append("⚠️  Template missing Description")
        
        # Check resource count
        resource_count = len(resources)
        if resource_count > 200:
            self.warnings.append(f"⚠️  Large template with {resource_count} resources - consider splitting")
    
    def _check_naming_conflicts(self, logical_ids: Set[str]):
        """Check for potential naming conflicts"""
        # Check for similar names that might cause confusion
        id_list = list(logical_ids)
        for i, id1 in enumerate(id_list):
            for id2 in id_list[i+1:]:
                if self._are_similar(id1, id2):
                    self.warnings.append(f"⚠️  Similar resource names: {id1}, {id2}")
    
    def _are_similar(self, name1: str, name2: str) -> bool:
        """Check if two names are confusingly similar"""
        # Simple similarity check
        if abs(len(name1) - len(name2)) <= 1:
            differences = sum(c1 != c2 for c1, c2 in zip(name1, name2))
            return differences <= 2
        return False
    
    def _create_result(self, success: bool) -> Dict:
        """Create validation result"""
        return {
            'success': success,
            'errors': self.errors,
            'warnings': self.warnings,
            'info': self.info,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings)
        }

def main():
    if len(sys.argv) != 2:
        print("Usage: python local-cf-validator.py <template-file>")
        sys.exit(1)
    
    template_path = sys.argv[1]
    
    validator = LocalTemplateValidator()
    result = validator.validate_template_file(template_path)
    
    print("\n" + "=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("=" * 60)
    
    # Print info messages
    for info in result['info']:
        print(info)
    
    # Print warnings
    if result['warnings']:
        print(f"\n⚠️  WARNINGS ({len(result['warnings'])}):")
        for warning in result['warnings']:
            print(f"   {warning}")
    
    # Print errors
    if result['errors']:
        print(f"\n❌ ERRORS ({len(result['errors'])}):")
        for error in result['errors']:
            print(f"   {error}")
    
    # Final result
    print("\n" + "=" * 60)
    if result['success']:
        print("✅ VALIDATION PASSED")
        if result['warning_count'] > 0:
            print(f"   ({result['warning_count']} warnings)")
    else:
        print("❌ VALIDATION FAILED")
        print(f"   {result['error_count']} errors, {result['warning_count']} warnings")
    
    sys.exit(0 if result['success'] else 1)

if __name__ == '__main__':
    main()
