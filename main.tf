
# ============================================================================
#  CHAT HISTORY DYNAMODB TABLE
# ============================================================================
resource "aws_dynamodb_table" "chat_history" {
  name         = "chat-history"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"
  attribute {
    name = "session_id"
    type = "S"
  }
  tags = var.common_tags
}
# ============================================================================
#  S3 BUCKET FOR USER DOCUMENTS
# ============================================================================
module "bot_documents_bucket" {
  source        = "../platform/modules/s3"
  organization  = var.organization
  project       = var.project
  environment   = var.environment
  purpose       = "bot-documents"
  force_destroy = true
  common_tags   = var.common_tags
}
# ============================================================================
#  LLM LAMBDA ECR REPOSITORY
# ============================================================================
resource "aws_ecr_repository" "llm_lambda" {
  name                 = var.ecr_repository
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = var.common_tags
}
# ============================================================================
#  S3 BUCKET FOR CONFIG STORAGE (using platform module)
# ============================================================================
module "config_bucket" {
  source        = "../platform/modules/s3"
  organization  = var.organization
  project       = var.project
  environment   = var.environment
  purpose       = "config"
  bucket_name   = var.config_bucket_name  # Optional: override default naming
  force_destroy = true
  common_tags   = var.common_tags
}
# ============================================================================
#  DOCUMENT METADATA DYNAMODB TABLE
# ============================================================================
resource "aws_dynamodb_table" "metadata" {
  name         = "document-metadata"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "content_hash"
  attribute {
    name = "content_hash"
    type = "S"
  }
  tags = var.common_tags
}
# ============================================================================
#  LLM LAMBDA FUNCTION (using platform lambda module)
# ============================================================================
module "llm_lambda" {
  source                = "../platform/modules/docker_lambda"
  organization          = var.organization
  project               = var.project
  environment           = var.environment
  purpose               = "llm"
  image_uri             = "${aws_ecr_repository.llm_lambda.repository_url}:latest"
  memory_size           = 512
  timeout               = 30
  environment_variables = merge({
    CONFIG_BUCKET = module.config_bucket.bucket_id
    CONFIG_KEY    = "config.yaml"
    GOOGLE_API_KEY_SECRET  = "google-api-key-secret-name"
    GROQ_API_KEY_SECRET    = "groq-api-key-secret-name"
    OPENAI_API_KEY_SECRET  = "openai-api-key-secret-name"
    BEDROCK_API_KEY_SECRET = "bedrock-api-key-secret-name"
    CHAT_HISTORY_TABLE     = aws_dynamodb_table.chat_history.name
    METADATA_TABLE         = aws_dynamodb_table.metadata.name
  }, {})
  custom_policy_arns    = []
  common_tags           = var.common_tags
}
