#!/usr/bin/env python3
"""
CloudFormation Fast Validation Tool
Validates CloudFormation deployments without lengthy deployment cycles
"""

import boto3
import json
import yaml
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class CloudFormationValidator:
    def __init__(self, region: str = 'us-east-1'):
        self.session = boto3.Session()
        self.cf_client = self.session.client('cloudformation', region_name=region)
        self.s3_client = self.session.client('s3', region_name=region)
        self.region = region
    
    def validate_template_syntax(self, template_path: str) -> bool:
        """
        Validate CloudFormation template syntax using AWS API
        Fast: ~1-2 seconds
        """
        print(f"📋 Validating template syntax: {template_path}")
        
        try:
            with open(template_path, 'r') as f:
                template_body = f.read()
            
            response = self.cf_client.validate_template(TemplateBody=template_body)
            
            print("✅ Template syntax is valid")
            print(f"   Description: {response.get('Description', 'N/A')}")
            print(f"   Parameters: {len(response.get('Parameters', []))}")
            print(f"   Capabilities: {response.get('Capabilities', [])}")
            
            return True
            
        except Exception as e:
            print(f"❌ Template validation failed: {str(e)}")
            return False
    
    def create_changeset(self, stack_name: str, template_path: str, parameters: Dict = None) -> Optional[str]:
        """
        Create a changeset without executing it
        Fast: ~5-10 seconds vs 10-15 minutes for full deployment
        """
        print(f"📊 Creating changeset for stack: {stack_name}")
        
        try:
            with open(template_path, 'r') as f:
                template_body = f.read()
            
            # Create unique changeset name
            changeset_name = f"validation-{int(time.time())}"
            
            # Prepare parameters
            cf_parameters = []
            if parameters:
                for key, value in parameters.items():
                    cf_parameters.append({
                        'ParameterKey': key,
                        'ParameterValue': str(value)
                    })
            
            # Check if stack exists
            stack_exists = self._stack_exists(stack_name)
            change_set_type = 'UPDATE' if stack_exists else 'CREATE'
            
            response = self.cf_client.create_change_set(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=cf_parameters,
                Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM'],
                ChangeSetName=changeset_name,
                ChangeSetType=change_set_type,
                Description=f"Validation changeset created at {datetime.now().isoformat()}"
            )
            
            changeset_id = response['Id']
            print(f"✅ Changeset created: {changeset_name}")
            print(f"   Type: {change_set_type}")
            print(f"   ID: {changeset_id}")
            
            return changeset_id
            
        except Exception as e:
            print(f"❌ Changeset creation failed: {str(e)}")
            return None
    
    def analyze_changeset(self, changeset_id: str, stack_name: str) -> Dict:
        """
        Analyze changeset to see what would change
        Shows exactly what will happen without deploying
        """
        print(f"🔍 Analyzing changeset: {changeset_id}")
        
        try:
            # Wait for changeset to be ready
            waiter = self.cf_client.get_waiter('change_set_create_complete')
            waiter.wait(
                ChangeSetName=changeset_id,
                StackName=stack_name,
                WaiterConfig={'Delay': 2, 'MaxAttempts': 30}
            )
            
            # Get changeset details
            response = self.cf_client.describe_change_set(
                ChangeSetName=changeset_id,
                StackName=stack_name
            )
            
            changes = response.get('Changes', [])
            status = response.get('Status', 'UNKNOWN')
            
            print(f"📈 Changeset Status: {status}")
            print(f"📊 Total Changes: {len(changes)}")
            
            analysis = {
                'status': status,
                'total_changes': len(changes),
                'changes_by_action': {},
                'changes_by_resource_type': {},
                'critical_changes': [],
                'warnings': []
            }
            
            # Analyze changes
            for change in changes:
                resource_change = change.get('ResourceChange', {})
                action = resource_change.get('Action', 'Unknown')
                resource_type = resource_change.get('ResourceType', 'Unknown')
                logical_id = resource_change.get('LogicalResourceId', 'Unknown')
                
                # Count by action
                analysis['changes_by_action'][action] = analysis['changes_by_action'].get(action, 0) + 1
                
                # Count by resource type
                analysis['changes_by_resource_type'][resource_type] = \
                    analysis['changes_by_resource_type'].get(resource_type, 0) + 1
                
                # Check for critical changes
                if self._is_critical_change(resource_change):
                    analysis['critical_changes'].append({
                        'logical_id': logical_id,
                        'resource_type': resource_type,
                        'action': action,
                        'reason': self._get_critical_reason(resource_change)
                    })
                
                # Print change details
                print(f"   {action}: {resource_type} ({logical_id})")
                
                # Show replacement details
                replacement = resource_change.get('Replacement', 'N/A')
                if replacement != 'N/A':
                    print(f"     Replacement: {replacement}")
            
            # Show summary
            print(f"\n📊 Changes Summary:")
            for action, count in analysis['changes_by_action'].items():
                print(f"   {action}: {count}")
            
            # Show warnings
            if analysis['critical_changes']:
                print(f"\n⚠️  Critical Changes Detected ({len(analysis['critical_changes'])}):")
                for critical in analysis['critical_changes']:
                    print(f"   - {critical['logical_id']}: {critical['reason']}")
            
            return analysis
            
        except Exception as e:
            print(f"❌ Changeset analysis failed: {str(e)}")
            return {'status': 'FAILED', 'error': str(e)}
    
    def cleanup_changeset(self, changeset_id: str, stack_name: str) -> bool:
        """Clean up the validation changeset"""
        try:
            self.cf_client.delete_change_set(
                ChangeSetName=changeset_id,
                StackName=stack_name
            )
            print(f"🗑️  Changeset cleaned up: {changeset_id}")
            return True
        except Exception as e:
            print(f"⚠️  Changeset cleanup failed: {str(e)}")
            return False
    
    def validate_drift(self, stack_name: str) -> Dict:
        """
        Check for configuration drift in existing stack
        Fast way to see if deployed resources match template
        """
        print(f"🔍 Checking drift for stack: {stack_name}")
        
        try:
            # Start drift detection
            response = self.cf_client.detect_stack_drift(StackName=stack_name)
            drift_detection_id = response['StackDriftDetectionId']
            
            # Wait for drift detection to complete
            print("⏳ Waiting for drift detection...")
            waiter = self.cf_client.get_waiter('stack_drift_detection_complete')
            waiter.wait(
                StackName=stack_name,
                StackDriftDetectionId=drift_detection_id,
                WaiterConfig={'Delay': 5, 'MaxAttempts': 60}
            )
            
            # Get drift results
            response = self.cf_client.describe_stack_drift_detection_status(
                StackDriftDetectionId=drift_detection_id
            )
            
            drift_status = response.get('StackDriftStatus', 'UNKNOWN')
            drifted_resources = response.get('DriftedStackResourcesCount', 0)
            
            print(f"📊 Drift Status: {drift_status}")
            print(f"📊 Drifted Resources: {drifted_resources}")
            
            # Get detailed drift info if resources have drifted
            drift_details = []
            if drifted_resources > 0:
                drift_response = self.cf_client.describe_stack_resource_drifts(
                    StackName=stack_name
                )
                
                for resource_drift in drift_response.get('StackResourceDrifts', []):
                    if resource_drift.get('StackResourceDriftStatus') == 'MODIFIED':
                        drift_details.append({
                            'logical_id': resource_drift.get('LogicalResourceId'),
                            'resource_type': resource_drift.get('ResourceType'),
                            'drift_status': resource_drift.get('StackResourceDriftStatus'),
                            'property_differences': resource_drift.get('PropertyDifferences', [])
                        })
                        
                        print(f"   🔄 DRIFTED: {resource_drift.get('ResourceType')} "
                              f"({resource_drift.get('LogicalResourceId')})")
            
            return {
                'drift_status': drift_status,
                'drifted_resources_count': drifted_resources,
                'drift_details': drift_details
            }
            
        except Exception as e:
            print(f"❌ Drift detection failed: {str(e)}")
            return {'drift_status': 'FAILED', 'error': str(e)}
    
    def validate_resources_exist(self, stack_name: str) -> Dict:
        """
        Quick check that all stack resources exist and are healthy
        Much faster than full deployment
        """
        print(f"🔍 Validating resources exist for stack: {stack_name}")
        
        try:
            response = self.cf_client.describe_stack_resources(StackName=stack_name)
            resources = response.get('StackResources', [])
            
            resource_status = {}
            unhealthy_resources = []
            
            for resource in resources:
                logical_id = resource.get('LogicalResourceId')
                resource_type = resource.get('ResourceType')
                status = resource.get('ResourceStatus')
                
                resource_status[logical_id] = status
                
                if not status.endswith('_COMPLETE'):
                    unhealthy_resources.append({
                        'logical_id': logical_id,
                        'resource_type': resource_type,
                        'status': status
                    })
                
                print(f"   {status}: {resource_type} ({logical_id})")
            
            print(f"\n📊 Resource Health Summary:")
            print(f"   Total Resources: {len(resources)}")
            print(f"   Unhealthy Resources: {len(unhealthy_resources)}")
            
            return {
                'total_resources': len(resources),
                'unhealthy_count': len(unhealthy_resources),
                'unhealthy_resources': unhealthy_resources,
                'all_resources_healthy': len(unhealthy_resources) == 0
            }
            
        except Exception as e:
            print(f"❌ Resource validation failed: {str(e)}")
            return {'error': str(e)}
    
    def estimate_deployment_time(self, template_path: str) -> Dict:
        """
        Estimate deployment time based on resources in template
        Helps you know what you're getting into
        """
        print(f"⏱️  Estimating deployment time for: {template_path}")
        
        try:
            with open(template_path, 'r') as f:
                if template_path.endswith('.json'):
                    template = json.load(f)
                else:
                    template = yaml.safe_load(f)
            
            resources = template.get('Resources', {})
            
            # Time estimates for different resource types (in minutes)
            time_estimates = {
                'AWS::CloudFront::Distribution': 15,  # The slow one!
                'AWS::RDS::DBInstance': 10,
                'AWS::ElasticLoadBalancingV2::LoadBalancer': 3,
                'AWS::ECS::Service': 5,
                'AWS::Lambda::Function': 1,
                'AWS::S3::Bucket': 1,
                'AWS::IAM::Role': 1,
                'AWS::ApiGateway::RestApi': 2,
                'default': 2
            }
            
            total_time = 0
            resource_breakdown = {}
            
            for logical_id, resource_def in resources.items():
                resource_type = resource_def.get('Type', 'Unknown')
                estimated_time = time_estimates.get(resource_type, time_estimates['default'])
                
                total_time += estimated_time
                resource_breakdown[logical_id] = {
                    'type': resource_type,
                    'estimated_minutes': estimated_time
                }
                
                print(f"   {resource_type}: ~{estimated_time} minutes ({logical_id})")
            
            print(f"\n⏱️  Total Estimated Time: ~{total_time} minutes")
            
            if total_time > 10:
                print("⚠️  Long deployment detected! Consider using validation methods.")
            
            return {
                'total_estimated_minutes': total_time,
                'resource_breakdown': resource_breakdown,
                'is_long_deployment': total_time > 10
            }
            
        except Exception as e:
            print(f"❌ Time estimation failed: {str(e)}")
            return {'error': str(e)}
    
    def _stack_exists(self, stack_name: str) -> bool:
        """Check if stack exists"""
        try:
            self.cf_client.describe_stacks(StackName=stack_name)
            return True
        except:
            return False
    
    def _is_critical_change(self, resource_change: Dict) -> bool:
        """Determine if a resource change is critical"""
        resource_type = resource_change.get('ResourceType', '')
        action = resource_change.get('Action', '')
        replacement = resource_change.get('Replacement', '')
        
        # Critical if it's a replacement of important resources
        critical_resources = [
            'AWS::RDS::DBInstance',
            'AWS::CloudFront::Distribution',
            'AWS::ElasticLoadBalancing::LoadBalancer'
        ]
        
        return (action == 'Remove' or 
                replacement in ['True', 'Conditional'] or
                resource_type in critical_resources)
    
    def _get_critical_reason(self, resource_change: Dict) -> str:
        """Get reason why change is critical"""
        action = resource_change.get('Action', '')
        replacement = resource_change.get('Replacement', '')
        
        if action == 'Remove':
            return "Resource will be deleted"
        elif replacement == 'True':
            return "Resource will be replaced (downtime expected)"
        elif replacement == 'Conditional':
            return "Resource may be replaced depending on properties"
        else:
            return "Critical resource type"

