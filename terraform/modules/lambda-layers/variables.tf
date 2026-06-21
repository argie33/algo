variable "project_name" {
  description = "Project name for naming Lambda layers"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "orchestrator_layer_enabled" {
  description = "Whether orchestrator Lambda layer exists (built by GitHub Actions)"
  type        = bool
  default     = false
}

variable "api_layer_enabled" {
  description = "Whether API Lambda layer exists (built by GitHub Actions)"
  type        = bool
  default     = false
}
