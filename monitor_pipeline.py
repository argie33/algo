import boto3
import time
import sys

client = boto3.client('stepfunctions', region_name='us-east-1')
execution_arn = 'arn:aws:states:us-east-1:626216981288:execution:algo-computed-metrics-pipeline-dev:manual-metrics-20260716-220504'

print("[*] Monitoring computed metrics pipeline...\n")

while True:
    response = client.describe_execution(executionArn=execution_arn)
    status = response['status']

    print(f"Status: {status} | Duration: {(time.time() - response['startDate'].timestamp()):.0f}s", end='\r')

    if status in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
        print(f"\n[OK] Execution {status}\n")

        if status != 'SUCCEEDED':
            print("Output/Error:")
            print(response.get('cause', 'No error details'))
        else:
            print("Pipeline completed successfully!")
            print(f"Started: {response['startDate']}")
            if 'stopDate' in response:
                print(f"Completed: {response['stopDate']}")
        sys.exit(0 if status == 'SUCCEEDED' else 1)

    time.sleep(5)
