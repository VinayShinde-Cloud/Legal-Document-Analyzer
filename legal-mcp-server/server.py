from __future__ import annotations

"""Legal Document Analysis MCP Server.

Exposes the CloudAge legal document analysis agents as an MCP tool.
Uses direct agent calls (Classification → Specialist) for reliability,
bypassing the supervisor agent which times out in EU cross-region inference.
"""

import os
import json
import io
import pathlib
import uuid

import boto3
from mcp.server.fastmcp import FastMCP

# Load .env file from the project root if env vars aren't set
_project_root = pathlib.Path(__file__).resolve().parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if key.strip() not in os.environ or not os.environ[key.strip()]:
                    os.environ[key.strip()] = value.strip()

# Initialize the MCP server
mcp = FastMCP(
    "legal-doc-analyzer",
    instructions="Analyze legal documents using Amazon Bedrock multi-agent collaboration",
)

# Agent IDs (direct calls to individual agents)
AGENTS = {
    "classification": {
        "id": os.environ.get("CLASSIFICATION_AGENT_ID", ""),
        "alias": os.environ.get("CLASSIFICATION_ALIAS_ID", ""),
    },
    "Contract": {
        "id": os.environ.get("CONTRACT_AGENT_ID", ""),
        "alias": os.environ.get("CONTRACT_ALIAS_ID", ""),
    },
    "Email": {
        "id": os.environ.get("EMAIL_AGENT_ID", ""),
        "alias": os.environ.get("EMAIL_ALIAS_ID", ""),
    },
    "Legal": {
        "id": os.environ.get("LEGAL_AGENT_ID", ""),
        "alias": os.environ.get("LEGAL_ALIAS_ID", ""),
    },
}


def _get_bedrock_client():
    """Create a Bedrock Agent Runtime client."""
    region = os.environ.get("AWS_REGION", "eu-north-1")
    return boto3.client("bedrock-agent-runtime", region_name=region)


def _invoke_agent(agent_key: str, text: str) -> str | None:
    """Invoke a single agent directly.

    Args:
        agent_key: Key in AGENTS dict (classification, Contract, Email, Legal).
        text: Document text to send.

    Returns:
        Agent response string or None on failure.
    """
    agent = AGENTS[agent_key]
    client = _get_bedrock_client()

    response = client.invoke_agent(
        agentId=agent["id"],
        agentAliasId=agent["alias"],
        sessionId=str(uuid.uuid4()),
        inputText=text,
    )

    full_response = ""
    if "completion" in response:
        for event in response["completion"]:
            if isinstance(event, dict) and "chunk" in event and "bytes" in event["chunk"]:
                full_response += event["chunk"]["bytes"].decode("utf-8")

    return full_response if full_response else None


@mcp.tool()
def analyze_document(document_text: str) -> str:
    """Analyze a legal document using the full multi-agent pipeline.

    Sends the document through the eDiscovery Collaborator supervisor agent,
    which orchestrates: Classification → Specialized Analysis → Synthesis.

    The pipeline detects document type (Contract, Email, Legal), scans for PII,
    routes to the appropriate specialist agent, and returns a comprehensive
    analysis report including risk assessment and recommended actions.

    Args:
        document_text: The full text content of the legal document to analyze.
            Supports contracts, emails, legal filings, terms of service, NDAs, etc.

    Returns:
        A comprehensive analysis report in JSON format containing:
        - Executive summary with key points and risk level
        - Document classification and confidence score
        - PII detection results
        - Specialized analysis (varies by document type)
        - Risk assessment with mitigation suggestions
        - Recommended actions (immediate, short-term, long-term)
    """
    if not document_text or not document_text.strip():
        return json.dumps({"error": "No document text provided."})

    try:
        # Step 1: Classification + PII detection
        classification_raw = _invoke_agent("classification", document_text[:5000])

        # Step 2: Determine document type
        doc_type = "Contract"  # default
        classification_data = None
        if classification_raw:
            try:
                clean = classification_raw.replace("{{", "{").replace("}}", "}")
                classification_data = json.loads(clean)
                if isinstance(classification_data, dict) and "classification" in classification_data:
                    doc_type = classification_data["classification"].get("category", "Contract")
            except (json.JSONDecodeError, ValueError):
                pass

        # Step 3: Specialist analysis
        specialist_raw = _invoke_agent(doc_type, document_text[:5000])

        # Parse specialist result
        specialist_data = None
        if specialist_raw:
            try:
                specialist_data = json.loads(specialist_raw)
            except (json.JSONDecodeError, ValueError):
                specialist_data = specialist_raw

        # Combine into final report
        report = {
            "document_type": doc_type,
            "classification": classification_data,
            "specialist_analysis": specialist_data,
            "text_length": len(document_text),
        }

        return json.dumps(report, indent=2)

    except Exception as e:
        error_msg = str(e)
        if "throttling" in error_msg.lower():
            return json.dumps({
                "error": "Rate limited by Bedrock. Please wait 60 seconds and try again."
            })
        return json.dumps({"error": f"Analysis failed: {error_msg}"})


# --- Entry Point ---

if __name__ == "__main__":
    import sys

    # Run as HTTP server if --http flag is passed, otherwise stdio (for Kiro/Claude)
    if "--http" in sys.argv:
        port = 8080
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = port
        print(f"Starting MCP server on http://0.0.0.0:{port}/mcp")
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
