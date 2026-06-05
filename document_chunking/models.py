"""Type definitions and data models for the document chunking pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class BoundaryType(Enum):
    """Semantic boundary types ordered by priority (1 = highest priority).

    When multiple boundary types exist within a valid split range, the
    Chunking_Engine selects the boundary with the highest priority
    (lowest numeric value) as the split point.
    """

    SECTION_HEADING = 1
    CLAUSE_NUMBER = 2
    PAGE_BREAK = 3
    PARAGRAPH_BREAK = 4
    SENTENCE_ENDING = 5


@dataclass
class Boundary:
    """A detected semantic boundary in the document text.

    Attributes:
        position: Character offset in the original text where the boundary occurs.
        boundary_type: The type/priority of the boundary.
    """

    position: int
    boundary_type: BoundaryType


@dataclass
class Chunk:
    """A semantically meaningful segment of document text.

    Attributes:
        position: 1-based sequential position in the document.
        text: The chunk text content.
        start_offset: Character offset of the chunk start in the original document.
        end_offset: Character offset of the chunk end in the original document.
        section_heading: Optional section heading associated with this chunk.
    """

    position: int
    text: str
    start_offset: int
    end_offset: int
    section_heading: str | None = None


@dataclass
class ChunkAnalysis:
    """The analysis result returned by the Bedrock Agent for a single chunk.

    Attributes:
        chunk_position: 1-based position of the analyzed chunk.
        analysis_text: Full analysis text returned by the agent.
        summary: Short summary for context propagation to subsequent chunks.
    """

    chunk_position: int
    analysis_text: str
    summary: str


@dataclass
class FailedChunk:
    """Record of a chunk that failed processing after retry attempts.

    Attributes:
        chunk_position: 1-based position of the failed chunk.
        section_heading: Optional section heading of the failed chunk.
        error_category: Category of error: "throttling", "timeout", or "agent_error".
        error_message: Human-readable description of the failure.
    """

    chunk_position: int
    section_heading: str | None
    error_category: str
    error_message: str


@dataclass
class Finding:
    """A single finding (PII, risk, key term, etc.) detected in the document.

    Attributes:
        entity_value: The detected entity value (e.g., a name, SSN pattern).
        finding_type: Category of the finding: "pii", "risk", "key_term", etc.
        chunk_position: 1-based chunk position where the finding was detected.
        char_offset_start: Start character offset within the chunk.
        char_offset_end: End character offset within the chunk.
        description: Human-readable description of the finding.
    """

    entity_value: str
    finding_type: str
    chunk_position: int
    char_offset_start: int
    char_offset_end: int
    description: str


@dataclass
class SynthesisReport:
    """The unified final report combining all chunk analyses.

    Attributes:
        executive_summary: High-level summary of the document analysis.
        document_classification: Classification of the document type.
        pii_findings: List of PII-related findings across all chunks.
        key_findings_by_category: Findings grouped by category.
        risk_assessment: Overall risk assessment narrative.
        recommended_actions: List of recommended actions.
        coverage_gaps: List of chunks that failed processing, if any.
        processing_metadata: Additional metadata about the processing run.
    """

    executive_summary: str
    document_classification: str
    pii_findings: list[Finding]
    key_findings_by_category: dict[str, list[Finding]]
    risk_assessment: str
    recommended_actions: list[str]
    coverage_gaps: list[FailedChunk] | None = None
    processing_metadata: dict = field(default_factory=dict)


@dataclass
class ProcessingResult:
    """Final result of the document processing pipeline.

    Attributes:
        report: Either a SynthesisReport (for chunked processing) or a raw
            string response (for pass-through single invocation).
        was_chunked: Whether the document went through the chunking pipeline.
        total_chunks: Total number of chunks produced (0 for pass-through).
        successful_chunks: Number of chunks successfully analyzed.
        failed_chunks: Number of chunks that failed analysis.
        processing_time_seconds: Total wall-clock processing time in seconds.
    """

    report: SynthesisReport | str
    was_chunked: bool
    total_chunks: int
    successful_chunks: int
    failed_chunks: int
    processing_time_seconds: float


class ProgressCallback(Protocol):
    """Protocol for progress reporting to the UI.

    Implementations receive callbacks at key points during document processing
    to update progress indicators, elapsed time displays, and status messages.
    """

    def on_chunk_complete(
        self, current: int, total: int, elapsed_seconds: float
    ) -> None:
        """Called when a chunk completes analysis (success or failure).

        Args:
            current: The 1-based position of the completed chunk.
            total: Total number of chunks being processed.
            elapsed_seconds: Total elapsed time since processing started.
        """
        ...

    def on_synthesis_start(self) -> None:
        """Called when synthesis begins after all chunks are processed."""
        ...

    def on_chunk_failed(
        self, chunk_position: int, section_heading: str | None
    ) -> None:
        """Called when a chunk fails after exhausting retries.

        Args:
            chunk_position: 1-based position of the failed chunk.
            section_heading: Section heading of the failed chunk, if available.
        """
        ...

    def on_complete(self, result: ProcessingResult) -> None:
        """Called when the entire processing pipeline completes.

        Args:
            result: The final processing result.
        """
        ...
