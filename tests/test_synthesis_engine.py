"""Unit tests for the SynthesisEngine class."""

import pytest

from document_chunking.models import ChunkAnalysis, FailedChunk, Finding, SynthesisReport
from document_chunking.synthesis_engine import SynthesisEngine, SynthesisError


# --- Fixtures ---


def make_finding(
    entity_value: str = "John Doe",
    finding_type: str = "pii",
    chunk_position: int = 1,
    char_offset_start: int = 0,
    char_offset_end: int = 8,
    description: str = "Name detected",
) -> Finding:
    """Helper to create a Finding with defaults."""
    return Finding(
        entity_value=entity_value,
        finding_type=finding_type,
        chunk_position=chunk_position,
        char_offset_start=char_offset_start,
        char_offset_end=char_offset_end,
        description=description,
    )


def make_chunk_analysis(
    chunk_position: int = 1,
    analysis_text: str = "Analysis of chunk",
    summary: str = "Summary of chunk",
) -> ChunkAnalysis:
    """Helper to create a ChunkAnalysis with defaults."""
    return ChunkAnalysis(
        chunk_position=chunk_position,
        analysis_text=analysis_text,
        summary=summary,
    )


def make_failed_chunk(
    chunk_position: int = 1,
    section_heading: str | None = "Section A",
    error_category: str = "timeout",
    error_message: str = "Request timed out",
) -> FailedChunk:
    """Helper to create a FailedChunk with defaults."""
    return FailedChunk(
        chunk_position=chunk_position,
        section_heading=section_heading,
        error_category=error_category,
        error_message=error_message,
    )


# --- Deduplication Tests ---


class TestDeduplicateFindings:
    """Tests for _deduplicate_findings method."""

    def test_same_entity_type_keeps_earliest_chunk_position(self):
        """Deduplication retains finding with lowest chunk_position."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        findings = [
            make_finding(entity_value="SSN-123", finding_type="pii", chunk_position=3),
            make_finding(entity_value="SSN-123", finding_type="pii", chunk_position=1),
            make_finding(entity_value="SSN-123", finding_type="pii", chunk_position=5),
        ]

        result = engine._deduplicate_findings(findings)

        assert len(result) == 1
        assert result[0].chunk_position == 1

    def test_different_entity_values_kept_separate(self):
        """Findings with different entity_value are not deduplicated."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        findings = [
            make_finding(entity_value="John Doe", finding_type="pii", chunk_position=1),
            make_finding(entity_value="Jane Doe", finding_type="pii", chunk_position=2),
        ]

        result = engine._deduplicate_findings(findings)

        assert len(result) == 2

    def test_same_entity_different_type_kept_separate(self):
        """Same entity_value with different finding_type are not deduplicated."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        findings = [
            make_finding(entity_value="ACME Corp", finding_type="pii", chunk_position=1),
            make_finding(entity_value="ACME Corp", finding_type="key_term", chunk_position=2),
        ]

        result = engine._deduplicate_findings(findings)

        assert len(result) == 2

    def test_location_preserved_after_deduplication(self):
        """Retained finding preserves its original location references."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        findings = [
            make_finding(
                entity_value="SSN-456",
                finding_type="pii",
                chunk_position=5,
                char_offset_start=100,
                char_offset_end=120,
            ),
            make_finding(
                entity_value="SSN-456",
                finding_type="pii",
                chunk_position=2,
                char_offset_start=50,
                char_offset_end=70,
            ),
        ]

        result = engine._deduplicate_findings(findings)

        assert len(result) == 1
        retained = result[0]
        # Should retain chunk_position=2 (earliest)
        assert retained.chunk_position == 2
        assert retained.char_offset_start == 50
        assert retained.char_offset_end == 70

    def test_empty_findings_returns_empty(self):
        """Empty input returns empty output."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        result = engine._deduplicate_findings([])

        assert result == []

    def test_single_finding_preserved(self):
        """A single finding passes through unchanged."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        finding = make_finding(
            entity_value="Test",
            finding_type="risk",
            chunk_position=3,
            char_offset_start=10,
            char_offset_end=20,
        )

        result = engine._deduplicate_findings([finding])

        assert len(result) == 1
        assert result[0] is finding


# --- SynthesisError Tests ---


