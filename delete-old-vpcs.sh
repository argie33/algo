#!/bin/bash
set -u

REGION="us-east-1"
FAILED_VPCS=""
echo "Deleting orphaned VPCs in $REGION..."

VPC_IDS=$(aws ec2 describe-vpcs --region $REGION --filters "Name=isDefault,Values=false" --query 'Vpcs[*].VpcId' --output text 2>/dev/null || echo "")

if [ -z "$VPC_IDS" ]; then
  echo "✅ No VPCs to delete"
  exit 0
fi

echo "Found VPCs: $VPC_IDS"

# In CI environment (GitHub Actions), skip confirmation prompt
if [ -z "${GITHUB_ACTIONS:-}" ]; then
  read -p "Type 'DELETE' to confirm: " CONFIRM
  if [ "$CONFIRM" != "DELETE" ]; then
    echo "Cancelled"
    exit 0
  fi
else
  echo "Running in GitHub Actions - proceeding with deletion"
fi

for VPC_ID in $VPC_IDS; do
  echo ""
  echo "=== Deleting VPC: $VPC_ID ==="

  # Delete Load Balancers
  echo "  Deleting Load Balancers..."
  aws elbv2 describe-load-balancers --region $REGION --query "LoadBalancers[?VpcId=='$VPC_ID'].LoadBalancerArn" --output text 2>/dev/null | while read ARN; do
    [ -n "$ARN" ] && aws elbv2 delete-load-balancer --load-balancer-arn $ARN --region $REGION 2>/dev/null || true
  done

  # Delete RDS instances (filter by VPC)
  echo "  Deleting RDS instances..."
  aws rds describe-db-instances --region $REGION --query "DBInstances[?DBSubnetGroup.VpcId=='$VPC_ID'].DBInstanceIdentifier" --output text 2>/dev/null | while read DB; do
    [ -n "$DB" ] && aws rds delete-db-instance --db-instance-identifier $DB --skip-final-snapshot --region $REGION 2>/dev/null || true
  done

  # Delete ElastiCache (filter by VPC)
  echo "  Deleting ElastiCache..."
  aws elasticache describe-cache-clusters --region $REGION --query "CacheClusters[?CacheSubnetGroupName].CacheClusterId" --output text 2>/dev/null | while read CC; do
    if [ -n "$CC" ]; then
      SUBNET_GROUP=$(aws elasticache describe-cache-clusters --cache-cluster-id $CC --region $REGION --query "CacheClusters[0].CacheSubnetGroupName" --output text 2>/dev/null)
      if [ -n "$SUBNET_GROUP" ]; then
        SG_VPC=$(aws elasticache describe-cache-subnet-groups --cache-subnet-group-name "$SUBNET_GROUP" --region $REGION --query "CacheSubnetGroups[0].VpcId" --output text 2>/dev/null)
        [ "$SG_VPC" = "$VPC_ID" ] && aws elasticache delete-cache-cluster --cache-cluster-id $CC --region $REGION 2>/dev/null || true
      fi
    fi
  done

  # Delete VPC peering (filter by target VPC)
  echo "  Deleting VPC peering..."
  aws ec2 describe-vpc-peering-connections --region $REGION --query "VpcPeeringConnections[?RequesterVpcInfo.VpcId=='$VPC_ID' || AccepterVpcInfo.VpcId=='$VPC_ID'].VpcPeeringConnectionId" --output text 2>/dev/null | while read PEER; do
    [ -n "$PEER" ] && aws ec2 delete-vpc-peering-connection --vpc-peering-connection-id $PEER --region $REGION 2>/dev/null || true
  done

  # Delete VPN connections (filter by target VPC)
  echo "  Deleting VPN connections..."
  aws ec2 describe-vpn-gateways --region $REGION --query "VpnGateways[?VpcAttachments[?VpcId=='$VPC_ID']].VpnGatewayId" --output text 2>/dev/null | while read VGW; do
    if [ -n "$VGW" ]; then
      aws ec2 detach-vpn-gateway --vpn-gateway-id $VGW --vpc-id $VPC_ID --region $REGION 2>/dev/null || true
      aws ec2 delete-vpn-gateway --vpn-gateway-id $VGW --region $REGION 2>/dev/null || true
    fi
  done
  aws ec2 describe-vpn-connections --region $REGION --filters "Name=type,Values=ipsec.1" --query "VpnConnections[*].VpnConnectionId" --output text 2>/dev/null | while read VPN; do
    [ -n "$VPN" ] && aws ec2 delete-vpn-connection --vpn-connection-id $VPN --region $REGION 2>/dev/null || true
  done

  # Delete VPC endpoints
  echo "  Deleting VPC endpoints..."
  aws ec2 describe-vpc-endpoints --region $REGION --query "VpcEndpoints[?VpcId=='$VPC_ID'].VpcEndpointId" --output text 2>/dev/null | while read VPCE; do
    [ -n "$VPCE" ] && aws ec2 delete-vpc-endpoints --vpc-endpoint-ids $VPCE --region $REGION 2>/dev/null || true
  done

  # Terminate EC2 instances
  echo "  Terminating EC2 instances..."
  aws ec2 describe-instances --region $REGION --filters "Name=vpc-id,Values=$VPC_ID" "Name=instance-state-name,Values=running,stopped,pending,stopping" --query "Reservations[*].Instances[*].InstanceId" --output text 2>/dev/null | while read INST; do
    [ -n "$INST" ] && aws ec2 terminate-instances --instance-ids $INST --region $REGION 2>/dev/null || true
  done
  sleep 5

  # Release EIPs (filter by VPC)
  echo "  Releasing Elastic IPs..."
  aws ec2 describe-addresses --region $REGION --query "Addresses[?Domain=='vpc' && AssociationId!=null && NetworkInterfaceOwnerId!=null].AllocationId" --output text 2>/dev/null | while read EIP; do
    if [ -n "$EIP" ]; then
      # Check if EIP is in target VPC
      ENI=$(aws ec2 describe-addresses --region $REGION --allocation-ids $EIP --query "Addresses[0].NetworkInterfaceId" --output text 2>/dev/null)
      if [ -n "$ENI" ] && [ "$ENI" != "None" ]; then
        ENI_VPC=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI --region $REGION --query "NetworkInterfaces[0].VpcId" --output text 2>/dev/null)
        if [ "$ENI_VPC" = "$VPC_ID" ]; then
          aws ec2 release-address --allocation-id $EIP --region $REGION 2>/dev/null || true
        fi
      fi
    fi
  done

  # Delete NAT Gateways
  echo "  Deleting NAT Gateways..."
  aws ec2 describe-nat-gateways --region $REGION --query "NatGateways[?VpcId=='$VPC_ID' && State=='available'].NatGatewayId" --output text 2>/dev/null | while read NGW; do
    [ -n "$NGW" ] && aws ec2 delete-nat-gateway --nat-gateway-id $NGW --region $REGION 2>/dev/null || true
  done
  sleep 5

  # Delete ENIs
  echo "  Deleting network interfaces..."
  aws ec2 describe-network-interfaces --region $REGION --query "NetworkInterfaces[?VpcId=='$VPC_ID'].NetworkInterfaceId" --output text 2>/dev/null | while read ENI; do
    if [ -n "$ENI" ]; then
      ATTACH=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI --region $REGION --query "NetworkInterfaces[0].Attachment.AttachmentId" --output text 2>/dev/null || echo "")
      [ -n "$ATTACH" ] && [ "$ATTACH" != "None" ] && aws ec2 detach-network-interface --attachment-id $ATTACH --region $REGION 2>/dev/null || true
      sleep 1
      aws ec2 delete-network-interface --network-interface-id $ENI --region $REGION 2>/dev/null || true
    fi
  done

  # Delete subnets
  echo "  Deleting subnets..."
  aws ec2 describe-subnets --region $REGION --query "Subnets[?VpcId=='$VPC_ID'].SubnetId" --output text 2>/dev/null | while read SUBNET; do
    [ -n "$SUBNET" ] && aws ec2 delete-subnet --subnet-id $SUBNET --region $REGION 2>/dev/null || true
  done

  # Delete IGWs
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

  # Delete SG rules FIRST using a Python script (handles all rule types safely)
  echo "  Clearing security group rules..."
  SG_IDS=$(aws ec2 describe-security-groups --region $REGION --query "SecurityGroups[?VpcId=='$VPC_ID' && GroupName!='default'].GroupId" --output text 2>/dev/null || echo "")

  python3 << EOFPYTHON
