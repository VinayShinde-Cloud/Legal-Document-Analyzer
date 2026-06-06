# CloudAge Legal Document Analyzer

AI-powered legal document analysis using Amazon Bedrock's multi-agent collaboration. Upload contracts, emails, or legal documents and receive comprehensive analysis including classification, PII detection, risk assessment, and actionable recommendations.

![CloudAge](https://assets.cloudage.llc/logo.png)


aws cloudformation create-stack \
  --stack-name AnalyzeDoc-batch-pipeline \
  --template-body file://LEGAL-Documents-BatchPipeline.yaml \
  --parameters \
    ParameterKey=EnvironmentName,ParameterValue=LegalDocSetup \
    ParameterKey=AgentId,ParameterValue=$BEDROCK_AGENT_ID \
    ParameterKey=AgentAliasId,ParameterValue=$BEDROCK_AGENT_ALIAS_ID \
  --capabilities CAPABILITY_IAM

---

## Features

- **Multi-Agent AI Analysis** — 5 specialized agents collaborate to analyze documents
- **Semantic Document Chunking** — Large documents are split at meaningful boundaries (sections, clauses, paragraphs) for comprehensive analysis
- **PII Detection** — Automatically identifies Social Security Numbers, emails, phone numbers, and addresses
- **Cross-Chunk Context** — Maintains document-wide context across chunks so nothing is missed
- **Real-Time Progress** — Live progress bar with elapsed time during chunked analysis
- **Secure Authentication** — AWS Cognito with SRP protocol (passwords never transmitted in cleartext)
- **Production-Ready** — Deployed on ECS Fargate with ALB, CI/CD via CodeCommit + CodeBuild

---

## Architecture: Multi-Agent Collaboration

The system uses Amazon Bedrock's multi-agent collaboration pattern with one supervisor agent orchestrating four specialist agents:

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
│   Chunking_Engine → Context_Manager → Sequential Invocation     │
│         ↓                                       ↓               │
│   Split at semantic              Maintain doc-level context     │
│   boundaries                     across all chunks              │
│         ↓                                       ↓               │
│                    Synthesis_Engine                              │
│              (Combines all chunk results)                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│          ┌─────────────────────────────────────┐                │
│          │   eDiscovery Collaborator Agent      │                │
│          │         (SUPERVISOR)                 │                │
│          │                                     │                │
│          │  • Receives document chunks         │                │
│          │  • Orchestrates analysis workflow    │                │
│          │  • Synthesizes final report         │                │
│          └────────────────┬────────────────────┘                │
│                           │                                     │
│              Step 1: Classify & Detect PII                      │
│                           │                                     │
│                           ▼                                     │
│          ┌─────────────────────────────────────┐                │
│          │     Classification Agent             │                │
│          │                                     │                │
│          │  • Document type (Contract/Email/   │                │
│          │    Legal)                           │                │
│          │  • PII detection (SSN, emails,     │                │
│          │    phones, addresses)              │                │
│          │  • Risk level assessment           │                │
│          └────────────────┬────────────────────┘                │
│                           │                                     │
│              Step 2: Route to Specialist                        │
│                           │                                     │
│              ┌────────────┼────────────┐                        │
│              ▼            ▼            ▼                        │
│   ┌──────────────┐ ┌──────────┐ ┌──────────────┐              │
│   │   Contract   │ │  Email   │ │    Legal     │              │
│   │    Agent     │ │  Agent   │ │    Agent     │              │
│   │              │ │          │ │              │              │
│   │ • Parties    │ │ • Sender │ │ • Arguments  │              │
│   │ • Key dates  │ │ • Topics │ │ • Citations  │              │
│   │ • Financial  │ │ • Action │ │ • Precedents │              │
│   │   terms      │ │   items  │ │ • Risk       │              │
│   │ • Obligations│ │ • Tone   │ │   factors    │              │
│   │ • Termination│ │ • Legal  │ │ • Privilege  │              │
│   │   clauses    │ │   risk   │ │   indicators │              │
│   └──────────────┘ └──────────┘ └──────────────┘              │
│                                                                 │
│                    AMAZON BEDROCK                                │
│          Model: eu.amazon.nova-pro-v1:0                         │
│          (EU Cross-Region Inference)                             │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Responsibilities

| Agent | Role | Key Outputs |
|-------|------|-------------|
| **eDiscovery Collaborator** | Supervisor — orchestrates the full workflow | Executive summary, final risk assessment, recommended actions |
| **Classification Agent** | Triage — identifies document type and flags PII | Document category, confidence score, PII inventory, risk level |
| **Contract Agent** | Specialist — extracts contract elements | Parties, dates, financials, obligations, termination clauses |
| **Email Agent** | Specialist — analyzes communications | Participants, topics, action items, sentiment, legal implications |
| **Legal Agent** | Specialist — evaluates legal documents | Arguments, citations, precedents, risk factors, privilege status |

### How They Collaborate

1. **Classification first** — Every document goes to the Classification Agent for triage
2. **Smart routing** — Based on the classification result, the Supervisor routes to the appropriate specialist
3. **Specialist analysis** — The domain expert performs deep analysis specific to that document type
4. **Synthesis** — The Supervisor combines all findings into a unified report with deduplication

---

## Document Chunking Pipeline

For documents exceeding 10,000 characters, the system uses semantic chunking:

```
Document Text
     │
     ▼
┌──────────────────┐     ┌─────────────────────┐
│ Chunking_Engine  │────▶│ Semantic Boundaries │
│                  │     │ • Section headings  │
│ Split at meaning │     │ • Clause numbers    │
│ boundaries       │     │ • Page breaks       │
│                  │     │ • Paragraph breaks   │
└──────────────────┘     └─────────────────────┘
     │
     ▼
┌──────────────────┐     ┌─────────────────────┐
│ Context_Manager  │────▶│ Per-Chunk Context   │
│                  │     │ • Document summary  │
│ Maintain context │     │ • Chunk position    │
│ across chunks    │     │ • Defined terms     │
│                  │     │ • Party names       │
└──────────────────┘     └─────────────────────┘
     │
     ▼
┌──────────────────┐     ┌─────────────────────┐
│ Sequential Agent │────▶│ Per-Chunk Analysis  │
│ Invocation       │     │ • Retry on throttle │
│                  │     │ • Skip on failure   │
│ With progress    │     │ • Progress updates  │
└──────────────────┘     └─────────────────────┘
     │
     ▼
┌──────────────────┐     ┌─────────────────────┐
│ Synthesis_Engine │────▶│ Final Report        │
│                  │     │ • Deduplicated      │
│ Combine results  │     │ • Coverage gaps     │
│ via Agent call   │     │ • Location refs     │
└──────────────────┘     └─────────────────────┘
```

**Key parameters (configurable):**
- Max chunk size: 8,000 chars (range: 1,000–50,000)
- Min chunk size: 500 chars (range: 100–5,000)
- Context window: 1,500 chars (range: 200–5,000)
- Chunk overlap: 200 chars (range: 0–2,000)

---

## Infrastructure

```
┌─────────────────────────────────────────────────────────┐
│                     eu-central-1                         │
│                                                         │
│  ┌───────────┐    ┌───────────┐    ┌───────────────┐   │
│  │    ALB    │───▶│  Fargate  │───▶│    Bedrock    │   │
│  │  (HTTP)   │    │  (8501)   │    │   Agent API   │   │
│  └───────────┘    └───────────┘    └───────────────┘   │
│       ▲                │                                │
│       │                ▼                                │
│  ┌────┴────┐    ┌───────────┐    ┌───────────────┐     │
│  │ Cognito │    │    ECR    │◀───│  CodeBuild    │     │
│  │  (Auth) │    │  (Image)  │    │  (CI/CD)      │     │
│  └─────────┘    └───────────┘    └───────┬───────┘     │
│                                          │              │
│                                   ┌──────┴──────┐      │
│                                   │ CodeCommit  │      │
│                                   │   (Repo)    │      │
│                                   └─────────────┘      │
└─────────────────────────────────────────────────────────┘
```

| Service | Resource | Purpose |
|---------|----------|---------|
| ECS Fargate | `legal-doc-analyzer` cluster | Runs the Streamlit container |
| ALB | `legal-doc-alb` | Stable DNS, load balancing, future HTTPS |
| ECR | `legal-doc-analyzer` repo | Docker image registry |
| CodeCommit | `legal-doc-analyzer` repo | Source code repository |
| CodeBuild | `legal-doc-analyzer-build` | Automated Docker builds on push |
| Cognito | `legal-doc-analyzer-users` pool | User authentication (SRP) |
| Bedrock | Multi-agent with Nova Pro | AI inference (EU cross-region) |
| CloudWatch | `/ecs/legal-doc-analyzer` | Application logs |

---

## Getting Started

### Prerequisites

- AWS CLI configured with appropriate permissions
- Docker installed (for local development)
- Python 3.13+

### Local Development

```bash
# Clone the repository
git clone https://git-codecommit.eu-central-1.amazonaws.com/v1/repos/legal-doc-analyzer
cd legal-doc-analyzer

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AWS_REGION=eu-central-1
export BEDROCK_AGENT_ID=PO5MANKEJ7
export BEDROCK_AGENT_ALIAS_ID=JBCQI46K23
export COGNITO_POOL_ID=eu-central-1_6gWLCx0L9
export COGNITO_APP_CLIENT_ID=31piugl5insei2m4nf08jp4gm9
export COGNITO_APP_CLIENT_SECRET=<your-secret>

# Run the app
streamlit run Analyze-LegalDocumentsUI.py
```

### Docker

```bash
docker build -t legal-doc-analyzer .
docker run -p 8501:8501 \
  -e AWS_REGION=eu-central-1 \
  -e BEDROCK_AGENT_ID=PO5MANKEJ7 \
  -e BEDROCK_AGENT_ALIAS_ID=JBCQI46K23 \
  -e AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
  -e AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY} \
  legal-doc-analyzer
```

### Deploy to AWS

```bash
# Push code (triggers CodeBuild automatically)
git add . && git commit -m "Update" && git push origin main

# Or use the deploy script for manual push to ECR
./deploy.sh
```

---

## Project Structure

```
├── Analyze-LegalDocumentsUI.py      # Streamlit application
├── document_chunking/               # Chunking pipeline package
│   ├── __init__.py
│   ├── config.py                    # ChunkConfig with validation
│   ├── models.py                    # Type definitions
│   ├── chunking_engine.py           # Semantic boundary detection & splitting
│   ├── context_manager.py           # Cross-chunk context management
│   ├── synthesis_engine.py          # Result deduplication & report generation
│   └── document_processor.py        # Pipeline orchestrator
├── tests/                           # 189 unit tests
│   ├── test_config.py
│   ├── test_chunking_engine.py
│   ├── test_context_manager.py
│   ├── test_synthesis_engine.py
│   └── test_document_processor.py
├── LEGAL-Documents-Collab-Amazon-Model.yaml  # CloudFormation (Bedrock agents)
├── LEGAL-Documents-Infrastructure.yaml      # CloudFormation (ECS, ALB, ECR, Cognito, CodeBuild)
├── LEGAL-Documents-BatchPipeline.yaml       # CloudFormation (S3 + Step Functions batch)
├── Dockerfile                       # Container build
├── buildspec.yml                    # CodeBuild CI/CD
├── taskdef.json                     # ECS task definition
├── requirements.txt                 # Python dependencies
└── deploy.sh                        # Manual deployment script
```

---

## Security

- **Authentication:** AWS Cognito User Pool with SRP protocol
- **Guardrails:** Bedrock Guardrail blocks harmful content, off-topic queries, and enforces PII anonymization in outputs
- **Network:** Fargate tasks only accept traffic from ALB (no direct public access)
- **IAM:** Least-privilege roles for ECS execution and Bedrock access
- **Data:** EU cross-region inference keeps data within EU boundaries
- **Secrets:** Agent IDs and Cognito credentials stored as environment variables (use Secrets Manager for production)

### Guardrail Configuration

The `LegalDocGuardrail` is attached to all 5 agents and enforces:

| Policy | Behavior |
|--------|----------|
| **Content filters** | Blocks sexual, violence, hate, insults, misconduct content (HIGH strength) |
| **Prompt attack** | Blocks jailbreak and injection attempts |
| **Topic: Legal Advice** | Denies responses that give specific legal opinions or recommendations |
| **Topic: Off-Topic** | Denies non-document-analysis queries (poems, weather, coding, etc.) |
| **PII: SSN** | Anonymizes Social Security Numbers in agent outputs |
| **PII: Credit Cards** | Anonymizes credit/debit card numbers in outputs |
| **PII: Passwords/PINs** | Anonymizes passwords and PINs in outputs |

### Knowledge Base (Optional)

Enable RAG by setting `KnowledgeBaseEnabled=true` during stack deployment:

```bash
aws cloudformation update-stack \
  --stack-name AnalyzeDoc-bedrock-agents \
  --template-body file://LEGAL-Documents-Collab-Amazon-Model.yaml \
  --parameters \
    ParameterKey=EnvironmentName,ParameterValue=LegalDocSetup \
    ParameterKey=FoundationModelId,ParameterValue=eu.amazon.nova-pro-v1:0 \
    ParameterKey=KnowledgeBaseEnabled,ParameterValue=true \
  --capabilities CAPABILITY_IAM \
  --region eu-central-1
```

Then upload reference documents (legal precedents, company policies, contract templates) to the created S3 bucket:

```bash
# Get the bucket name from stack outputs
BUCKET=$(aws cloudformation describe-stacks --stack-name AnalyzeDoc-bedrock-agents \
  --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseBucketName`].OutputValue' --output text)

