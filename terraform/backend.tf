# ============================================================
# Root Module - Backend Configuration
# ============================================================
# State bucket must exist before first apply:
#   aws s3api create-bucket --bucket stocks-terraform-state --region us-east-1
#   aws s3api put-bucket-versioning --bucket stocks-terraform-state \
#     --versioning-configuration Status=Enabled
#
# deploy-all-infrastructure.yml passes backend config via -backend-config flags:
#   bucket  = stocks-terraform-state
#   key     = stocks/terraform.tfstate
#   region  = us-east-1
#   encrypt = true
# ============================================================

terraform {
  backend "s3" {}
}
