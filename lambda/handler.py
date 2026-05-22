"""
AI-Powered Terraform Plan Analyzer
Generic External AI API version

Works with:
- Local testing without AWS credentials
- Lambda deployment
- Any OpenAI-compatible external API endpoint

Required env vars:
  EXTERNAL_API_URL
  EXTERNAL_API_KEY
  EXTERNAL_MODEL_ID

Optional env vars:
  MAX_TOKENS
  ENVIRONMENT
  SNS_TOPIC_ARN
  AWS_REGION
  LOCAL_DEBUG
"""

import json
import logging
import os
import datetime
import urllib.request
import urllib.error
from typing import Any, Dict, Tuple


logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ── Generic Config ────────────────────────────────────────────────────────────
AI_PROVIDER = os.environ.get("AI_PROVIDER", "external")

EXTERNAL_API_URL = os.environ.get(
    "EXTERNAL_API_URL",
    "https://api.ai.kodekloud.com/v1"
).rstrip("/")

EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")

EXTERNAL_MODEL_ID = os.environ.get(
    "EXTERNAL_MODEL_ID",
    "moonshotai/kimi-k2.5"
)

MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "2048"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0"))

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

LOCAL_DEBUG = os.environ.get("LOCAL_DEBUG", "true").lower() == "true"
API_TIMEOUT_SECONDS = int(os.environ.get("API_TIMEOUT_SECONDS", "90"))


# ══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def debug_print(title: str, data: Dict[str, Any]) -> None:
    """
    Local terminal debug output.
    Lambda logs mein bhi print visible hota hai.
    """
    if not LOCAL_DEBUG:
        return

    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    for key, value in data.items():
        if "key" in key.lower() or "token" in key.lower() or "secret" in key.lower():
            value = "***MASKED***"
        print(f"{key:22}: {value}")
    print("=" * 80 + "\n")


def strip_json_fences(raw_text: str) -> str:
    """
    Model kabhi-kabhi ```json ... ``` return karta hai.
    Is function se clean JSON string milti hai.
    """
    text = raw_text.strip()

    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].strip()
        if text.startswith("json"):
            text = text[4:].strip()

    return text


def extract_message_content(api_result: Dict[str, Any]) -> str:
    """
    OpenAI-compatible response se assistant content nikalta hai.
    """
    choices = api_result.get("choices", [])
    if not choices:
        raise ValueError("External API response has no choices[]")

    message = choices[0].get("message", {})
    content = message.get("content", "")

    # Some APIs return content as list
    if isinstance(content, list):
        merged = []
        for item in content:
            if isinstance(item, dict):
                merged.append(item.get("text", ""))
            else:
                merged.append(str(item))
        content = "\n".join(merged)

    if not content:
        raise ValueError("External API response message.content is empty")

    return str(content).strip()