# Upload reference documents
aws s3 cp ./legal-references/ s3://${BUCKET}/ --recursive
```

---

## Configuration

All chunk processing parameters can be configured via:
1. **Streamlit sidebar** (highest priority)
2. **Environment variables** (`CHUNK_MAX_SIZE`, `CHUNK_MIN_SIZE`, `CHUNK_CONTEXT_WINDOW`, `CHUNK_OVERLAP`)
3. **Default values** (lowest priority)

---

## Agent Configuration

All agents are defined in `LEGAL-Documents-Collab-Amazon-Model.yaml` and deployed via CloudFormation. Here's how each is configured:

### Collaborator Agent (Supervisor) — 2–5s processing

| Property | Value |
|----------|-------|
| **Resource** | `CollabBedrockAgent` |
| **Role** | Central orchestrator and workflow manager |
| **Config** | `AgentCollaboration: "SUPERVISOR"` |
| **Connects to** | All 4 specialists via `AgentCollaborators` list |
| **Outputs** | Document routing decisions, consolidated final report |

The supervisor's `Instruction` defines the full workflow: classify first → route to specialist → synthesize results.

### Classification Agent — 5–10s processing

| Property | Value |
|----------|-------|
| **Resource** | `ClassificationAgent` |
| **Role** | Initial document triage and sensitivity detection |
| **Instruction** | Classify into Contract/Email/Legal + detect PII |
| **Outputs** | Document type, confidence score (0-100), PII inventory (SSN, emails, phones, addresses), risk level (HIGH/MEDIUM/LOW) |

### Email Analysis Agent — 10–20s processing

| Property | Value |
|----------|-------|
| **Resource** | `EmailAgent` |
| **Role** | Communication pattern analysis |
| **Instruction** | Analyze sender/recipients, topics, action items, sentiment, legal implications |
| **Outputs** | Participant maps, conversation threads, action items, sentiment score, legal risk flags |

### Legal Document Agent — 15–30s processing

| Property | Value |
|----------|-------|
| **Resource** | `LegalAgent` |
| **Role** | Court filing and legal brief analysis |
| **Instruction** | Analyze legal arguments, citations, precedents, risk factors, privilege indicators |
| **Outputs** | Case citations, legal arguments, procedural dates, risk factors (high/medium/low), privilege status |

### Contract Analysis Agent — 20–40s processing

| Property | Value |
|----------|-------|
| **Resource** | `ContractAgent` |
| **Role** | Contract terms extraction and risk assessment |
| **Instruction** | Analyze parties, key dates, financial terms, obligations, termination clauses |
| **Outputs** | Party details, dates, payment schedules, obligations per party, termination conditions, risk scores |

### Modifying Agent Behavior

Edit the `Instruction` field in the YAML and redeploy:

```bash
# Edit the agent instructions
vim LEGAL-Documents-Collab-Amazon-Model.yaml

