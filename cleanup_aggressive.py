#!/usr/bin/env python3
import boto3
import time

cf = boto3.client('cloudformation', region_name='us-east-1')
ec2 = boto3.client('ec2', region_name='us-east-1')

print('[AGGRESSIVE CLEANUP]\n')

# Force delete stacks
print('=== FORCE DELETE STACKS ===\n')
for stack in ['stocks-app-stack', 'stocks-core-stack']:
    print(f'Deleting: {stack}')
    try:
        cf.delete_stack(StackName=stack)
        print(f'  [OK] Delete initiated')
    except Exception as e:
        print(f'  [WARN] {str(e)[:50]}')

print('\nWaiting 20s for stack deletions to process...')
time.sleep(20)

print('\n=== FORCE DELETE VPC ===\n')
vpc_id = 'vpc-01bac8b5a4479dad9'

print('Removing network interfaces...')
try:
    enis = ec2.describe_network_interfaces(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    for eni in enis['NetworkInterfaces']:
        try:
            if 'Attachment' in eni:
                ec2.detach_network_interface(AttachmentId=eni['Attachment']['AttachmentId'], Force=True)
            ec2.delete_network_interface(NetworkInterfaceId=eni['NetworkInterfaceId'])
        except:
            pass
    print('[OK]')
except Exception as e:
    print(f'[WARN] {e}')

print('Removing internet gateways...')
try:
    igws = ec2.describe_internet_gateways(Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}])
    for igw in igws['InternetGateways']:
        try:
            ec2.detach_internet_gateway(InternetGatewayId=igw['InternetGatewayId'], VpcId=vpc_id)
            ec2.delete_internet_gateway(InternetGatewayId=igw['InternetGatewayId'])
        except:
            pass
    print('[OK]')
except Exception as e:
    print(f'[WARN] {e}')

print('Removing route tables...')
try:
    rts = ec2.describe_route_tables(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    for rt in rts['RouteTables']:
        if not any(a['Main'] for a in rt.get('Associations', [])):
            try:
                ec2.delete_route_table(RouteTableId=rt['RouteTableId'])
            except:
                pass
    print('[OK]')
except Exception as e:
    print(f'[WARN] {e}')

print('Removing subnets...')
try:
    subnets = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    for subnet in subnets['Subnets']:
        try:
            ec2.delete_subnet(SubnetId=subnet['SubnetId'])
        except:
            pass
    print('[OK]')
except Exception as e:
    print(f'[WARN] {e}')

print('Removing security groups...')
try:
    sgs = ec2.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    for sg in sgs['SecurityGroups']:
        if sg['GroupName'] != 'default':
            try:
                ec2.delete_security_group(GroupId=sg['GroupId'])
            except:
                pass
    print('[OK]')
except Exception as e:
    print(f'[WARN] {e}')

print('Removing VPC...')
try:
    time.sleep(3)
    ec2.delete_vpc(VpcId=vpc_id)
    print('[OK]')
except Exception as e:
    print(f'[WARN] {e}')

print('\n=== FINAL VERIFICATION ===\n')

vpcs = ec2.describe_vpcs(Filters=[{'Name': 'cidr', 'Values': ['10.0.0.0/16']}])
if vpcs['Vpcs']:
    print('[FAIL] VPC still exists:')
    for vpc in vpcs['Vpcs']:
        print(f'  {vpc["VpcId"]} ({vpc["State"]})')
else:
    print('[OK] VPC deleted')

stacks = cf.list_stacks(StackStatusFilter=['CREATE_COMPLETE', 'UPDATE_COMPLETE', 'ROLLBACK_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE', 'REVIEW_IN_PROGRESS'])
remaining = [s for s in stacks['StackSummaries'] if 'stocks' in s['StackName']]
if remaining:
    print('[FAIL] Stacks still exist:')
    for s in remaining:
        print(f'  {s["StackName"]}: {s["StackStatus"]}')
else:
    print('[OK] All stacks deleted')

print('\n[DONE]')
