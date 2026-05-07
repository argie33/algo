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
  echo "=== AGGRESSIVELY Deleting VPC: $VPC_ID ==="

  # Delete all Load Balancers (ALB, NLB, ELB)
  echo "  Deleting Load Balancers..."
  aws elbv2 describe-load-balancers --region $REGION --query "LoadBalancers[?VpcId=='$VPC_ID'].LoadBalancerArn" --output text 2>/dev/null | while read ARN; do
    [ -n "$ARN" ] && aws elbv2 delete-load-balancer --load-balancer-arn $ARN --region $REGION 2>/dev/null || true
  done

  # Delete classic load balancers
  aws elb describe-load-balancers --region $REGION --query "LoadBalancerDescriptions[?VPCId=='$VPC_ID'].LoadBalancerName" --output text 2>/dev/null | while read LB; do
    [ -n "$LB" ] && aws elb delete-load-balancer --load-balancer-name $LB --region $REGION 2>/dev/null || true
  done

  # Delete RDS instances
  echo "  Deleting RDS instances..."
  aws rds describe-db-instances --region $REGION --query "DBInstances[?DBSubnetGroup.VpcSecurityGroups[?Status=='active']].DBInstanceIdentifier" --output text 2>/dev/null | while read DB; do
    [ -n "$DB" ] && aws rds delete-db-instance --db-instance-identifier $DB --skip-final-snapshot --region $REGION 2>/dev/null || true
  done

  # Delete ElastiCache clusters
  echo "  Deleting ElastiCache clusters..."
  aws elasticache describe-cache-clusters --region $REGION --query "CacheClusters[?Engine!=''].CacheClusterId" --output text 2>/dev/null | while read CC; do
    if [ -n "$CC" ]; then
      SG=$(aws elasticache describe-cache-clusters --cache-cluster-id $CC --region $REGION --query "CacheClusters[0].SecurityGroups[0].GroupId" --output text 2>/dev/null || echo "")
      if [[ "$SG" == sg-* ]]; then
        VPC=$(aws ec2 describe-security-groups --group-ids $SG --region $REGION --query "SecurityGroups[0].VpcId" --output text 2>/dev/null || echo "")
        [ "$VPC" == "$VPC_ID" ] && aws elasticache delete-cache-cluster --cache-cluster-id $CC --region $REGION 2>/dev/null || true
      fi
    fi
  done

  # Delete VPC peering connections
  echo "  Deleting VPC peering connections..."
  aws ec2 describe-vpc-peering-connections --region $REGION --filters "Name=requester-vpc-info.vpc-id,Values=$VPC_ID" --query "VpcPeeringConnections[?Status.Code!='rejected'].VpcPeeringConnectionId" --output text 2>/dev/null | while read PEER; do
    [ -n "$PEER" ] && aws ec2 delete-vpc-peering-connection --vpc-peering-connection-id $PEER --region $REGION 2>/dev/null || true
  done

  # Delete customer gateways and VPN connections
  echo "  Deleting VPN connections..."
  aws ec2 describe-vpn-connections --region $REGION --filters "Name=vpc-id,Values=$VPC_ID" --query "VpnConnections[*].VpnConnectionId" --output text 2>/dev/null | while read VPN; do
    [ -n "$VPN" ] && aws ec2 delete-vpn-connection --vpn-connection-id $VPN --region $REGION 2>/dev/null || true
  done

  # Delete VPC endpoints
  echo "  Deleting VPC endpoints..."
  aws ec2 describe-vpc-endpoints --region $REGION --query "VpcEndpoints[?VpcId=='$VPC_ID'].VpcEndpointId" --output text 2>/dev/null | while read VPCE; do
    [ -n "$VPCE" ] && aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $VPCE --region $REGION 2>/dev/null || true
  done

  # Delete all EC2 instances
  echo "  Terminating all EC2 instances..."
  aws ec2 describe-instances --region $REGION --filters "Name=vpc-id,Values=$VPC_ID" "Name=instance-state-name,Values=running,stopped,pending,stopping" --query "Reservations[*].Instances[*].InstanceId" --output text 2>/dev/null | while read INST; do
    [ -n "$INST" ] && aws ec2 terminate-instances --instance-ids $INST --region $REGION 2>/dev/null || true
  done

  # Wait for instances to terminate
  sleep 5

  # Release all Elastic IPs
  echo "  Releasing Elastic IPs..."
  aws ec2 describe-addresses --region $REGION --query "Addresses[?Domain=='vpc'].AllocationId" --output text 2>/dev/null | while read EIP; do
    [ -n "$EIP" ] && aws ec2 release-address --allocation-id $EIP --region $REGION 2>/dev/null || true
  done

  # Delete NAT Gateways
  echo "  Deleting NAT Gateways..."
  aws ec2 describe-nat-gateways --region $REGION --query "NatGateways[?VpcId=='$VPC_ID' && State=='available'].NatGatewayId" --output text 2>/dev/null | while read NGW; do
    [ -n "$NGW" ] && aws ec2 delete-nat-gateway --nat-gateway-id $NGW --region $REGION 2>/dev/null || true
  done
  sleep 5

  # Delete Network Interfaces
  echo "  Deleting network interfaces..."
  aws ec2 describe-network-interfaces --region $REGION --query "NetworkInterfaces[?VpcId=='$VPC_ID'].NetworkInterfaceId" --output text 2>/dev/null | while read ENI; do
    if [ -n "$ENI" ]; then
      # Detach if attached
      ATTACH=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI --region $REGION --query "NetworkInterfaces[0].Attachment.AttachmentId" --output text 2>/dev/null || echo "None")
      [ "$ATTACH" != "None" ] && [ -n "$ATTACH" ] && aws ec2 detach-network-interface --attachment-id $ATTACH --region $REGION 2>/dev/null || true
      sleep 1
      aws ec2 delete-network-interface --network-interface-id $ENI --region $REGION 2>/dev/null || true
    fi
  done

  # Delete subnets
  echo "  Deleting subnets..."
  aws ec2 describe-subnets --region $REGION --query "Subnets[?VpcId=='$VPC_ID'].SubnetId" --output text 2>/dev/null | while read SUBNET; do
    [ -n "$SUBNET" ] && aws ec2 delete-subnet --subnet-id $SUBNET --region $REGION 2>/dev/null || true
  done

  # Delete Internet Gateways
  echo "  Deleting Internet Gateways..."
  aws ec2 describe-internet-gateways --region $REGION --query "InternetGateways[?Attachments[?VpcId=='$VPC_ID']].InternetGatewayId" --output text 2>/dev/null | while read IGW; do
    if [ -n "$IGW" ]; then
      aws ec2 detach-internet-gateway --internet-gateway-id $IGW --vpc-id $VPC_ID --region $REGION 2>/dev/null || true
      aws ec2 delete-internet-gateway --internet-gateway-id $IGW --region $REGION 2>/dev/null || true
    fi
  done

  # Delete route tables
  echo "  Deleting route tables..."
  aws ec2 describe-route-tables --region $REGION --query "RouteTables[?VpcId=='$VPC_ID' && !Associations[0].Main].RouteTableId" --output text 2>/dev/null | while read RT; do
    [ -n "$RT" ] && aws ec2 delete-route-table --route-table-id $RT --region $REGION 2>/dev/null || true
  done

  # Delete security groups
  echo "  Deleting security groups..."
  for ATTEMPT in {1..5}; do
    aws ec2 describe-security-groups --region $REGION --query "SecurityGroups[?VpcId=='$VPC_ID' && GroupName!='default'].GroupId" --output text 2>/dev/null | while read SG; do
      [ -n "$SG" ] && aws ec2 delete-security-group --group-id $SG --region $REGION 2>/dev/null || true
    done
    sleep 1
  done

  # Finally, delete the VPC
  echo "  Deleting VPC..."
  if aws ec2 delete-vpc --vpc-id $VPC_ID --region $REGION 2>/dev/null; then
    echo "  ✅ Successfully deleted $VPC_ID"
  else
    echo "  ❌ FAILED to delete $VPC_ID"
    echo "     Attempting to diagnose remaining dependencies..."

    # Try to identify what's still blocking
    aws ec2 describe-vpc-endpoints --region $REGION --query "VpcEndpoints[?VpcId=='$VPC_ID'].VpcEndpointId" --output text 2>/dev/null | grep -q . && echo "     - VPC Endpoints still exist"
    aws ec2 describe-nat-gateways --region $REGION --query "NatGateways[?VpcId=='$VPC_ID'].NatGatewayId" --output text 2>/dev/null | grep -q . && echo "     - NAT Gateways still exist"
    aws ec2 describe-network-interfaces --region $REGION --query "NetworkInterfaces[?VpcId=='$VPC_ID'].NetworkInterfaceId" --output text 2>/dev/null | grep -q . && echo "     - Network Interfaces still exist"
    aws ec2 describe-security-groups --region $REGION --query "SecurityGroups[?VpcId=='$VPC_ID'].GroupId" --output text 2>/dev/null | grep -q . && echo "     - Security Groups still exist"
  fi
done

echo ""
echo "=== VPC Deletion Complete ==="
VPC_COUNT=$(aws ec2 describe-vpcs --region $REGION --query 'length(Vpcs)' --output text 2>/dev/null || echo "unknown")
echo "Final VPC count: $VPC_COUNT/5"
