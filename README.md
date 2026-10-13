# CloudAge Legal Document Analyzer

AI-powered legal document analysis using Amazon Bedrock's multi-agent collaboration. Upload contracts, emails, or legal documents and receive comprehensive analysis including classification, PII detection, risk assessment, and actionable recommendations.

![CloudAge](https://assets.cloudage.llc/logo.png)

---

## Features

- **Multi-Agent AI Analysis** — 5 specialized agents collaborate to analyze documents
- **Semantic Document Chunking** — Large documents split at meaningful boundaries (sections, clauses, paragraphs)
- **PII Detection** — Automatically identifies Social Security Numbers, emails, phone numbers, and addresses
- **Cross-Chunk Context** — Maintains document-wide context across chunks so nothing is missed
- **Real-Time Progress** — Live progress bar with elapsed time during chunked analysis
- **Result Persistence** — Analysis results stored in DynamoDB + S3 from both the UI and batch pipeline
- **Secure Authentication** — AWS Cognito with SRP protocol and optional MFA
- **WAF Protection** — Rate limiting + AWS managed rule sets on the ALB
- **HTTPS Ready** — Conditional TLS 1.3 listener (provide ACM certificate ARN)
- **Production-Ready** — ECS Fargate, ALB, CI/CD, non-root container, least-privilege IAM

---

## Architecture: Multi-Agent Collaboration

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                            │
│              Streamlit App (CloudAge Blue Theme)                 │
│         Upload → Analyze → Chat about findings                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              DOCUMENT CHUNKING PIPELINE                          │
│                                                                 │
│   Chunking Engine → Context Manager → Sequential Invocation     │
│         ↓                                       ↓               │
│   Split at semantic              Maintain doc-level context     │
│   boundaries                     across all chunks              │
│         ↓                                       ↓               │
│                    Synthesis Engine                              │
│              (Combines all chunk results)                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│          ┌─────────────────────────────────────┐                │
│          │   eDiscovery Collaborator Agent      │                │
│          │         (SUPERVISOR)                 │                │
│          └────────────────┬────────────────────┘                │
│                           │                                     │
│              Step 1: Classify & Detect PII                      │
│                           ▼                                     │
│          ┌─────────────────────────────────────┐                │
│          │     Classification Agent             │                │
│          └────────────────┬────────────────────┘                │
│                           │                                     │
│              Step 2: Route to Specialist                        │
│              ┌────────────┼────────────┐                        │
│              ▼            ▼            ▼                        │
│   ┌──────────────┐ ┌──────────┐ ┌──────────────┐              │
│   │   Contract   │ │  Email   │ │    Legal     │              │
│   │    Agent     │ │  Agent   │ │    Agent     │              │
│   └──────────────┘ └──────────┘ └──────────────┘              │
│                                                                 │
│                    AMAZON BEDROCK                                │
│          Model: eu.amazon.nova-pro-v1:0                         │
│          (EU Cross-Region Inference)                             │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RESULT PERSISTENCE                            │
│                                                                 │
│   ┌──────────┐    ┌──────────┐                                 │
│   │ DynamoDB │    │ S3 Output│                                 │
│   │ (status) │    │  (JSON)  │                                 │
│   └──────────┘    └──────────┘                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Responsibilities

| Agent | Role | Key Outputs |
|-------|------|-------------|
| **eDiscovery Collaborator** | Supervisor — orchestrates the workflow | Executive summary, risk assessment, recommendations |
| **Classification Agent** | Triage — identifies type and PII | Document category, confidence score, PII inventory, risk level |
| **Contract Agent** | Specialist — extracts contract elements | Parties, dates, financials, obligations, termination clauses |
| **Email Agent** | Specialist — analyzes communications | Participants, topics, action items, sentiment, legal implications |
| **Legal Agent** | Specialist — evaluates legal documents | Arguments, citations, precedents, risk factors, privilege status |

---

## Quick Start

### Prerequisites

- Python 3.13+
- AWS CLI configured (`aws configure` with region `eu-north-1`)
- Docker (for containerized deployment)

### Automated Deployment

```bash
chmod +x deploy-full.sh
./deploy-full.sh --email your-admin@company.com
```

This single command deploys everything: Bedrock agents, ECS infrastructure, batch pipeline, and creates a Cognito user. A random password is generated automatically and displayed in the deployment summary.

### Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment (run deploy-full.sh first to generate .env)
# Or copy and fill in manually:
cp .env.example .env

# Run the app
streamlit run Analyze-LegalDocumentsUI.py
```

### Docker

```bash
docker build -t legal-doc-analyzer .
docker run -p 8501:8501 --env-file .env legal-doc-analyzer
```

---

## Environment Variables

All configuration flows from CloudFormation outputs via environment variables. No values are hardcoded in source code.

| Variable | Source | Purpose |
|----------|--------|---------|
| `AWS_REGION` | aws configure | AWS region (default: eu-north-1) |
| `BEDROCK_AGENT_ID` | Agents stack output | Supervisor agent ID |
| `BEDROCK_AGENT_ALIAS_ID` | Agents stack output | Supervisor agent alias |
| `CLASSIFICATION_AGENT_ID` | Agents stack output | Classification agent (direct calls) |
| `CLASSIFICATION_ALIAS_ID` | Agents stack output | Classification agent alias |
| `CONTRACT_AGENT_ID` | Agents stack output | Contract agent (direct calls) |
| `CONTRACT_ALIAS_ID` | Agents stack output | Contract agent alias |
| `EMAIL_AGENT_ID` | Agents stack output | Email agent (direct calls) |
| `EMAIL_ALIAS_ID` | Agents stack output | Email agent alias |
| `LEGAL_AGENT_ID` | Agents stack output | Legal agent (direct calls) |
| `LEGAL_ALIAS_ID` | Agents stack output | Legal agent alias |
| `COGNITO_POOL_ID` | Infra stack output | Cognito User Pool ID |
| `COGNITO_APP_CLIENT_ID` | Infra stack output | Cognito App Client ID |
| `COGNITO_APP_CLIENT_SECRET` | Cognito API | App Client Secret |
| `RESULTS_TABLE` | Batch stack output | DynamoDB table for results |
| `OUTPUT_BUCKET` | Batch stack output | S3 bucket for analysis JSON |
| `CHUNK_MAX_SIZE` | Optional (default: 8000) | Max chars per chunk |
| `CHUNK_MIN_SIZE` | Optional (default: 500) | Min chars per chunk |
| `CHUNK_CONTEXT_WINDOW` | Optional (default: 1500) | Context prepended to each chunk |
| `CHUNK_OVERLAP` | Optional (default: 200) | Overlap between adjacent chunks |

---

## Infrastructure

### CloudFormation Stacks

| Stack | Template | Resources |
|-------|----------|-----------|
| **Agents** | `LEGAL-Documents-Collab-Amazon-Model.yaml` | 5 Bedrock Agents, Guardrail, IAM roles |
| **Infrastructure** | `LEGAL-Documents-Infrastructure.yaml` | ECS, ALB, WAF, ECR, CodeBuild, Cognito |
| **Batch Pipeline** | `LEGAL-Documents-BatchPipeline.yaml` | S3, Step Functions, Lambda, DynamoDB |

### AWS Services Used

| Service | Purpose |
|---------|---------|
| ECS Fargate | Runs Streamlit container (non-root, 512 CPU / 1024 MB) |
| ALB | Load balancing, sticky sessions, HTTPS termination |
| WAF v2 | Rate limiting (300 req/5min per IP), AWS managed rule sets |
| ECR | Docker image registry (scan on push, 5-image lifecycle) |
| Cognito | Authentication (SRP, optional TOTP MFA, 12-char passwords) |
| Bedrock | Multi-agent AI inference (EU cross-region) |
| CodeBuild + CodeCommit | CI/CD pipeline |
| S3 | Document storage (input + output, AES-256 encrypted) |
| Step Functions | Batch document processing orchestration |
| Lambda | Text extraction + agent invocation + result storage |
| DynamoDB | Processing status tracking (PAY_PER_REQUEST) |
| CloudWatch | Application logs (90-day retention) |

### Deploy Steps

```bash
# Option A: Fully automated (recommended)
./deploy-full.sh --email admin@yourcompany.com

# Option B: Manual stack-by-stack (see deploy-full.sh for full parameter list)
aws cloudformation create-stack --stack-name legal-doc-agents ...
aws cloudformation create-stack --stack-name legal-doc-infra ...
aws cloudformation create-stack --stack-name legal-doc-batch ...
```

### HTTPS Setup

To enable HTTPS, provide an ACM certificate ARN:

```bash
./deploy-full.sh --email admin@company.com --cert-arn arn:aws:acm:eu-north-1:123456789:certificate/abc-123
```

Or pass `CertificateArn` when creating/updating the infra stack. When a certificate is provided:
- HTTPS listener is created on port 443 (TLS 1.3 policy)
- HTTP port 80 redirects to HTTPS (301)

### Tear Down

```bash
./teardown.sh
# Or manually:
aws cloudformation delete-stack --stack-name legal-doc-batch
aws cloudformation delete-stack --stack-name legal-doc-infra
aws cloudformation delete-stack --stack-name legal-doc-agents
```

---

## Security

### Authentication & Access Control

| Control | Implementation |
|---------|---------------|
| User authentication | AWS Cognito (SRP protocol, passwords never in cleartext) |
| MFA | Optional TOTP (software token) — users can enable in their account |
| Password policy | 12 characters minimum, requires uppercase + lowercase + numbers + symbols |
| Network isolation | ECS tasks only accept traffic from ALB security group |
| WAF | Rate limiting (300 req/5min/IP) + CommonRuleSet + KnownBadInputs |
| HTTPS | TLS 1.3 (conditional on certificate ARN) with HTTP→HTTPS redirect |

### IAM Least-Privilege

| Role | Permissions |
|------|-------------|
| ECS Task Role | `bedrock:InvokeAgent` + scoped DynamoDB/S3 access |
| CodeBuild Role | Scoped ECR push + specific log group + CodeCommit pull |
| Lambda Role | Scoped S3/DynamoDB + `bedrock:InvokeAgent` |
| Bedrock Agent Roles | Scoped to specific inference profiles + guardrail |

### Application Security

| Measure | Detail |
|---------|--------|
| Container | Non-root user (`appuser`), minimal base image (`python:3.13-slim`) |
| XSS protection | All user/agent content HTML-escaped before rendering |
| XSRF protection | Enabled in Streamlit (`--server.enableXsrfProtection=true`) |
| CORS | Enabled (`--server.enableCORS=true`) |
| Prompt injection | Bedrock Guardrail with MEDIUM-strength prompt attack detection |
| PII in outputs | SSN, credit cards, PINs, passwords auto-anonymized by guardrail |
| Dependency pinning | All packages pinned to exact versions |
| No hardcoded secrets | All IDs/credentials flow from CloudFormation via environment variables |
| ALB header security | Invalid headers dropped (`drop_invalid_header_fields.enabled`) |

### Guardrail Configuration

Attached to all 5 agents:

| Policy | Strength |
|--------|----------|
| Sexual content | LOW (input + output) |
| Violence | LOW (input + output) |
| Hate speech | LOW (input + output) |
| Prompt attack / jailbreak | MEDIUM (input) |
| PII: SSN, credit cards, PINs, passwords | ANONYMIZE (output) |

---

## Document Chunking Pipeline

For documents exceeding 10,000 characters:

| Parameter | Default | Range | Configurable via |
|-----------|---------|-------|-----------------|
| Max chunk size | 8,000 chars | 1,000–50,000 | Sidebar / env var |
| Min chunk size | 500 chars | 100–5,000 | Sidebar / env var |
| Context window | 1,500 chars | 200–5,000 | Sidebar / env var |
| Chunk overlap | 200 chars | 0–2,000 | Sidebar / env var |

Configuration precedence: **Sidebar** > **Environment variables** > **Dataclass defaults**

---

## Batch Processing Pipeline

For processing documents at scale without the UI:

```bash
# Upload documents to trigger processing
aws s3 cp contract.pdf s3://<ENV>-doc-input-<ACCOUNT>-<REGION>/upload/

# Bulk upload
aws s3 cp ./legal-docs/ s3://<ENV>-doc-input-<ACCOUNT>-<REGION>/upload/ --recursive

# Check status
aws dynamodb scan --table-name <ENV>-doc-results --filter-expression "#s = :v" \
  --expression-attribute-names '{"#s":"status"}' \
  --expression-attribute-values '{":v":{"S":"COMPLETED"}}'
```

**Flow:** S3 upload → EventBridge → Step Functions → (Extract Text → Analyze via Bedrock → Store Results)

**Supported formats:** PDF, DOCX, TXT

---

## Result Persistence

Both the Streamlit app and the batch pipeline write results to the same DynamoDB table and S3 bucket:

| Source | DynamoDB Record | S3 Object |
|--------|----------------|-----------|
| Streamlit app | `source: "streamlit_app"`, includes user info | `results/YYYY/MM/DD/<doc_id>/<filename>.json` |
| Batch pipeline | `source: "batch_pipeline"` | Same path pattern |

This gives you a unified view of all analyzed documents regardless of entry point.

---

## Running Tests

```bash
pip install pytest
pytest
```

**189 unit tests** run in < 0.2 seconds. All AWS calls are mocked — no cloud access needed.

---

## Project Structure

```
├── Analyze-LegalDocumentsUI.py          # Streamlit application (main entry point)
├── document_chunking/                   # Core chunking pipeline package
│   ├── __init__.py                      # Public API exports
│   ├── config.py                        # ChunkConfig dataclass with validation
│   ├── models.py                        # Data models (Chunk, Finding, SynthesisReport)
│   ├── chunking_engine.py              # Semantic boundary detection & text splitting
│   ├── context_manager.py             # Cross-chunk context propagation
│   ├── synthesis_engine.py            # Result deduplication & final report
│   └── document_processor.py          # Pipeline orchestrator
├── legal-mcp-server/                   # MCP server for IDE integration
│   ├── server.py                       # FastMCP tool exposing Bedrock agents
│   ├── requirements.txt               # MCP server dependencies
│   └── README.md                       # MCP server usage
├── tests/                              # 189 unit tests (pytest)
├── LEGAL-Documents-Collab-Amazon-Model.yaml   # CloudFormation: Bedrock agents
├── LEGAL-Documents-Infrastructure.yaml        # CloudFormation: ECS/ALB/WAF/Cognito
├── LEGAL-Documents-BatchPipeline.yaml         # CloudFormation: S3/Step Functions/Lambda
├── Dockerfile                          # Non-root Python 3.13-slim container
├── buildspec.yml                       # CodeBuild CI/CD spec
├── requirements.txt                    # Pinned Python dependencies
├── deploy-full.sh                      # Automated deployment (all stacks)
├── teardown.sh                         # Stack teardown
└── .env.example                        # Environment variable template
```

---

## License

CloudAge Global — Internal Use

---

*Built by [CloudAge](https://cloudage.llc) — Powered by Amazon Bedrock*
