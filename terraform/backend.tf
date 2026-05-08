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
  backend "s3" {
    bucket         = "stocks-terraform-state"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "stocks-terraform-locks"
    encrypt        = true
  }

  # Alternative: uncomment for local testing (do NOT use in production)
  # backend "local" {
  #   path = ".terraform/state/dev/terraform.tfstate"
  # }
}
