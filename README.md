# 🤖 AI-Powered Terraform Plan Analyzer
### Works with ANY Terraform project • External AI API • Jenkins • Lambda/SNS optional • Manual Approval Gate

---

## What This Project Does

This project reviews a Terraform plan **before `terraform apply`**.

It converts your Terraform plan into JSON, sends it to an **external OpenAI-compatible AI API**, receives a risk/security review, and then returns a pipeline decision:

```text
PROCEED        → Low risk, apply can continue
WAIT_APPROVAL  → Medium/High risk, human approval required
FAIL           → Critical risk, stop the pipeline
```

The setup is generic. You can change the model from variables only, and the output will show exactly which model was requested and which model the API reported.

---

## Current AI Provider

This version uses an external AI API endpoint:

```bash
https://api.ai.kodekloud.com/v1
```

The handler uses OpenAI-compatible chat completion format:

```text
POST /chat/completions
Authorization: Bearer <EXTERNAL_API_KEY>
```

Example models:

```bash
claude-haiku-4-5-20251001
moonshotai/kimi-k2.5
```

> Important: If you pasted an API key in chat, terminal, ticket, or Git, rotate/revoke it and use a new key.

---

## ⚡ Quick Start — Local Test Without AWS

Use this when AWS keys are disabled or you only want to verify model/API output locally.

```bash
# 1. Export external AI config
export AI_PROVIDER="external"
export EXTERNAL_API_URL="https://api.ai.kodekloud.com/v1"
export EXTERNAL_API_KEY="YOUR_NEW_ROTATED_API_KEY"
export EXTERNAL_MODEL_ID="claude-haiku-4-5-20251001"

# 2. Runtime settings
export MAX_TOKENS="4096"
export TEMPERATURE="0"
export API_TIMEOUT_SECONDS="90"
export ENVIRONMENT="dev"

# 3. Disable AWS/SNS for local test
export SNS_TOPIC_ARN=""
export LOCAL_DEBUG="true"

# 4. Run local test
python3 tests/test_local.py
```

Expected output:

```text
================================================================================
AI MODEL CALL STARTED
================================================================================
ai_provider             : external
api_url                 : https://api.ai.kodekloud.com/v1
model_requested         : claude-haiku-4-5-20251001
max_tokens              : 4096
temperature             : 0.0
api_timeout_seconds     : 90
external_api_key        : ***MASKED***
================================================================================

================================================================================
AI MODEL CALL COMPLETED
================================================================================
ai_provider             : external
api_status_code         : 200
api_url                 : https://api.ai.kodekloud.com/v1
model_requested         : claude-haiku-4-5-20251001
model_reported_by_api   : claude-haiku-4-5-20251001
overall_risk            : HIGH
approval_recommendation : REVIEW
================================================================================
```

---

## 🗺️ Architecture

```text
Your Terraform Project
        |
        | terraform plan -out=tfplan
        | terraform show -json tfplan > plan.json
        v
Local Test / Jenkins Pipeline
        |
        | payload.json
        v
handler.py
        |
        | EXTERNAL_API_URL
        | EXTERNAL_API_KEY
        | EXTERNAL_MODEL_ID
        v
External AI API
        |
        | JSON risk analysis
        v
Pipeline Decision
        |
        +--> PROCEED        → terraform apply
        +--> WAIT_APPROVAL  → manual approval
        +--> FAIL           → stop pipeline

Optional AWS Deployment:
        Lambda + SNS Email + CloudWatch Logs
```

---

## 📁 Project Structure

```text
ai-tf-analyzer/
|
├── config.env
│   └── Main config for setup.sh and terraform.tfvars generation
|
├── lambda/
│   ├── handler.py
│   │   └── Main Terraform plan analyzer + external AI API call
│   └── requirements.txt
|
├── terraform/
│   ├── main.tf
│   │   └── Optional AWS Lambda + SNS + CloudWatch deployment
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars
│       └── Generated from config.env, do not commit
|
├── scripts/
│   ├── setup.sh
│   ├── deploy.sh
│   └── analyze.sh
|
├── tests/
│   ├── test_local.py
│   └── sample_plan.json
|
└── jenkins/
    └── Jenkinsfile
```

---

## 🔧 Configuration

### `config.env`

Use this for local setup and terraform variable generation.

