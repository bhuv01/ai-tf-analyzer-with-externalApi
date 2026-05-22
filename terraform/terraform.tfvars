# Auto-generated from config.env — do not edit manually
# Edit config.env and re-run ./scripts/setup.sh

aws_region         = "ap-south-1"
project_name       = "tf-analyzer"
environment        = "dev"
alert_email        = "your-email@example.com"

lambda_timeout     = 120
lambda_memory      = 256
log_retention_days = 14

ai_provider        = "external"

external_api_url   = "https://api.ai.kodekloud.com/v1"
external_api_key   = "sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
external_model_id  = "moonshotai/kimi-k2.5"

max_tokens          = 2048
temperature         = 0
api_timeout_seconds = 90
local_debug         = true