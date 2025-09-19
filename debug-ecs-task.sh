#!/bin/bash
# Debug script for ECS task failures

echo "=== ECS Task Debug Script ==="
echo "Looking for failed info loader tasks..."

# Get the most recent task for info loader
echo "1. Getting most recent loadinfo task..."
TASK_ARN=$(aws ecs list-tasks --cluster stocks-cluster --family loadinfo-task --desired-status STOPPED --query 'taskArns[0]' --output text --region us-east-1)

if [ "$TASK_ARN" = "None" ] || [ -z "$TASK_ARN" ]; then
    echo "❌ No stopped tasks found. Checking running tasks..."
    TASK_ARN=$(aws ecs list-tasks --cluster stocks-cluster --family loadinfo-task --query 'taskArns[0]' --output text --region us-east-1)
fi

echo "📋 Most recent task: $TASK_ARN"

if [ "$TASK_ARN" = "None" ] || [ -z "$TASK_ARN" ]; then
    echo "❌ No tasks found at all!"
    echo "Available task families:"
    aws ecs list-task-definitions --family-prefix load --region us-east-1 --query 'taskDefinitionArns[*]' --output text
    exit 1
fi

# Get task details
echo -e "\n2. Getting task details..."
aws ecs describe-tasks --cluster stocks-cluster --tasks $TASK_ARN --region us-east-1 --query 'tasks[0].{
    exitCode: containers[0].exitCode,
    reason: containers[0].reason,
    stoppedReason: stoppedReason,
    lastStatus: lastStatus,
    createdAt: createdAt,
    startedAt: startedAt,
    stoppedAt: stoppedAt,
    containerName: containers[0].name
}' --output table

# Get CloudWatch logs
echo -e "\n3. Getting CloudWatch logs..."
CONTAINER_NAME=$(aws ecs describe-tasks --cluster stocks-cluster --tasks $TASK_ARN --region us-east-1 --query 'tasks[0].containers[0].name' --output text)
TASK_ID=$(echo $TASK_ARN | cut -d'/' -f3)

LOG_GROUP="/ecs/loadinfo-task"
LOG_STREAM="$CONTAINER_NAME/$CONTAINER_NAME/$TASK_ID"

echo "📄 Log Group: $LOG_GROUP"
echo "📄 Log Stream: $LOG_STREAM"

echo -e "\n4. Checking if log stream exists..."
aws logs describe-log-streams --log-group-name "$LOG_GROUP" --log-stream-name-prefix "$CONTAINER_NAME" --region us-east-1 --query 'logStreams[*].logStreamName' --output text

echo -e "\n5. Getting logs (last 50 events)..."
aws logs get-log-events --log-group-name "$LOG_GROUP" --log-stream-name "$LOG_STREAM" --region us-east-1 --start-from-head --output text --query 'events[*].[timestamp,message]' | tail -50

echo -e "\n6. If no logs found, checking alternative log stream patterns..."
aws logs describe-log-streams --log-group-name "$LOG_GROUP" --region us-east-1 --order-by LastEventTime --descending --max-items 5 --query 'logStreams[*].{name: logStreamName, lastEvent: lastEventTime}' --output table

echo -e "\n=== Debug Complete ==="