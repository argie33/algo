# ============================================================
# Root Module - Backend Configuration
# ============================================================
# NOTE: For initial deployment, you may need to:
# 1. Create S3 bucket: stocks-terraform-state-dev
# 2. Create DynamoDB table: stocks-terraform-locks
# 3. Or temporarily use local backend (see below)
#
# To bootstrap the state bucket, run:
#   aws s3api create-bucket --bucket stocks-terraform-state-dev --region us-east-1
#   aws dynamodb create-table --table-name stocks-terraform-locks \
#     --attribute-definitions AttributeName=LockID,AttributeType=S \
#     --key-schema AttributeName=LockID,KeyType=HASH \
#     --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5
# ============================================================

terraform {
  # S3 backend for remote state management
  # Configuration provided via -backend-config flags during init
  backend "s3" {
    # bucket = "stocks-terraform-state-{ACCOUNT_ID}-us-east-1"
    # key = "stocks/terraform.tfstate"
    # region = "us-east-1"
    # encrypt = true
  }
}