import json, subprocess, sys, os
region = os.environ.get('REGION', 'us-east-1')
sg_ids = "$SG_IDS".split()

for sg_id in sg_ids:
    if not sg_id:
        continue

    try:
        result = subprocess.run(['aws', 'ec2', 'describe-security-groups',
                                '--group-ids', sg_id, '--region', region, '--output', 'json'],
                               capture_output=True, text=True, check=True)
        sg_data = json.loads(result.stdout)

        # Revoke all ingress rules
        ingress_rules = sg_data['SecurityGroups'][0].get('IpPermissions', [])
        if ingress_rules:
            subprocess.run(['aws', 'ec2', 'revoke-security-group-ingress',
                           '--group-id', sg_id, '--region', region,
                           '--cli-input-json', json.dumps({'IpPermissions': ingress_rules})],
                          capture_output=True)

        # Revoke all egress rules
        egress_rules = sg_data['SecurityGroups'][0].get('IpPermissionsEgress', [])
        if egress_rules:
            subprocess.run(['aws', 'ec2', 'revoke-security-group-egress',
                           '--group-id', sg_id, '--region', region,
                           '--cli-input-json', json.dumps({'IpPermissions': egress_rules})],
                          capture_output=True)
    except Exception as e:
        print(f"  Skipping SG {sg_id}: {e}", file=sys.stderr)
