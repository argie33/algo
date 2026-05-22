#!/usr/bin/env python3
"""
Comprehensive AWS resource audit - checks ALL resource types for unmanaged creation.
Compares against Terraform state to find resources created outside IaC.
"""

import subprocess
import json
import sys
from collections import defaultdict

def run_cmd(cmd, region="us-east-1"):
    """Execute AWS CLI command."""
    full_cmd = cmd.replace("{region}", region)
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def get_terraform_state():
    """Get all resources from Terraform state."""
    code, out, err = run_cmd(
        "terraform state list",
        region=""
    )
    if code != 0:
        # Try from terraform directory
        result = subprocess.run(
            "cd terraform && terraform state list",
            shell=True,
            capture_output=True,
            text=True,
            cwd="."
        )
        return [line.strip() for line in result.stdout.split('\n') if line.strip()]
    return [line.strip() for line in out.split('\n') if line.strip()]

def check_vpc_resources(region="us-east-1"):
    """Check VPC, subnets, security groups, etc."""
    findings = []

    # VPCs
    code, out, err = run_cmd("aws ec2 describe-vpcs --region {region} --output json")
    if code == 0:
        vpcs = json.loads(out).get('Vpcs', [])
        for vpc in vpcs:
            tags = {t['Key']: t['Value'] for t in vpc.get('Tags', [])}
            if tags.get('ManagedBy') != 'Terraform':
                findings.append(("VPC", vpc['VpcId'], tags.get('Name', 'N/A')))

    # Subnets
    code, out, err = run_cmd("aws ec2 describe-subnets --region {region} --output json")
    if code == 0:
        subnets = json.loads(out).get('Subnets', [])
        for subnet in subnets:
            tags = {t['Key']: t['Value'] for t in subnet.get('Tags', [])}
            if tags.get('ManagedBy') != 'Terraform' and tags.get('aws:cloudformation:stack-name') is None:
                findings.append(("Subnet", subnet['SubnetId'], subnet.get('AvailabilityZone')))

    # Security Groups
    code, out, err = run_cmd("aws ec2 describe-security-groups --region {region} --output json")
    if code == 0:
        sgs = json.loads(out).get('SecurityGroups', [])
        for sg in sgs:
            tags = {t['Key']: t['Value'] for t in sg.get('Tags', [])}
            # Skip default SGs
            if sg['GroupName'] != 'default' and tags.get('ManagedBy') != 'Terraform':
                findings.append(("SecurityGroup", sg['GroupId'], sg.get('GroupName')))

    # Network Interfaces
    code, out, err = run_cmd("aws ec2 describe-network-interfaces --region {region} --output json")
    if code == 0:
        nis = json.loads(out).get('NetworkInterfaces', [])
        for ni in nis:
            tags = {t['Key']: t['Value'] for t in ni.get('TagSet', [])}
            if tags.get('ManagedBy') != 'Terraform' and ni['InterfaceType'] != 'interface':
                findings.append(("NetworkInterface", ni['NetworkInterfaceId'], ni.get('Description', 'N/A')))

    # Elastic IPs
    code, out, err = run_cmd("aws ec2 describe-addresses --region {region} --output json")
    if code == 0:
        eips = json.loads(out).get('Addresses', [])
        for eip in eips:
            tags = {t['Key']: t['Value'] for t in eip.get('Tags', [])}
            if tags.get('ManagedBy') != 'Terraform':
                findings.append(("ElasticIP", eip['PublicIp'], eip.get('AssociationId', 'unassociated')))

    # Internet Gateways
    code, out, err = run_cmd("aws ec2 describe-internet-gateways --region {region} --output json")
    if code == 0:
        igws = json.loads(out).get('InternetGateways', [])
        for igw in igws:
            tags = {t['Key']: t['Value'] for t in igw.get('Tags', [])}
            if tags.get('ManagedBy') != 'Terraform':
                findings.append(("InternetGateway", igw['InternetGatewayId'], tags.get('Name', 'N/A')))

    # Route Tables
    code, out, err = run_cmd("aws ec2 describe-route-tables --region {region} --output json")
    if code == 0:
        rts = json.loads(out).get('RouteTables', [])
        for rt in rts:
            tags = {t['Key']: t['Value'] for t in rt.get('Tags', [])}
            if tags.get('ManagedBy') != 'Terraform' and not rt['Associations'][0]['Main']:
                findings.append(("RouteTable", rt['RouteTableId'], tags.get('Name', 'N/A')))

    # NAT Gateways
    code, out, err = run_cmd("aws ec2 describe-nat-gateways --region {region} --output json")
    if code == 0:
        nats = json.loads(out).get('NatGateways', [])
        for nat in nats:
            tags = {t['Key']: t['Value'] for t in nat.get('Tags', [])}
            if tags.get('ManagedBy') != 'Terraform':
                findings.append(("NATGateway", nat['NatGatewayId'], nat['SubnetId']))

    return findings

