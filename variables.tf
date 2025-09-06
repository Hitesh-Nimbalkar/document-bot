variable "common_tags" {
  type    = map(string)
  default = {
    Project     = "chatbot-document-v2"
    Environment = "dev"
    Owner       = "msumani"
    ManagedBy   = "Terraform"
  }
}

variable "organization" {
  type    = string
  default = "org"
}

variable "project" {
  type    = string
  default = "chatbot-document-v2"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "config_bucket_name" {
  type    = string
  default = "chatbot-document-v2-config"
}

variable "ecr_repository" {
  type    = string
  default = "chatbot-document-v2-llm-lambda"
 }