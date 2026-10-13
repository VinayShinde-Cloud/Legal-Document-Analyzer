"""
Amazon Bedrock AgentCore Runtime — Legal Document Analysis Agent Handler

This file is deployed to AgentCore Runtime via S3 codeConfiguration.
AgentCore calls the /invocation HTTP endpoint on each agent request.

Agent role is selected by the AGENT_ROLE environment variable:
  - classification   → Document classification + PII detection (Nova Lite)
  - contract         → Contract analysis specialist (Nova Pro)
  - email            → Email communication analysis specialist (Nova Pro)
  - legal            → Legal document analysis specialist (Nova Pro)
  - supervisor       → Lead synthesizer + orchestrator (Nova Pro)
"""

from __future__ import annotations

import json
import logging
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agentcore-handler")

# ── Configuration ─────────────────────────────────────────────────────────────
REGION        = os.environ.get("AWS_REGION", "us-east-1")
AGENT_ROLE    = os.environ.get("AGENT_ROLE", "supervisor").lower()
NOVA_LITE     = "amazon.nova-lite-v1:0"   # All agents use Nova Lite
PORT          = int(os.environ.get("PORT", "8080"))

# ── System Prompts ─────────────────────────────────────────────────────────────
PROMPTS = {
    "classification": """You are a document classification and PII detection specialist.
Classify the document into EXACTLY ONE: Contract | Email | Legal
Detect PII: SSNs, emails, phones, addresses.
Output:
Document Classification:
Category: Contract|Email|Legal
Risk Level: HIGH|MEDIUM|LOW
Confidence Score: 0-100%
PII Findings:
- SSNs: [list or None]
- Emails: [list or None]
- Phones: [list or None]
- Addresses: [list or None]
Reasoning: <concise explanation>""",

    "contract": """You are a senior contract analysis specialist.
Extract parties, dates, financial terms, obligations, termination clauses, and risk factors.
Output:
Specialist Analysis:
Executive Summary: <summary>
Key Findings:
- Parties: <details>
- Dates: <effective, expiration, renewal>
- Financials: <amounts, currency, terms>
- Obligations: <key duties>
- Termination: <rules and penalties>
Risk Assessment:
Level: HIGH|MEDIUM|LOW
Factors: <bulleted risk factors>
Recommended Actions:
- <immediate action>
- <negotiation or follow-up>""",

    "email": """You are an email communication analysis specialist.
Analyze participants, topics, action items, sentiment, legal implications, and timeline.
Output:
Specialist Analysis:
Executive Summary: <summary>
Key Findings:
- Participants: <sender, recipients, third parties>
- Core Topics: <main discussion points>
- Commitments & Action Items: <who agreed to do what>
- Sentiment: <positive/neutral/negative>
- Legal Implications: <admissions, potential exposures>
Risk Assessment:
Level: HIGH|MEDIUM|LOW
Factors: <bulleted risk factors>
Recommended Actions:
- <recommended steps>""",

    "legal": """You are a legal analysis specialist.
Evaluate court filings, briefs, motions, opinions, and regulatory documents.
Output:
Specialist Analysis:
Executive Summary: <summary>
Key Findings:
- Procedural Details: <court, case, filing type>
- Legal Arguments: <claims, defenses>
- Citations & Authorities: <cases, statutes cited>
- Privilege Status: <privileged or non-privileged>
Risk Assessment:
Level: HIGH|MEDIUM|LOW
Factors: <procedural or substantive risks>
Recommended Actions:
- <strategic legal recommendations>""",

    "supervisor": """You are the Lead eDiscovery Supervisor Agent for CloudAge Legal Document Analysis.
Synthesize all specialist findings into an executive-ready comprehensive report.
Structure:
Executive Summary: <high-level summary>
Document Classification: <type, confidence, overall risk>
PII Findings: <inventory or clean confirmation>
Key Findings: <consolidated findings>
Risk Assessment: <overall level + specific factors>
Recommended Actions:
- <immediate actions>
- <short-term reviews>
- <long-term governance>""",
}

# All agents use Nova Lite
MODEL_MAP = {
    "classification": NOVA_LITE,
    "contract":       NOVA_LITE,
    "email":          NOVA_LITE,
    "legal":          NOVA_LITE,
    "supervisor":     NOVA_LITE,
}

# ── Bedrock Client ─────────────────────────────────────────────────────────────
bedrock = boto3.client("bedrock-runtime", region_name=REGION)


def invoke_model(system_prompt: str, user_message: str, model_id: str, max_retries: int = 4) -> str:
    """Call Bedrock Converse API with exponential backoff."""
    for attempt in range(max_retries):
        try:
            response = bedrock.converse(
                modelId=model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_message}]}],
                inferenceConfig={"maxTokens": 4096, "temperature": 0.1},
            )
            blocks = response.get("output", {}).get("message", {}).get("content", [])
            return "".join(b.get("text", "") for b in blocks if "text" in b)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("ThrottlingException", "TooManyRequestsException") and attempt < max_retries - 1:
                time.sleep((2 ** attempt) * 2)
                continue
            raise
    raise RuntimeError(f"Max retries exceeded for model {model_id}")


# ── AgentCore HTTP Handler ─────────────────────────────────────────────────────
class AgentCoreHandler(BaseHTTPRequestHandler):
    """AgentCore Runtime HTTP handler — receives agent invocations."""

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)

    def do_GET(self):
        """Health check endpoint."""
        if self.path in ("/", "/health", "/ping"):
            self._respond(200, {"status": "healthy", "role": AGENT_ROLE})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        """Agent invocation endpoint."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid JSON"})
            return

        # Extract input text — AgentCore sends {"inputText": "..."} or {"input": "..."}
        input_text = (
            payload.get("inputText")
            or payload.get("input")
            or payload.get("prompt")
            or str(payload)
        )

        logger.info("Agent role=%s | input_len=%d", AGENT_ROLE, len(input_text))

        try:
            system_prompt = PROMPTS.get(AGENT_ROLE, PROMPTS["supervisor"])
            model_id      = MODEL_MAP.get(AGENT_ROLE, NOVA_LITE)
            result        = invoke_model(system_prompt, input_text, model_id)
            self._respond(200, {"output": result, "role": AGENT_ROLE})
        except Exception as exc:
            logger.error("Agent invocation failed: %s", exc)
            self._respond(500, {"error": str(exc)})

    def _respond(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("Starting AgentCore handler | role=%s | port=%d | region=%s", AGENT_ROLE, PORT, REGION)
    server = HTTPServer(("0.0.0.0", PORT), AgentCoreHandler)
    logger.info("AgentCore agent ready on port %d", PORT)
    server.serve_forever()