def parse_ai_json_response(raw_text: str) -> Dict[str, Any]:
    """
    AI response ko valid JSON dict mein convert karta hai.
    """
    cleaned = strip_json_fences(raw_text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("AI returned invalid JSON: %s", cleaned[:1000])
        raise ValueError(f"AI response is not valid JSON: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TERRAFORM PLAN PARSING
# ══════════════════════════════════════════════════════════════════════════════

def extract_changes(plan: dict) -> dict:
    """
    Terraform plan JSON ko parse karke create/delete/update/replace classify karta hai.
    """
    resource_changes = plan.get("resource_changes", [])

    creates = []
    deletes = []
    updates = []
    replaces = []
    no_ops = []
    unknowns = []

    for rc in resource_changes:
        address = rc.get("address", rc.get("name", "unknown"))
        actions = rc.get("change", {}).get("actions", [])
        rtype = rc.get("type", "unknown_type")

        entry = {
            "address": address,
            "type": rtype
        }

        if not actions or actions == ["no-op"]:
            no_ops.append(entry)
        elif actions == ["create"]:
            creates.append(entry)
        elif actions == ["delete"]:
            deletes.append(entry)
        elif actions == ["update"]:
            updates.append(entry)
        elif set(actions) == {"delete", "create"} or actions == ["create", "delete"]:
            replaces.append(entry)
        else:
            entry["actions"] = actions
            unknowns.append(entry)

    return {
        "creates": creates,
        "deletes": deletes,
        "updates": updates,
        "replaces": replaces,
        "no_ops": no_ops,
        "unknowns": unknowns,
    }


def format_resource_list(resources: list) -> str:
    """
    Prompt ke liye resource list readable format mein banata hai.
    """
    if not resources:
        return "[]"

    lines = [
        f"  - {r['address']} ({r['type']})"
        for r in resources[:30]
    ]

    if len(resources) > 30:
        lines.append(f"  ... and {len(resources) - 30} more")

    return "\n" + "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT
# ══════════════════════════════════════════════════════════════════════════════

def build_prompt(changes: dict, raw_plan_excerpt: str, metadata: dict) -> str:
    """
    External AI model ke liye prompt banata hai.
    """
    return f"""You are a senior DevOps and Cloud Security engineer reviewing a Terraform plan before deployment.

Your job:
- Analyze Terraform changes.
- Find security, availability, cost, and data-loss risks.
- Return ONLY valid JSON.
- Do not return markdown.
- Do not wrap output in code fences.

━━━ PIPELINE CONTEXT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Environment  : {metadata.get('environment', 'unknown')}
Triggered by : {metadata.get('triggered_by', 'unknown')}
Branch       : {metadata.get('branch', 'unknown')}
Commit       : {metadata.get('commit_id', 'unknown')}
Build Number : {metadata.get('build_number', 'unknown')}
Timestamp    : {metadata.get('timestamp', 'unknown')}

━━━ RESOURCE CHANGES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE  ({len(changes['creates'])}): {format_resource_list(changes['creates'])}
DELETE  ({len(changes['deletes'])}): {format_resource_list(changes['deletes'])}
UPDATE  ({len(changes['updates'])}): {format_resource_list(changes['updates'])}
REPLACE ({len(changes['replaces'])}): {format_resource_list(changes['replaces'])}
NO-OP   ({len(changes['no_ops'])}): {len(changes['no_ops'])} resources unchanged
UNKNOWN ({len(changes['unknowns'])}): {format_resource_list(changes['unknowns'])}

━━━ SECURITY CHECKLIST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Check all of these:
1. IAM roles/policies with overly broad permissions such as Admin or *
2. Security groups with 0.0.0.0/0 or ::/0 on sensitive ports
3. Public S3 buckets or open ACLs
4. Databases/storage being deleted
5. Encryption disabled or removed
6. Resources being replaced, causing downtime
7. Missing deletion protection
8. Backup or retention being reduced
9. Unexpected public-facing resources
10. Production resources changed from non-production branches
11. Large cost-impact resources
12. Secrets exposed in user_data, environment variables, or tags

━━━ TERRAFORM PLAN EXCERPT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{raw_plan_excerpt[:5000]}

━━━ REQUIRED JSON RESPONSE FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return exactly this JSON structure:

{{
  "summary": "One-line executive summary",

  "creates": {{
    "count": 0,
    "resources": [],
    "description": "What is being created",
    "security_notes": "Security concerns for new resources"
  }},

  "deletes": {{
    "count": 0,
    "resources": [],
    "description": "What is being deleted",
    "warning": "Data loss or service disruption warning",
    "data_loss_risk": false
  }},

  "updates": {{
    "count": 0,
    "resources": [],
    "description": "What is being updated"
  }},

  "replaces": {{
    "count": 0,
    "resources": [],
    "description": "What is being replaced",
    "downtime_risk": false,
    "warning": "Downtime or data loss from destroy and recreate"
  }},

  "security_findings": [
    {{
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "category": "IAM|Network|Data|Encryption|Availability|Cost|Compliance|Secrets",
      "resource": "resource address",
      "finding": "Specific security issue found",
      "recommendation": "Exact action to remediate"
    }}
  ],

  "risks": [
    {{
      "severity": "HIGH|MEDIUM|LOW",
      "resource": "resource address or General",
      "risk": "Operational risk description",
      "recommendation": "How to mitigate"
    }}
  ],

  "overall_risk": "CRITICAL|HIGH|MEDIUM|LOW",
  "approval_recommendation": "APPROVE|REVIEW|REJECT",
  "approval_reason": "Clear reason for recommendation",
  "requires_manual_approval": true,

  "estimated_cost_impact": "Brief cost impact description",
  "rollback_complexity": "EASY|MEDIUM|HARD|IMPOSSIBLE",
  "rollback_steps": "How to rollback if something goes wrong"
}}
"""


# ══════════════════════════════════════════════════════════════════════════════
# EXTERNAL AI API CALL
# ══════════════════════════════════════════════════════════════════════════════

def call_external_ai(prompt: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Generic OpenAI-compatible external API call.

    Reads from:
      EXTERNAL_API_URL
      EXTERNAL_API_KEY
      EXTERNAL_MODEL_ID

    Returns:
      analysis dict
      ai_call_info dict
    """
    if not EXTERNAL_API_URL:
        raise ValueError("EXTERNAL_API_URL is missing")

    if not EXTERNAL_API_KEY:
        raise ValueError("EXTERNAL_API_KEY is missing")

    if not EXTERNAL_MODEL_ID:
        raise ValueError("EXTERNAL_MODEL_ID is missing")

    debug_print("AI MODEL CALL STARTED", {
        "ai_provider": AI_PROVIDER,
        "api_url": EXTERNAL_API_URL,
        "model_requested": EXTERNAL_MODEL_ID,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "api_timeout_seconds": API_TIMEOUT_SECONDS,
        "external_api_key": EXTERNAL_API_KEY,
    })

    payload = json.dumps({
        "model": EXTERNAL_MODEL_ID,
        "messages": [
            {
                "role": "system",
                "content": "You are a senior DevOps and cloud security reviewer. Return only valid JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE
    }).encode("utf-8")

    request = urllib.request.Request(
        url=f"{EXTERNAL_API_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {EXTERNAL_API_KEY}",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")
            api_result = json.loads(response_body)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(
            f"External API HTTP error. Status={e.code}, Body={error_body[:1000]}"
        )

    except urllib.error.URLError as e:
        raise RuntimeError(f"External API connection failed: {e}")

    model_reported = api_result.get("model", EXTERNAL_MODEL_ID)
    raw_text = extract_message_content(api_result)
    analysis = parse_ai_json_response(raw_text)

    ai_call_info = {
        "ai_provider": AI_PROVIDER,
        "api_url": EXTERNAL_API_URL,
        "model_requested": EXTERNAL_MODEL_ID,
        "model_reported_by_api": model_reported,
        "api_status_code": status_code,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
    }

    debug_print("AI MODEL CALL COMPLETED", {
        "ai_provider": ai_call_info["ai_provider"],
        "api_status_code": ai_call_info["api_status_code"],
        "api_url": ai_call_info["api_url"],
        "model_requested": ai_call_info["model_requested"],
        "model_reported_by_api": ai_call_info["model_reported_by_api"],
        "overall_risk": analysis.get("overall_risk"),
        "approval_recommendation": analysis.get("approval_recommendation"),
        "raw_preview": raw_text[:500],
    })

    return analysis, ai_call_info


# ══════════════════════════════════════════════════════════════════════════════
# ALERTING
# ══════════════════════════════════════════════════════════════════════════════

def send_sns_alert(analysis: dict, metadata: dict, ai_call_info: dict) -> bool:
    """
    SNS alert optional hai.
    Local test mein SNS_TOPIC_ARN empty rakho, AWS call skip ho jayegi.
    """
    if not SNS_TOPIC_ARN:
        logger.warning("SNS_TOPIC_ARN not set — skipping email alert")
        return False

    try:
        import boto3
    except ImportError:
        logger.warning("boto3 not installed — skipping SNS alert")
        return False

    risk = analysis.get("overall_risk", "LOW")
    rec = analysis.get("approval_recommendation", "APPROVE")

    risk_icon = {
        "CRITICAL": "🚨",
        "HIGH": "🔴",
        "MEDIUM": "🟡",
        "LOW": "🟢",
    }.get(risk, "⚪")

    rec_icon = {
        "APPROVE": "✅",
        "REVIEW": "⚠️",
        "REJECT": "❌",
    }.get(rec, "❓")

    findings = analysis.get("security_findings", [])
    findings_text = ""

    for f in findings[:8]:
        findings_text += f"\n  [{f.get('severity')}] {f.get('category')} — {f.get('resource', 'N/A')}"
        findings_text += f"\n     Issue  : {f.get('finding', '')}"
        findings_text += f"\n     Action : {f.get('recommendation', '')}\n"

    risks = analysis.get("risks", [])
    risks_text = ""

    for r in risks[:5]:
        risks_text += f"\n  [{r.get('severity')}] {r.get('resource', 'General')}: {r.get('risk', '')}"

    message = f"""
==============================================================
  TERRAFORM PLAN ALERT {risk_icon} {risk} RISK {rec_icon} {rec}
==============================================================

PIPELINE INFO
  Environment  : {metadata.get('environment', 'N/A')}
  Branch       : {metadata.get('branch', 'N/A')}
  Commit       : {metadata.get('commit_id', 'N/A')}
  Triggered by : {metadata.get('triggered_by', 'N/A')}
  Build #      : {metadata.get('build_number', 'N/A')}
  Timestamp    : {metadata.get('timestamp', 'N/A')}

AI MODEL INFO
  Provider     : {ai_call_info.get('ai_provider')}
  API URL      : {ai_call_info.get('api_url')}
  Model Req    : {ai_call_info.get('model_requested')}
  Model API    : {ai_call_info.get('model_reported_by_api')}
  API Status   : {ai_call_info.get('api_status_code')}

ANALYSIS
  Summary      : {analysis.get('summary', 'N/A')}
  Risk Level   : {risk}
  Recommend    : {rec}
  Reason       : {analysis.get('approval_reason', 'N/A')}
  Cost Impact  : {analysis.get('estimated_cost_impact', 'N/A')}
  Rollback     : {analysis.get('rollback_complexity', 'N/A')}
  Rollback How : {analysis.get('rollback_steps', 'N/A')}

CHANGES
  Create       : {analysis.get('creates', {}).get('count', 0)}
  Delete       : {analysis.get('deletes', {}).get('count', 0)}
  Update       : {analysis.get('updates', {}).get('count', 0)}
  Replace      : {analysis.get('replaces', {}).get('count', 0)}

SECURITY FINDINGS
{findings_text if findings_text else '  None detected.'}

OPERATIONAL RISKS
{risks_text if risks_text else '  None detected.'}

==============================================================
"""

    subject = (
        f"[TF-ANALYZER][{metadata.get('environment', '?').upper()}] "
        f"{rec} — {risk} Risk | Model: {ai_call_info.get('model_requested')}"
    )

    try:
        sns = boto3.client("sns", region_name=AWS_REGION)
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject[:100],
            Message=message,
        )
        logger.info("SNS alert sent. Subject: %s", subject)
        return True

    except Exception as e:
        logger.error("SNS publish failed: %s", e)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE DECISION
# ══════════════════════════════════════════════════════════════════════════════

def determine_pipeline_action(analysis: dict) -> tuple:
    """
    Jenkins/GitLab/CI pipeline ke liye final action.
    """
    rec = analysis.get("approval_recommendation", "APPROVE")
    risk = analysis.get("overall_risk", "LOW")

    if rec == "REJECT":
        return (
            "FAIL",
            f"Plan REJECTED — {analysis.get('approval_reason', 'Critical issues found')}. Fix issues and re-run."
        )

    if rec == "REVIEW" or analysis.get("requires_manual_approval") or risk in ("HIGH", "CRITICAL"):
        return (
            "WAIT_APPROVAL",
            f"Plan requires manual approval. Risk={risk}."
        )

    return (
        "PROCEED",
        f"Plan APPROVED. Risk={risk}. Proceeding with terraform apply."
    )


# ══════════════════════════════════════════════════════════════════════════════
# LAMBDA ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def lambda_handler(event: dict, context: Any) -> dict:
    """
    Universal entry point.

    Accepted input:

    {
      "plan_json": { ...terraform show -json output... },
      "metadata": {
        "environment": "dev",
        "branch": "main",
        "commit_id": "abc123",
        "triggered_by": "local|jenkins",
        "build_number": "42"
      }
    }
    """
    logger.info("Analyzer invoked. Event keys: %s", list(event.keys()))

    timestamp = datetime.datetime.utcnow().isoformat() + "Z"

    metadata = event.get("metadata", {})
    metadata.setdefault("environment", ENVIRONMENT)
    metadata.setdefault("triggered_by", "unknown")
    metadata.setdefault("branch", "unknown")
    metadata.setdefault("commit_id", "unknown")
    metadata.setdefault("build_number", "unknown")
    metadata["timestamp"] = timestamp

    # 1. Parse plan
    try:
        if "plan_json" in event:
            plan = event["plan_json"]
        elif "plan_json_string" in event:
            plan = json.loads(event["plan_json_string"])
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "Missing required field: plan_json or plan_json_string",
                    "hint": "Run: terraform show -json tfplan > plan.json"
                }, indent=2)
            }

    except json.JSONDecodeError as e:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": f"Invalid JSON: {e}"
            }, indent=2)
        }

    # 2. Extract Terraform changes
    try:
        changes = extract_changes(plan)

        logger.info(
            "Changes extracted — create:%d delete:%d update:%d replace:%d no-op:%d unknown:%d",
            len(changes["creates"]),
            len(changes["deletes"]),
            len(changes["updates"]),
            len(changes["replaces"]),
            len(changes["no_ops"]),
            len(changes["unknowns"]),
        )

    except Exception as e:
        logger.error("Failed to extract changes: %s", e)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": f"Plan parsing failed: {e}"
            }, indent=2)
        }

    # 3. Call external AI model
    try:
        prompt = build_prompt(
            changes=changes,
            raw_plan_excerpt=json.dumps(plan, indent=2),
            metadata=metadata,
        )

        analysis, ai_call_info = call_external_ai(prompt)

        logger.info(
            "External AI response — Provider:%s Model:%s Risk:%s Rec:%s",
            ai_call_info.get("ai_provider"),
            ai_call_info.get("model_requested"),
            analysis.get("overall_risk"),
            analysis.get("approval_recommendation"),
        )

    except Exception as e:
        logger.error("External AI call failed: %s", e)
        return {
            "statusCode": 502,
            "body": json.dumps({
                "error": f"External AI failed: {e}",
                "ai_provider": AI_PROVIDER,
                "api_url": EXTERNAL_API_URL,
                "model_requested": EXTERNAL_MODEL_ID,
            }, indent=2)
        }

    # 4. Optional SNS alert
    alert_sent = send_sns_alert(
        analysis=analysis,
        metadata=metadata,
        ai_call_info=ai_call_info,
    )

    # 5. Pipeline action
    pipeline_action, pipeline_message = determine_pipeline_action(analysis)

    debug_print("FINAL AI ANALYSIS RESULT", {
        "pipeline_action": pipeline_action,
        "pipeline_message": pipeline_message,
        "ai_provider": ai_call_info.get("ai_provider"),
        "api_url": ai_call_info.get("api_url"),
        "model_requested": ai_call_info.get("model_requested"),
        "model_reported_by_api": ai_call_info.get("model_reported_by_api"),
        "overall_risk": analysis.get("overall_risk"),
        "approval_recommendation": analysis.get("approval_recommendation"),
    })

    # 6. Return structured response
    return {
        "statusCode": 200,
        "body": json.dumps({
            "pipeline_action": pipeline_action,
            "pipeline_message": pipeline_message,

            "ai_call": ai_call_info,

            "analysis": analysis,

            "change_counts": {
                "creates": len(changes["creates"]),
                "deletes": len(changes["deletes"]),
                "updates": len(changes["updates"]),
                "replaces": len(changes["replaces"]),
                "no_ops": len(changes["no_ops"]),
                "unknowns": len(changes["unknowns"]),
            },

            "alert_sent": alert_sent,
            "metadata": metadata,
        }, indent=2)
    }