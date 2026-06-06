import streamlit as st
import boto3
import uuid
import time
import json
from datetime import datetime
import io
import os

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
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "Legal Document Analysis powered by CloudAge & Amazon Bedrock"
    }
)

# Custom CSS — Blue theme with CloudAge branding
st.markdown("""
<style>
    /* Hide Streamlit deploy button and toolbar */
    .stDeployButton { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    #MainMenu { visibility: hidden; }

    .main-header {
        font-size: 2.2rem;
        color: #0D47A1;
        margin-bottom: 0.5rem;
        font-weight: 700;
    }
    .sub-header {
        font-size: 1.4rem;
        color: #1A237E;
        margin-top: 1.5rem;
        font-weight: 600;
    }
    .file-info {
        background-color: #F5F9FF;
        padding: 1rem;
        border-radius: 0.75rem;
        margin-bottom: 1rem;
        border: 1px solid #BBDEFB;
    }
    .user-message {
        background-color: #E3F2FD;
        padding: 1rem;
        border-radius: 0.75rem;
        margin-bottom: 0.5rem;
        border-left: 4px solid #1565C0;
    }
    .assistant-message {
        background-color: #F5F9FF;
        padding: 1rem;
        border-radius: 0.75rem;
        margin-bottom: 0.5rem;
        border-left: 4px solid #42A5F5;
    }
    .footer {
        margin-top: 3rem;
        text-align: center;
        color: #78909C;
        font-size: 0.85rem;
    }
    .stButton>button {
        background-color: #1565C0 !important;
        color: white !important;
        border: none !important;
        border-radius: 0.5rem !important;
        padding: 0.5rem 1.5rem !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    .stButton>button:hover {
        background-color: #0D47A1 !important;
        box-shadow: 0 2px 8px rgba(21, 101, 192, 0.3) !important;
    }
    .config-section {
        background-color: #F5F9FF;
        padding: 1rem;
        border-radius: 0.75rem;
        margin-bottom: 1.5rem;
        border-left: 4px solid #1565C0;
    }
    .chat-container {
        margin-bottom: 5rem;
    }
    .chunking-info {
        background-color: #E8F5E9;
        padding: 0.75rem 1rem;
        border-radius: 0.5rem;
        font-size: 0.85rem;
        margin-top: 0.5rem;
        border-left: 4px solid #2E7D32;
    }
    .file-size-error {
        background-color: #FFEBEE;
        padding: 0.75rem 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #C62828;
        margin: 1rem 0;
    }
    .coverage-gap-warning {
        background-color: #FFF3E0;
        padding: 0.6rem 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #F57C00;
        margin: 0.5rem 0;
        font-size: 0.85rem;
    }
    .processing-stats {
        background-color: #E3F2FD;
        padding: 0.75rem 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1565C0;
        margin: 0.5rem 0;
        font-size: 0.85rem;
    }
    .section-header {
        font-size: 1.05rem;
        font-weight: 600;
        color: #1A237E;
        margin-top: 1.2rem;
        margin-bottom: 0.5rem;
        border-bottom: 2px solid #BBDEFB;
        padding-bottom: 0.3rem;
    }
    .finding-item {
        background-color: #FFF8E1;
        padding: 0.6rem 1rem;
        border-radius: 0.5rem;
        margin: 0.3rem 0;
        font-size: 0.85rem;
        border-left: 3px solid #FFA000;
    }
    .validation-warning {
        background-color: #FFF3E0;
        padding: 0.5rem 0.75rem;
        border-radius: 0.4rem;
        border-left: 3px solid #F57C00;
        margin: 0.3rem 0;
        font-size: 0.82rem;
    }
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #F8FBFF;
    }
    /* Progress bar blue */
    .stProgress > div > div > div > div {
        background-color: #1565C0 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- AWS Cognito Authentication ---
from streamlit_cognito_auth import CognitoAuthenticator

# Cognito configuration (same region as deployment)
COGNITO_POOL_ID = os.environ.get("COGNITO_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")
COGNITO_APP_CLIENT_SECRET = os.environ.get("COGNITO_APP_CLIENT_SECRET", "")

authenticator = CognitoAuthenticator(
    pool_id=COGNITO_POOL_ID,
    app_client_id=COGNITO_APP_CLIENT_ID,
    app_client_secret=COGNITO_APP_CLIENT_SECRET,
)

# Show login form - blocks the rest of the app until authenticated
is_logged_in = authenticator.login()
if not is_logged_in:
    st.stop()

# User is authenticated
def logout():
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
    st.session_state.aws_region = os.environ.get("AWS_REGION", "eu-north-1")
if 'agent_id' not in st.session_state:
    st.session_state.agent_id = os.environ.get("BEDROCK_AGENT_ID", "")
if 'agent_alias_id' not in st.session_state:
    st.session_state.agent_alias_id = os.environ.get("BEDROCK_AGENT_ALIAS_ID", "")
if 'config_saved' not in st.session_state:
    st.session_state.config_saved = False

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


# Initialize Bedrock Agent Runtime client
@st.cache_resource(show_spinner=False)
def get_bedrock_agent_client(region):
    return boto3.client('bedrock-agent-runtime', region_name=region)


def invoke_agent(input_text, max_retries=3):
    """Invoke agent with retry logic for throttling."""
    for attempt in range(max_retries):
        try:
            bedrock_agent = get_bedrock_agent_client(st.session_state.aws_region)

            response = bedrock_agent.invoke_agent(
                agentId=st.session_state.agent_id,
                agentAliasId=st.session_state.agent_alias_id,
                sessionId=st.session_state.session_id,
                inputText=input_text
            )

            if 'completion' in response and hasattr(response['completion'], '__iter__'):
                full_response = ""
                for event in response['completion']:
                    if isinstance(event, dict) and 'chunk' in event and 'bytes' in event['chunk']:
                        chunk_text = event['chunk']['bytes'].decode('utf-8')
                        full_response += chunk_text

                try:
                    return json.loads(full_response)
                except (json.JSONDecodeError, ValueError):
                    return full_response
            else:
                return "No completion found in response"

        except bedrock_agent.exceptions.ThrottlingException:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 10
                st.toast(f"⏳ Rate limited. Retrying in {wait_time}s... (attempt {attempt + 2}/{max_retries})")
                time.sleep(wait_time)
            else:
                return ("Error: Request rate too high. The multi-agent workflow triggers multiple model calls. "
                        "Please wait 60 seconds and try again, or request a quota increase in the AWS Console "
                        "under Service Quotas → Amazon Bedrock.")
        except Exception as e:
            if "throttling" in str(e).lower() or "ThrottlingException" in str(e):
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 10
                    st.toast(f"⏳ Rate limited. Retrying in {wait_time}s... (attempt {attempt + 2}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    return ("Error: Request rate too high. Please wait 60 seconds and try again. "
                            "Consider requesting a quota increase in AWS Console → Service Quotas → Amazon Bedrock.")
            else:
                return f"Error: {str(e)}"

    return "Error: Max retries exceeded due to throttling."


def agent_invoker_for_processor(input_text: str) -> str | None:
    """Agent invoker callable compatible with DocumentProcessor.

    Wraps the existing invoke_agent function to return str or None
    (None on failure), and raises exceptions for throttling so
    DocumentProcessor can apply its own retry logic.
    """
    try:
        bedrock_agent = get_bedrock_agent_client(st.session_state.aws_region)

        response = bedrock_agent.invoke_agent(
            agentId=st.session_state.agent_id,
            agentAliasId=st.session_state.agent_alias_id,
            sessionId=st.session_state.session_id,
            inputText=input_text
        )

        if 'completion' in response and hasattr(response['completion'], '__iter__'):
            full_response = ""
            for event in response['completion']:
                if isinstance(event, dict) and 'chunk' in event and 'bytes' in event['chunk']:
                    chunk_text = event['chunk']['bytes'].decode('utf-8')
                    full_response += chunk_text
            return full_response if full_response else None
        else:
            return None

    except Exception as e:
        # Re-raise so DocumentProcessor can handle throttling vs other errors
        raise


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
                f'<strong>{finding.finding_type}:</strong> {finding.entity_value} — '
                f'{finding.description} <em>{location_ref}</em>'
                f'</div>',
                unsafe_allow_html=True
            )
    else:
        st.markdown("No PII findings detected.")

    # Key Findings by Category
    st.markdown('<div class="section-header">🔍 Key Findings</div>', unsafe_allow_html=True)
    if report.key_findings_by_category:
        for category, findings in report.key_findings_by_category.items():
            st.markdown(f"**{category}**")
            for finding in findings:
                location_ref = f"[Chunk {finding.chunk_position}, offset {finding.char_offset_start}-{finding.char_offset_end}]"
                st.markdown(
                    f'<div class="finding-item">'
                    f'{finding.entity_value} — {finding.description} <em>{location_ref}</em>'
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
            st.markdown(f"{i}. {action}")
    else:
        st.markdown("No specific actions recommended.")

    # Coverage Gaps (if present)
    if report.coverage_gaps:
        st.markdown('<div class="section-header">📊 Coverage Gaps</div>', unsafe_allow_html=True)
        for gap in report.coverage_gaps:
            heading_info = f" (Section: {gap.section_heading})" if gap.section_heading else ""
            st.markdown(
                f'<div class="coverage-gap-warning">'
                f'⚠️ <strong>Chunk {gap.chunk_position}{heading_info}:</strong> '
                f'{gap.error_message} (Category: {gap.error_category})'
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
            st.markdown(
                f'<div class="assistant-message">{content}</div>',
                unsafe_allow_html=True
            )
    else:
        st.markdown(
            f'<div class="assistant-message">{content}</div>',
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

# Sidebar for configuration and info
with st.sidebar:
    st.image("https://assets.cloudage.llc/logo.png", width=200)
    st.caption("Powered by Amazon Bedrock")

    # Show logged-in user and logout
    st.markdown("---")
    st.markdown(f"👤 **{authenticator.get_username()}**")
    st.button("Logout", on_click=logout, type="secondary")

    # Configuration section
    st.markdown("### Agent Configuration")

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
        st.markdown("**Chunk Configuration**")

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
        st.info("File size limit: 25MB. Documents ≤ 10,000 characters are processed in a single pass; larger documents use chunked analysis.")

        # Save button
        if st.button("Save Configuration"):
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
        st.markdown("#### Current Settings")
        region_display = REGION_DISPLAY_MAP.get(st.session_state.aws_region, st.session_state.aws_region)
        st.markdown(f"**Region:** {region_display}")
        st.markdown(f"**Agent ID:** {st.session_state.agent_id[:6]}...")
        st.markdown(f"**Agent Alias ID:** {st.session_state.agent_alias_id[:6]}...")
        st.markdown(f"**File Size Limit:** 25MB")
        st.markdown(f"**Max Chunk Size:** {st.session_state.get('chunk_max_size', 8000):,} chars")

    st.markdown("---")

    st.markdown("### Session Info")
    st.markdown(f"**Session ID:** {st.session_state.session_id[:8]}...")

    if st.session_state.document_uploaded:
        st.markdown(f"**Document:** {st.session_state.document_name}")
        if st.session_state.analysis_time:
            st.markdown(f"**Analyzed at:** {st.session_state.analysis_time.strftime('%H:%M:%S')}")

        # Word count of document
        word_count = len(st.session_state.document_content.split())
        st.markdown(f"**Document size:** {word_count} words")

        # Show processing result info if available
        if st.session_state.processing_result:
            result = st.session_state.processing_result
            if result.get('was_chunked'):
                st.markdown(f"**Processing:** Chunked analysis")
                st.markdown(f"**Chunks:** {result.get('successful_chunks', 0)}/{result.get('total_chunks', 0)} successful")
                if result.get('failed_chunks', 0) > 0:
                    st.markdown(f"**Failed:** {result['failed_chunks']} chunks")
            else:
                st.markdown(f"**Processing:** Single-pass analysis")
            elapsed_str = DocumentProcessor.format_elapsed_time(result.get('processing_time_seconds', 0))
            st.markdown(f"**Processing time:** {elapsed_str}")

        # Add export conversation option
        if st.button("Export Conversation"):
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

# Main content area
st.markdown('<h1 class="main-header">📄 Legal Document Analysis</h1>', unsafe_allow_html=True)
st.markdown('<p style="color: #546E7A; margin-top: -0.5rem; margin-bottom: 1.5rem;">Upload documents for AI-powered classification, PII detection, and comprehensive analysis.</p>', unsafe_allow_html=True)

# Check if configuration is saved before allowing document upload
if not st.session_state.config_saved:
    st.warning("⚙️ Please configure your Bedrock Agent settings in the sidebar first.")
else:
    # Create two columns for upload section
    if not st.session_state.document_uploaded:
        col1, col2 = st.columns([2, 1])

        st.warning(f"⚠️ **IMPORTANT:** While the uploader shows 200MB limit, files over {MAX_FILE_SIZE_MB}MB will be rejected by the application.")

        with col1:
            st.markdown("### Upload a document to analyze")
            uploaded_file = st.file_uploader("Choose a document file",
                                            type=["txt", "pdf", "docx"],
                                            help=f"Supported formats: TXT, PDF, DOCX. Maximum file size: {MAX_FILE_SIZE_MB}MB")

            st.caption(f"📌 Note: Files larger than {MAX_FILE_SIZE_MB}MB will be rejected")

        with col2:
            st.markdown("### How it works")
            st.markdown("""
1. **Upload** a document (PDF, DOCX, TXT)
2. **AI analyzes** it for classification, PII, risks
3. **Ask questions** in the chat about findings
            """)
            st.info("Large documents are automatically split into semantic chunks for comprehensive analysis.")

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
                st.markdown('<div class="file-info">', unsafe_allow_html=True)
                st.write(f"**Filename:** {uploaded_file.name}")
                st.write(f"**Size:** {file_size_mb:.2f} MB")
                file_type = uploaded_file.name.split('.')[-1].upper()
                st.write(f"**Type:** {file_type}")
                st.markdown('</div>', unsafe_allow_html=True)

                # Process the document
                if st.button("Analyze Document", key="analyze_btn"):
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

                            # Force a rerun to show the chat interface
                            st.rerun()

                    except Exception as e:
                        st.error(f"An error occurred: {str(e)}")

    # Chat interface once document is uploaded
    if st.session_state.document_uploaded:
        # Create tabs for different views
        tab1, tab2 = st.tabs(["Chat", "Document Preview"])

        with tab1:
            st.markdown(
                f'<h2 class="sub-header">Conversation about: {st.session_state.document_name}</h2>',
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
                                f'<div class="user-message">{message["content"]}</div>',
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
            st.markdown('<h2 class="sub-header">Document Content</h2>', unsafe_allow_html=True)

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
            if st.button("Start Over"):
                reset_session()
                st.rerun()
        with col2:
            if st.button("Edit Agent Configuration"):
                st.session_state.config_saved = False
                st.rerun()

# Footer
st.markdown('<div class="footer">Built by CloudAge Global — Powered by Amazon Bedrock</div>', unsafe_allow_html=True)
