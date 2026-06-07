# ============================================================
# VPC Module - Networking Foundation
# ============================================================

# ============================================================
# 1. VPC & Core Network
# ============================================================

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-vpc"
  })
}

# Internet Gateway for public subnets
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-igw"
  })
}

# ============================================================
# 2. Public Subnets (Bastion, NAT endpoints, etc.)
# ============================================================

resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-public-subnet-${count.index + 1}"
    Tier = "Public"
  })
}

# Public route table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-public-rt"
  })
}

# Default route: IGW
resource "aws_route" "public_igw" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

# Associate public subnets with public route table
resource "aws_route_table_association" "public" {
  count          = length(var.public_subnet_cidrs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ============================================================
# NAT Gateway for Private Subnet Internet Access
# ============================================================

# Elastic IP for NAT Gateway
resource "aws_eip" "nat" {
  count  = length(var.public_subnet_cidrs) >= 1 ? 1 : 0
  domain = "vpc"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-nat-eip"
  })

  depends_on = [aws_internet_gateway.main]
}

# NAT Gateway in first public subnet
resource "aws_nat_gateway" "main" {
  count         = length(var.public_subnet_cidrs) >= 1 ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-nat"
  })

  depends_on = [aws_internet_gateway.main]
}

# Route from private subnets to NAT Gateway (internet access)
resource "aws_route" "private_nat" {
  count                  = length(var.public_subnet_cidrs) >= 1 ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main[0].id
}

# ============================================================
# 3. Private Subnets (RDS, ECS, Lambda)
# ============================================================

resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-private-subnet-${count.index + 1}"
    Tier = "Private"
  })
}

# Private route table (no IGW route)
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-private-rt"
  })
}

# Associate private subnets with private route table
resource "aws_route_table_association" "private" {
  count          = length(var.private_subnet_cidrs)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ============================================================
# 4. Security Groups
# ============================================================

# Bastion Host Security Group
resource "aws_security_group" "bastion" {
  count       = var.bastion_sg_enabled ? 1 : 0
  name        = "${var.project_name}-bastion-sg"
  description = "Security group for Bastion host"
  vpc_id      = aws_vpc.main.id

  # Egress: allow all outbound (for package updates, RDS access, etc.)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"] #tfsec:ignore:aws-ec2-no-public-egress-sgr
    description = "Allow all outbound traffic"
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-bastion-sg"
  })
}

# ECS Tasks Security Group
resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "Security group for ECS tasks (private)"
  vpc_id      = aws_vpc.main.id

  # Egress: DNS for hostname resolution to VPC resolver
  egress {
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow DNS queries (UDP) to VPC DNS resolver"
  }

  # Egress: HTTPS to VPC endpoints for ECR, Secrets Manager, S3, CloudWatch Logs
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow HTTPS to VPC endpoints (ECR, Secrets Manager, S3, CloudWatch)"
  }

  # Egress: PostgreSQL to RDS
  egress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow PostgreSQL to RDS"
  }

  # Egress: HTTPS to external APIs (yfinance, IEX Cloud, Alpaca, FRED, etc.) via NAT Gateway
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] #tfsec:ignore:aws-ec2-no-public-egress-sgr
    description = "Allow HTTPS to external APIs (yfinance, Alpaca, FRED, etc.)"
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-ecs-tasks-sg"
  })
}

# API Lambda Security Group
resource "aws_security_group" "api_lambda" {
  name        = "${var.project_name}-api-lambda-sg"
  description = "Security group for API Lambda function (REST API)"
  vpc_id      = aws_vpc.main.id

  # Egress: allow DNS (UDP port 53) for hostname resolution - allow to VPC DNS resolver
  egress {
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow DNS queries (UDP) to VPC DNS resolver"
  }

  # Egress: allow DNS (TCP port 53) for hostname resolution - allow to VPC DNS resolver
  egress {
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow DNS queries (TCP) to VPC DNS resolver"
  }

  # Egress: allow HTTPS to VPC endpoints for Secrets Manager, CloudWatch Logs, SNS
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow HTTPS to VPC endpoints (Secrets Manager, CloudWatch Logs, SNS)"
  }

  # Egress: allow HTTPS to internet for Cognito JWT validation via NAT Gateway.
  # The cognito-idp VPC endpoint service is not available in all AZs; NAT Gateway is the fallback.
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] #tfsec:ignore:aws-ec2-no-public-egress-sgr
    description = "Allow HTTPS to internet for Cognito JWT validation via NAT Gateway"
  }

  # Egress: allow PostgreSQL to RDS
  egress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow PostgreSQL to RDS"
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-api-lambda-sg"
  })
}