class TestSynthesizeAllFailed:
    """Tests for SynthesisError when all chunks fail."""

    def test_all_chunks_failed_raises_synthesis_error(self):
        """When no analyses exist and all chunks failed, raises SynthesisError."""
        engine = SynthesisEngine(agent_invoker=lambda x: "response")

        failed = [
            make_failed_chunk(chunk_position=1, error_category="throttling", error_message="Rate limited"),
            make_failed_chunk(chunk_position=2, error_category="timeout", error_message="Timed out"),
        ]

        with pytest.raises(SynthesisError) as exc_info:
            engine.synthesize(chunk_analyses={}, failed_chunks=failed)

        error_msg = str(exc_info.value)
        assert "All chunks failed" in error_msg
        assert "Chunk 1" in error_msg
        assert "Chunk 2" in error_msg
        assert "throttling" in error_msg
        assert "timeout" in error_msg

    def test_all_chunks_failed_with_single_failure(self):
        """Single failed chunk with no analyses raises SynthesisError."""
        engine = SynthesisEngine(agent_invoker=lambda x: "response")

        failed = [
            make_failed_chunk(chunk_position=1, error_category="agent_error", error_message="Internal error"),
        ]

        with pytest.raises(SynthesisError):
            engine.synthesize(chunk_analyses={}, failed_chunks=failed)


# --- Coverage Gaps Tests ---


class TestCoverageGaps:
    """Tests for coverage gaps in synthesis report."""

    def test_single_failed_chunk_produces_coverage_gaps(self):
        """When one chunk fails but others succeed, report includes coverage_gaps."""
        engine = SynthesisEngine(
            agent_invoker=lambda x: "Executive Summary: Analysis complete.\nDocument Classification: Legal contract."
        )

        analyses = {
            1: make_chunk_analysis(chunk_position=1, summary="First chunk summary"),
            3: make_chunk_analysis(chunk_position=3, summary="Third chunk summary"),
        }
        failed = [
            make_failed_chunk(chunk_position=2, section_heading="Definitions", error_category="timeout"),
        ]

        report = engine.synthesize(analyses, failed)

        assert report.coverage_gaps is not None
        assert len(report.coverage_gaps) == 1
        assert report.coverage_gaps[0].chunk_position == 2
        assert report.coverage_gaps[0].section_heading == "Definitions"

    def test_no_failed_chunks_no_coverage_gaps(self):
        """When no chunks fail, coverage_gaps is None."""
        engine = SynthesisEngine(
            agent_invoker=lambda x: "Executive Summary: All good."
        )

        analyses = {
            1: make_chunk_analysis(chunk_position=1, summary="Summary 1"),
            2: make_chunk_analysis(chunk_position=2, summary="Summary 2"),
        }

        report = engine.synthesize(analyses, failed_chunks=[])

        assert report.coverage_gaps is None


# --- Successful Synthesis Tests ---


class TestSuccessfulSynthesis:
    """Tests for successful synthesis with mock agent."""

    def test_successful_synthesis_returns_report(self):
        """Agent returns valid response, synthesis produces a SynthesisReport."""
        agent_response = (
            "Executive Summary: This is a legal services agreement.\n"
            "Document Classification: Service Agreement\n"
            "Risk Assessment: Low risk overall.\n"
            "Recommended Actions:\n"
            "- Review indemnity clause\n"
            "- Verify jurisdiction\n"
        )
        engine = SynthesisEngine(agent_invoker=lambda x: agent_response)

        analyses = {
            1: make_chunk_analysis(chunk_position=1, summary="Parties and definitions"),
            2: make_chunk_analysis(chunk_position=2, summary="Service terms"),
            3: make_chunk_analysis(chunk_position=3, summary="Liability and termination"),
        }

        report = engine.synthesize(analyses, failed_chunks=[])

        assert isinstance(report, SynthesisReport)
        assert report.executive_summary != ""
        assert report.coverage_gaps is None
        assert report.processing_metadata["total_chunks_analyzed"] == 3
        assert report.processing_metadata["failed_chunks_count"] == 0

    def test_synthesis_with_findings_in_analyses(self):
        """Findings embedded as JSON in analyses are extracted and deduplicated."""
        analysis_with_findings = (
            'Some analysis text. '
            '[{"entity_value": "John Smith", "finding_type": "pii", '
            '"chunk_position": 1, "char_offset_start": 10, "char_offset_end": 20, '
            '"description": "Person name"}]'
        )

        engine = SynthesisEngine(agent_invoker=lambda x: "Summary of findings.")

        analyses = {
            1: ChunkAnalysis(
                chunk_position=1,
                analysis_text=analysis_with_findings,
                summary="Found PII",
            ),
        }

        report = engine.synthesize(analyses, failed_chunks=[])

        assert len(report.pii_findings) == 1
        assert report.pii_findings[0].entity_value == "John Smith"
        assert report.pii_findings[0].chunk_position == 1
        assert report.pii_findings[0].char_offset_start == 10
        assert report.pii_findings[0].char_offset_end == 20


