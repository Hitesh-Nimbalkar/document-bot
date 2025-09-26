

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
  source        = "git::https://github.com/Hitesh-Nimbalkar/aws-platform.git//modules/s3?ref=v0.0.1"
  organization  = var.organization
  project       = var.project
  environment   = var.environment
  purpose       = "config"
  bucket_name   = var.config_bucket_name  # Optional: override default naming
  force_destroy = true
  common_tags   = var.common_tags
}
# # ============================================================================
# #  DOCUMENT METADATA DYNAMODB TABLE
# # ============================================================================
resource "aws_dynamodb_table" "metadata" {
  name         = "document-metadata"
  billing_mode = "PAY_PER_REQUEST"
  # Primary key = document_id (unique per file)
  hash_key     = "document_id"
  attribute {
    name = "document_id"
    type = "S"
  }
  # Attribute for content_hash (used in GSI)
  attribute {
    name = "content_hash"
    type = "S"
  }
  # Global Secondary Index for content_hash lookups
  global_secondary_index {
    name            = "content_hash-index"
    hash_key        = "content_hash"
    projection_type = "ALL"
  }
  tags = var.common_tags
}
#============================================================================
#  LLM LAMBDA FUNCTION (using platform lambda module)
# ============================================================================
module "llm_lambda" {
  source                = "git::https://github.com/Hitesh-Nimbalkar/aws-platform.git//modules/docker_lambda?ref=v0.0.7"
  organization          = var.organization
  project               = var.project
  environment           = var.environment
  purpose               = "llm"
  image_uri             = "${aws_ecr_repository.llm_lambda.repository_url}:0.0.1"
  memory_size           = 512
  timeout               = 30
  environment_variables = merge({
    # S3 Configuration
    CONFIG_BUCKET          = module.config_bucket.bucket_id
    CONFIG_KEY             = "config/config.yaml"
    DOCUMENTS_S3_BUCKET    = module.config_bucket.bucket_id
    TEMP_DATA_KEY          = "project_data/uploads/temp"
    DOCUMENTS_DATA_KEY     = "project_data/uploads/documents"
    
    # DynamoDB Tables
    CHAT_HISTORY_TABLE     = aws_dynamodb_table.chat_history.name
    METADATA_TABLE         = aws_dynamodb_table.metadata.name
    
    # Vector Database Configuration (Qdrant)
    VECTOR_DB_HOST         = "28b2ee72-9fc9-4ecd-acdf-d024c1c7bf5d.eu-west-1-0.aws.cloud.qdrant.io"
    VECTOR_DB_PORT         = "6333"
    VECTOR_DB_API_KEY      = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.U6PprcKnZl1ByQCBOurGp-ObPUmn0hKaUeZtenYEQ_8"
    COLLECTION_NAME        = "Demo"
    VECTOR_DIMENSION       = "1024"
    
    # API Key Secrets (for AWS Secrets Manager)
    # GOOGLE_API_KEY_SECRET  = "google-api-key-secret-name"
    # GROQ_API_KEY_SECRET    = "groq-api-key-secret-name"
    # OPENAI_API_KEY_SECRET  = "openai-api-key-secret-name"
    # BEDROCK_API_KEY_SECRET = "bedrock-api-key-secret-name"
  }, {})
  
  # Add required IAM policies
  custom_policy_arns = [
    aws_iam_policy.lambda_dynamodb_policy.arn,
    aws_iam_policy.lambda_s3_policy.arn
  ]
  
  common_tags = var.common_tags
}
# ============================================================================


# -----------------------------------------------------
# Upload config.yaml into the new config bucket
# -----------------------------------------------------
resource "aws_s3_object" "config_file" {
  bucket = module.config_bucket.bucket_id     # new bucket created above
  key    = "config/config.yaml"               # object path in bucket
  source = "${path.module}/s3/config/config.yaml"  # local file path
  etag   = filemd5("${path.module}/s3/config/config.yaml")
  depends_on = [module.config_bucket]         # ensures bucket is created first
}

# -----------------------------
# IAM Policy for DynamoDB access
# -----------------------------
resource "aws_iam_policy" "lambda_dynamodb_policy" {
  name        = "LambdaDynamoDBPolicy"
  description = "Allow Lambda to access chat history and metadata tables"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.chat_history.arn,
          aws_dynamodb_table.metadata.arn
        ]
      }
    ]
  })
}
# -----------------------------
# IAM Policy for S3 access
# -----------------------------
resource "aws_iam_policy" "lambda_s3_policy" {
  name        = "LambdaS3AccessPolicy"
  description = "Allow Lambda full access to the documents bucket"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          module.config_bucket.bucket_arn,
          "${module.config_bucket.bucket_arn}/*"
        ]
      }
    ]
  })
}
resource "aws_iam_user_policy" "allow_assume_lambda_role" {
  name = "allow-assume-lambda-role"
  user = "HiteshNimbalkar"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = "arn:aws:iam::454842419567:role/org-dev-chatbot-document-v2-lambda-llm_lambda_test-role"
      }
    ]
  })
}
# ===============================
# API GATEWAY MODULE
# ===============================
module "api_gateway" {
  source       = "git::https://github.com/Hitesh-Nimbalkar/aws-platform.git//modules/api_gateway?ref=v0.0.7"
  aws_region   = local.account_region
  organization = var.organization
  environment  = var.environment
  project      = var.project
  purpose      = "document-portal"
  stage_name = "dev"
  endpoints = [
    {
      path                     = "ingest_data"
      http_method              = "POST"
      integration_type         = "AWS_PROXY"
      integration_uri          = module.llm_lambda.lambda_invoke_arn
      integration_http_method  = "POST"
    },
    {
      path                     = "doc_compare"
      http_method              = "POST"
      integration_type         = "AWS_PROXY"
      integration_uri          = module.llm_lambda.lambda_invoke_arn
      integration_http_method  = "POST"
    }
  ]
  common_tags = var.common_tags
}
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.llm_lambda.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${module.api_gateway.api_gateway_execution_arn}/*/*"
}
# ===============================
# AMPLIFY MODULE (with base_directory)
# ===============================
module "amplify_ui" {
  source        = "git::https://github.com/Hitesh-Nimbalkar/aws-platform.git//modules/amplify?ref=v0.0.7"
  organization  = var.organization
  environment   = var.environment
  project       = var.project
  purpose       = "ui"
  # GitHub connection
  repo_url     = "https://github.com/Hitesh-Nimbalkar/document-bot"
  branch_name  = "main"
  framework    = "Web"
  stage        = "DEVELOPMENT"
  github_token = null   # if using Amplify GitHub App
  enable_auto_build = false
  # Deploy only /ui folder
  base_directory = "/ui"
  # Inject backend API URL into frontend
  environment_variables = {
    API_URL = module.api_gateway.invoke_url
  }
  custom_rules = []
  tags         = var.common_tags
}
# ===============================
# OUTPUTS
# ===============================
output "api_gateway_url" {
  value = module.api_gateway.invoke_url
}
output "amplify_ui_url" {
  value = module.amplify_ui.amplify_branch_url
}
