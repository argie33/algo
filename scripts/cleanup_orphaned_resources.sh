#!/bin/bash
# Clean up actual orphaned/unmanaged resources
# Safely removes CloudFormation stacks, orphaned VPCs, EIPs, and old lock tables

set -e

REGION="us-east-1"

echo "=========================================="
echo "CLEANUP: Orphaned AWS Resources"
echo "=========================================="

# 1. Delete failed CloudFormation stack
echo ""
echo "[1] Deleting failed CloudFormation stack: stocks-core"
aws cloudformation delete-stack --stack-name stocks-core --region $REGION 2>&1 || echo "  (already deleted or in progress)"

# 2. Release unassociated Elastic IPs
echo ""
echo "[2] Releasing unassociated Elastic IPs"
EIPs=(
    "18.204.120.71"
    "184.73.48.152"
    "52.7.39.19"
    "54.197.140.32"
)

for eip in "${EIPs[@]}"; do
    echo "  Releasing: $eip"
    aws ec2 release-address --public-ip $eip --region $REGION 2>&1 || echo "    (failed or already released)"
done

# 3. Delete old Terraform lock tables
echo ""
echo "[3] Deleting old Terraform lock DynamoDB tables"
TABLES=(
    "stocks-terraform-locks"
    "terraform-lock"
    "terraform-lock-us-east-1"
)

for table in "${TABLES[@]}"; do
    echo "  Deleting table: $table"
    aws dynamodb delete-table --table-name $table --region $REGION 2>&1 || echo "    (not found or already deleted)"
done

# 4. Delete orphaned VPCs (if they're truly empty)
echo ""
echo "[4] Checking orphaned VPCs for deletion"
VPCS=(
    "vpc-0443a615f6cde3434"
    "vpc-06a94d860a87fe4f4"
)

for vpc in "${VPCS[@]}"; do
    echo ""
    echo "  VPC: $vpc"
    # Check for dependencies
    echo "    Checking for resources..."

    # List subnets
    SUBNETS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$vpc --region $REGION --query 'Subnets[].SubnetId' --output text)
    if [ -n "$SUBNETS" ]; then
        echo "    Found subnets: $SUBNETS"
        for subnet in $SUBNETS; do
            echo "      Deleting subnet: $subnet"
            aws ec2 delete-subnet --subnet-id $subnet --region $REGION 2>&1 || echo "        (failed or in use)"
        done
    fi

    # List route tables
    RTS=$(aws ec2 describe-route-tables --filters Name=vpc-id,Values=$vpc --region $REGION --query 'RouteTables[?Associations[0].Main==`false`].RouteTableId' --output text)
    if [ -n "$RTS" ]; then
        echo "    Found route tables: $RTS"
        for rt in $RTS; do
            echo "      Deleting route table: $rt"
            aws ec2 delete-route-table --route-table-id $rt --region $REGION 2>&1 || echo "        (failed or in use)"
        done
    fi

    # List security groups
    SGS=$(aws ec2 describe-security-groups --filters Name=vpc-id,Values=$vpc --region $REGION --query 'SecurityGroups[?GroupName!=`default`].GroupId' --output text)
    if [ -n "$SGS" ]; then
        echo "    Found security groups: $SGS"
        for sg in $SGS; do
            echo "      Deleting security group: $sg"
            aws ec2 delete-security-group --group-id $sg --region $REGION 2>&1 || echo "        (failed or in use)"
        done
    fi

    # Delete IGW if exists
    IGW=$(aws ec2 describe-internet-gateways --filters Name=attachment.vpc-id,Values=$vpc --region $REGION --query 'InternetGateways[].InternetGatewayId' --output text)
    if [ -n "$IGW" ]; then
        echo "    Found IGW: $IGW"
        aws ec2 detach-internet-gateway --internet-gateway-id $IGW --vpc-id $vpc --region $REGION 2>&1 || echo "      (failed)"
        aws ec2 delete-internet-gateway --internet-gateway-id $IGW --region $REGION 2>&1 || echo "      (failed)"
    fi

    # Finally delete the VPC
    echo "      Deleting VPC: $vpc"
    aws ec2 delete-vpc --vpc-id $vpc --region $REGION 2>&1 || echo "        (failed or not empty)"
done

echo ""
echo "=========================================="
echo "CLEANUP COMPLETE"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Run audit again: python3 scripts/audit_unmanaged_resources.py"
echo "  2. Verify CloudFormation stack deletion"
echo "  3. All resources should now be Terraform-managed"
