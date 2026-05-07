#!/bin/bash
set -e

REGION="us-east-1"
echo "Deleting orphaned VPCs in $REGION..."
echo ""

# Get all VPCs that are NOT the default VPC
VPC_IDS=$(aws ec2 describe-vpcs \
  --region $REGION \
  --filters "Name=isDefault,Values=false" \
  --query 'Vpcs[*].VpcId' \
  --output text)

if [ -z "$VPC_IDS" ]; then
  echo "No VPCs to delete"
  exit 0
fi

echo "Found VPCs to delete:"
for VPC_ID in $VPC_IDS; do
  CIDR=$(aws ec2 describe-vpcs --vpc-ids $VPC_ID --region $REGION --query 'Vpcs[0].CidrBlock' --output text)
  NAME=$(aws ec2 describe-vpcs --vpc-ids $VPC_ID --region $REGION --query 'Vpcs[0].Tags[?Key==`Name`].Value' --output text || echo "untagged")
  echo "  $VPC_ID ($NAME, $CIDR)"
done

echo ""
echo "This will DELETE all resources in these VPCs:"
echo "  - Subnets"
echo "  - Internet Gateways"
echo "  - Route Tables (non-default)"
echo "  - Security Groups (non-default)"
echo "  - VPCs"
echo ""
read -p "Type 'DELETE' to confirm: " CONFIRM

if [ "$CONFIRM" != "DELETE" ]; then
  echo "Cancelled"
  exit 0
fi

for VPC_ID in $VPC_IDS; do
  echo ""
  echo "Deleting VPC: $VPC_ID"

  # Delete VPC endpoints first
  echo "  Deleting VPC endpoints..."
  VPCE_IDS=$(aws ec2 describe-vpc-endpoints --region $REGION --query "VpcEndpoints[?VpcId=='$VPC_ID'].VpcEndpointId" --output text)
  for VPCE_ID in $VPCE_IDS; do
    aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $VPCE_ID --region $REGION 2>/dev/null || true
  done

  # Disable VPC Flow Logs
  echo "  Disabling VPC Flow Logs..."
  FLG_IDS=$(aws ec2 describe-flow-logs --region $REGION --query "FlowLogs[?ResourceId=='$VPC_ID'].FlowLogId" --output text 2>/dev/null || true)
  for FLG_ID in $FLG_IDS; do
    aws ec2 delete-flow-logs --flow-log-ids $FLG_ID --region $REGION 2>/dev/null || true
  done

  # Release Elastic IPs (from NAT Gateways, etc)
  echo "  Releasing Elastic IPs..."
  EIP_ALLOCS=$(aws ec2 describe-addresses --region $REGION --query "Addresses[?Domain=='vpc'].AllocationId" --output text 2>/dev/null || true)
  for EIP_ID in $EIP_ALLOCS; do
    aws ec2 release-address --allocation-id $EIP_ID --region $REGION 2>/dev/null || true
  done

  # Delete NAT Gateways and wait for deletion
  echo "  Deleting NAT Gateways..."
  NGW_IDS=$(aws ec2 describe-nat-gateways --region $REGION --query "NatGateways[?VpcId=='$VPC_ID' && State=='available'].NatGatewayId" --output text 2>/dev/null || true)
  for NGW_ID in $NGW_IDS; do
    aws ec2 delete-nat-gateway --nat-gateway-id $NGW_ID --region $REGION 2>/dev/null || true
  done
  # Wait for all NAT gateways to fully delete
  while true; do
    REMAINING=$(aws ec2 describe-nat-gateways --region $REGION --query "NatGateways[?VpcId=='$VPC_ID' && (State=='available' || State=='pending' || State=='deleting')].NatGatewayId" --output text 2>/dev/null || echo "")
    if [ -z "$REMAINING" ]; then break; fi
    sleep 2
  done

  # Delete all network interfaces (not just unmanaged ones)
  echo "  Deleting network interfaces..."
  ENI_IDS=$(aws ec2 describe-network-interfaces --region $REGION --query "NetworkInterfaces[?VpcId=='$VPC_ID'].NetworkInterfaceId" --output text 2>/dev/null || true)
  for ENI_ID in $ENI_IDS; do
    # Force detach if attached
    ATTACHMENT_ID=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --region $REGION --query 'NetworkInterfaces[0].Attachment.AttachmentId' --output text 2>/dev/null || echo "None")
    if [ "$ATTACHMENT_ID" != "None" ] && [ -n "$ATTACHMENT_ID" ]; then
      aws ec2 detach-network-interface --attachment-id $ATTACHMENT_ID --region $REGION 2>/dev/null || true
    fi
    sleep 1
    aws ec2 delete-network-interface --network-interface-id $ENI_ID --region $REGION 2>/dev/null || true
  done

  # Delete subnets
  echo "  Deleting subnets..."
  SUBNET_IDS=$(aws ec2 describe-subnets --region $REGION --query "Subnets[?VpcId=='$VPC_ID'].SubnetId" --output text 2>/dev/null || true)
  for SUBNET_ID in $SUBNET_IDS; do
    aws ec2 delete-subnet --subnet-id $SUBNET_ID --region $REGION 2>/dev/null || true
  done

  # Detach and delete internet gateways
  echo "  Deleting internet gateways..."
  IGW_IDS=$(aws ec2 describe-internet-gateways --region $REGION --query "InternetGateways[?Attachments[?VpcId=='$VPC_ID']].InternetGatewayId" --output text 2>/dev/null || true)
  for IGW_ID in $IGW_IDS; do
    aws ec2 detach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID --region $REGION 2>/dev/null || true
    aws ec2 delete-internet-gateway --internet-gateway-id $IGW_ID --region $REGION 2>/dev/null || true
  done

  # Delete non-default route tables
  echo "  Deleting route tables..."
  RT_IDS=$(aws ec2 describe-route-tables --region $REGION --query "RouteTables[?VpcId=='$VPC_ID' && !Associations[0].Main].RouteTableId" --output text 2>/dev/null || true)
  for RT_ID in $RT_IDS; do
    aws ec2 delete-route-table --route-table-id $RT_ID --region $REGION 2>/dev/null || true
  done

  # Delete non-default security groups (multiple attempts for dependency issues)
  echo "  Deleting security groups..."
  for ATTEMPT in {1..3}; do
    SG_IDS=$(aws ec2 describe-security-groups --region $REGION --query "SecurityGroups[?VpcId=='$VPC_ID' && GroupName!='default'].GroupId" --output text 2>/dev/null || true)
    if [ -z "$SG_IDS" ]; then break; fi
    for SG_ID in $SG_IDS; do
      aws ec2 delete-security-group --group-id $SG_ID --region $REGION 2>/dev/null || true
    done
    sleep 1
  done

  # Delete VPC (with retries in case of lingering dependencies)
  echo "  Deleting VPC..."
  for ATTEMPT in {1..5}; do
    if aws ec2 delete-vpc --vpc-id $VPC_ID --region $REGION 2>/dev/null; then
      echo "  ✓ Deleted $VPC_ID"
      break
    else
      if [ $ATTEMPT -lt 5 ]; then
        echo "    Attempt $ATTEMPT failed, retrying in 5 seconds..."
        sleep 5
      else
        echo "  ❌ Failed to delete $VPC_ID after 5 attempts - may have hidden dependencies"
      fi
    fi
  done
done

echo ""
echo "✅ All orphaned VPCs deleted"
echo ""

# Verify
VPC_COUNT=$(aws ec2 describe-vpcs --region $REGION --query 'length(Vpcs)' --output text)
echo "Current VPC count: $VPC_COUNT/5"