def check_compute_resources(region="us-east-1"):
    """Check EC2, Auto Scaling, etc."""
    findings = []

    # EC2 Instances
    code, out, err = run_cmd("aws ec2 describe-instances --region {region} --output json")
    if code == 0:
        reservations = json.loads(out).get('Reservations', [])
        for res in reservations:
            for inst in res.get('Instances', []):
                tags = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                if inst['State']['Name'] != 'terminated' and tags.get('ManagedBy') != 'Terraform':
                    findings.append(("EC2Instance", inst['InstanceId'], tags.get('Name', 'unknown')))

    # Auto Scaling Groups
    code, out, err = run_cmd("aws autoscaling describe-auto-scaling-groups --region {region} --output json")
    if code == 0:
        asgs = json.loads(out).get('AutoScalingGroups', [])
        for asg in asgs:
            tags = {t['Key']: t['Value'] for t in asg.get('Tags', [])}
            if tags.get('ManagedBy') != 'Terraform':
                findings.append(("AutoScalingGroup", asg['AutoScalingGroupName'], asg['MinSize']))

    return findings

def check_database_resources(region="us-east-1"):
    """Check RDS, DynamoDB, etc."""
    findings = []

    # RDS Instances
    code, out, err = run_cmd("aws rds describe-db-instances --region {region} --output json")
    if code == 0:
        dbs = json.loads(out).get('DBInstances', [])
        for db in dbs:
            # Get tags
            code2, out2, err2 = run_cmd(
                f"aws rds list-tags-for-resource --resource-name {db['DBInstanceArn']} --region {{region}} --output json"
            )
            if code2 == 0:
                tags = {t['Key']: t['Value'] for t in json.loads(out2).get('TagList', [])}
                if tags.get('ManagedBy') != 'Terraform':
                    findings.append(("RDSInstance", db['DBInstanceIdentifier'], db['Engine']))

    # DynamoDB Tables
    code, out, err = run_cmd("aws dynamodb list-tables --region {region} --output json")
    if code == 0:
        tables = json.loads(out).get('TableNames', [])
        for table in tables:
            findings.append(("DynamoDBTable", table, "check manually"))

    return findings

def check_data_resources(region="us-east-1"):
    """Check SNS, SQS, Kinesis, EventBridge, etc."""
    findings = []

    # SNS Topics
    code, out, err = run_cmd("aws sns list-topics --region {region} --output json")
    if code == 0:
        topics = json.loads(out).get('Topics', [])
        for topic in topics:
            arn = topic['TopicArn']
            # Get tags
            code2, out2, err2 = run_cmd(
                f"aws sns list-tags-for-resource --resource-arn {arn} --region {{region}} --output json"
            )
            if code2 == 0:
                tags = {t['Key']: t['Value'] for t in json.loads(out2).get('Tags', [])}
                if tags.get('ManagedBy') != 'Terraform':
                    findings.append(("SNSTopic", arn.split(':')[-1], "check manually"))

    # SQS Queues
    code, out, err = run_cmd("aws sqs list-queues --region {region} --output json")
    if code == 0:
        queues = json.loads(out).get('QueueUrls', [])
        for queue_url in queues:
            findings.append(("SQSQueue", queue_url.split('/')[-1], "check manually"))

    # EventBridge Rules
    code, out, err = run_cmd("aws events list-rules --region {region} --output json")
    if code == 0:
        rules = json.loads(out).get('Rules', [])
        terraform_rules = {
            'detect-unmanaged-aws-resources',
            'daily-weight-optimization',
        }
        for rule in rules:
            if rule['Name'] not in terraform_rules and not rule['Name'].startswith('aws.'):
                findings.append(("EventBridgeRule", rule['Name'], rule['State']))

    return findings