# Algo Lambda Security Group
resource "aws_security_group" "algo_lambda" {
  name        = "${var.project_name}-algo-lambda-sg"
  description = "Security group for Algo Lambda function (orchestrator)"
  vpc_id      = aws_vpc.main.id

  # Egress: allow DNS (UDP port 53) for hostname resolution - allow to VPC DNS resolver
  egress {
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow DNS queries (UDP) to VPC DNS resolver"
  }

  # Egress: allow DNS (TCP port 53) for hostname resolution - allow to VPC DNS resolver
  egress {
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow DNS queries (TCP) to VPC DNS resolver"
  }

  # Egress: allow HTTPS to VPC endpoints for Secrets Manager, CloudWatch Logs, SNS
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow HTTPS to VPC endpoints (Secrets Manager, CloudWatch Logs, SNS)"
  }

  # Egress: allow PostgreSQL to RDS
  egress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow PostgreSQL to RDS"
  }

  # Egress: allow HTTPS to external internet for Alpaca API calls
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] #tfsec:ignore:aws-ec2-no-public-egress-sgr
    description = "Allow HTTPS to external internet (Alpaca API)"
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-algo-lambda-sg"
  })
}

# RDS Security Group - managed via separate aws_security_group_rule resources
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = aws_vpc.main.id

  # NOTE: RDS never initiates outbound connections, only receives inbound.
  # No egress rules needed. All egress is implicitly denied.

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-rds-sg"
  })

  depends_on = [aws_security_group.ecs_tasks, aws_security_group.api_lambda, aws_security_group.algo_lambda]

  lifecycle {
    ignore_changes = [ingress]
  }
}

# RDS Security Group Rules: allow PostgreSQL from different sources
resource "aws_security_group_rule" "rds_from_ecs_tasks" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.ecs_tasks.id
  description              = "Allow PostgreSQL from ECS tasks"
}

resource "aws_security_group_rule" "rds_from_api_lambda" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.api_lambda.id
  description              = "Allow PostgreSQL from API Lambda"
}

resource "aws_security_group_rule" "rds_from_algo_lambda" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.algo_lambda.id
  description              = "Allow PostgreSQL from Algo Lambda"
}

resource "aws_security_group_rule" "rds_from_bastion" {
  count                    = var.bastion_sg_enabled ? 1 : 0
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.bastion[0].id
  description              = "Allow PostgreSQL from Bastion"
}

# Note: Circuit breaker Lambda SG is created in monitoring module and added here via Terraform
# This allows the circuit breaker to query portfolio P&L without being in the RDS SG

resource "aws_security_group_rule" "rds_self_postgres" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.rds.id
  description              = "Allow PostgreSQL from RDS security group (db-init Lambda)"
}

# VPC Endpoints Security Group (for services in private subnets to reach AWS services)
resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.project_name}-vpc-endpoints-sg"
  description = "Security group for VPC Endpoints"
  vpc_id      = aws_vpc.main.id

  # Ingress: allow DNS (port 53) from private subnets
  ingress {
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow DNS TCP from VPC (Route 53 Resolver)"
  }

  ingress {
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow DNS UDP from VPC (Route 53 Resolver)"
  }

  # Ingress: allow HTTPS from private subnets
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
    description = "Allow HTTPS from VPC (for AWS service endpoints)"
  }

  # Egress: allow all outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"] #tfsec:ignore:aws-ec2-no-public-egress-sgr
    description = "Allow all outbound traffic"
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-vpc-endpoints-sg"
  })
}

