
# Fetch AWS account ID dynamically
data "aws_caller_identity" "current" {}
# Fetch default VPC for the account/region
data "aws_vpc" "default" {
  default = true
}
# Consolidated locals for account-wide settings
locals {
  organization    = var.organization
  project         = var.project
  # Set region directly here: "ap-south-1" for Mumbai or "ap-south-2" for Hyderabad
  account_region  = "ap-south-1" # Change to "ap-south-2" for Hyderabad if needed
  environment     = var.environment
  account_id      = data.aws_caller_identity.current.account_id
  default_vpc_id  = data.aws_vpc.default.id
}
output "default_vpc_id" {
  value = local.default_vpc_id
}