# Update the deployed stack
aws cloudformation update-stack \
  --stack-name AnalyzeDoc-bedrock-agents \
  --template-body file://LEGAL-Documents-Collab-Amazon-Model.yaml \
  --parameters ParameterKey=EnvironmentName,ParameterValue=LegalDocSetup \
    ParameterKey=FoundationModelId,ParameterValue=eu.amazon.nova-pro-v1:0 \
  --capabilities CAPABILITY_IAM \
  --region eu-central-1
```

### Tuning Processing Times

| Factor | Where to configure | Impact |
|--------|-------------------|--------|
| Model choice | `FoundationModelId` parameter | Nova Lite = faster; Nova Pro = more thorough |
| Instruction length | Agent `Instruction` field | Shorter = faster response |
| Input size | Chunk size settings (sidebar/env vars) | Smaller chunks = faster per-chunk processing |
| Session timeout | `IdleSessionTTLInSeconds` per agent | Keepalive for multi-turn (default 30 min) |

### Adding a New Specialist Agent

1. Add the agent + alias resource in the YAML:
```yaml
NewSpecialistAgent:
  Type: AWS::Bedrock::Agent
  Properties:
    AgentName: !Sub "${EnvironmentName}-New-Specialist"
    Description: Agent for analyzing [your domain]
    AutoPrepare: true
    Instruction: |
      Your analysis instructions here...
    AgentResourceRoleArn: !GetAtt BedrockAgentExecutionRole.Arn
    IdleSessionTTLInSeconds: 1800
    FoundationModel: !Ref FoundationModelId