# --- Agent Failure Fallback Tests ---


class TestAgentFailureFallback:
    """Tests for fallback report when agent invocation fails."""

    def test_agent_returns_none_produces_fallback_report(self):
        """When agent_invoker returns None, a fallback report is generated."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        analyses = {
            1: make_chunk_analysis(chunk_position=1, summary="First summary"),
            2: make_chunk_analysis(chunk_position=2, summary="Second summary"),
        }

        report = engine.synthesize(analyses, failed_chunks=[])

        assert isinstance(report, SynthesisReport)
        assert "Chunk 1: First summary" in report.executive_summary
        assert "Chunk 2: Second summary" in report.executive_summary
        assert report.processing_metadata.get("synthesis_fallback") is True

    def test_fallback_report_includes_coverage_gaps(self):
        """Fallback report still includes coverage gaps for failed chunks."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        analyses = {
            1: make_chunk_analysis(chunk_position=1, summary="Summary 1"),
        }
        failed = [
            make_failed_chunk(chunk_position=2, error_category="throttling"),
        ]

        report = engine.synthesize(analyses, failed)

        assert report.coverage_gaps is not None
        assert len(report.coverage_gaps) == 1


# --- Prompt Construction Tests ---


class TestBuildSynthesisPrompt:
    """Tests for _build_synthesis_prompt method."""

    def test_prompt_includes_all_chunk_summaries(self):
        """Prompt contains summaries from all analyzed chunks."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        analyses = {
            1: make_chunk_analysis(chunk_position=1, summary="Summary A"),
            2: make_chunk_analysis(chunk_position=2, summary="Summary B"),
            3: make_chunk_analysis(chunk_position=3, summary="Summary C"),
        }

        prompt = engine._build_synthesis_prompt(analyses, failed_chunks=[])

        assert "Chunk 1: Summary A" in prompt
        assert "Chunk 2: Summary B" in prompt
        assert "Chunk 3: Summary C" in prompt

    def test_prompt_includes_failed_chunks_info(self):
        """Prompt mentions failed chunks when they exist."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        analyses = {
            1: make_chunk_analysis(chunk_position=1, summary="Summary"),
        }
        failed = [
            make_failed_chunk(chunk_position=2, error_category="timeout"),
            make_failed_chunk(chunk_position=4, error_category="throttling"),
        ]

        prompt = engine._build_synthesis_prompt(analyses, failed)

        assert "Failed chunks:" in prompt
        assert "Chunk 2" in prompt
        assert "Chunk 4" in prompt

    def test_prompt_starts_with_synthesis_instruction(self):
        """Prompt starts with the synthesis instruction header."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        analyses = {1: make_chunk_analysis(chunk_position=1, summary="Test")}

        prompt = engine._build_synthesis_prompt(analyses, failed_chunks=[])

        assert prompt.startswith("Synthesize the following chunk analyses into a comprehensive report:")

    def test_prompt_requests_all_report_sections(self):
        """Prompt asks for executive summary, classification, PII, findings, risk, actions."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        analyses = {1: make_chunk_analysis(chunk_position=1, summary="Test")}

        prompt = engine._build_synthesis_prompt(analyses, failed_chunks=[])

        assert "executive summary" in prompt
        assert "document classification" in prompt
        assert "PII findings" in prompt
        assert "key findings" in prompt
        assert "risk assessment" in prompt
        assert "recommended actions" in prompt

    def test_prompt_orders_chunks_by_position(self):
        """Chunks appear in the prompt ordered by position number."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        analyses = {
            3: make_chunk_analysis(chunk_position=3, summary="Third"),
            1: make_chunk_analysis(chunk_position=1, summary="First"),
            2: make_chunk_analysis(chunk_position=2, summary="Second"),
        }

        prompt = engine._build_synthesis_prompt(analyses, failed_chunks=[])

        pos_1 = prompt.index("Chunk 1:")
        pos_2 = prompt.index("Chunk 2:")
        pos_3 = prompt.index("Chunk 3:")
        assert pos_1 < pos_2 < pos_3

    def test_prompt_no_failed_section_when_none_failed(self):
        """Prompt does not include 'Failed chunks:' when there are none."""
        engine = SynthesisEngine(agent_invoker=lambda x: None)

        analyses = {1: make_chunk_analysis(chunk_position=1, summary="Test")}

        prompt = engine._build_synthesis_prompt(analyses, failed_chunks=[])

        assert "Failed chunks:" not in prompt
