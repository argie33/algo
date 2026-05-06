#!/usr/bin/env python3
import boto3

ec2 = boto3.client('ec2', region_name='us-east-1')
vpc_id = 'vpc-01bac8b5a4479dad9'

print('[DIAGNOSING VPC DEPENDENCIES]\n')

print('Network Interfaces:')
enis = ec2.describe_network_interfaces(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
print(f'  Count: {len(enis["NetworkInterfaces"])}')
for eni in enis['NetworkInterfaces']:
    print(f'    {eni["NetworkInterfaceId"]}: {eni["Status"]}')
    if eni.get('Attachment'):
        print(f'      Attached to: {eni["Attachment"]["InstanceId"]}')

print('\nSubnets:')
sn = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
print(f'  Count: {len(sn["Subnets"])}')
for subnet in sn['Subnets']:
    print(f'    {subnet["SubnetId"]}: {subnet["AvailabilityZone"]}')

print('\nVPC Endpoints:')
vpce = ec2.describe_vpc_endpoints(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
print(f'  Count: {len(vpce["VpcEndpoints"])}')
for ep in vpce['VpcEndpoints']:
    print(f'    {ep["VpcEndpointId"]}: {ep["State"]}')

print('\nInternet Gateways:')
igw = ec2.describe_internet_gateways(Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}])
print(f'  Count: {len(igw["InternetGateways"])}')

print('\nRoute Tables:')
rt = ec2.describe_route_tables(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
print(f'  Count: {len(rt["RouteTables"])}')

print('\nSecurity Groups:')
sg = ec2.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
print(f'  Count: {len(sg["SecurityGroups"])}')
for grp in sg['SecurityGroups']:
    print(f'    {grp["GroupId"]}: {grp["GroupName"]}')

print('\nElastic IPs:')
eips = ec2.describe_addresses()
vpc_eips = [addr for addr in eips["Addresses"] if "VpcId" in addr and addr["VpcId"] == vpc_id]
print(f'  Count: {len(vpc_eips)}')
for eip in vpc_eips:
    print(f'    {eip["PublicIp"]}')

print('\nNetwork ACLs:')
nacls = ec2.describe_network_acls(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
print(f'  Count: {len(nacls["NetworkAcls"])}')
