#!/bin/bash
set -e

REGION="us-east-1"
echo "Deleting orphaned VPCs in $REGION..."

# Get all non-default VPCs
VPC_IDS=$(aws ec2 describe-vpcs --region $REGION --filters "Name=isDefault,Values=false" --query 'Vpcs[*].VpcId' --output text 2>/dev/null || echo "")

if [ -z "$VPC_IDS" ]; then
  echo "✅ No VPCs to delete"
  exit 0
fi

echo "Found VPCs to delete:"
for VPC_ID in $VPC_IDS; do
  CIDR=$(aws ec2 describe-vpcs --vpc-ids $VPC_ID --region $REGION --query 'Vpcs[0].CidrBlock' --output text 2>/dev/null || echo "unknown")
  echo "  $VPC_ID ($CIDR)"
done
echo ""
read -p "Type 'DELETE' to confirm: " CONFIRM

if [ "$CONFIRM" != "DELETE" ]; then
  echo "Cancelled"
  exit 0
fi

for VPC_ID in $VPC_IDS; do
  echo ""
  echo "=== Deleting VPC: $VPC_ID ==="

  # List and delete all EC2 instances
  INSTANCE_IDS=$(aws ec2 describe-instances --region $REGION --filters "Name=vpc-id,Values=$VPC_ID" "Name=instance-state-name,Values=running,stopped" --query 'Reservations[*].Instances[*].InstanceId' --output text 2>/dev/null || echo "")
  if [ -n "$INSTANCE_IDS" ]; then
    echo "  Terminating EC2 instances..."
    for INSTANCE_ID in $INSTANCE_IDS; do
      aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION 2>/dev/null || true
    done
    echo "  Waiting for instances to terminate..."
    for INSTANCE_ID in $INSTANCE_IDS; do
      aws ec2 wait instance-terminated --instance-ids $INSTANCE_ID --region $REGION 2>/dev/null || true
    done
  fi

  # Delete VPC endpoints
  echo "  Deleting VPC endpoints..."
  VPCE_IDS=$(aws ec2 describe-vpc-endpoints --region $REGION --query "VpcEndpoints[?VpcId=='$VPC_ID'].VpcEndpointId" --output text 2>/dev/null || echo "")
  for VPCE_ID in $VPCE_IDS; do
    aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $VPCE_ID --region $REGION 2>/dev/null || true
  done

  # Delete NAT Gateways and release their Elastic IPs
  echo "  Deleting NAT Gateways..."
  NGWS=$(aws ec2 describe-nat-gateways --region $REGION --query "NatGateways[?VpcId=='$VPC_ID'].{Id:NatGatewayId,EipAlloc:SubnetId}" --output text 2>/dev/null || echo "")
  NGW_IDS=$(echo "$NGWS" | awk '{print $1}')
  for NGW_ID in $NGW_IDS; do
    aws ec2 delete-nat-gateway --nat-gateway-id $NGW_ID --region $REGION 2>/dev/null || true
  done
  sleep 3

  # Release all Elastic IPs in this VPC
  echo "  Releasing Elastic IPs..."
  EIP_ALLOCS=$(aws ec2 describe-addresses --region $REGION --query "Addresses[?Domain=='vpc'].AllocationId" --output text 2>/dev/null || echo "")
  for EIP_ID in $EIP_ALLOCS; do
    aws ec2 release-address --allocation-id $EIP_ID --region $REGION 2>/dev/null || true
  done

  # Delete all network interfaces
  echo "  Deleting network interfaces..."
  ENI_IDS=$(aws ec2 describe-network-interfaces --region $REGION --query "NetworkInterfaces[?VpcId=='$VPC_ID'].NetworkInterfaceId" --output text 2>/dev/null || echo "")
  for ENI_ID in $ENI_IDS; do
    ATTACHMENT=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --region $REGION --query 'NetworkInterfaces[0].Attachment.AttachmentId' --output text 2>/dev/null || echo "")
    if [ "$ATTACHMENT" != "None" ] && [ -n "$ATTACHMENT" ]; then
      aws ec2 detach-network-interface --attachment-id $ATTACHMENT --region $REGION 2>/dev/null || true
      sleep 1
    fi
    aws ec2 delete-network-interface --network-interface-id $ENI_ID --region $REGION 2>/dev/null || true
  done

  # Delete subnets
  echo "  Deleting subnets..."
  SUBNET_IDS=$(aws ec2 describe-subnets --region $REGION --query "Subnets[?VpcId=='$VPC_ID'].SubnetId" --output text 2>/dev/null || echo "")
  for SUBNET_ID in $SUBNET_IDS; do
    aws ec2 delete-subnet --subnet-id $SUBNET_ID --region $REGION 2>/dev/null || true
  done

  # Delete Internet Gateways
  echo "  Deleting Internet Gateways..."
  IGW_IDS=$(aws ec2 describe-internet-gateways --region $REGION --query "InternetGateways[?Attachments[?VpcId=='$VPC_ID']].InternetGatewayId" --output text 2>/dev/null || echo "")
  for IGW_ID in $IGW_IDS; do
    aws ec2 detach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID --region $REGION 2>/dev/null || true
    aws ec2 delete-internet-gateway --internet-gateway-id $IGW_ID --region $REGION 2>/dev/null || true
  done

  # Delete route tables
  echo "  Deleting route tables..."
  RT_IDS=$(aws ec2 describe-route-tables --region $REGION --query "RouteTables[?VpcId=='$VPC_ID' && !Associations[0].Main].RouteTableId" --output text 2>/dev/null || echo "")
  for RT_ID in $RT_IDS; do
    aws ec2 delete-route-table --route-table-id $RT_ID --region $REGION 2>/dev/null || true
  done

  # Delete all security groups
  echo "  Deleting security groups..."
  for ATTEMPT in {1..3}; do
    SG_IDS=$(aws ec2 describe-security-groups --region $REGION --query "SecurityGroups[?VpcId=='$VPC_ID' && GroupName!='default'].GroupId" --output text 2>/dev/null || echo "")
    if [ -z "$SG_IDS" ]; then break; fi
    for SG_ID in $SG_IDS; do
      aws ec2 delete-security-group --group-id $SG_ID --region $REGION 2>/dev/null || true
    done
    sleep 1
  done

  # Delete the VPC
  echo "  Deleting VPC..."
  aws ec2 delete-vpc --vpc-id $VPC_ID --region $REGION 2>/dev/null && echo "  ✓ Deleted $VPC_ID" || echo "  ⚠ Failed to delete $VPC_ID (may have hidden dependencies)"
done

echo ""
echo "=== VPC Deletion Complete ==="
VPC_COUNT=$(aws ec2 describe-vpcs --region $REGION --query 'length(Vpcs)' --output text 2>/dev/null || echo "unknown")
echo "Current VPC count: $VPC_COUNT/5"
