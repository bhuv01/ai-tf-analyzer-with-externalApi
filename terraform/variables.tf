variable "aws_region" {
  type        = string
  description = "AWS region for Lambda, SNS and CloudWatch"
  default     = "ap-south-1"
}

variable "project_name" {
  type        = string
  description = "Project name"
  default     = "tf-analyzer"
}

variable "environment" {
  type        = string
  description = "Environment name"
  default     = "dev"
}

variable "alert_email" {
  type        = string
  description = "Email address for SNS alerts"
}

variable "lambda_timeout" {
  type        = number
  description = "Lambda timeout in seconds"
  default     = 120
}

variable "lambda_memory" {
  type        = number
  description = "Lambda memory in MB"
  default     = 256
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention days"
  default     = 14
}

variable "ai_provider" {
  type        = string
  description = "AI provider name"
  default     = "external"
}

variable "external_api_url" {
  type        = string
  description = "External AI API base URL"
  default     = "https://api.ai.kodekloud.com/v1"
}

variable "external_api_key" {
  type        = string
  description = "External AI API key"
  sensitive   = true
}

variable "external_model_id" {
  type        = string
  description = "External AI model ID"
  default     = "claude-haiku-4-5-20251001"
}

variable "max_tokens" {
  type        = number
  description = "Max output tokens"
  default     = 2048
}

variable "temperature" {
  type        = number
  description = "AI temperature"
  default     = 0
}

variable "api_timeout_seconds" {
  type        = number
  description = "External API timeout"
  default     = 90
}

variable "local_debug" {
  type        = bool
  description = "Print debug logs showing provider and model"
  default     = true
}