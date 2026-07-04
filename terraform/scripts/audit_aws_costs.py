#!/usr/bin/env python3
"""Audit AWS resources for waste and cost optimization."""


import boto3

ec2 = boto3.client('ec2', region_name='us-east-1')
rds = boto3.client('rds', region_name='us-east-1')
s3 = boto3.client('s3')
lambda_client = boto3.client('lambda', region_name='us-east-1')
logs = boto3.client('logs', region_name='us-east-1')

print("=" * 70)
print("AWS COST AUDIT - Identifying Wasteful Resources")
print("=" * 70)

# 1. Check EC2 instances
print("\n📦 EC2 INSTANCES")
print("-" * 70)
try:
    response = ec2.describe_instances(Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped']}])

    running = 0
    stopped = 0
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            state = instance['State']['Name']
            instance_id = instance['InstanceId']
            instance_type = instance['InstanceType']
            launched = instance['LaunchTime'].strftime("%Y-%m-%d")

            if state == 'running':
                running += 1
                print(f"  ⚠️  RUNNING: {instance_id} ({instance_type}) - launched {launched}")
            elif state == 'stopped':
                stopped += 1
                print(f"  💤 STOPPED: {instance_id} ({instance_type}) - COSTING MONEY FOR STORAGE")

    if running == 0 and stopped == 0:
        print("  ✅ No EC2 instances")
    else:
        print(f"\n  Summary: {running} running, {stopped} stopped")
        if stopped > 0:
            print("  💡 TIP: Stopped instances still cost money. Terminate if not needed.")
except Exception as e:
    print(f"  ❌ Error: {e}")

# 2. Check RDS snapshots (can be expensive)
print("\n🗄️  RDS SNAPSHOTS")
print("-" * 70)
try:
    response = rds.describe_db_snapshots()
    # CRITICAL FIX: Explicit check for DBSnapshots field
    snapshots = response.get('DBSnapshots')
    if snapshots is None:
        snapshots = []

    if not snapshots:
        print("  ✅ No RDS snapshots")
    else:
        total_size = 0
        for snap in snapshots:
            snap_id = snap['DBSnapshotIdentifier']
            created = snap['SnapshotCreateTime'].strftime("%Y-%m-%d")
            size = snap.get('AllocatedStorage', 0)
            total_size += size
            print(f"  ⚠️  {snap_id} - {size}GB - created {created}")

        print(f"\n  💰 Total snapshot storage: {total_size}GB")
        print("  💡 TIP: Delete old snapshots. Cost: ~$0.095/GB/month")
except Exception as e:
    print(f"  ❌ Error: {e}")

# 3. Check S3 buckets and old versions
print("\n🪣 S3 BUCKETS")
print("-" * 70)
try:
    response = s3.list_buckets()
    # CRITICAL FIX: Explicit check for Buckets field
    buckets = response.get('Buckets')
    if buckets is None:
        buckets = []

    if not buckets:
        print("  ✅ No S3 buckets")
    else:
        total_size = 0
        for bucket in buckets:
            name = bucket['Name']
            try:
                # List objects
                obj_response = s3.list_objects_v2(Bucket=name, MaxKeys=1000)
                # CRITICAL FIX: Explicit check for Contents field
                contents = obj_response.get('Contents')
                if contents is None:
                    contents = []
                size = sum([obj.get('Size') if obj.get('Size') is not None else 0 for obj in contents])
                total_size += size
                size_mb = size / (1024*1024)
                print(f"  📦 {name}: {size_mb:.1f}MB")
            except Exception:
                print(f"  ❌ {name}: Cannot access")

        print(f"\n  💰 Total S3 storage: {total_size/(1024*1024):.1f}MB")
except Exception as e:
    print(f"  ❌ Error: {e}")

# 4. Check Lambda functions
print("\n⚡ LAMBDA FUNCTIONS")
print("-" * 70)
try:
    response = lambda_client.list_functions()
    # CRITICAL FIX: Explicit check for Functions field
    functions = response.get('Functions')
    if functions is None:
        functions = []

    if not functions:
        print("  ✅ No Lambda functions")
    else:
        print(f"  Found {len(functions)} Lambda functions")
        for func in functions:
            name = func['FunctionName']
            memory = func['MemorySize']
            print(f"    - {name} ({memory}MB memory)")
except Exception as e:
    print(f"  ❌ Error: {e}")

# 5. Check CloudWatch logs
print("\n📋 CLOUDWATCH LOGS")
print("-" * 70)
try:
    response = logs.describe_log_groups(limit=50)
    # CRITICAL FIX: Explicit check for logGroups field
    log_groups = response.get('logGroups')
    if log_groups is None:
        log_groups = []

    if not log_groups:
        print("  ✅ No CloudWatch log groups")
    else:
        print(f"  Found {len(log_groups)} log groups")
        total_retention = 0
        unlimited = 0
        for lg in log_groups[:10]:
            name = lg['logGroupName']
            retention = lg.get('retentionInDays', 'unlimited')
            if retention == 'unlimited':
                unlimited += 1
                print(f"    ⚠️  {name}: UNLIMITED retention - EXPENSIVE")
            else:
                print(f"    ✅ {name}: {retention} days")
                total_retention += retention

        if unlimited > 0:
            print("\n  💡 TIP: Set retention limits (7-30 days) to reduce costs")
except Exception as e:
    print(f"  ❌ Error: {e}")

print("\n" + "=" * 70)
print("RECOMMENDATIONS:")
print("=" * 70)
print("""
1. 🗄️  RDS Snapshots:
   - Delete old snapshots that are no longer needed
   - Cost: ~$0.095/GB/month per snapshot

2. 💤 Stopped EC2:
   - Terminate stopped instances you don't need
   - Stopped instances still cost for EBS storage

3. 📋 CloudWatch Logs:
   - Set retention limits (7-30 days) instead of unlimited
   - Unlimited retention is expensive long-term

4. ⚡ Lambda:
   - Reduce memory allocation if not needed (faster = more expensive)
   - Remove unused functions

5. 🪣 S3:
   - Enable lifecycle policies to delete old versions
   - Move infrequent access to Glacier classes
""")

print("\nTo remove resources:")
print("  - RDS Snapshots: aws rds delete-db-snapshot --db-snapshot-identifier <id>")
print("  - EC2 Instance: aws ec2 terminate-instances --instance-ids <id>")
print("  - Log Group: aws logs delete-log-group --log-group-name <name>")

