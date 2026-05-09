# ============================================================
# DEPRECATED: This module is orphaned and should not be used
# ============================================================
# WARNING: This module duplicates resources from the services module
# (Lambda, API Gateway, CloudFront, Cognito, S3)
# Do NOT instantiate this module in root main.tf
# Use the services module instead for all REST API/web resources
#
# These outputs are deprecated - the webapp module is no longer maintained
# All resources should come from the services module

output "deprecated_notice" {
  value       = "WARNING: webapp module is deprecated and duplicates services module resources. Do not use."
  description = "Deprecation notice for webapp module"
}
