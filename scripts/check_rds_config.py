#!/usr/bin/env python3
"""
Check RDS configuration and timeout parameters.
"""

import boto3

def check_rds_config():
    rds = boto3.client('rds', region_name='us-east-1')

    # Get RDS instance details
    response = rds.describe_db_instances(DBInstanceIdentifier='algo-db')
    instance = response['DBInstances'][0]

    print("=" * 80)
    print("RDS INSTANCE CONFIGURATION")
    print("=" * 80)
    print(f"Instance Class:        {instance['DBInstanceClass']}")
    print(f"Allocated Storage:     {instance['AllocatedStorage']} GB")
    print(f"Engine:                {instance['Engine']} {instance['EngineVersion']}")
    print(f"Multi-AZ:              {instance['MultiAZ']}")

    # Get parameter group details
    param_group = instance['DBParameterGroups'][0]['DBParameterGroupName']
    print(f"Parameter Group:       {param_group}")

    # Get parameters
    pg_response = rds.describe_db_parameters(DBParameterGroupName=param_group)
    print("\n" + "=" * 80)
    print("TIMEOUT & PERFORMANCE PARAMETERS")
    print("=" * 80)

    key_params = [
        'statement_timeout',
        'work_mem',
        'shared_buffers',
        'max_connections',
        'effective_cache_size',
        'random_page_cost',
        'idle_in_transaction_session_timeout'
    ]

    for param in pg_response['Parameters']:
        if param['ParameterName'] in key_params:
            val = param.get('ParameterValue', param.get('DefaultValue', 'N/A'))
            source = param.get('Source', '')
            print(f"{param['ParameterName']:<40} {val:<20} ({source})")

    # Check RDS Proxy settings
    print("\n" + "=" * 80)
    print("RDS PROXY CONFIGURATION")
    print("=" * 80)

    try:
        proxy_response = rds.describe_db_proxies()
        found = False
        for proxy in proxy_response['DBProxies']:
            if 'algo' in proxy['DBProxyName']:
                found = True
                print(f"Proxy Name:            {proxy['DBProxyName']}")
                print(f"Status:                {proxy['Status']}")
                print(f"Max Idle Connections:  {proxy['MaxIdleConnectionsPercent']}%")
                print(f"Max Connections:       {proxy['MaxConnectionsPercent']}%")

                # Get proxy targets
                targets = rds.describe_db_proxy_targets(DBProxyName=proxy['DBProxyName'])
                print(f"\nTargets:")
                for target in targets['Targets']:
                    print(f"  - {target['Endpoint']} ({target['Type']})")

        if not found:
            print("No RDS proxy found with 'algo' in name")

    except Exception as e:
        print(f"Error checking proxy: {str(e)}")

    # Check recent metric values
    print("\n" + "=" * 80)
    print("CURRENT RDS METRICS (CloudWatch)")
    print("=" * 80)

    cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

    metrics_to_check = [
        ('DatabaseConnections', 'Count'),
        ('CPUUtilization', 'Percent'),
        ('FreeableMemory', 'Bytes'),
        ('ReadLatency', 'Milliseconds'),
        ('WriteLatency', 'Milliseconds'),
        ('DiskQueueDepth', 'Count'),
    ]

    from datetime import datetime, timedelta

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=10)

    for metric_name, unit in metrics_to_check:
        try:
            response = cloudwatch.get_metric_statistics(
                Namespace='AWS/RDS',
                MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': 'algo-db'}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,
                Statistics=['Average', 'Maximum']
            )

            if response['Datapoints']:
                latest = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])[-1]
                avg = latest.get('Average', 'N/A')
                max_val = latest.get('Maximum', 'N/A')
                print(f"{metric_name:<30} Avg: {avg:>8} | Max: {max_val:>8}")
            else:
                print(f"{metric_name:<30} No data in last 10 minutes")

        except Exception as e:
            print(f"{metric_name:<30} Error: {str(e)[:40]}")

if __name__ == '__main__':
    check_rds_config()
