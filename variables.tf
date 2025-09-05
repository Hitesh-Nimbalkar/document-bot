
# ============================================================================
#  VARIABLES FOR LLM LAMBDA ECR REPOSITORY
# ============================================================================
variable "ecr_repository" {
  description = "Name of the ECR repository for LLM Lambda."
  type        = string
}
variable "common_tags" {
  description = "Common tags to apply to all resources."
  type        = map(string)
  default     = {
    Project     = "chatbot-document-v2"
    Environment = "dev"
    Owner       = "your-team-or-name"
    ManagedBy   = "Terraform"
  }
}
# ============================================================================
#  VARIABLES FOR CONFIG S3 BUCKET MODULE
# ============================================================================
variable "organization" {
  description = "Organization name (platform-level constant)"
  type        = string
  default     = "your-org"
}
variable "project" {
  description = "Project name (project-specific input)"
  type        = string
  default     = "chatbot-document-v2"
}
variable "environment" {
  description = "Environment name (platform-level managed)"
  type        = string
  default     = "dev"
}
variable "config_bucket_name" {
  description = "Name of the S3 bucket for config storage (optional)"
  type        = string
  default     = null
}
