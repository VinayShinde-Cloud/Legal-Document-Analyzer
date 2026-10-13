"""Bedrock Converse Multi-Agent Engine.

Production-grade multi-agent orchestration powered by Amazon Bedrock Converse API
using Amazon Nova foundation models (amazon.nova-lite-v1:0 and amazon.nova-pro-v1:0).

Replaces deprecated AWS::Bedrock::Agent with direct, high-performance Converse API.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("bedrock_agents")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# Default models in us-east-1
DEFAULT_CLASSIFICATION_MODEL = os.environ.get("CLASSIFICATION_MODEL", "amazon.nova-lite-v1:0")
DEFAULT_SPECIALIST_MODEL = os.environ.get("SPECIALIST_MODEL", "amazon.nova-pro-v1:0")
DEFAULT_SUPERVISOR_MODEL = os.environ.get("SUPERVISOR_MODEL", "amazon.nova-pro-v1:0")

# ==============================================================================
# SPECIALIZED AGENT SYSTEM PROMPTS
# ==============================================================================

CLASSIFICATION_SYSTEM_PROMPT = """You are a document classification and PII detection specialist. Your task is to analyze the provided document text and produce a structured assessment.

## Classification Task
Classify the document into EXACTLY ONE of these categories:
- **Contract**: Agreements, terms of service, NDAs, SLAs, purchase orders, leases
- **Email**: Email communications, correspondence, message threads
- **Legal**: Court filings, briefs, motions, legal opinions, regulations, statutes

## PII Detection Task
Scan the entire document for the following PII types:
- Social Security Numbers (SSNs)
- Email addresses
- Phone numbers
- Physical postal addresses

## Output Format
Respond with a clear section header and valid JSON:
Document Classification:
Category: Contract|Email|Legal
Risk Level: HIGH|MEDIUM|LOW
Confidence Score: 0-100%

PII Findings:
- SSNs: [list or None]
- Emails: [list or None]
- Phones: [list or None]
- Addresses: [list or None]

Reasoning: <concise explanation>
"""

CONTRACT_SYSTEM_PROMPT = """You are a senior contract analysis specialist. Your task is to extract key contractual elements, risks, and obligations from contracts and agreements.

## Analysis Areas
1. **Parties**: Named parties, their roles, and defined entities.
2. **Key Dates**: Effective date, expiration/renewal dates, milestones, notice deadlines.
3. **Financial Terms**: Total values, payment schedules, currencies, penalties, and fee structures.
4. **Obligations**: Specific duties and commitments organized by party.
5. **Termination Clauses**: Termination for convenience, for cause, notice periods, cure periods, early termination fees.
6. **Risk Assessment**: One-sided indemnities, unlimited liabilities, missing warranty protections, governing law.

## Output Format
Provide a well-structured breakdown:
Specialist Analysis:
Executive Summary: <summary of the contract>
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
- <immediate action item>
- <negotiation or follow-up recommendation>
"""

EMAIL_SYSTEM_PROMPT = """You are an email communication analysis specialist. Your task is to analyze email threads, extract communication patterns, participants, commitments, sentiment, and legal implications.

## Analysis Areas
1. **Participants**: Sender, recipients (To/CC/BCC), and referenced third parties.
2. **Discussion Topics**: Core subjects discussed, organized by importance.
3. **Action Items & Commitments**: Specific tasks with assigned owners and deadlines.
4. **Sentiment & Tone**: Professional tone, urgency, hostility, or distress.
5. **Legal Implications**: Admissions of liability, commitments, disputes, notices, waiver of rights.
6. **Timeline**: Chronology of events or deadlines.

## Output Format
Specialist Analysis:
Executive Summary: <summary of the communication thread>
Key Findings:
- Participants: <sender, recipients, third parties>
- Core Topics: <main discussion points>
- Commitments & Action Items: <who agreed to do what>
- Sentiment: <positive/neutral/negative and confidence>
- Legal Implications: <admissions, potential exposures>

