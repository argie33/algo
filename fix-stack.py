#!/usr/bin/env python3
import boto3
import sys
import time

# Initialize clients
cf = boto3.client('cloudformation', region_name='us-east-1')
ec2 = boto3.client('ec2', region_name='us-east-1')

stack_name = 'stocks-webapp-dev'
sg_id = 'sg-0075699472f6edb04'

print(f"Fixing stuck CloudFormation stack: {stack_name}")

try:
    # First, check current stack status
    response = cf.describe_stacks(StackName=stack_name)
    stack = response['Stacks'][0]
    current_status = stack['StackStatus']
    
    print(f"Current stack status: {current_status}")
    
    if 'CLEANUP_IN_PROGRESS' in current_status:
        print("Stack is in cleanup state. Attempting to continue update rollback...")
        
        # Try to continue update rollback to get to a stable state
        try:
            cf.continue_update_rollback(
                StackName=stack_name,
                ResourcesToSkip=['LambdaSecurityGroup']  # Skip the problematic security group
            )
            print("Initiated continue-update-rollback with LambdaSecurityGroup skipped")
            
            # Wait for stack to stabilize
            print("Waiting for stack to reach stable state...")
            waiter = cf.get_waiter('stack_update_complete')
            waiter.wait(
                StackName=stack_name,
                WaiterConfig={
                    'Delay': 5,
                    'MaxAttempts': 120
                }
            )
            print("Stack is now in a stable state!")
            
        except Exception as e:
            print(f"Error during continue-update-rollback: {str(e)}")
            
            # If that fails, try to manually clean up the security group
            print("\nAttempting manual cleanup of security group dependencies...")
            
            # Find and detach any network interfaces using this security group
            try:
                # Get network interfaces using this security group
                enis = ec2.describe_network_interfaces(
                    Filters=[
                        {'Name': 'group-id', 'Values': [sg_id]}
                    ]
                )
                
                for eni in enis['NetworkInterfaces']:
                    eni_id = eni['NetworkInterfaceId']
                    print(f"Found ENI {eni_id} using security group")
                    
                    # If it's attached to a Lambda function, it might be in 'available' state
                    if eni['Status'] == 'available':
                        try:
                            print(f"Deleting available ENI: {eni_id}")
                            ec2.delete_network_interface(NetworkInterfaceId=eni_id)
                            print(f"Deleted ENI: {eni_id}")
                        except Exception as del_err:
                            print(f"Could not delete ENI {eni_id}: {del_err}")
                    else:
                        print(f"ENI {eni_id} is in {eni['Status']} state - Lambda might still be using it")
                
                # Wait a bit for cleanup
                time.sleep(10)
                
                # Try continue-update-rollback again
                cf.continue_update_rollback(
                    StackName=stack_name,
                    ResourcesToSkip=['LambdaSecurityGroup']
                )
                print("Retried continue-update-rollback after manual cleanup")
                
            except Exception as cleanup_error:
                print(f"Manual cleanup error: {cleanup_error}")
    
    else:
        print(f"Stack is in {current_status} state - no action needed")
        
except Exception as e:
    print(f"Error: {str(e)}")
    sys.exit(1)