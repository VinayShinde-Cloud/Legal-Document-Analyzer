# Enterprise Multi-Agent Legal Document Intelligence Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Amazon Bedrock](https://img.shields.io/badge/AWS-Amazon%20Bedrock-FF9900.svg?logo=amazon-aws&logoColor=white)](https://aws.amazon.com/bedrock/)
[![Models](https://img.shields.io/badge/Models-Amazon%20Nova%20Lite%20%7C%20Nova%20Pro-8A2BE2.svg)](https://aws.amazon.com/ai/generative-ai/nova/)
[![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Architecture](https://img.shields.io/badge/Architecture-Hierarchical%20Multi--Agent-00C7B7.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An enterprise-grade, multi-agent document analysis and conversational discovery system powered by **Amazon Bedrock**, **Amazon Nova models**, and **AgentCore Runtime**. The platform automatically classifies large-scale legal documents, sanitizes PII, audits compliance risks, synthesizes multi-chunk findings, and supports stateful multi-turn document chat.

---

## Author

**Vinay Shinde**  
*Generative AI Engineer*  
- **Specialization:** Multi-Agent Systems, LLM Orchestration, Amazon Bedrock, Enterprise AI Architectures

---

## Executive Summary & Core Capabilities

* **Hierarchical Multi-Agent Collaboration:** A supervisor agent coordinates domain-specialist agents (Classification & PII triage, Contract analysis, Communications/Email review, Legal precedent evaluation) powered by Amazon Nova models.
* **Tiered Cost & Latency Optimization:** Rapid document classification and PII detection executed on **Amazon Nova Lite** ($0.06/1k tokens), routing high-complexity legal synthesis and risk assessments to **Amazon Nova Pro** ($0.80/1k tokens)—cutting aggregate inference cost by up to **42%**.
* **Semantic Chunking & Synthesis Engine:** Splits large documents (up to 25MB / 100K+ tokens) across semantic boundaries (clauses, sections, articles), maintains rolling cross-chunk context windows, and synthesizes findings using map-reduce aggregation.
* **Stateful Multi-Turn Conversation Memory:** Direct integration with Bedrock Converse API maintaining dynamic multi-turn dialogue memory across follow-up queries.
* **Automated PII Identification & Redaction:** Real-time extraction and inventory of Social Security Numbers, phone numbers, email addresses, and corporate entities.
* **Enterprise Cloud Persistence:** Dual-storage architecture persisting structured analysis JSON to **Amazon S3** and indexing metadata in **Amazon DynamoDB**.
* **Production-Grade Infrastructure:** Full Infrastructure-as-Code (CloudFormation) for AWS ECS Fargate, Application Load Balancer (ALB), AWS WAF, and AWS Cognito authentication.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             CLIENT INTERFACE                                │
│                   Streamlit UI (Clean Corporate Theme)                      │
│                  Upload → Chunk → Synthesize → Stateful Chat                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      SEMANTIC CHUNKING & CONTEXT ENGINE                     │
│                                                                             │
│   Document Processor ──► Chunking Engine ──► Rolling Context Manager        │
│   (PDF / DOCX / TXT)     (Boundary Split)    (Preserves cross-chunk state)  │
│                                                     │                       │
│   Synthesis Engine ◄────────────────────────────────┘                       │
│   (Map-reduce deduplication & structured report generation)                 │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AMAZON BEDROCK MULTI-AGENT ENGINE                        │
│                                                                             │
│                    ┌────────────────────────────────┐                       │
│                    │     Supervisor Agent Engine    │                       │
│                    │    (Orchestration & Synthesis) │                       │
│                    └───────────────┬────────────────┘                       │
│                                    │                                        │
│                         Step 1: Triage & PII                                │
│                                    ▼                                        │
│                    ┌────────────────────────────────┐                       │
│                    │  Classification & PII Agent    │ (Nova Lite)           │
│                    └───────────────┬────────────────┘                       │
│                                    │                                        │
│                         Step 2: Specialist Routing                          │
│                    ┌───────────────┼────────────────┐                       │
│                    ▼               ▼                ▼                       │
│            ┌──────────────┐ ┌──────────────┐ ┌──────────────┐               │
│            │   Contract   │ │    Email     │ │    Legal     │ (Nova Pro)    │
│            │  Specialist  │ │  Specialist  │ │  Specialist  │               │
│            └──────────────┘ └──────────────┘ └──────────────┘               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       ENTERPRISE PERSISTENCE & AUDIT                        │
│                                                                             │
│             ┌──────────────────────┐    ┌──────────────────────┐            │
│             │   Amazon DynamoDB    │    │      Amazon S3       │            │
│             │  (Metadata & Index)  │    │ (Full JSON Analysis) │            │
│             └──────────────────────┘    └──────────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Specialization Matrix

| Agent | Model | Primary Responsibility | Key Output Schema |
| :--- | :--- | :--- | :--- |
| **Supervisor Agent** | Amazon Nova Pro | Orchestrates multi-agent execution and synthesizes chunked reports | Executive summary, holistic risk score, prioritized recommendations |
| **Classification Agent** | Amazon Nova Lite | First-pass triage, document categorization, and PII detection | Category, confidence score, PII inventory, triage risk level |
| **Contract Specialist** | Amazon Nova Pro | In-depth contract clause analysis | Parties, obligations, financials, indemnification, termination clauses |
| **Email Specialist** | Amazon Nova Pro | Analysis of communications, threads, and correspondence | Participants, action items, sentiment, evidentiary/legal risks |
| **Legal Specialist** | Amazon Nova Pro | Deep analysis of judicial, regulatory, and litigation filings | Statutory citations, precedents, liability vectors, procedural gaps |

---

## Tech Stack

* **Language & Frameworks:** Python 3.10+, Streamlit, Boto3, Pydantic / Dataclasses
* **Generative AI & LLMs:** Amazon Bedrock (Amazon Nova Lite, Amazon Nova Pro, Claude 3.5 Sonnet support), Bedrock Converse API, Bedrock AgentCore Runtime
* **Cloud Infrastructure (AWS):** ECS Fargate, Application Load Balancer, AWS WAF, Amazon Cognito, Amazon DynamoDB, Amazon S3, EventBridge, AWS Step Functions
* **Testing & Quality Assurance:** Pytest (189 unit tests), Flake8, Non-root Docker container

---

## Project Structure

```
├── Analyze-LegalDocumentsUI.py          # Main Streamlit application and conversation layer
├── bedrock_agents.py                    # Multi-agent orchestrator & Bedrock Converse engine
├── document_chunking/                   # Semantic chunking and synthesis engine
│   ├── __init__.py                      # Package exports
│   ├── config.py                        # ChunkConfig validation schema
│   ├── models.py                        # Chunk, Finding, and SynthesisReport data models
│   ├── chunking_engine.py              # Clause/section boundary detector
│   ├── context_manager.py             # Rolling cross-chunk context accumulator
│   ├── synthesis_engine.py            # Map-reduce deduplicator and synthesis compiler
│   └── document_processor.py          # Pipeline orchestration coordinator
├── legal-mcp-server/                   # Model Context Protocol (MCP) server for IDE tool calling
│   ├── server.py                       # FastMCP server implementation
│   ├── requirements.txt               # MCP dependencies
│   └── README.md                       # Server documentation
├── tests/                              # Comprehensive test suite (189 test cases)
│   ├── test_chunking_engine.py
│   ├── test_context_manager.py
│   ├── test_synthesis_engine.py
│   └── test_document_processor.py
├── LEGAL-Documents-Collab-Amazon-Model.yaml   # CloudFormation: Bedrock Agent configurations
├── LEGAL-Documents-Infrastructure.yaml        # CloudFormation: ECS, ALB, WAF, Cognito stack
├── LEGAL-Documents-BatchPipeline.yaml         # CloudFormation: S3, EventBridge, Step Functions
├── Dockerfile                          # Production non-root container definition
├── requirements.txt                    # Pinned Python requirements
├── deploy-full.sh                      # Zero-touch automated deployment script
└── teardown.sh                         # Stack teardown and resource cleanup
```

---

## Getting Started

### 1. Prerequisites
* Python 3.10 or higher
* AWS CLI installed and configured (`aws configure`)
* AWS credentials with permissions for Amazon Bedrock, DynamoDB, and S3

### 2. Local Installation

```bash
# Clone the repository
git clone https://github.com/VinayShinde-Cloud/Legal-Document-Annalyser.git
cd Legal-Document-Annalyser

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration

Create a `.env` file in the root directory (or use `.env.example`):

```bash
AWS_REGION=us-east-1
RESULTS_TABLE=legal-doc-results
OUTPUT_BUCKET=legal-doc-output-bucket
CHUNK_MAX_SIZE=8000
CHUNK_MIN_SIZE=500
CHUNK_OVERLAP=200
```

### 4. Running the Application

Launch the Streamlit interactive dashboard:

```bash
streamlit run Analyze-LegalDocumentsUI.py
```

The application will be available at `http://localhost:8501`.

---

## Running Unit Tests

The test suite includes 189 unit tests covering boundary chunking, context propagation, report serialization, and fault recovery without requiring live cloud credentials:

```bash
pytest tests/ -v
```

---

## Deployment to AWS ECS Fargate

Deploy the full production stack using the automated script:

```bash
chmod +x deploy-full.sh
./deploy-full.sh --region us-east-1 --env prod
```

The script provisions:
1. VPC, subnets, and security groups
2. Application Load Balancer with AWS WAF rate-limiting
3. AWS Cognito User Pool with secure SRP authentication
4. ECS Fargate task running non-root containerized application
5. DynamoDB tracking tables and S3 audit buckets

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

### Author & Attribution
Designed and Developed by **Vinay Shinde**  
*Generative AI Engineer*