Risk Assessment:
Level: HIGH|MEDIUM|LOW
Factors: <bulleted risk factors>

Recommended Actions:
- <recommended steps or follow-ups>
"""

LEGAL_SYSTEM_PROMPT = """You are a legal analysis specialist. Your task is to evaluate court filings, briefs, motions, opinions, regulatory compliance documents, and statutes.

## Analysis Areas
1. **Procedural Information**: Court, case number, filing dates, document type.
2. **Legal Arguments**: Primary claims, defenses, and supporting evidence.
3. **Citations & Precedents**: Case law, statutory references, and judicial precedents.
4. **Risk Factors**: Procedural pitfalls, jurisdictional exposure, substantive liabilities.
5. **Privilege Indicators**: Attorney-client privilege or work-product doctrine status.

## Output Format
Specialist Analysis:
Executive Summary: <summary of the legal document>
Key Findings:
- Procedural Details: <court, case, filing type>
- Legal Arguments: <claims, defenses>
- Citations & Authorities: <cases, statutes cited>
- Privilege Status: <privileged or non-privileged>

Risk Assessment:
Level: HIGH|MEDIUM|LOW
Factors: <procedural or substantive risks>

Recommended Actions:
- <strategic legal recommendations>
"""

SUPERVISOR_SYSTEM_PROMPT = """You are the Lead eDiscovery Collaborator and Supervisor Agent for CloudAge Legal Document Analysis.

Your role is to coordinate specialist insights, evaluate risks, and synthesize a comprehensive, executive-ready report combining:
1. Document Classification & PII inventory
2. Specialist Analysis (Contract terms, Email communications, or Legal arguments)
3. Cross-domain Risk Assessment
4. Concrete, actionable recommendations

Always structure your final synthesis clearly:
Executive Summary:
<High-level summary of the document, primary purpose, and overall assessment>

Document Classification:
<Type: Contract/Email/Legal | Confidence | Overall Risk>

PII Findings:
<Inventory of sensitive data found or confirmation of clean document>

Key Findings:
<Consolidated key findings from specialist analyses>

Risk Assessment:
<Overall Risk Level (HIGH/MEDIUM/LOW) followed by specific risk factors and business impacts>