NewSpecialistAgentAlias:
  Type: AWS::Bedrock::AgentAlias
  Properties:
    AgentAliasName: !Sub "${EnvironmentName}-NewSpecialist"
    AgentId: !Ref NewSpecialistAgent
```

2. Add it to the Supervisor's `AgentCollaborators` list with a `CollaborationInstruction`
3. Add its alias ARN to the `CollabAgentPolicy` IAM policy resources
4. Update the Supervisor's `Instruction` to include routing logic for the new document type
5. Update the Classification Agent's categories to include the new type
6. Redeploy the stack

---

## Batch Processing Pipeline (S3 + Step Functions)

For processing hundreds of documents at scale without the Streamlit UI:

```
┌──────────────┐     ┌─────────────┐     ┌───────────────────────────────┐
│  S3 Bucket   │────▶│ EventBridge │────▶│      Step Functions           │
│  /upload/    │     │  (trigger)  │     │                               │
│              │     └─────────────┘     │  ┌─────────┐  ┌───────────┐  │
│  Drop docs   │                         │  │Extract  │─▶│  Analyze  │  │
│  here        │                         │  │  Text   │  │ (Bedrock) │  │
└──────────────┘                         │  └─────────┘  └─────┬─────┘  │
                                         │                     │        │
                                         │              ┌──────▼──────┐ │
                                         │              │   Store     │ │
                                         │              │  Results    │ │
                                         │              └─────────────┘ │
                                         └───────────────────────────────┘
                                                        │
                                         ┌──────────────┼──────────────┐
                                         ▼              ▼              ▼
                                   ┌──────────┐  ┌──────────┐  ┌──────────┐
                                   │ S3 Output│  │ DynamoDB  │  │CloudWatch│
                                   │ (JSON)   │  │ (status)  │  │ (logs)   │
                                   └──────────┘  └──────────┘  └──────────┘