```bash
# AWS settings — required only for Lambda/SNS deployment
AWS_REGION=ap-south-1
PROJECT_NAME=tf-analyzer
ENVIRONMENT=dev
ALERT_EMAIL=your-email@example.com

# External AI settings
AI_PROVIDER=external
EXTERNAL_API_URL=https://api.ai.kodekloud.com/v1
EXTERNAL_API_KEY=YOUR_NEW_ROTATED_API_KEY
EXTERNAL_MODEL_ID=claude-haiku-4-5-20251001

# Runtime settings
MAX_TOKENS=4096
TEMPERATURE=0
API_TIMEOUT_SECONDS=90
LOCAL_DEBUG=true

# Terraform project path for analyze.sh
YOUR_TF_DIR=../your-terraform-project

# Lambda settings — required only for AWS deployment
LAMBDA_TIMEOUT=120
LAMBDA_MEMORY=256
LOG_RETENTION_DAYS=14
```

---

## Changing Model

Only change this value:

```bash
export EXTERNAL_MODEL_ID="moonshotai/kimi-k2.5"
```

or in `terraform.tfvars`:

```hcl
external_model_id = "moonshotai/kimi-k2.5"
```

The output will show:

```json
{
  "ai_call": {
    "ai_provider": "external",
    "api_url": "https://api.ai.kodekloud.com/v1",
    "model_requested": "moonshotai/kimi-k2.5",
    "model_reported_by_api": "moonshotai/kimi-k2.5",
    "api_status_code": 200
  }
}
```

`model_requested` means the model sent in the API request.

`model_reported_by_api` means the model returned by the API response. If the provider internally routes to a different model, this field helps you detect that.

---

## Local Test With Your Own Terraform Project

Generate a Terraform JSON plan:

```bash
cd /path/to/your/terraform
terraform init
terraform plan -out=tfplan
terraform show -json tfplan > plan.json
```

Run analyzer:

```bash
cd /path/to/ai-tf-analyzer
python3 tests/test_local.py --plan /path/to/your/terraform/plan.json
```

If your `test_local.py` does not support `--plan`, use the sample test first:

```bash
python3 tests/test_local.py
```

---

## Optional AWS Deployment

Use this only when you want Lambda + SNS email + CloudWatch.

```bash
./scripts/setup.sh
./scripts/deploy.sh plan
./scripts/deploy.sh apply
```

This creates:

```text
Lambda Function
IAM Role
SNS Topic
SNS Email Subscription
CloudWatch Log Group
```

After deployment, confirm the SNS email subscription from your inbox.

---

## Terraform Variables

Your `terraform/variables.tf` should include:

```hcl
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
  default     = 4096
}

variable "temperature" {
  type        = number
  description = "AI temperature"
  default     = 0
}

variable "api_timeout_seconds" {
  type        = number
  description = "External API timeout seconds"
  default     = 90
}

variable "local_debug" {
  type        = bool
  description = "Print debug logs showing provider/model"
  default     = true
}
```

---

## Lambda Environment Variables

Your `terraform/main.tf` Lambda environment should pass these values:

```hcl
environment {
  variables = {
    AWS_REGION  = var.aws_region
    ENVIRONMENT = var.environment

    AI_PROVIDER = var.ai_provider

    EXTERNAL_API_URL  = var.external_api_url
    EXTERNAL_API_KEY  = var.external_api_key
    EXTERNAL_MODEL_ID = var.external_model_id

    MAX_TOKENS          = tostring(var.max_tokens)
    TEMPERATURE         = tostring(var.temperature)
    API_TIMEOUT_SECONDS = tostring(var.api_timeout_seconds)

    SNS_TOPIC_ARN = aws_sns_topic.alerts.arn
    LOCAL_DEBUG   = tostring(var.local_debug)
  }
}
```

---

## 📊 What the AI Analyzes

The analyzer checks Terraform changes for:

| Check | What it looks for |
|------|-------------------|
| IAM | AdministratorAccess, wildcard `*`, overly broad policies |
| Network | `0.0.0.0/0` or `::/0` ingress on sensitive ports |
| Data Loss | RDS, DB, volume, or bucket deletion |
| Encryption | Encryption disabled or removed |
| Availability | Resource replacement causing downtime |
| Backup | Backup or retention reduced to unsafe values |
| Public Access | Public S3 bucket, public ACL, public policy |
| Deletion Protection | Missing deletion protection on critical resources |
| Environment Safety | Prod resources changed from non-prod branch |
| Cost | Large or unexpected cost-impact resources |
| Secrets | Secrets in user data, tags, env vars, or plain text |

