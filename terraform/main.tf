# ═══════════════════════════════════════════════════════════════════════════════
# main.tf — AI-Powered Terraform Plan Analyzer
# External AI API version
# Free tier friendly: Lambda + SNS Email + CloudWatch
# ═══════════════════════════════════════════════════════════════════════════════

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Purpose     = "ai-tf-plan-analyzer"
    }
  }
}

locals {
  fn_name = "${var.project_name}-${var.environment}-analyzer"
}

# ── Lambda ZIP ────────────────────────────────────────────────────────────────
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda"
  output_path = "${path.module}/lambda.zip"
}

# ── SNS Topic for Email Alerts ────────────────────────────────────────────────
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-${var.environment}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ── IAM Role for Lambda ───────────────────────────────────────────────────────
resource "aws_iam_role" "lambda" {
  name = "${local.fn_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "lambda.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })
}

# ── IAM Policy: CloudWatch Logging ────────────────────────────────────────────
resource "aws_iam_policy" "logging" {
  name = "${local.fn_name}-logging"

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]

        Resource = [
          "arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/${local.fn_name}",
          "arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/${local.fn_name}:*"
        ]
      }
    ]
  })
}

# ── IAM Policy: SNS Publish ───────────────────────────────────────────────────
resource "aws_iam_policy" "sns" {
  name = "${local.fn_name}-sns"

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Action = [
          "sns:Publish"
        ]

        Resource = aws_sns_topic.alerts.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "logging" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.logging.arn
}

resource "aws_iam_role_policy_attachment" "sns" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.sns.arn
}

# ── CloudWatch Log Group ──────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.fn_name}"
  retention_in_days = var.log_retention_days
}

# ── Lambda Function ───────────────────────────────────────────────────────────
resource "aws_lambda_function" "analyzer" {
  function_name    = local.fn_name
  description      = "AI-powered Terraform plan analyzer using external AI API"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda.arn
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory

  environment {
    variables = {
      AWS_REGION  = var.aws_region
      ENVIRONMENT = var.environment

      AI_PROVIDER = var.ai_provider

      EXTERNAL_API_URL   = var.external_api_url
      EXTERNAL_API_KEY   = var.external_api_key
      EXTERNAL_MODEL_ID  = var.external_model_id

      MAX_TOKENS          = tostring(var.max_tokens)
      TEMPERATURE         = tostring(var.temperature)
      API_TIMEOUT_SECONDS = tostring(var.api_timeout_seconds)

      SNS_TOPIC_ARN = aws_sns_topic.alerts.arn

      LOCAL_DEBUG = tostring(var.local_debug)
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.logging,
    aws_iam_role_policy_attachment.sns,
    aws_cloudwatch_log_group.lambda,
  ]
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "lambda_function_name" {
  value = aws_lambda_function.analyzer.function_name
}

output "sns_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "external_ai_model_configured" {
  value = var.external_model_id
}

output "external_api_url_configured" {
  value = var.external_api_url
}