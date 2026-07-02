terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0, < 7.0"
    }
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = ">= 1.15"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

provider "postgresql" {
  host            = module.database.rds_address
  port            = module.database.rds_port
  database        = module.database.rds_database_name
  username        = module.database.rds_username
  password        = module.database.rds_password
  sslmode         = "require"
  connect_timeout = 15
}