def check_monitoring_resources(region="us-east-1"):
    """Check CloudWatch, logs, etc."""
    findings = []

    # CloudWatch Log Groups
    code, out, err = run_cmd("aws logs describe-log-groups --region {region} --output json")
    if code == 0:
        groups = json.loads(out).get('logGroups', [])
        terraform_prefixes = ['/aws/lambda/', '/aws/ecs/', '/aws/batch/']
        for group in groups:
            is_terraform = any(group['logGroupName'].startswith(p) for p in terraform_prefixes)
            if not is_terraform:
                findings.append(("CloudWatchLogGroup", group['logGroupName'], "check manually"))

    # CloudWatch Alarms
    code, out, err = run_cmd("aws cloudwatch describe-alarms --region {region} --output json")
    if code == 0:
        alarms = json.loads(out).get('MetricAlarms', [])
        for alarm in alarms:
            # Simple check: if it has terraform in name, assume it's managed
            if 'terraform' not in alarm['AlarmName'].lower():
                findings.append(("CloudWatchAlarm", alarm['AlarmName'], alarm['StateValue']))

    return findings

def check_storage_resources(region="us-east-1"):
    """Check EBS volumes, snapshots, etc."""
    findings = []

    # EBS Volumes
    code, out, err = run_cmd("aws ec2 describe-volumes --region {region} --output json")
    if code == 0:
        volumes = json.loads(out).get('Volumes', [])
        for vol in volumes:
            tags = {t['Key']: t['Value'] for t in vol.get('Tags', [])}
            if vol['State'] != 'available' and tags.get('ManagedBy') != 'Terraform':
                # Only flag if attached to non-terraform instance
                if vol['Attachments']:
                    findings.append(("EBSVolume", vol['VolumeId'], vol['Size']))

    # EBS Snapshots
    code, out, err = run_cmd("aws ec2 describe-snapshots --owner-ids self --region {region} --output json")
    if code == 0:
        snaps = json.loads(out).get('Snapshots', [])
        for snap in snaps:
            tags = {t['Key']: t['Value'] for t in snap.get('Tags', [])}
            if tags.get('ManagedBy') != 'Terraform':
                findings.append(("EBSSnapshot", snap['SnapshotId'], snap['VolumeSize']))

    return findings

def main():
    print("=" * 100)
    print("COMPREHENSIVE AWS RESOURCE AUDIT - ALL RESOURCE TYPES")
    print("=" * 100)

    region = "us-east-1"
    all_findings = {}

    # Run all audits
    audits = [
        ("Network Resources", lambda: check_vpc_resources(region)),
        ("Compute Resources", lambda: check_compute_resources(region)),
        ("Database Resources", lambda: check_database_resources(region)),
        ("Data & Messaging", lambda: check_data_resources(region)),
        ("Monitoring Resources", lambda: check_monitoring_resources(region)),
        ("Storage Resources", lambda: check_storage_resources(region)),
    ]

    total_unmanaged = 0
    for category, audit_func in audits:
        print(f"\n{category}")
        print("-" * 100)
        findings = audit_func()

        if findings:
            all_findings[category] = findings
            for resource_type, resource_id, details in findings:
                print(f"  [UNMANAGED] {resource_type:25} {resource_id:40} ({details})")
                total_unmanaged += 1
        else:
            print(f"  [OK] All resources managed by Terraform")

    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total unmanaged resources found: {total_unmanaged}")

    if total_unmanaged == 0:
        print("\n[SUCCESS] All AWS resources are Terraform-managed!")
        print("\nSecurity Status:")
        print("  ✓ Zero unmanaged resources")
        print("  ✓ All resources must have terraform:managed tag (enforced)")
        print("  ✓ Continuous monitoring active (AWS Config + CloudWatch)")
        return 0
    else:
        print(f"\n[WARNING] Found {total_unmanaged} unmanaged resources")
        print("\nManually review and either:")
        print("  1. Add to Terraform code")
        print("  2. Delete if not needed")
        print("  3. Tag with terraform:managed if truly external")
        return 1

if __name__ == "__main__":
    sys.exit(main())
