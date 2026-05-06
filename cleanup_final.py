#!/usr/bin/env python3
import boto3
import time

cf = boto3.client('cloudformation', region_name='us-east-1')
ec2 = boto3.client('ec2', region_name='us-east-1')

vpc_id = 'vpc-01bac8b5a4479dad9'

print('[FINAL AGGRESSIVE CLEANUP]\n')

# Kill any running instances first
print('=== TERMINATE INSTANCES ===')
instances = ec2.describe_instances(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
for res in instances['Reservations']:
    for inst in res['Instances']:
        if inst['State']['Name'] != 'terminated':
            print(f'Terminating: {inst["InstanceId"]}')
            ec2.terminate_instances(InstanceIds=[inst['InstanceId']])

time.sleep(5)

# Force delete ENIs
print('\n=== DELETE NETWORK INTERFACES (FORCE) ===')
enis = ec2.describe_network_interfaces(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
for eni in enis['NetworkInterfaces']:
    print(f'Deleting ENI: {eni["NetworkInterfaceId"]} ({eni["Status"]})')
    try:
        # Try to detach any attachments
        if eni.get('Attachment'):
            try:
                ec2.detach_network_interface(
                    AttachmentId=eni['Attachment']['AttachmentId'],
                    Force=True
                )
                print(f'  Detached')
                time.sleep(1)
            except Exception as e:
                print(f'  [WARN] Could not detach: {str(e)[:40]}')

        # Delete
        ec2.delete_network_interface(NetworkInterfaceId=eni['NetworkInterfaceId'])
        print(f'  [OK] Deleted')
    except Exception as e:
        print(f'  [WARN] {str(e)[:40]}')

# Try again to delete VPC
print('\n=== DELETE VPC ===')
time.sleep(3)
try:
    ec2.delete_vpc(VpcId=vpc_id)
    print(f'[OK] VPC {vpc_id} deleted')
except Exception as e:
    print(f'[FAIL] VPC still has dependencies: {str(e)[:80]}')
    print('\nRemaining resources - will attempt manual AWS Console cleanup:')

    print('\nENIs:')
    enis = ec2.describe_network_interfaces(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    for eni in enis['NetworkInterfaces']:
        print(f'  {eni["NetworkInterfaceId"]}: {eni["Status"]}')

    print('\nStacks (stuck):')
    stacks = cf.list_stacks(StackStatusFilter=['UPDATE_ROLLBACK_COMPLETE'])
    for s in stacks['StackSummaries']:
        if 'stocks' in s['StackName']:
            print(f'  {s["StackName"]}: {s["StackStatus"]}')
