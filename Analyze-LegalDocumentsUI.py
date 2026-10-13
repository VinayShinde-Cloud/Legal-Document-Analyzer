from __future__ import annotations

import streamlit as st
import boto3
import uuid
import time
import json
from datetime import datetime
import io
import os
import html as html_lib

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

# Additional imports for file processing
import PyPDF2
import docx
import tempfile

# Document chunking pipeline imports
from document_chunking import (
    ChunkConfig,
    DocumentProcessor,
    ProcessingResult,
    SynthesisReport,
    Finding,
    FailedChunk,
    load_config_from_env,
)

# Configure page with a custom theme and favicon
st.set_page_config(
    page_title="CloudAge | Legal Document Analysis",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "Legal Document Analysis powered by CloudAge & Amazon Bedrock"
    }
)

# ─────────────────────────────────────────────────────────────
# Clean & Responsive Styling (Demo-Ready)
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Clean Hero Header */
    .hero-container {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1.5rem 1.75rem;
        margin-bottom: 1.5rem;
        color: #ffffff;
    }
    .hero-title {
        font-size: 1.85rem;
        font-weight: 700;
        color: #f8fafc;
        margin: 0 0 0.35rem 0;
    }
    .hero-subtitle {
        font-size: 0.95rem;
        color: #94a3b8;
        margin: 0;
    }
    .hero-badge {
        display: inline-block;
        background: #1e3a5f;
        border: 1px solid #3b82f6;
        color: #60a5fa;
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-top: 0.75rem;
    }

    /* Cards & Steps */
    .upload-zone {
        background: #f8fafc;
        border: 2px dashed #cbd5e1;
        border-radius: 12px;
        padding: 1.5rem 1.25rem;
        text-align: center;
        margin-bottom: 1rem;
    }
    .upload-icon { font-size: 2.2rem; margin-bottom: 0.5rem; display: block; }
    .upload-title { font-size: 1.05rem; font-weight: 600; color: #1e293b; margin-bottom: 0.25rem; }
    .upload-desc { font-size: 0.85rem; color: #64748b; }

    .steps-container {
        display: flex;
        flex-direction: column;
        gap: 0.6rem;
    }
    .step-item {
        display: flex;
        align-items: center;
        gap: 0.85rem;
        padding: 0.75rem 1rem;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }
    .step-number {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.8rem;
        font-weight: 700;
        flex-shrink: 0;
    }
    .step-1 .step-number { background: #dbeafe; color: #1e40af; }
    .step-2 .step-number { background: #ede9fe; color: #5b21b6; }
    .step-3 .step-number { background: #dcfce7; color: #166534; }
    .step-title { font-size: 0.88rem; font-weight: 600; color: #1e293b; }
    .step-desc { font-size: 0.78rem; color: #64748b; }

    .file-info-card {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
    }

    /* Chat Messages */
    .user-msg {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 10px;
        padding: 0.85rem 1.15rem;
        margin: 0.4rem 0;
        color: #1e293b;
        font-size: 0.95rem;
        line-height: 1.5;
    }
    .assistant-msg {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.85rem 1.15rem;
        margin: 0.4rem 0;
        color: #1e293b;
        font-size: 0.95rem;
        line-height: 1.5;
    }

    /* Section Headers & Findings */
    .section-header {
        font-size: 1.05rem;
        font-weight: 700;
        color: #0f172a;
        margin-top: 1.25rem;
        margin-bottom: 0.6rem;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid #e2e8f0;
    }
    .finding-item {
        background: #fffbeb;
        border: 1px solid #fde68a;
        border-left: 3px solid #f59e0b;
        border-radius: 6px;
        padding: 0.65rem 0.9rem;
        margin: 0.4rem 0;
        font-size: 0.88rem;
        color: #1e293b;
    }
    .coverage-gap-warning {
        background: #fff7ed;
        border: 1px solid #fed7aa;
        border-left: 3px solid #f97316;
        border-radius: 6px;
        padding: 0.65rem 0.9rem;
        margin: 0.4rem 0;
        font-size: 0.88rem;
        color: #1e293b;
    }
    .processing-stats {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin: 0.5rem 0;
        font-size: 0.88rem;
        color: #166534;
    }
    .chunking-info {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-left: 3px solid #3b82f6;
        border-radius: 6px;
        padding: 0.65rem 0.9rem;
        font-size: 0.85rem;
        color: #1e293b;
        margin-top: 0.4rem;
    }
    .file-size-error {
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-left: 3px solid #ef4444;
        border-radius: 6px;
        padding: 0.65rem 0.9rem;
        margin: 0.5rem 0;
        color: #991b1b;
    }
    .config-section {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.85rem;
        margin-bottom: 0.85rem;
    }
    .app-footer {
        margin-top: 3rem;
        text-align: center;
        padding: 1.5rem 0;
        border-top: 1px solid #e2e8f0;
        font-size: 0.8rem;
        color: #64748b;
    }
</style>
""", unsafe_allow_html=True)

# --- AWS Cognito Authentication ---
from streamlit_cognito_auth import CognitoAuthenticator

# Cognito configuration (same region as deployment)
COGNITO_POOL_ID = os.environ.get("COGNITO_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")
COGNITO_APP_CLIENT_SECRET = os.environ.get("COGNITO_APP_CLIENT_SECRET", "")

authenticator = None
if COGNITO_POOL_ID and COGNITO_APP_CLIENT_ID:
    try:
        authenticator = CognitoAuthenticator(
            pool_id=COGNITO_POOL_ID,
            app_client_id=COGNITO_APP_CLIENT_ID,
            app_client_secret=COGNITO_APP_CLIENT_SECRET,
        )
        is_logged_in = authenticator.login()
        if not is_logged_in:
            st.stop()
    except Exception as e:
        st.warning(f"Cognito auth initialization note: {e}")

# User is authenticated
def logout():
    if authenticator:
        authenticator.logout()

# Initialize session state
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'document_uploaded' not in st.session_state:
    st.session_state.document_uploaded = False
if 'document_content' not in st.session_state:
    st.session_state.document_content = ""
if 'document_name' not in st.session_state:
    st.session_state.document_name = ""
if 'analysis_time' not in st.session_state:
    st.session_state.analysis_time = None
if 'processing_result' not in st.session_state:
    st.session_state.processing_result = None

# Default AWS region and agent configuration (read from environment variables if available)
if 'aws_region' not in st.session_state:
    st.session_state.aws_region = os.environ.get("AWS_REGION", "us-east-1")
if 'agent_id' not in st.session_state:
    st.session_state.agent_id = os.environ.get("BEDROCK_AGENT_ID", "bedrock-converse-engine")
if 'agent_alias_id' not in st.session_state:
    st.session_state.agent_alias_id = os.environ.get("BEDROCK_AGENT_ALIAS_ID", "nova-v1")
if 'config_saved' not in st.session_state:
    st.session_state.config_saved = True

# Constants
MAX_FILE_SIZE_MB = 25  # 25MB file size limit


# --- Streamlit ProgressCallback Implementation ---

class StreamlitProgressCallback:
    """ProgressCallback implementation for Streamlit UI updates.

    Uses st.progress() for the progress bar and st.empty() placeholders
    for status text updates during document processing.
    """

    def __init__(self, progress_bar, status_text, warning_container):
        """Initialize with Streamlit UI elements.

        Args:
            progress_bar: st.progress() element for the progress bar.
            status_text: st.empty() element for status messages.
            warning_container: st.container() for displaying chunk failure warnings.
        """
        self._progress_bar = progress_bar
        self._status_text = status_text
        self._warning_container = warning_container

    def on_chunk_complete(self, current: int, total: int, elapsed_seconds: float) -> None:
        """Update progress bar and status text when a chunk completes."""
        progress = current / total
        self._progress_bar.progress(progress)
        elapsed_str = DocumentProcessor.format_elapsed_time(elapsed_seconds)
        self._status_text.markdown(
            f"📊 Processing chunk {current}/{total} — Elapsed: {elapsed_str}"
        )

    def on_synthesis_start(self) -> None:
        """Show synthesis status with progress bar at 100%."""
        self._progress_bar.progress(1.0)
        self._status_text.markdown("🔄 Synthesizing results from all chunks...")

    def on_chunk_failed(self, chunk_position: int, section_heading: str | None) -> None:
        """Display a warning for each failed chunk."""
        heading_info = f" (Section: {section_heading})" if section_heading else ""
        with self._warning_container:
            st.warning(f"⚠️ Chunk {chunk_position}{heading_info} failed after retry attempts.")

    def on_complete(self, result: ProcessingResult) -> None:
        """Display completion stats."""
        elapsed_str = DocumentProcessor.format_elapsed_time(result.processing_time_seconds)
        if result.was_chunked:
            stats = (
                f"✅ Chunked analysis complete — "
                f"{result.successful_chunks}/{result.total_chunks} chunks processed, "
                f"{result.failed_chunks} failed — Total time: {elapsed_str}"
            )
        else:
            stats = f"✅ Processed as single piece — Total time: {elapsed_str}"
        self._status_text.markdown(stats)


# --- Helper Functions ---

def extract_text_from_pdf(file_content):
    """Extract text from PDF file content."""
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
    text = ""
    for page_num in range(len(pdf_reader.pages)):
        text += pdf_reader.pages[page_num].extract_text() + "\n"
    return text


def extract_text_from_docx(file_content):
    """Extract text from DOCX file content."""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name

    try:
        doc = docx.Document(tmp_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def extract_text_from_file(uploaded_file):
    """Extract text from uploaded file based on file type."""
    file_type = uploaded_file.name.split('.')[-1].lower()
    file_content = uploaded_file.getvalue()

    if file_type == 'pdf':
        return extract_text_from_pdf(file_content)
    elif file_type in ['docx', 'doc']:
        return extract_text_from_docx(file_content)
    elif file_type == 'txt':
        return file_content.decode('utf-8')
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


# Initialize Bedrock Converse Multi-Agent Engine
import bedrock_agents

def invoke_agent(input_text, max_retries=3):
    """Invoke the agent engine for conversational chat with the document."""
    try:
        engine = bedrock_agents.get_agent_engine(st.session_state.aws_region)
        doc_context = st.session_state.get("document_content", "")
        # Pass conversation history (memory) excluding current question
        all_messages = st.session_state.get("messages", [])
        chat_history = [m for m in all_messages if m.get("content") != input_text]
        return engine.chat(
            user_question=input_text,
            document_context=doc_context,
            chat_history=chat_history
        )
    except Exception as e:
        return f"Error: {str(e)}"


def agent_invoker_for_processor(input_text: str) -> str | None:
    """Agent invoker for chunked processing and synthesis via Bedrock Converse API.

    Coordinates the multi-agent workflow:
    1. Classification & PII Detection Agent (Nova Lite)
    2. Routed Specialist Agent: Contract, Email, or Legal (Nova Pro)
    3. Supervisor Agent for synthesis (Nova Pro)
    """
    engine = bedrock_agents.get_agent_engine(st.session_state.aws_region)
    return engine.invoke(input_text)


def save_document_to_input_bucket(uploaded_file) -> str | None:
    """Save the uploaded raw document into the S3 input drop zone bucket."""
    input_bucket = os.environ.get("INPUT_BUCKET", "")
    if not input_bucket:
        return None
    try:
        s3_client = boto3.client("s3", region_name=st.session_state.get("aws_region", "us-east-1"))
        key = f"upload/{uploaded_file.name}"
        s3_client.put_object(
            Bucket=input_bucket,
            Key=key,
            Body=uploaded_file.getvalue(),
        )
        return key
    except Exception as e:
        print(f"Warning: could not save to S3 input bucket: {e}")
        return None


def persist_analysis_result(filename: str, analysis_content, processing_result: dict) -> str | None:
    """Persist analysis result to DynamoDB and S3.

    Stores the analysis output in S3 as JSON and records metadata in DynamoDB,
    matching the same schema used by the batch pipeline for consistency.

    Args:
        filename: Original document filename.
        analysis_content: The analysis result (string or serialized dict).
        processing_result: Processing metadata dict from DocumentProcessor.

    Returns:
        The document_id if persistence succeeded, None if not configured.
    """
    results_table = os.environ.get("RESULTS_TABLE", "")
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")

    if not results_table or not output_bucket:
        return None

    try:
        dynamodb = boto3.resource("dynamodb", region_name=st.session_state.aws_region)
        s3_client = boto3.client("s3", region_name=st.session_state.aws_region)
        table = dynamodb.Table(results_table)

        document_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Serialize analysis content
        if isinstance(analysis_content, dict):
            analysis_json = json.dumps(analysis_content, indent=2, default=str)
        elif isinstance(analysis_content, str):
            analysis_json = analysis_content
        else:
            analysis_json = str(analysis_content)

        # Store in S3
        result_key = f"results/{datetime.utcnow().strftime('%Y/%m/%d')}/{document_id}/{filename}.json"
        s3_client.put_object(
            Bucket=output_bucket,
            Key=result_key,
            Body=json.dumps({
                "document_id": document_id,
                "filename": filename,
                "analysis": analysis_json,
                "source": "streamlit_app",
                "processed_at": timestamp,
                "text_length": len(st.session_state.document_content),
                "was_chunked": processing_result.get("was_chunked", False),
                "total_chunks": processing_result.get("total_chunks", 0),
                "successful_chunks": processing_result.get("successful_chunks", 0),
                "failed_chunks": processing_result.get("failed_chunks", 0),
                "processing_time_seconds": processing_result.get("processing_time_seconds", 0),
            }, indent=2, default=str),
            ContentType="application/json",
        )

        # Store metadata in DynamoDB
        table.put_item(Item={
            "document_id": document_id,
            "upload_timestamp": timestamp,
            "status": "COMPLETED",
            "filename": filename,
            "source": "streamlit_app",
            "result_key": result_key,
            "text_length": len(st.session_state.document_content),
            "was_chunked": processing_result.get("was_chunked", False),
            "total_chunks": processing_result.get("total_chunks", 0),
            "successful_chunks": processing_result.get("successful_chunks", 0),
            "failed_chunks": processing_result.get("failed_chunks", 0),
            "processing_time_seconds": str(processing_result.get("processing_time_seconds", 0)),
            "user": authenticator.get_username() if authenticator else "unknown",
        })

        return document_id

    except Exception as e:
        # Non-fatal: log but don't block the user
        st.toast(f"⚠️ Could not persist results: {str(e)[:100]}", icon="⚠️")
        return None


def build_chunk_config() -> ChunkConfig:
    """Build ChunkConfig with precedence: sidebar > env vars > defaults.

    Returns:
        A validated ChunkConfig instance.
    """
    # Start with env vars (or defaults if env vars not set)
    env_config = load_config_from_env()

    # Apply sidebar overrides if they exist in session state
    max_chunk_size = st.session_state.get('chunk_max_size', env_config.max_chunk_size)
    min_chunk_size = st.session_state.get('chunk_min_size', env_config.min_chunk_size)
    context_window_size = st.session_state.get('chunk_context_window', env_config.context_window_size)
    chunk_overlap = st.session_state.get('chunk_overlap', env_config.chunk_overlap)

    config = ChunkConfig(
        max_chunk_size=max_chunk_size,
        min_chunk_size=min_chunk_size,
        context_window_size=context_window_size,
        chunk_overlap=chunk_overlap,
    )

    return config


def render_synthesis_report(report: SynthesisReport):
    """Render a SynthesisReport as structured Streamlit content."""

    # Executive Summary
    st.markdown('<div class="section-header">📋 Executive Summary</div>', unsafe_allow_html=True)
    st.markdown(report.executive_summary)

    # Document Classification
    st.markdown('<div class="section-header">📁 Document Classification</div>', unsafe_allow_html=True)
    st.markdown(report.document_classification)

    # PII Findings
    st.markdown('<div class="section-header">🔒 PII Findings</div>', unsafe_allow_html=True)
    if report.pii_findings:
        for finding in report.pii_findings:
            location_ref = f"[Chunk {finding.chunk_position}, offset {finding.char_offset_start}-{finding.char_offset_end}]"
            st.markdown(
                f'<div class="finding-item">'
                f'<strong>{html_lib.escape(finding.finding_type)}:</strong> {html_lib.escape(finding.entity_value)} — '
                f'{html_lib.escape(finding.description)} <em>{html_lib.escape(location_ref)}</em>'
                f'</div>',
                unsafe_allow_html=True
            )
    else:
        st.markdown("No PII findings detected.")

    # Key Findings by Category
    st.markdown('<div class="section-header">🔍 Key Findings</div>', unsafe_allow_html=True)
    if report.key_findings_by_category:
        for category, findings in report.key_findings_by_category.items():
            st.markdown(f"**{html_lib.escape(category)}**")
            for finding in findings:
                location_ref = f"[Chunk {finding.chunk_position}, offset {finding.char_offset_start}-{finding.char_offset_end}]"
                st.markdown(
                    f'<div class="finding-item">'
                    f'{html_lib.escape(finding.entity_value)} — {html_lib.escape(finding.description)} <em>{html_lib.escape(location_ref)}</em>'
                    f'</div>',
                    unsafe_allow_html=True
                )
    else:
        st.markdown("No key findings identified.")

    # Risk Assessment
    st.markdown('<div class="section-header">⚠️ Risk Assessment</div>', unsafe_allow_html=True)
    st.markdown(report.risk_assessment)

    # Recommended Actions
    st.markdown('<div class="section-header">✅ Recommended Actions</div>', unsafe_allow_html=True)
    if report.recommended_actions:
        for i, action in enumerate(report.recommended_actions, 1):
            st.markdown(f"{i}. {html_lib.escape(action)}")
    else:
        st.markdown("No specific actions recommended.")

    # Coverage Gaps (if present)
    if report.coverage_gaps:
        st.markdown('<div class="section-header">📊 Coverage Gaps</div>', unsafe_allow_html=True)
        for gap in report.coverage_gaps:
            heading_info = f" (Section: {html_lib.escape(gap.section_heading)})" if gap.section_heading else ""
            st.markdown(
                f'<div class="coverage-gap-warning">'
                f'⚠️ <strong>Chunk {gap.chunk_position}{heading_info}:</strong> '
                f'{html_lib.escape(gap.error_message)} (Category: {html_lib.escape(gap.error_category)})'
                f'</div>',
                unsafe_allow_html=True
            )


def render_message_content(content):
    """Render message content handling both string and SynthesisReport types."""
    if isinstance(content, dict) and content.get('_type') == 'synthesis_report':
        # Reconstruct SynthesisReport from stored dict
        report = _reconstruct_synthesis_report(content)
        render_synthesis_report(report)
    elif isinstance(content, str) and content.startswith("{"):
        try:
            content_json = json.loads(content)
            st.json(content_json)
        except (json.JSONDecodeError, ValueError):
            escaped = html_lib.escape(content)
            st.markdown(
                f'<div class="assistant-msg">{escaped}</div>',
                unsafe_allow_html=True
            )
    else:
        escaped = html_lib.escape(str(content))
        st.markdown(
            f'<div class="assistant-msg">{escaped}</div>',
            unsafe_allow_html=True
        )


def _serialize_synthesis_report(report: SynthesisReport) -> dict:
    """Serialize a SynthesisReport to a dict for session state storage."""
    return {
        '_type': 'synthesis_report',
        'executive_summary': report.executive_summary,
        'document_classification': report.document_classification,
        'pii_findings': [
            {
                'entity_value': f.entity_value,
                'finding_type': f.finding_type,
                'chunk_position': f.chunk_position,
                'char_offset_start': f.char_offset_start,
                'char_offset_end': f.char_offset_end,
                'description': f.description,
            }
            for f in report.pii_findings
        ],
        'key_findings_by_category': {
            category: [
                {
                    'entity_value': f.entity_value,
                    'finding_type': f.finding_type,
                    'chunk_position': f.chunk_position,
                    'char_offset_start': f.char_offset_start,
                    'char_offset_end': f.char_offset_end,
                    'description': f.description,
                }
                for f in findings
            ]
            for category, findings in report.key_findings_by_category.items()
        },
        'risk_assessment': report.risk_assessment,
        'recommended_actions': report.recommended_actions,
        'coverage_gaps': [
            {
                'chunk_position': g.chunk_position,
                'section_heading': g.section_heading,
                'error_category': g.error_category,
                'error_message': g.error_message,
            }
            for g in report.coverage_gaps
        ] if report.coverage_gaps else None,
        'processing_metadata': report.processing_metadata,
    }


def _reconstruct_synthesis_report(data: dict) -> SynthesisReport:
    """Reconstruct a SynthesisReport from a serialized dict."""
    pii_findings = [
        Finding(**f) for f in data.get('pii_findings', [])
    ]
    key_findings = {
        category: [Finding(**f) for f in findings]
        for category, findings in data.get('key_findings_by_category', {}).items()
    }
    coverage_gaps = None
    if data.get('coverage_gaps'):
        coverage_gaps = [FailedChunk(**g) for g in data['coverage_gaps']]

    return SynthesisReport(
        executive_summary=data.get('executive_summary', ''),
        document_classification=data.get('document_classification', ''),
        pii_findings=pii_findings,
        key_findings_by_category=key_findings,
        risk_assessment=data.get('risk_assessment', ''),
        recommended_actions=data.get('recommended_actions', []),
        coverage_gaps=coverage_gaps,
        processing_metadata=data.get('processing_metadata', {}),
    )


def save_configuration():
    """Save configuration and reset session."""
    st.session_state.config_saved = True
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []


def reset_session():
    """Reset session and clear document state."""
    st.session_state.document_uploaded = False
    st.session_state.document_content = ""
    st.session_state.document_name = ""
    st.session_state.messages = []
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.analysis_time = None
    st.session_state.processing_result = None


# Region display mapping
REGION_DISPLAY_MAP = {
    "eu-north-1": "Stockholm",
    "eu-central-1": "Frankfurt",
    "eu-west-1": "Ireland",
    "eu-west-2": "London",
    "us-east-1": "N. Virginia",
    "us-east-2": "Ohio",
    "us-west-2": "Oregon"
}

# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    # Brand Logo Area
    st.markdown("""
    <div style="text-align:center; padding: 1rem 0 0.5rem 0;">
        <div style="font-size: 2rem; margin-bottom: 0.25rem;">⚖️</div>
        <div style="font-size: 1.1rem; font-weight: 700; 
            background: linear-gradient(135deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text;">CloudAge Legal AI</div>
        <div style="font-size: 0.7rem; color: #64748b; margin-top: 4px; letter-spacing: 1px; text-transform: uppercase;">
            Powered by Amazon Bedrock
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Show logged-in user and logout
    st.markdown("---")
    username = authenticator.get_username() if authenticator else "Admin / Local"
    st.markdown(f"👤 **{username}**")
    if authenticator:
        st.button("Logout", on_click=logout, type="secondary")

    # Configuration section
    st.markdown("### ⚙️ Agent Configuration")

    config_expanded = not st.session_state.config_saved
    with st.expander("Edit Configuration", expanded=config_expanded):
        st.markdown('<div class="config-section">', unsafe_allow_html=True)

        # AWS Region selection
        region_options = [
            "EU (Stockholm)",
            "EU (Frankfurt)",
            "EU (Ireland)",
            "EU (London)",
            "US East (N. Virginia)",
            "US East (Ohio)",
            "US West (Oregon)"
        ]

        region_mapping = {
            "EU (Stockholm)": "eu-north-1",
            "EU (Frankfurt)": "eu-central-1",
            "EU (Ireland)": "eu-west-1",
            "EU (London)": "eu-west-2",
            "US East (N. Virginia)": "us-east-1",
            "US East (Ohio)": "us-east-2",
            "US West (Oregon)": "us-west-2"
        }

        current_region_display = next(
            (display for display, code in region_mapping.items() if code == st.session_state.aws_region),
            region_options[0]
        )

        selected_region_display = st.selectbox(
            "AWS Region",
            options=region_options,
            index=region_options.index(current_region_display)
        )

        selected_region = region_mapping[selected_region_display]

        # Agent ID input
        agent_id = st.text_input("Agent ID", value=st.session_state.agent_id,
                                 help="CollabBedrockAgentId from CloudFormation outputs")

        # Agent Alias ID input
        agent_alias_id = st.text_input("Agent Alias ID", value=st.session_state.agent_alias_id,
                                       help="CollabBedrockAgentAliasId from CloudFormation outputs")

        # --- Chunk Configuration Section ---
        st.markdown("---")
        st.markdown("**📐 Chunk Configuration**")

        # Load env-based defaults for initial slider values
        env_config = load_config_from_env()

        chunk_max_size = st.slider(
            "Max Chunk Size (chars)",
            min_value=1000,
            max_value=50000,
            value=st.session_state.get('chunk_max_size', env_config.max_chunk_size),
            step=500,
            help="Maximum characters per chunk (1000-50000). Default: 8000",
            key="sidebar_chunk_max_size",
        )

        chunk_min_size = st.slider(
            "Min Chunk Size (chars)",
            min_value=100,
            max_value=5000,
            value=st.session_state.get('chunk_min_size', env_config.min_chunk_size),
            step=50,
            help="Minimum characters per chunk (100-5000). Default: 500",
            key="sidebar_chunk_min_size",
        )

        chunk_context_window = st.slider(
            "Context Window Size (chars)",
            min_value=200,
            max_value=5000,
            value=st.session_state.get('chunk_context_window', env_config.context_window_size),
            step=100,
            help="Context window prepended to each chunk (200-5000). Default: 1500",
            key="sidebar_chunk_context_window",
        )

        chunk_overlap = st.slider(
            "Chunk Overlap (chars)",
            min_value=0,
            max_value=2000,
            value=st.session_state.get('chunk_overlap', env_config.chunk_overlap),
            step=50,
            help="Characters overlapping between adjacent chunks (0-2000). Default: 200",
            key="sidebar_chunk_overlap",
        )

        # Validate chunk configuration and display warnings
        test_config = ChunkConfig(
            max_chunk_size=chunk_max_size,
            min_chunk_size=chunk_min_size,
            context_window_size=chunk_context_window,
            chunk_overlap=chunk_overlap,
        )
        validation_errors = test_config.validate()
        if validation_errors:
            for err in validation_errors:
                st.markdown(
                    f'<div class="validation-warning">⚠️ {err}</div>',
                    unsafe_allow_html=True,
                )
            st.caption("Invalid values will be replaced with defaults when processing.")

        # Information about limits
        st.info("📏 File limit: 25MB. Documents ≤ 10K chars → single pass; larger → chunked analysis.")

        # Save button
        if st.button("💾 Save Configuration"):
            if not agent_id or not agent_alias_id:
                st.error("Agent ID and Agent Alias ID are required.")
            else:
                st.session_state.aws_region = selected_region
                st.session_state.agent_id = agent_id
                st.session_state.agent_alias_id = agent_alias_id

                # Save chunk configuration to session state
                st.session_state.chunk_max_size = chunk_max_size
                st.session_state.chunk_min_size = chunk_min_size
                st.session_state.chunk_context_window = chunk_context_window
                st.session_state.chunk_overlap = chunk_overlap

                save_configuration()
                st.success("Configuration validated and saved!")
                time.sleep(1)
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    # Display current configuration
    if st.session_state.config_saved:
        st.markdown("#### 📊 Current Settings")
        region_display = REGION_DISPLAY_MAP.get(st.session_state.aws_region, st.session_state.aws_region)
        st.markdown(f"**Region:** {region_display}")
        st.markdown(f"**Agent:** `{st.session_state.agent_id[:12]}...`")
        st.markdown(f"**Chunk Size:** {st.session_state.get('chunk_max_size', 8000):,} chars")

    st.markdown("---")

    st.markdown("### 📋 Session Info")
    st.markdown(f"**ID:** `{st.session_state.session_id[:8]}...`")

    if st.session_state.document_uploaded:
        st.markdown(f"**Document:** {st.session_state.document_name}")
        if st.session_state.analysis_time:
            st.markdown(f"**Analyzed:** {st.session_state.analysis_time.strftime('%H:%M:%S')}")

        # Word count of document
        word_count = len(st.session_state.document_content.split())
        st.markdown(f"**Size:** {word_count:,} words")

        # Show processing result info if available
        if st.session_state.processing_result:
            result = st.session_state.processing_result
            if result.get('was_chunked'):
                st.markdown(f"**Mode:** Chunked ({result.get('successful_chunks', 0)}/{result.get('total_chunks', 0)})")
                if result.get('failed_chunks', 0) > 0:
                    st.markdown(f"**Failed:** {result['failed_chunks']} chunks")
            else:
                st.markdown(f"**Mode:** Single-pass")
            elapsed_str = DocumentProcessor.format_elapsed_time(result.get('processing_time_seconds', 0))
            st.markdown(f"**Time:** {elapsed_str}")

        # Add export conversation option
        if st.button("📥 Export Conversation"):
            conversation = ""
            for msg in st.session_state.messages:
                content = msg['content']
                if isinstance(content, dict):
                    content = json.dumps(content, indent=2)
                conversation += f"{msg['role'].upper()}: {content}\n\n"

            st.download_button(
                label="Download Conversation",
                data=conversation,
                file_name=f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain"
            )

# ─────────────────────────────────────────────────────────────
# MAIN CONTENT AREA
# ─────────────────────────────────────────────────────────────

# Hero Header
st.markdown("""
<div class="hero-container">
    <div class="hero-title">⚖️ Legal Document Analysis</div>
    <div class="hero-subtitle">
        AI-powered document classification, PII detection, risk assessment & compliance analysis
    </div>
    <div class="hero-badge">Amazon Bedrock • Nova Lite • Multi-Agent</div>
</div>
""", unsafe_allow_html=True)

# Check if configuration is saved before allowing document upload
if not st.session_state.config_saved:
    st.warning("⚙️ Please configure your Bedrock Agent settings in the sidebar first.")
else:
    # Create two columns for upload section
    if not st.session_state.document_uploaded:
        col1, col2 = st.columns([3, 2])

        with col1:
            st.markdown("""
            <div class="upload-zone">
                <span class="upload-icon">📤</span>
                <div class="upload-title">Upload a Legal Document</div>
                <div class="upload-desc">Drag & drop or browse — PDF, DOCX, TXT up to 25MB</div>
            </div>
            """, unsafe_allow_html=True)

            uploaded_file = st.file_uploader("Choose a document file",
                                            type=["txt", "pdf", "docx"],
                                            help=f"Supported formats: TXT, PDF, DOCX. Maximum file size: {MAX_FILE_SIZE_MB}MB",
                                            label_visibility="collapsed")

        with col2:
            st.markdown("""
            <div class="steps-container">
                <div class="step-item step-1">
                    <div class="step-number">01</div>
                    <div>
                        <div class="step-title">Upload Document</div>
                        <div class="step-desc">PDF, DOCX, or TXT format</div>
                    </div>
                </div>
                <div class="step-item step-2">
                    <div class="step-number">02</div>
                    <div>
                        <div class="step-title">AI Analysis</div>
                        <div class="step-desc">Classification, PII, risks & compliance</div>
                    </div>
                </div>
                <div class="step-item step-3">
                    <div class="step-number">03</div>
                    <div>
                        <div class="step-title">Chat & Explore</div>
                        <div class="step-desc">Ask follow-up questions about findings</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Display file information if uploaded
        if uploaded_file:
            file_size_bytes = len(uploaded_file.getvalue())
            file_size_mb = file_size_bytes / (1024 * 1024)

            # Use DocumentProcessor's file size validation
            processor = DocumentProcessor(
                config=ChunkConfig(),
                agent_invoker=lambda x: None,
            )
            size_error = processor.validate_file_size(file_size_bytes)

            if size_error:
                st.markdown(
                    f'<div class="file-size-error">'
                    f'⚠️ <strong>File too large:</strong> {size_error}'
                    f'</div>',
                    unsafe_allow_html=True
                )
            else:
                # File is within size limit, display file info
                file_type = uploaded_file.name.split('.')[-1].upper()
                st.markdown(f"""
                <div class="file-info-card">
                    <div style="display:flex; align-items:center; gap:1rem;">
                        <div style="font-size:2.5rem;">📄</div>
                        <div>
                            <div style="font-weight:600; font-size:1rem; color:#1e293b;">{html_lib.escape(uploaded_file.name)}</div>
                            <div style="font-size:0.85rem; color:#64748b; margin-top:4px;">
                                {file_type} • {file_size_mb:.2f} MB
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Process the document
                if st.button("🚀 Analyze Document", key="analyze_btn"):
                    # Set up progress UI elements
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    warning_container = st.container()

                    status_text.markdown("📄 Extracting text from document...")

                    try:
                        # Extract text based on file type
                        file_content = extract_text_from_file(uploaded_file)

                        if not file_content or not file_content.strip():
                            st.error("The document appears to be empty or could not be parsed.")
                        else:
                            # Save document content to session state
                            st.session_state.document_content = file_content
                            st.session_state.document_name = uploaded_file.name
                            st.session_state.document_uploaded = True
                            st.session_state.analysis_time = datetime.now()

                            # Upload raw document to S3 input drop zone
                            save_document_to_input_bucket(uploaded_file)

                            # Build configuration with precedence
                            config = build_chunk_config()
                            validation_errors = config.validate()
                            if validation_errors:
                                # Use defaults if config is invalid
                                config = ChunkConfig()
                                st.warning("Configuration validation failed. Using default chunk parameters.")

                            # Create progress callback
                            progress_callback = StreamlitProgressCallback(
                                progress_bar=progress_bar,
                                status_text=status_text,
                                warning_container=warning_container,
                            )

                            # Create DocumentProcessor and process
                            doc_processor = DocumentProcessor(
                                config=config,
                                agent_invoker=agent_invoker_for_processor,
                                progress_callback=progress_callback,
                            )

                            status_text.markdown("🔄 Analyzing document...")
                            result = doc_processor.process_document(file_content, uploaded_file.name)

                            # Store processing result metadata in session state
                            st.session_state.processing_result = {
                                'was_chunked': result.was_chunked,
                                'total_chunks': result.total_chunks,
                                'successful_chunks': result.successful_chunks,
                                'failed_chunks': result.failed_chunks,
                                'processing_time_seconds': result.processing_time_seconds,
                            }

                            # Build message content based on result type
                            if isinstance(result.report, SynthesisReport):
                                # Chunked analysis - store serialized report
                                report_content = _serialize_synthesis_report(result.report)
                            else:
                                # Pass-through string response
                                report_content = result.report if isinstance(result.report, str) else str(result.report)

                            # Add to conversation history
                            st.session_state.messages.append(
                                {"role": "user", "content": f"Please analyze this document: {uploaded_file.name}"}
                            )
                            st.session_state.messages.append(
                                {"role": "assistant", "content": report_content}
                            )

                            # Persist results to DynamoDB + S3
                            doc_id = persist_analysis_result(
                                filename=uploaded_file.name,
                                analysis_content=report_content,
                                processing_result=st.session_state.processing_result,
                            )
                            if doc_id:
                                st.session_state.persisted_doc_id = doc_id

                            # Force a rerun to show the chat interface
                            st.rerun()

                    except Exception as e:
                        st.error(f"An error occurred: {str(e)}")

    # Chat interface once document is uploaded
    if st.session_state.document_uploaded:
        # Create tabs for different views
        tab1, tab2, tab3 = st.tabs(["💬 Chat", "📊 Dashboard", "📄 Document"])

        with tab1:
            st.markdown(
                f'<div class="section-header" style="font-size:1.15rem; margin-top:0.5rem;">'
                f'💬 Conversation — {html_lib.escape(st.session_state.document_name)}</div>',
                unsafe_allow_html=True
            )

            # Show processing info
            if st.session_state.processing_result:
                result_info = st.session_state.processing_result
                elapsed_str = DocumentProcessor.format_elapsed_time(result_info.get('processing_time_seconds', 0))
                if result_info.get('was_chunked'):
                    st.markdown(
                        f'<div class="processing-stats">'
                        f'📊 <strong>Chunked analysis:</strong> '
                        f'{result_info["successful_chunks"]}/{result_info["total_chunks"]} chunks processed, '
                        f'{result_info["failed_chunks"]} failed — Total time: {elapsed_str}'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f'<div class="chunking-info">'
                        f'📄 <strong>Processed as single piece</strong> — Total time: {elapsed_str}'
                        f'</div>',
                        unsafe_allow_html=True
                    )

            if st.session_state.get("persisted_doc_id"):
                out_bucket = os.environ.get("OUTPUT_BUCKET", "")
                table_name = os.environ.get("RESULTS_TABLE", "")
                st.caption(f"💾 **Cloud Persistence:** Saved to S3 (`s3://{out_bucket}/`) & DynamoDB (`{table_name}`) — Record ID: `{st.session_state.persisted_doc_id[:8]}...`")

            # Create a container for chat messages
            chat_container = st.container()

            # Place the chat input
            user_input = st.chat_input("Ask a question about the document...")

            # Display all messages in the container
            with chat_container:
                for message in st.session_state.messages:
                    if message["role"] == "user":
                        with st.chat_message("user", avatar="👤"):
                            st.markdown(
                                f'<div class="user-msg">{html_lib.escape(str(message["content"]))}</div>',
                                unsafe_allow_html=True
                            )
                    else:
                        with st.chat_message("assistant", avatar="🤖"):
                            render_message_content(message["content"])

            # Handle user input after displaying messages
            if user_input:
                st.session_state.messages.append({"role": "user", "content": user_input})

                with st.spinner("Getting response..."):
                    response = invoke_agent(user_input)

                st.session_state.messages.append(
                    {"role": "assistant", "content": response if isinstance(response, str) else json.dumps(response)}
                )

                st.rerun()

        with tab2:
            st.markdown('<div class="section-header" style="font-size:1.15rem; margin-top:0.5rem;">📊 Analysis Dashboard</div>', unsafe_allow_html=True)

            # Get the latest analysis content
            last_analysis = None
            for msg in reversed(st.session_state.messages):
                if msg["role"] == "assistant":
                    last_analysis = msg["content"]
                    break

            if last_analysis and isinstance(last_analysis, dict) and last_analysis.get('_type') == 'synthesis_report':
                report_data = last_analysis

                # --- KPI Metrics Row ---
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    pii_count = len(report_data.get('pii_findings', []))
                    st.metric("🔒 PII Items Found", pii_count, delta_color="inverse")
                with col2:
                    findings_count = sum(len(f) for f in report_data.get('key_findings_by_category', {}).values())
                    st.metric("🔍 Key Findings", findings_count)
                with col3:
                    risk = report_data.get('risk_assessment', 'Unknown')
                    risk_label = "HIGH" if "high" in risk.lower() else "MEDIUM" if "medium" in risk.lower() else "LOW"
                    st.metric("⚠️ Risk Level", risk_label)
                with col4:
                    actions_count = len(report_data.get('recommended_actions', []))
                    st.metric("✅ Actions Required", actions_count)

                st.markdown("---")

                # --- Charts Row ---
                col_left, col_right = st.columns(2)

                with col_left:
                    # PII Types Distribution
                    st.markdown("**PII Distribution by Type**")
                    pii_findings = report_data.get('pii_findings', [])
                    if pii_findings:
                        pii_types = {}
                        for f in pii_findings:
                            pii_type = f.get('finding_type', 'unknown')
                            pii_types[pii_type] = pii_types.get(pii_type, 0) + 1
                        import pandas as pd
                        df_pii = pd.DataFrame(list(pii_types.items()), columns=['Type', 'Count'])
                        st.bar_chart(df_pii.set_index('Type'))
                    else:
                        st.success("No PII detected in this document.")

                with col_right:
                    # Findings by Category
                    st.markdown("**Findings by Category**")
                    key_findings = report_data.get('key_findings_by_category', {})
                    if key_findings:
                        import pandas as pd
                        categories = {k: len(v) for k, v in key_findings.items()}
                        df_cat = pd.DataFrame(list(categories.items()), columns=['Category', 'Count'])
                        st.bar_chart(df_cat.set_index('Category'))
                    else:
                        st.info("No categorized findings in this analysis.")

                st.markdown("---")

                # --- Processing Stats ---
                if st.session_state.processing_result:
                    result_info = st.session_state.processing_result
                    st.markdown("**⏱️ Processing Statistics**")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Chunks", result_info.get('total_chunks', 0))
                    with col2:
                        st.metric("Successful", result_info.get('successful_chunks', 0))
                    with col3:
                        elapsed = DocumentProcessor.format_elapsed_time(result_info.get('processing_time_seconds', 0))
                        st.metric("Processing Time", elapsed)

                    # Processing success rate
                    total = result_info.get('total_chunks', 1)
                    success = result_info.get('successful_chunks', 0)
                    if total > 0:
                        rate = success / total
                        st.progress(rate, text=f"Chunk success rate: {rate*100:.0f}%")

                st.markdown("---")

                # --- Document Classification ---
                st.markdown("**📁 Document Classification**")
                classification = report_data.get('document_classification', 'Unknown')
                st.info(f"📁 **Type:** {classification}")

                # --- Recommended Actions Timeline ---
                actions = report_data.get('recommended_actions', [])
                if actions:
                    st.markdown("**✅ Recommended Actions**")
                    for i, action in enumerate(actions, 1):
                        st.checkbox(action, key=f"action_{i}", value=False)

            elif last_analysis and isinstance(last_analysis, str) and len(last_analysis) > 50:
                # Simple analysis (pass-through) — show basic stats
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("📄 Document Type", "Single-Pass")
                with col2:
                    word_count = len(st.session_state.document_content.split())
                    st.metric("📝 Word Count", f"{word_count:,}")
                with col3:
                    char_count = len(st.session_state.document_content)
                    st.metric("🔤 Characters", f"{char_count:,}")

                st.markdown("---")
                st.markdown("**Analysis Summary**")
                st.markdown(last_analysis[:1000] if isinstance(last_analysis, str) else "Analysis complete.")
            else:
                st.info("Upload and analyze a document to see dashboard analytics.")

        with tab3:
            st.markdown('<div class="section-header" style="font-size:1.15rem; margin-top:0.5rem;">📄 Document Content</div>', unsafe_allow_html=True)

            # Display document content
            file_extension = st.session_state.document_name.split('.')[-1].lower()

            if file_extension == 'pdf':
                st.info("Displaying extracted text from PDF document")
            elif file_extension in ['docx', 'doc']:
                st.info("Displaying extracted text from Word document")

            st.text_area("Document Text", st.session_state.document_content, height=400, disabled=True)

    # Reset button to clear session and start over
    if st.session_state.document_uploaded:
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🔄 Start Over"):
                reset_session()
                st.rerun()
        with col2:
            if st.button("⚙️ Edit Configuration"):
                st.session_state.config_saved = False
                st.rerun()

# Footer
st.markdown("""
<div class="app-footer">
    <div class="footer-text">
        Built by <span class="footer-brand">CloudAge Global</span> — 
        Powered by <span class="footer-brand">Amazon Bedrock</span>
    </div>
</div>
""", unsafe_allow_html=True)