# ============================================================
# 5. VPC Endpoints (Gateway & Interface)
# ============================================================

# S3 Gateway Endpoint (no cost, no security group needed)
resource "aws_vpc_endpoint" "s3" {
  count             = var.enable_vpc_endpoints ? 1 : 0
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-s3-endpoint"
  })
}

# DynamoDB Gateway Endpoint (no cost, for future use)
resource "aws_vpc_endpoint" "dynamodb" {
  count             = var.enable_vpc_endpoints ? 1 : 0
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-dynamodb-endpoint"
  })
}

# Secrets Manager Interface Endpoint
resource "aws_vpc_endpoint" "secretsmanager" {
  count               = var.enable_vpc_endpoints ? 1 : 0
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  subnet_ids          = aws_subnet.private[*].id
  private_dns_enabled = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-secretsmanager-endpoint"
  })
}

# ECR API Interface Endpoint
resource "aws_vpc_endpoint" "ecr_api" {
  count               = var.enable_vpc_endpoints ? 1 : 0
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.ecr.api"
  vpc_endpoint_type   = "Interface"
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  subnet_ids          = aws_subnet.private[*].id
  private_dns_enabled = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-ecr-api-endpoint"
  })
}

# ECR DKR (Docker) Interface Endpoint
resource "aws_vpc_endpoint" "ecr_dkr" {
  count               = var.enable_vpc_endpoints ? 1 : 0
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.ecr.dkr"
  vpc_endpoint_type   = "Interface"
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  subnet_ids          = aws_subnet.private[*].id
  private_dns_enabled = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-ecr-dkr-endpoint"
  })
}

# CloudWatch Logs Interface Endpoint
resource "aws_vpc_endpoint" "logs" {
  count               = var.enable_vpc_endpoints ? 1 : 0
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.logs"
  vpc_endpoint_type   = "Interface"
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  subnet_ids          = aws_subnet.private[*].id
  private_dns_enabled = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-logs-endpoint"
  })
}

# SNS Interface Endpoint (for Lambda alerts from private subnet)
resource "aws_vpc_endpoint" "sns" {
  count               = var.enable_vpc_endpoints ? 1 : 0
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.sns"
  vpc_endpoint_type   = "Interface"
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  subnet_ids          = aws_subnet.private[*].id
  private_dns_enabled = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-sns-endpoint"
  })
}

# Route 53 Resolver Endpoint - Critical for DNS resolution in private subnets
resource "aws_vpc_endpoint" "route53_resolver" {
  count               = var.enable_vpc_endpoints ? 1 : 0
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.route53resolver"
  vpc_endpoint_type   = "Interface"
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  subnet_ids          = aws_subnet.private[*].id
  private_dns_enabled = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-route53resolver-endpoint"
  })
}

# Cognito IDP Interface Endpoint - Required for Lambda JWT validation in private subnets.
# Without this endpoint, Lambdas in private VPC subnets cannot reach cognito-idp.us-east-1.amazonaws.com
# causing 30-second timeouts on every protected API request -> 503 errors at API Gateway.
# The Lambda SG already allows HTTPS to VPC CIDR (10.0.0.0/16); VPC endpoint ENIs use private IPs
# within the VPC, so no security group changes are needed.
resource "aws_vpc_endpoint" "cognito_idp" {
  # Disabled: cognito-idp endpoint service not available in all AZs of this region.
  # Lambda JWT validation works via NAT Gateway as fallback. Re-enable after verifying
  # supported AZs with: aws ec2 describe-vpc-endpoint-services --service-names com.amazonaws.us-east-1.cognito-idp
  count               = 0
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.cognito-idp"
  vpc_endpoint_type   = "Interface"
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  subnet_ids          = aws_subnet.private[*].id
  private_dns_enabled = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cognito-idp-endpoint"
  })
}