EOFPYTHON


  echo "  Deleting security groups..."
  for SG_ID in $SG_IDS; do
    aws ec2 delete-security-group --group-id $SG_ID --region $REGION 2>/dev/null || true
  done

  # Finally delete the VPC (with detailed error info)
  echo "  Deleting VPC..."
  VPC_DELETE_ERROR=$(aws ec2 delete-vpc --vpc-id $VPC_ID --region $REGION 2>&1)
  if [ $? -eq 0 ]; then
    echo "  ✅ Deleted $VPC_ID"
  else
    echo "  ❌ FAILED to delete $VPC_ID"
    echo "    Error: $VPC_DELETE_ERROR"
    FAILED_VPCS="$FAILED_VPCS $VPC_ID"

    # Show remaining resources in this VPC
    echo "    Diagnosing blocking resources..."

    INST_COUNT=$(aws ec2 describe-instances --region $REGION --filters "Name=vpc-id,Values=$VPC_ID" "Name=instance-state-name,Values=running,stopped,pending,stopping" --query "length(Reservations[*].Instances[*][])" --output text 2>/dev/null || echo "0")
    [ "$INST_COUNT" -gt 0 ] && echo "      ⚠️  $INST_COUNT EC2 instances still running/stopped"

    ENI_COUNT=$(aws ec2 describe-network-interfaces --region $REGION --filters "Name=vpc-id,Values=$VPC_ID" --query "length(NetworkInterfaces)" --output text 2>/dev/null || echo "0")
    [ "$ENI_COUNT" -gt 0 ] && echo "      ⚠️  $ENI_COUNT network interfaces still attached"

    SG_COUNT=$(aws ec2 describe-security-groups --region $REGION --filters "Name=vpc-id,Values=$VPC_ID" --query "length(SecurityGroups)" --output text 2>/dev/null || echo "0")
    [ "$SG_COUNT" -gt 0 ] && echo "      ⚠️  $SG_COUNT security groups still exist"

    SUBNET_COUNT=$(aws ec2 describe-subnets --region $REGION --filters "Name=vpc-id,Values=$VPC_ID" --query "length(Subnets)" --output text 2>/dev/null || echo "0")
    [ "$SUBNET_COUNT" -gt 0 ] && echo "      ⚠️  $SUBNET_COUNT subnets still exist"
  fi
done

echo ""
VPC_COUNT=$(aws ec2 describe-vpcs --region $REGION --query 'length(Vpcs)' --output text 2>/dev/null || echo "unknown")
echo "Final VPC count: $VPC_COUNT/5"

if [ -n "$FAILED_VPCS" ]; then
  echo "❌ Failed to delete VPCs:$FAILED_VPCS"
  exit 1
fi

if [ "$VPC_COUNT" -lt 5 ]; then
  echo "✅ Ready for deployment"
  exit 0
else
  echo "❌ Still at VPC limit ($VPC_COUNT/5)"
  exit 1
fi