Recommended Actions:
- <Immediate actions>
- <Short-term reviews>
- <Long-term governance or legal follow-up>
"""

CHAT_SYSTEM_PROMPT = """You are CloudAge Legal Assistant, an expert AI legal document analyst.
Answer the user's questions accurately and concisely based strictly on the uploaded document's content and findings.
Always cite specific sections, clauses, or excerpts from the document when answering.
Never hallucinate terms not present in the document.
"""


# ==============================================================================
# CORE ENGINE IMPLEMENTATION
# ==============================================================================

class BedrockConverseAgentEngine:
    """Multi-agent engine utilizing Amazon Bedrock Runtime Converse API."""

    def __init__(
        self,
        region: Optional[str] = None,
        classification_model: str = DEFAULT_CLASSIFICATION_MODEL,
        specialist_model: str = DEFAULT_SPECIALIST_MODEL,
        supervisor_model: str = DEFAULT_SUPERVISOR_MODEL,
    ):
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.classification_model = classification_model
        self.specialist_model = specialist_model
        self.supervisor_model = supervisor_model

        self._client = boto3.client("bedrock-runtime", region_name=self.region)

    def converse(
        self,
        model_id: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        max_retries: int = 4,
    ) -> str:
        """Call Bedrock converse API with exponential backoff on throttling."""
        messages = [
            {
                "role": "user",
                "content": [{"text": user_message}],
            }
        ]
        system = [{"text": system_prompt}]

        inference_config = {
            "maxTokens": max_tokens,
            "temperature": temperature,
        }

        for attempt in range(max_retries):
            try:
                response = self._client.converse(
                    modelId=model_id,
                    system=system,
                    messages=messages,
                    inferenceConfig=inference_config,
                )
                output_message = response.get("output", {}).get("message", {})
                content_blocks = output_message.get("content", [])
                text_parts = [block.get("text", "") for block in content_blocks if "text" in block]
                return "".join(text_parts)

            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("ThrottlingException", "TooManyRequestsException", "ModelNotReadyException"):
                    if attempt < max_retries - 1:
                        sleep_time = (2 ** attempt) * 2 + 1
                        time.sleep(sleep_time)
                        continue
                elif code == "ValidationException" and "nova-pro" in model_id:
                    # Fallback to Nova Lite if Nova Pro is constrained
                    logger.warning(f"Falling back from {model_id} to {self.classification_model}")
                    return self.converse(
                        model_id=self.classification_model,
                        system_prompt=system_prompt,
                        user_message=user_message,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                raise

        raise RuntimeError(f"Max retries exceeded for Bedrock Converse with model {model_id}")

    def classify_and_detect_pii(self, text: str) -> str:
        """Run the Classification & PII specialist agent."""
        sample = text[:8000]
        prompt = f"Please classify this document and detect sensitive PII:\n\n{sample}"
        return self.converse(
            model_id=self.classification_model,
            system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
            user_message=prompt,
        )

    def run_specialist(self, doc_type: str, text: str) -> str:
        """Run the appropriate specialist agent based on document category."""
        doc_type_lower = doc_type.lower()
        sample = text[:15000]

        if "email" in doc_type_lower:
            system_prompt = EMAIL_SYSTEM_PROMPT
            prompt = f"Analyze the following email communication:\n\n{sample}"
        elif "legal" in doc_type_lower:
            system_prompt = LEGAL_SYSTEM_PROMPT
            prompt = f"Analyze the following legal document:\n\n{sample}"
        else:
            # Default to contract
            system_prompt = CONTRACT_SYSTEM_PROMPT
            prompt = f"Analyze the following contract/agreement:\n\n{sample}"

        return self.converse(
            model_id=self.specialist_model,
            system_prompt=system_prompt,
            user_message=prompt,
        )

    def synthesize(self, prompt: str) -> str:
        """Run the Supervisor agent to synthesize all chunk/specialist analyses."""
        return self.converse(
            model_id=self.supervisor_model,
            system_prompt=SUPERVISOR_SYSTEM_PROMPT,
            user_message=prompt,
        )

    def invoke(self, input_text: str) -> str:
        """Unified invoker compatible with document_processor and UI."""
        # Detect if this is a synthesis request from SynthesisEngine
        if "Synthesize the following chunk analyses" in input_text or "Provide: executive summary" in input_text:
            return self.synthesize(input_text)

        # Standard document chunk or single document analysis
        classification_result = self.classify_and_detect_pii(input_text)

        doc_type = "contract"
        lower_class = classification_result.lower()
        if "category: email" in lower_class or "email" in lower_class:
            doc_type = "email"
        elif "category: legal" in lower_class or "court" in lower_class:
            doc_type = "legal"

        specialist_result = self.run_specialist(doc_type, input_text)

        combined = (
            f"Document Classification:\n{classification_result}\n\n"
            f"{specialist_result}"
        )
        return combined

    def chat(self, user_question: str, document_context: str = "", chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        """Chat about the document with full context."""
        context_prompt = (
            f"Document Excerpt and Findings:\n{document_context[:12000]}\n\n"
            f"User Question: {user_question}"
        ) if document_context else user_question

        return self.converse(
            model_id=self.specialist_model,
            system_prompt=CHAT_SYSTEM_PROMPT,
            user_message=context_prompt,
        )


# Singleton instance helper
_engine_instance: Optional[BedrockConverseAgentEngine] = None

def get_agent_engine(region: Optional[str] = None) -> BedrockConverseAgentEngine:
    global _engine_instance
    if _engine_instance is None or (region and _engine_instance.region != region):
        _engine_instance = BedrockConverseAgentEngine(region=region)
    return _engine_instance