---

## Pipeline Decision Logic

```text
AI returns APPROVE + LOW risk
  -> PROCEED
  -> terraform apply can run

AI returns REVIEW or HIGH/CRITICAL risk
  -> WAIT_APPROVAL
  -> Jenkins/manual approval required

AI returns REJECT
  -> FAIL
  -> pipeline stops immediately
```

---

## Sample Output

```json
{
  "pipeline_action": "WAIT_APPROVAL",
  "pipeline_message": "Plan requires manual approval. Risk=HIGH.",
  "ai_call": {
    "ai_provider": "external",
    "api_url": "https://api.ai.kodekloud.com/v1",
    "model_requested": "moonshotai/kimi-k2.5",
    "model_reported_by_api": "moonshotai/kimi-k2.5",
    "api_status_code": 200,
    "max_tokens": 4096,
    "temperature": 0
  },
  "analysis": {
    "summary": "Creates public S3 access and admin IAM policy; deletes RDS instance.",
    "overall_risk": "HIGH",
    "approval_recommendation": "REVIEW",
    "requires_manual_approval": true
  }
}
```

---

## Invalid JSON / Truncated Response Fix

If you see this error:

```text
AI returned invalid JSON
Unterminated string starting at...
```

It usually means the model response was cut before JSON completed.

Fix it using these steps:

### 1. Increase max tokens

```bash
export MAX_TOKENS="4096"
```

If still failing:

```bash
export MAX_TOKENS="8192"
```

### 2. Keep temperature zero

```bash
export TEMPERATURE="0"
```

### 3. Reduce Terraform plan excerpt

In `handler.py`, reduce:

```python
raw_plan_excerpt[:5000]
```

to:

```python
raw_plan_excerpt[:2500]
```

### 4. Keep JSON response compact

Ask the model for:

```text
Return ONLY compact valid JSON.
Keep every string short.
Max 5 security findings.
Max 5 risks.
Complete the JSON fully.
```

### 5. Try another model

Some models are weaker at strict JSON output. If one model fails frequently, test another model with the same prompt.

---

## Troubleshooting

| Error | Meaning | Fix |
|------|---------|-----|
| `EXTERNAL_API_KEY is missing` | API key env var not set | Export `EXTERNAL_API_KEY` or set in `terraform.tfvars` |
| `External API HTTP error 401` | Invalid/expired API key | Rotate key and update config |
| `External API HTTP error 404` | Wrong endpoint/model | Check `EXTERNAL_API_URL` and `EXTERNAL_MODEL_ID` |
| `AI response is incomplete/truncated` | Model output cut before JSON completed | Increase `MAX_TOKENS`, reduce prompt size |
| `AI returned invalid JSON` | Model did not return strict JSON | Use compact JSON prompt, temperature 0 |
| `SNS_TOPIC_ARN not set` | Local mode or SNS disabled | Safe to ignore in local test |
| `No module named boto3` | Needed only for SNS/Lambda mode | `pip3 install boto3` |
| Lambda timeout | External API slow or plan too large | Increase `lambda_timeout` and reduce plan excerpt |

---

## Security Notes

For local testing, using environment variables is fine:

```bash
export EXTERNAL_API_KEY="..."
```

For production, avoid storing keys in:

```text
Git repo
README
config.env committed to Git
terraform.tfvars committed to Git
Lambda env if many users have Lambda read access
```

Production-grade option:

```text
AWS Secrets Manager
        |
Lambda IAM Role gets secretsmanager:GetSecretValue
        |
handler.py reads key at runtime
```

Minimum recommendation:

```text
- Keep terraform.tfvars gitignored
- Rotate API keys periodically
- Do not print API key in logs
- Mask API key in local debug output
- Give Jenkins only required permissions
```

---

## Cost Notes

External API pricing depends on your API provider/model.

This project itself can stay low-cost:

| Component | Local Mode | AWS Mode |
|----------|------------|----------|
| External AI API | Provider/model based | Provider/model based |
| Lambda | Not used | Usually low/free-tier friendly |
| SNS Email | Not used | Usually low/free-tier friendly |
| CloudWatch | Not used | Small log cost |

For local testing with disabled AWS keys, only the external AI API is used.

---

## Final Flow

```text
terraform plan
   |
terraform show -json
   |
handler.py
   |
External AI API using EXTERNAL_MODEL_ID
   |
JSON risk analysis
   |
PROCEED / WAIT_APPROVAL / FAIL
```

