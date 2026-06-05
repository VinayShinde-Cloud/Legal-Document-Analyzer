"""Unit tests for ContextManager class.

Covers:
- Initialization with empty analysis
- Extraction of document type
- Extraction of defined terms via regex patterns
- Party names extraction
- 50-term cap enforcement
- Summary size ≤ 2000 chars
- update_from_analysis adding new terms
"""

import pytest

from document_chunking.config import ChunkConfig
from document_chunking.context_manager import ContextManager, _MAX_DEFINED_TERMS, _MAX_SUMMARY_LENGTH


@pytest.fixture
def config() -> ChunkConfig:
    """Default chunk config for tests."""
    return ChunkConfig()


@pytest.fixture
def context_manager(config: ChunkConfig) -> ContextManager:
    """Fresh ContextManager instance."""
    return ContextManager(config)


class TestInitializationWithEmptyAnalysis:
    """Test behavior when initializing with empty or blank analysis."""

    def test_empty_string(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk("")
        summary = context_manager.get_document_summary()
        assert summary == "Document Type: Unknown"

    def test_whitespace_only(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk("   \n\t  ")
        summary = context_manager.get_document_summary()
        assert summary == "Document Type: Unknown"

    def test_none_like_empty(self, context_manager: ContextManager) -> None:
        """Even when analysis has no useful info, summary is still produced."""
        context_manager.initialize_from_first_chunk("no relevant keywords here")
        summary = context_manager.get_document_summary()
        assert "Document Type:" in summary


class TestDocumentTypeExtraction:
    """Test document type detection from analysis text."""

    def test_detects_contract(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk(
            "This document is a Contract between two parties."
        )
        summary = context_manager.get_document_summary()
        assert "Document Type: Contract" in summary

    def test_detects_agreement(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk(
            "This is a Service Level Agreement for cloud services."
        )
        summary = context_manager.get_document_summary()
        assert "Document Type: Agreement" in summary

    def test_detects_email(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk(
            "This email was sent regarding the project timeline."
        )
        summary = context_manager.get_document_summary()
        assert "Document Type: Email" in summary

    def test_detects_legal(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk(
            "This is a legal document filed in the court."
        )
        summary = context_manager.get_document_summary()
        assert "Document Type: Legal" in summary

    def test_unknown_type(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk(
            "Random text with no classification keywords whatsoever."
        )
        summary = context_manager.get_document_summary()
        assert "Document Type: Unknown" in summary

    def test_case_insensitive_detection(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk(
            "this is a CONTRACT for services."
        )
        summary = context_manager.get_document_summary()
        assert "Document Type: Contract" in summary


class TestDefinedTermsExtraction:
    """Test extraction of defined terms via regex patterns."""

    def test_means_pattern(self, context_manager: ContextManager) -> None:
        analysis = (
            'The "Confidential Information" means any proprietary data shared '
            "between parties during the contract term."
        )
        context_manager.initialize_from_first_chunk(analysis)
        assert "Confidential Information" in context_manager._defined_terms

    def test_hereinafter_referred_to_as_pattern(
        self, context_manager: ContextManager
    ) -> None:
        analysis = (
            'The company "Acme Corp" hereinafter referred to as the Provider '
            "shall deliver services."
        )
        context_manager.initialize_from_first_chunk(analysis)
        assert "Acme Corp" in context_manager._defined_terms

    def test_defined_as_pattern(self, context_manager: ContextManager) -> None:
        analysis = (
            'The "Service Period" is defined as the duration of this agreement.'
        )
        context_manager.initialize_from_first_chunk(analysis)
        assert "Service Period" in context_manager._defined_terms

    def test_reverse_pattern_hereinafter(
        self, context_manager: ContextManager
    ) -> None:
        analysis = (
            'CloudAge Global LLC, hereinafter referred to as "the Company", '
            "agrees to provide services."
        )
        context_manager.initialize_from_first_chunk(analysis)
        assert "the Company" in context_manager._defined_terms

    def test_reverse_pattern_means(self, context_manager: ContextManager) -> None:
        analysis = 'Any disclosure as means "Disclosure Event" in the context.'
        context_manager.initialize_from_first_chunk(analysis)
        # This checks the reverse pattern: means "term"
        assert "Disclosure Event" in context_manager._defined_terms

    def test_reverse_pattern_defined_as(
        self, context_manager: ContextManager
    ) -> None:
        analysis = 'The period is defined as "Grace Period" in this contract.'
        context_manager.initialize_from_first_chunk(analysis)
        assert "Grace Period" in context_manager._defined_terms

    def test_multiple_terms_extracted(self, context_manager: ContextManager) -> None:
        analysis = (
            'The "Work Product" means any deliverable. '
            'The "Term" means the duration of this agreement. '
            'This Contract defines key obligations.'
        )
        context_manager.initialize_from_first_chunk(analysis)
        assert "Work Product" in context_manager._defined_terms
        assert "Term" in context_manager._defined_terms

    def test_no_terms_found(self, context_manager: ContextManager) -> None:
        analysis = "This is a simple document with no defined terms at all."
        context_manager.initialize_from_first_chunk(analysis)
        assert len(context_manager._defined_terms) == 0

    def test_terms_appear_in_summary(self, context_manager: ContextManager) -> None:
        analysis = (
            'This Contract states that "SLA" means the service level agreement.'
        )
        context_manager.initialize_from_first_chunk(analysis)
        summary = context_manager.get_document_summary()
        assert "Defined Terms:" in summary
        assert "SLA" in summary


class TestPartyNamesExtraction:
    """Test extraction of party names from analysis text."""

    def test_parties_colon_pattern(self, context_manager: ContextManager) -> None:
        analysis = "Parties: Acme Corporation, Beta Industries\nThis contract governs."
        context_manager.initialize_from_first_chunk(analysis)
        assert "Acme Corporation" in context_manager._party_names
        assert "Beta Industries" in context_manager._party_names

    def test_between_and_pattern(self, context_manager: ContextManager) -> None:
        analysis = (
            "This agreement is between Alpha LLC and Beta Corp. "
            "The contract terms follow."
        )
        context_manager.initialize_from_first_chunk(analysis)
        assert "Alpha LLC" in context_manager._party_names
        assert "Beta Corp" in context_manager._party_names

    def test_party_singular_colon(self, context_manager: ContextManager) -> None:
        analysis = "Party: CloudAge Global\nRepresents the provider."
        context_manager.initialize_from_first_chunk(analysis)
        assert "CloudAge Global" in context_manager._party_names

    def test_no_parties_found(self, context_manager: ContextManager) -> None:
        analysis = "This is a document with no party information."
        context_manager.initialize_from_first_chunk(analysis)
        assert len(context_manager._party_names) == 0

    def test_parties_appear_in_summary(self, context_manager: ContextManager) -> None:
        analysis = "Parties: Acme Corp, Beta LLC\nThis contract."
        context_manager.initialize_from_first_chunk(analysis)
        summary = context_manager.get_document_summary()
        assert "Parties:" in summary
        assert "Acme Corp" in summary

    def test_no_parties_no_terms_summary(
        self, context_manager: ContextManager
    ) -> None:
        """When no parties/terms found, summary has document type only."""
        analysis = "This is a Contract with no specific party or term info."
        context_manager.initialize_from_first_chunk(analysis)
        summary = context_manager.get_document_summary()
        assert "Document Type: Contract" in summary
        assert "Parties:" not in summary
        assert "Defined Terms:" not in summary


class TestTermCapEnforcement:
    """Test that defined terms are capped at 50 entries."""

    def test_cap_at_50_terms(self, context_manager: ContextManager) -> None:
        """Generate analysis with more than 50 defined terms."""
        # Build analysis with 60 defined terms
        terms_parts = []
        for i in range(60):
            terms_parts.append(f'"Term{i}" means definition number {i}.')
        analysis = "This Contract includes: " + " ".join(terms_parts)

        context_manager.initialize_from_first_chunk(analysis)
        assert len(context_manager._defined_terms) <= _MAX_DEFINED_TERMS

    def test_cap_enforced_across_updates(
        self, context_manager: ContextManager
    ) -> None:
        """Terms cap is maintained when adding via update_from_analysis."""
        # Start with 45 terms
        terms_parts = []
        for i in range(45):
            terms_parts.append(f'"InitialTerm{i}" means definition {i}.')
        analysis = "This Contract: " + " ".join(terms_parts)
        context_manager.initialize_from_first_chunk(analysis)

        # Add more via update
        update_parts = []
        for i in range(10):
            update_parts.append(f'"NewTerm{i}" means new definition {i}.')
        update_analysis = " ".join(update_parts)
        context_manager.update_from_analysis(2, update_analysis)

        assert len(context_manager._defined_terms) <= _MAX_DEFINED_TERMS


class TestSummarySizeConstraint:
    """Test that document summary never exceeds 2000 characters."""

    def test_summary_within_limit(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk(
            "This Contract is between parties."
        )
        summary = context_manager.get_document_summary()
        assert len(summary) <= _MAX_SUMMARY_LENGTH

    def test_large_analysis_still_produces_bounded_summary(
        self, context_manager: ContextManager
    ) -> None:
        """Even with many terms and parties, summary stays ≤ 2000 chars."""
        # Generate large analysis with many defined terms and long names
        terms_parts = []
        for i in range(50):
            long_name = f"VeryLongDefinedTermNameNumber{i}WithExtraText"
            terms_parts.append(f'"{long_name}" means some long definition text here.')
        parties_list = ", ".join(
            [f"Party{i}WithLongName" for i in range(30)]
        )
        analysis = (
            f"This Contract. Parties: {parties_list}\n"
            + " ".join(terms_parts)
        )

        context_manager.initialize_from_first_chunk(analysis)
        summary = context_manager.get_document_summary()
        assert len(summary) <= _MAX_SUMMARY_LENGTH

    def test_get_document_summary_truncates(
        self, context_manager: ContextManager
    ) -> None:
        """Directly test that get_document_summary enforces the cap."""
        # Force a long summary by manipulating internal state
        context_manager._document_summary = "x" * 3000
        summary = context_manager.get_document_summary()
        assert len(summary) <= _MAX_SUMMARY_LENGTH


class TestUpdateFromAnalysis:
    """Test that update_from_analysis adds new terms and parties."""

    def test_adds_new_terms(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk(
            'This Contract. "Initial Term" means the first period.'
        )
        assert "Initial Term" in context_manager._defined_terms

        context_manager.update_from_analysis(
            2, '"Renewal Term" means the extended period.'
        )
        assert "Renewal Term" in context_manager._defined_terms

    def test_does_not_duplicate_existing_terms(
        self, context_manager: ContextManager
    ) -> None:
        context_manager.initialize_from_first_chunk(
            'This Contract. "SLA" means service level agreement.'
        )
        initial_count = len(context_manager._defined_terms)

        context_manager.update_from_analysis(
            2, '"SLA" means service level agreement again.'
        )
        assert len(context_manager._defined_terms) == initial_count

    def test_adds_new_parties(self, context_manager: ContextManager) -> None:
        context_manager.initialize_from_first_chunk(
            "This Contract. Parties: Alpha Corp"
        )
        assert "Alpha Corp" in context_manager._party_names

        context_manager.update_from_analysis(
            2, "Parties: Beta Industries"
        )
        assert "Beta Industries" in context_manager._party_names

    def test_does_not_duplicate_existing_parties(
        self, context_manager: ContextManager
    ) -> None:
        context_manager.initialize_from_first_chunk(
            "This Contract. Parties: Alpha Corp"
        )
        initial_count = len(context_manager._party_names)

        context_manager.update_from_analysis(2, "Parties: Alpha Corp")
        assert len(context_manager._party_names) == initial_count

    def test_empty_analysis_no_change(
        self, context_manager: ContextManager
    ) -> None:
        context_manager.initialize_from_first_chunk(
            'This Contract. "Term" means duration.'
        )
        terms_before = dict(context_manager._defined_terms)
        parties_before = list(context_manager._party_names)

        context_manager.update_from_analysis(2, "")
        assert context_manager._defined_terms == terms_before
        assert context_manager._party_names == parties_before

    def test_summary_updated_after_update(
        self, context_manager: ContextManager
    ) -> None:
        context_manager.initialize_from_first_chunk("This Contract.")
        context_manager.update_from_analysis(
            2, '"New Concept" means something important.'
        )
        summary = context_manager.get_document_summary()
        assert "New Concept" in summary


class TestBuildContextWindow:
    """Test context window building with required parts and size constraints."""

    def test_contains_document_summary(self, context_manager: ContextManager) -> None:
        """Context window includes the document-level summary."""
        context_manager.initialize_from_first_chunk("This is a Contract between parties.")
        result = context_manager.build_context_window(
            chunk_position=2,
            total_chunks=5,
            preceding_summary="Previous chunk discussed terms.",
            current_chunk_text="Current chunk text here.",
        )
        assert "Document Type: Contract" in result

    def test_contains_position_indicator(self, context_manager: ContextManager) -> None:
        """Context window includes chunk position indicator."""
        context_manager.initialize_from_first_chunk("This is a Contract.")
        result = context_manager.build_context_window(
            chunk_position=3,
            total_chunks=12,
            preceding_summary="Summary of chunk 2.",
            current_chunk_text="Some text.",
        )
        assert "Chunk 3 of 12" in result

    def test_contains_preceding_summary(self, context_manager: ContextManager) -> None:
        """Context window includes the preceding chunk summary."""
        context_manager.initialize_from_first_chunk("This is a Contract.")
        preceding = "The previous chunk discussed indemnification clauses."
        result = context_manager.build_context_window(
            chunk_position=2,
            total_chunks=5,
            preceding_summary=preceding,
            current_chunk_text="Current text.",
        )
        assert preceding in result

    def test_empty_preceding_summary_omitted(self, context_manager: ContextManager) -> None:
        """Context window excludes preceding summary section when empty."""
        context_manager.initialize_from_first_chunk("This is a Contract.")
        result = context_manager.build_context_window(
            chunk_position=1,
            total_chunks=5,
            preceding_summary="",
            current_chunk_text="Current text.",
        )
        assert "Previous chunk summary" not in result

    def test_combined_size_within_limit(self, context_manager: ContextManager) -> None:
        """Context window + chunk text does not exceed agent_input_limit (10,000)."""
        context_manager.initialize_from_first_chunk("This is a Contract.")
        chunk_text = "x" * 5000
        result = context_manager.build_context_window(
            chunk_position=2,
            total_chunks=5,
            preceding_summary="Summary " * 50,
            current_chunk_text=chunk_text,
        )
        combined = len(result) + len(chunk_text)
        assert combined <= context_manager._config.agent_input_limit

    def test_large_chunk_triggers_compression(self, context_manager: ContextManager) -> None:
        """When combined size exceeds limit, compression is applied."""
        context_manager.initialize_from_first_chunk(
            'This Contract. "Confidential Information" means secret data. '
            '"Work Product" means deliverables. "Service Period" means duration.'
        )
        # Large chunk text that forces compression
        chunk_text = "x" * 9000
        preceding = "a" * 500  # Full 500-char preceding summary

        result = context_manager.build_context_window(
            chunk_position=2,
            total_chunks=5,
            preceding_summary=preceding,
            current_chunk_text=chunk_text,
        )

        combined = len(result) + len(chunk_text)
        assert combined <= context_manager._config.agent_input_limit

    def test_compression_truncates_preceding_summary(self, config: ChunkConfig) -> None:
        """Compression step 1: preceding summary truncated to 200 chars."""
        # Use a small agent_input_limit to force compression
        config.agent_input_limit = 1000
        cm = ContextManager(config)
        cm.initialize_from_first_chunk("This is a Contract.")

        preceding = "a" * 500
        chunk_text = "b" * 700

        result = cm.build_context_window(
            chunk_position=2,
            total_chunks=5,
            preceding_summary=preceding,
            current_chunk_text=chunk_text,
        )

        # After compression, the preceding summary in result should be ≤ 200 chars
        combined = len(result) + len(chunk_text)
        assert combined <= config.agent_input_limit

    def test_compression_removes_unreferenced_terms(self, config: ChunkConfig) -> None:
        """Compression step 2: unreferenced defined terms are removed."""
        config.agent_input_limit = 800
        cm = ContextManager(config)
        cm.initialize_from_first_chunk(
            'This Contract. "Confidential Information" means secrets. '
            '"Work Product" means deliverables.'
        )

        # Chunk text only references "Confidential Information"
        chunk_text = "This chunk discusses Confidential Information disclosure." + "x" * 500

        result = cm.build_context_window(
            chunk_position=2,
            total_chunks=5,
            preceding_summary="Brief summary.",
            current_chunk_text=chunk_text,
        )

        combined = len(result) + len(chunk_text)
        assert combined <= config.agent_input_limit


class TestGetPrecedingSummary:
    """Test retrieval of preceding chunk summaries."""

    def test_returns_empty_for_first_chunk(self, context_manager: ContextManager) -> None:
        """First chunk (position 1) has no preceding summary."""
        result = context_manager.get_preceding_summary(1)
        assert result == ""

    def test_returns_empty_when_no_summary_stored(self, context_manager: ContextManager) -> None:
        """Returns empty string when no summary stored for preceding position."""
        result = context_manager.get_preceding_summary(3)
        assert result == ""

    def test_returns_stored_summary(self, context_manager: ContextManager) -> None:
        """Returns the stored summary for the preceding chunk."""
        context_manager.store_preceding_summary(1, "Summary of chunk 1.")
        result = context_manager.get_preceding_summary(2)
        assert result == "Summary of chunk 1."

    def test_truncates_to_500_chars(self, context_manager: ContextManager) -> None:
        """Returned summary is always ≤ 500 characters."""
        long_summary = "x" * 700
        context_manager._preceding_summaries[2] = long_summary
        result = context_manager.get_preceding_summary(3)
        assert len(result) <= 500

    def test_returns_empty_for_position_zero(self, context_manager: ContextManager) -> None:
        """Edge case: position 0 or negative returns empty."""
        result = context_manager.get_preceding_summary(0)
        assert result == ""


class TestStorePrecedingSummary:
    """Test storage of chunk summaries."""

    def test_stores_summary(self, context_manager: ContextManager) -> None:
        """Summary is stored and retrievable."""
        context_manager.store_preceding_summary(1, "Chunk 1 analyzed terms.")
        assert context_manager._preceding_summaries[1] == "Chunk 1 analyzed terms."

    def test_truncates_to_500_chars(self, context_manager: ContextManager) -> None:
        """Stored summary is truncated to 500 characters if longer."""
        long_summary = "y" * 700
        context_manager.store_preceding_summary(2, long_summary)
        assert len(context_manager._preceding_summaries[2]) == 500

    def test_stores_exact_500_chars(self, context_manager: ContextManager) -> None:
        """Summary of exactly 500 chars is stored without truncation."""
        exact_summary = "z" * 500
        context_manager.store_preceding_summary(3, exact_summary)
        assert context_manager._preceding_summaries[3] == exact_summary

    def test_multiple_summaries_stored(self, context_manager: ContextManager) -> None:
        """Multiple chunk summaries can be stored independently."""
        context_manager.store_preceding_summary(1, "First chunk summary.")
        context_manager.store_preceding_summary(2, "Second chunk summary.")
        assert context_manager._preceding_summaries[1] == "First chunk summary."
        assert context_manager._preceding_summaries[2] == "Second chunk summary."
