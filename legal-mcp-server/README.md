# Legal Document Analysis MCP Server

A custom MCP server that exposes the CloudAge legal document analysis agents (Amazon Bedrock) as a tool for AI assistants.

## What it does

Provides a single `analyze_document` tool that calls agents directly:

1. **Classification Agent** (`ZRLS0YXJHP`) — identifies document type (Contract/Email/Legal) + PII scan
2. **Specialist Agent** — routes to Contract, Email, or Legal agent based on classification
3. Returns combined structured JSON report

> **Note**: Uses direct agent calls instead of the supervisor agent, which times out in EU cross-region inference with larger documents.

## Setup

### 1. Install dependencies

```bash
cd legal-mcp-server
pip install -r requirements.txt
```

### 2. Configuration

The server reads agent IDs from environment variables or the project's `.env` file. Current agent IDs are hardcoded as defaults:

| Agent | ID | Alias |
|---|---|---|
| Classification | ZRLS0YXJHP | WMJWE8WRN5 |
| Contract | GPMTI99Z6T | ZR1HS5DF5G |
| Email | MIT1Y9TADT | 3L9IGJHKCJ |
| Legal | DFTFSYKGHQ | TQ5RQSHNPD |

### 3. Connect to Kiro

Already configured in `.kiro/settings/mcp.json`. The server connects automatically.

### 4. Test locally

```bash
source .venv/bin/activate
mcp dev legal-mcp-server/server.py
```

## Tool: `analyze_document`

**Input:** `document_text` (string) — the full text of a legal document

**Output:** JSON report containing:
- Document type classification + confidence score
- PII detection results
- Specialist analysis (parties, dates, obligations, risk factors, etc.)

## Requirements

- Python 3.13+
- AWS credentials configured (same as your Streamlit app)
- Bedrock agents deployed via the CloudFormation stack (`legal-doc-agents`)