def main():
    parser = argparse.ArgumentParser(description='CloudFormation Fast Validation Tool')
    parser.add_argument('command', choices=[
        'syntax', 'changeset', 'drift', 'resources', 'estimate', 'full'
    ], help='Validation command to run')
    parser.add_argument('--template', '-t', required=True, help='CloudFormation template file')
    parser.add_argument('--stack-name', '-s', help='Stack name (required for some commands)')
    parser.add_argument('--region', '-r', default='us-east-1', help='AWS region')
    parser.add_argument('--parameters', '-p', help='Parameters file (JSON)')
    
    args = parser.parse_args()
    
    # Load parameters if provided
    parameters = {}
    if args.parameters:
        with open(args.parameters, 'r') as f:
            parameters = json.load(f)
    
    validator = CloudFormationValidator(region=args.region)
    
    print(f"🚀 CloudFormation Validation Tool")
    print(f"📁 Template: {args.template}")
    print(f"🌍 Region: {args.region}")
    print("=" * 60)
    
    if args.command == 'syntax':
        # Just validate syntax
        success = validator.validate_template_syntax(args.template)
        sys.exit(0 if success else 1)
    
    elif args.command == 'changeset':
        # Create and analyze changeset
        if not args.stack_name:
            print("❌ --stack-name required for changeset validation")
            sys.exit(1)
        
        success = validator.validate_template_syntax(args.template)
        if not success:
            sys.exit(1)
        
        changeset_id = validator.create_changeset(args.stack_name, args.template, parameters)
        if changeset_id:
            analysis = validator.analyze_changeset(changeset_id, args.stack_name)
            validator.cleanup_changeset(changeset_id, args.stack_name)
            
            if analysis.get('status') == 'FAILED':
                sys.exit(1)
    
    elif args.command == 'drift':
        # Check drift
        if not args.stack_name:
            print("❌ --stack-name required for drift detection")
            sys.exit(1)
        
        drift_result = validator.validate_drift(args.stack_name)
        if 'error' in drift_result:
            sys.exit(1)
    
    elif args.command == 'resources':
        # Check resource health
        if not args.stack_name:
            print("❌ --stack-name required for resource validation")
            sys.exit(1)
        
        resource_result = validator.validate_resources_exist(args.stack_name)
        if 'error' in resource_result or not resource_result.get('all_resources_healthy', False):
            sys.exit(1)
    
    elif args.command == 'estimate':
        # Estimate deployment time
        estimate = validator.estimate_deployment_time(args.template)
        if 'error' in estimate:
            sys.exit(1)
    
    elif args.command == 'full':
        # Run all validations
        print("🔄 Running full validation suite...")
        print("=" * 60)
        
        # 1. Syntax validation
        success = validator.validate_template_syntax(args.template)
        if not success:
            sys.exit(1)
        
        print("\n" + "=" * 60)
        
        # 2. Time estimation
        validator.estimate_deployment_time(args.template)
        
        # 3. Changeset analysis (if stack name provided)
        if args.stack_name:
            print("\n" + "=" * 60)
            changeset_id = validator.create_changeset(args.stack_name, args.template, parameters)
            if changeset_id:
                analysis = validator.analyze_changeset(changeset_id, args.stack_name)
                validator.cleanup_changeset(changeset_id, args.stack_name)
                
                if analysis.get('status') == 'FAILED':
                    print("⚠️  Changeset validation failed, but continuing...")
            
            print("\n" + "=" * 60)
            
            # 4. Resource health (if stack exists)
            if validator._stack_exists(args.stack_name):
                validator.validate_resources_exist(args.stack_name)
                print("\n" + "=" * 60)
                validator.validate_drift(args.stack_name)
    
    print("\n✅ Validation complete!")

if __name__ == '__main__':
    main()