```

### Deploy the Batch Pipeline

```bash
aws cloudformation create-stack \
  --stack-name AnalyzeDoc-batch-pipeline \
  --template-body file://LEGAL-Documents-BatchPipeline.yaml \
  --parameters \
    ParameterKey=EnvironmentName,ParameterValue=LegalDocSetup \
    ParameterKey=AgentId,ParameterValue=PO5MANKEJ7 \
    ParameterKey=AgentAliasId,ParameterValue=JBCQI46K23 \
  --capabilities CAPABILITY_IAM \
  --region eu-central-1
```

### Usage

```bash
# Upload a single document
aws s3 cp contract.pdf s3://LegalDocSetup-doc-input-015337708931-eu-central-1/upload/

# Upload an entire folder of documents
aws s3 cp ./legal-docs/ s3://LegalDocSetup-doc-input-015337708931-eu-central-1/upload/ --recursive

# Check processing status
aws dynamodb scan --table-name LegalDocSetup-doc-results --region eu-central-1

# Get results for a specific document
aws s3 ls s3://LegalDocSetup-doc-output-015337708931-eu-central-1/results/ --recursive
```

### How It Works

1. **Drop documents** into the S3 input bucket under the `upload/` prefix
2. **EventBridge** detects the upload and triggers the Step Functions workflow
3. **Extract Text** Lambda reads the document (uses Textract for PDFs)
4. **Analyze Document** Lambda invokes the Bedrock Collaborator Agent (with retry logic)
5. **Store Results** Lambda saves the analysis JSON to the output bucket and updates DynamoDB
6. **DynamoDB** tracks status (PROCESSING → ANALYZING → COMPLETED/FAILED) for dashboarding

### Supported Formats

| Format | Extraction Method |
|--------|-------------------|
| PDF | Amazon Textract (OCR + text) |
| TXT | Direct read from S3 |
| DOCX | Basic text extraction |

### Concurrency & Throttling

- Step Functions processes one document per execution (no internal parallelism)
- EventBridge triggers a separate execution per file upload (concurrent by default)
- Built-in retry with exponential backoff for Bedrock throttling (10s → 20s → 40s)
- Lifecycle policy moves input files to Glacier after 30 days
- DynamoDB uses PAY_PER_REQUEST billing (scales automatically)

---

## License

CloudAge Global — Internal Use

---

*Built by [CloudAge](https://cloudage.llc) — Powered by Amazon Bedrock*
