#!/usr/bin/env python3
import boto3
from datetime import datetime, timezone

# Get EventBridge Scheduler client
scheduler = boto3.client('scheduler', region_name='us-east-1')

try:
    # List schedules
    print('=== EVENTBRIDGE SCHEDULER RULES ===')
    response = scheduler.list_schedules(MaxResults=20)

    for schedule in response.get('Schedules', []):
        name = schedule['Name']
        if 'computed' in name.lower() or 'growth' in name.lower() or 'metrics' in name.lower():
            print(f'\nSchedule: {name}')
            print(f'  Expression: {schedule.get("ScheduleExpression", "N/A")}')
            print(f'  Timezone: {schedule.get("ScheduleExpressionTimezone", "N/A")}')
            print(f'  State: {schedule.get("State", "N/A")}')

            # Get detailed schedule info
            try:
                detail_response = scheduler.get_schedule(Name=name)
                print(f'  LastModification: {detail_response.get("LastModificationDate", "N/A")}')
            except:
                pass

except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
