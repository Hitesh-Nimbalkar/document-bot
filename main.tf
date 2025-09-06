
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
# module "bot_documents_bucket" {
#   source        = "git::https://github.com/Hitesh-Nimbalkar/aws-platform.git//modules/s3?ref=v0.0.1"
#   organization  = var.organization
#   project       = var.project
#   environment   = var.environment
#   purpose       = "bot-documents"
#   force_destroy = true
#   common_tags   = var.common_tags
# }


module "layers_bucket" {
  source        = "git::https://github.com/Hitesh-Nimbalkar/aws-platform.git//modules/s3?ref=v0.0.1"
  organization  = var.organization
  project       = var.project
  environment   = var.environment
  purpose       = "my-lambda-layers-bucket"
  force_destroy = true
  common_tags   = var.common_tags
}
# # ============================================================================
# #  LLM LAMBDA ECR REPOSITORY
# # ============================================================================
# resource "aws_ecr_repository" "llm_lambda" {
#   name                 = var.ecr_repository
#   image_tag_mutability = "MUTABLE"
#   image_scanning_configuration {
#     scan_on_push = true
#   }
#   tags = var.common_tags
# }
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
  hash_key     = "content_hash"
  attribute {
    name = "content_hash"
    type = "S"
  }
  tags = var.common_tags
}
# ============================================================================
# #  LLM LAMBDA FUNCTION (using platform lambda module)
# # ============================================================================
# module "llm_lambda" {
#   source                = "git::https://github.com/Hitesh-Nimbalkar/aws-platform.git//modules/docker_lambda?ref=v0.0.1"
#   organization          = var.organization
#   project               = var.project
#   environment           = var.environment
#   purpose               = "llm"
#   image_uri             = "${aws_ecr_repository.llm_lambda.repository_url}:0.0.1"
#   memory_size           = 512
#   timeout               = 30
#   environment_variables = merge({
#     CONFIG_BUCKET = module.config_bucket.bucket_id
#     CONFIG_KEY    = "config.yaml"
#     GOOGLE_API_KEY_SECRET  = "google-api-key-secret-name"
#     GROQ_API_KEY_SECRET    = "groq-api-key-secret-name"
#     OPENAI_API_KEY_SECRET  = "openai-api-key-secret-name"
#     BEDROCK_API_KEY_SECRET = "bedrock-api-key-secret-name"
#   #  CHAT_HISTORY_TABLE     = aws_dynamodb_table.chat_history.name
#    # METADATA_TABLE         = aws_dynamodb_table.metadata.name
#   }, {})
#   custom_policy_arns    = []
#   common_tags           = var.common_tags
# }
# # ============================================================================


# =============================================================================
# Lambda Module: CloudWatch Logs Backup
# =============================================================================

# # Zip the Lambda code
# data "archive_file" "llm_lambda_zip" {
#   type        = "zip"
#   source_dir  = "${path.module}/Lambda/llm_lambda"  # your folder
#   output_path = "${path.module}/build/llm_lambda_deployment.zip"
# }
# module "llm_lambda" {
#   source       = "git::https://github.com/Hitesh-Nimbalkar/aws-platform.git//modules/lambda?ref=v0.0.1"
#   organization = var.organization
#   environment  = var.environment
#   project      = var.project
#   purpose      = "llm_lambda"

#   # ZIP deployment
#   zip_file_path  = data.archive_file.llm_lambda_zip.output_path
#   lambda_handler = "lambda_handler.lambda_handler"
#   lambda_runtime = "python3.11"

#   memory_size = 256
#   timeout     = 900

#   environment_variables = merge({
#     CONFIG_BUCKET           = module.config_bucket.bucket_id
#     CONFIG_KEY              = "config.yaml"
#     GOOGLE_API_KEY_SECRET   = "google-api-key-secret-name"
#     GROQ_API_KEY_SECRET     = "groq-api-key-secret-name"
#     OPENAI_API_KEY_SECRET   = "openai-api-key-secret-name"
#     BEDROCK_API_KEY_SECRET  = "bedrock-api-key-secret-name"
#     # CHAT_HISTORY_TABLE     = aws_dynamodb_table.chat_history.name
#     # METADATA_TABLE         = aws_dynamodb_table.metadata.name
#   }, {})

#   policy_arns = {}  # Add IAM policies if needed

#   tags = var.common_tags
# }

# -----------------------------------------------------
# Create a new bucket for configs
# -----------------------------------------------------
# module "project_bucket" {
#   source        = "git::https://github.com/Hitesh-Nimbalkar/aws-platform.git//modules/s3?ref=v0.0.1"
#   organization  = var.organization
#   project       = var.project
#   environment   = var.environment
#   purpose       = "project-bucket"
#   force_destroy = true
#   common_tags   = var.common_tags
# }

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

# Lambda Layer version
resource "aws_lambda_layer_version" "llm_lambda_layer" {
  layer_name  = "llm_lambda_layer"
  description = "Layer for llm_lambda_test with dependencies"

  # Use the bucket created by your module
  s3_bucket = module.layers_bucket.bucket_id
  s3_key    = "Lambda-layers/llm_lambda_test/layer-<timestamp>.zip" # update after CI/CD build

  compatible_runtimes = ["python3.11"]
  license_info        = "MIT"
}


# Zip the Lambda code
data "archive_file" "llm_lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/Lambda/llm_lambda_test"
  output_path = "${path.module}/build/llm_lambda_test.zip"

}# -----------------------------
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

# -----------------------------
# Lambda module
# -----------------------------
module "llm_lambda" {
  source       = "git::https://github.com/Hitesh-Nimbalkar/aws-platform.git//modules/lambda?ref=v0.0.3"
  organization = var.organization
  environment  = var.environment
  project      = var.project
  purpose      = "llm_lambda_test"

  # ZIP deployment
  zip_file_path  = data.archive_file.llm_lambda_zip.output_path
  lambda_handler = "lambda_handler.lambda_handler"
  lambda_runtime = "python3.11"

  memory_size = 256
  timeout     = 900

  environment_variables = merge({
    CONFIG_BUCKET       = module.config_bucket.bucket_id
    CONFIG_KEY          = "config/config.yaml"

    # S3 Bucket for User Documents
    DOCUMENTS_S3_BUCKET = module.config_bucket.bucket_id
    TEMP_DATA_KEY       = "project-data/uploads/temp"
    DOCUMENTS_DATA_KEY  = "project-data/uploads/data"

    # Chat History
    CHAT_HISTORY_TABLE  = aws_dynamodb_table.chat_history.name

    # Document Metadata
    METADATA_TABLE      = aws_dynamodb_table.metadata.name
  }, {})

  # Attach policies to Lambda (module handles the attachment)
    policy_arns = {
      dynamodb_policy = aws_iam_policy.lambda_dynamodb_policy.arn
      s3_policy       = aws_iam_policy.lambda_s3_policy.arn
    }

  tags = var.common_tags
}