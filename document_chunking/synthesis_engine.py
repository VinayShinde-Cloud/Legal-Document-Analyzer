"""Synthesis engine for combining chunk analyses into a unified report."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Callable

from document_chunking.models import (
    ChunkAnalysis,
    FailedChunk,
    Finding,
    SynthesisReport,
)


class SynthesisError(Exception):
    """Raised when synthesis cannot be completed (e.g., all chunks failed)."""

    pass


class SynthesisEngine:
    """Combines chunk analyses into a unified final report using the Bedrock Agent.

    The engine deduplicates findings across chunks, constructs a synthesis prompt
    from all chunk summaries, invokes the agent for synthesis, and parses the
    response into a structured SynthesisReport.
    """

    def __init__(self, agent_invoker: Callable[[str], str | None]) -> None:
        """Initialize with the agent invocation callable.

        Args:
            agent_invoker: A callable that takes a prompt string and returns
                the agent's response string, or None on failure.
        """
        self._agent_invoker = agent_invoker

    def synthesize(
        self,
        chunk_analyses: dict[int, ChunkAnalysis],
        failed_chunks: list[FailedChunk],
    ) -> SynthesisReport:
        """Combine all chunk analyses into a final report.

        Args:
            chunk_analyses: Map of chunk position (1-based) to analysis result.
            failed_chunks: List of chunks that failed processing.

        Returns:
            SynthesisReport with all required sections.

        Raises:
            SynthesisError: If all chunks failed (produces error report listing
                each failure).
        """
        # If all chunks failed, raise SynthesisError with details
        if not chunk_analyses:
            failure_details = "\n".join(
                f"  Chunk {fc.chunk_position}: [{fc.error_category}] {fc.error_message}"
                for fc in failed_chunks
            )
            raise SynthesisError(
                f"Synthesis could not be completed. All chunks failed analysis:\n{failure_details}"
            )

        # Build synthesis prompt and invoke agent
        prompt = self._build_synthesis_prompt(chunk_analyses, failed_chunks)
        response = self._agent_invoker(prompt)

        # If agent invocation fails, return fallback report
        if response is None:
            return self._build_fallback_report(chunk_analyses, failed_chunks)

        # Parse response into structured report
        return self._parse_synthesis_response(response, chunk_analyses, failed_chunks)

    def _deduplicate_findings(self, findings: list[Finding]) -> list[Finding]:
        """Deduplicate findings by (entity_value, finding_type).

        Groups findings by their (entity_value, finding_type) pair and retains
        only the instance with the lowest chunk_position. All location references
        (chunk_position, char_offset_start, char_offset_end) are preserved
        unchanged on the retained instance.

        Args:
            findings: List of Finding objects, potentially with duplicates.

        Returns:
            Deduplicated list of findings, one per unique (entity_value, finding_type).
        """
        groups: dict[tuple[str, str], Finding] = {}

        for finding in findings:
            key = (finding.entity_value, finding.finding_type)
            if key not in groups:
                groups[key] = finding
            else:
                # Retain the instance with the lowest chunk_position
                if finding.chunk_position < groups[key].chunk_position:
                    groups[key] = finding

        return list(groups.values())

    def _build_synthesis_prompt(
        self,
        analyses: dict[int, ChunkAnalysis],
        failed_chunks: list[FailedChunk],
    ) -> str:
        """Construct the prompt for agent-based synthesis invocation.

        Builds a prompt containing all chunk summaries in order and information
        about failed chunks if any exist.

        Args:
            analyses: Map of chunk position to analysis result.
            failed_chunks: List of chunks that failed processing.

        Returns:
            The synthesis prompt string.
        """
        lines = [
            "Synthesize the following chunk analyses into a comprehensive report:"
        ]
        lines.append("")

        # Add chunk summaries in position order
        for position in sorted(analyses.keys()):
            analysis = analyses[position]
            lines.append(f"Chunk {position}: {analysis.summary}")

        # Add failed chunks info if any
        if failed_chunks:
            lines.append("")
            failed_info = ", ".join(
                f"Chunk {fc.chunk_position} ({fc.error_category})"
                for fc in failed_chunks
            )
            lines.append(f"Failed chunks: {failed_info}")

        lines.append("")
        lines.append(
            "Provide: executive summary, document classification, "
            "PII findings, key findings, risk assessment, recommended actions."
        )

        return "\n".join(lines)

    def _parse_synthesis_response(
        self,
        response: str,
        chunk_analyses: dict[int, ChunkAnalysis],
        failed_chunks: list[FailedChunk],
    ) -> SynthesisReport:
        """Parse the agent response into a structured SynthesisReport.

        Attempts to extract sections from the response text. If parsing fails
        or sections are missing, creates a report with the raw response as
        executive_summary.

        Args:
            response: The raw agent response string.
            chunk_analyses: Map of chunk position to analysis result.
            failed_chunks: List of chunks that failed processing.

        Returns:
            A structured SynthesisReport.
        """
        # Extract findings from chunk analyses for deduplication
        all_findings = self._extract_findings_from_analyses(chunk_analyses)
        deduplicated = self._deduplicate_findings(all_findings)

        # Separate PII findings from other findings
        pii_findings = [f for f in deduplicated if f.finding_type == "pii"]
        other_findings = [f for f in deduplicated if f.finding_type != "pii"]

        # Group non-PII findings by category
        key_findings_by_category: dict[str, list[Finding]] = defaultdict(list)
        for finding in other_findings:
            key_findings_by_category[finding.finding_type].append(finding)

        # Try to parse sections from the response
        sections = self._extract_sections(response)

        executive_summary = sections.get("executive_summary", response)
        document_classification = sections.get("document_classification", "Unknown")
        risk_assessment = sections.get("risk_assessment", "")
        recommended_actions = sections.get("recommended_actions", [])

        if isinstance(recommended_actions, str):
            # Split string into list items
            recommended_actions = [
                line.strip().lstrip("- ").lstrip("• ")
                for line in recommended_actions.split("\n")
                if line.strip()
            ]

        # Build coverage gaps if there are failed chunks
        coverage_gaps = failed_chunks if failed_chunks else None

        return SynthesisReport(
            executive_summary=executive_summary,
            document_classification=document_classification,
            pii_findings=pii_findings,
            key_findings_by_category=dict(key_findings_by_category),
            risk_assessment=risk_assessment,
            recommended_actions=recommended_actions,
            coverage_gaps=coverage_gaps,
            processing_metadata={
                "total_chunks_analyzed": len(chunk_analyses),
                "failed_chunks_count": len(failed_chunks),
            },
        )

    def _extract_sections(self, response: str) -> dict:
        """Extract named sections from the agent response text.

        Looks for common section header patterns in the response.

        Args:
            response: The raw agent response.

        Returns:
            Dictionary with extracted section content.
        """
        sections: dict = {}

        # Try to match section patterns
        section_patterns = {
            "executive_summary": r"(?:executive\s+summary|summary)[:\s]*\n?(.*?)(?=\n\s*(?:document\s+classification|classification|pii|key\s+findings|risk|recommended)|$)",
            "document_classification": r"(?:document\s+classification|classification)[:\s]*\n?(.*?)(?=\n\s*(?:pii|key\s+findings|risk|recommended|executive)|$)",
            "risk_assessment": r"(?:risk\s+assessment|risk)[:\s]*\n?(.*?)(?=\n\s*(?:recommended|executive|document|pii|key\s+findings)|$)",
            "recommended_actions": r"(?:recommended\s+actions|recommendations)[:\s]*\n?(.*?)(?=\n\s*(?:executive|document|pii|key\s+findings|risk)|$)",
        }

        for key, pattern in section_patterns.items():
            match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
            if match:
                sections[key] = match.group(1).strip()

        return sections

    def _extract_findings_from_analyses(
        self, chunk_analyses: dict[int, ChunkAnalysis]
    ) -> list[Finding]:
        """Extract Finding objects from chunk analysis text.

        Attempts to parse structured findings from each chunk's analysis_text.
        Findings are expected to include entity_value, finding_type, and
        location references.

        Args:
            chunk_analyses: Map of chunk position to analysis result.

        Returns:
            List of all findings extracted from chunk analyses.
        """
        findings: list[Finding] = []

        for position, analysis in chunk_analyses.items():
            # Try to parse findings from analysis text
            # Look for JSON-formatted findings
            try:
                # Try to find JSON array of findings in the analysis text
                json_match = re.search(
                    r"\[.*?\]", analysis.analysis_text, re.DOTALL
                )
                if json_match:
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, dict) and "entity_value" in item:
                                findings.append(
                                    Finding(
                                        entity_value=item.get("entity_value", ""),
                                        finding_type=item.get("finding_type", ""),
                                        chunk_position=item.get(
                                            "chunk_position", position
                                        ),
                                        char_offset_start=item.get(
                                            "char_offset_start", 0
                                        ),
                                        char_offset_end=item.get(
                                            "char_offset_end", 0
                                        ),
                                        description=item.get("description", ""),
                                    )
                                )
            except (json.JSONDecodeError, ValueError):
                pass

        return findings

    def _build_fallback_report(
        self,
        chunk_analyses: dict[int, ChunkAnalysis],
        failed_chunks: list[FailedChunk],
    ) -> SynthesisReport:
        """Build a fallback report when agent synthesis invocation fails.

        Concatenates chunk summaries as the executive summary and includes
        available findings.

        Args:
            chunk_analyses: Map of chunk position to analysis result.
            failed_chunks: List of chunks that failed processing.

        Returns:
            A SynthesisReport with concatenated summaries as fallback.
        """
        # Concatenate summaries as fallback executive summary
        summaries = []
        for position in sorted(chunk_analyses.keys()):
            summaries.append(
                f"Chunk {position}: {chunk_analyses[position].summary}"
            )
        fallback_summary = "\n".join(summaries)

        # Extract and deduplicate findings
        all_findings = self._extract_findings_from_analyses(chunk_analyses)
        deduplicated = self._deduplicate_findings(all_findings)

        pii_findings = [f for f in deduplicated if f.finding_type == "pii"]
        other_findings = [f for f in deduplicated if f.finding_type != "pii"]

        key_findings_by_category: dict[str, list[Finding]] = defaultdict(list)
        for finding in other_findings:
            key_findings_by_category[finding.finding_type].append(finding)

        coverage_gaps = failed_chunks if failed_chunks else None

        return SynthesisReport(
            executive_summary=fallback_summary,
            document_classification="Unknown (synthesis failed)",
            pii_findings=pii_findings,
            key_findings_by_category=dict(key_findings_by_category),
            risk_assessment="Risk assessment unavailable (synthesis failed)",
            recommended_actions=[
                "Retry analysis - synthesis invocation failed"
            ],
            coverage_gaps=coverage_gaps,
            processing_metadata={
                "total_chunks_analyzed": len(chunk_analyses),
                "failed_chunks_count": len(failed_chunks),
                "synthesis_fallback": True,
            },
        )
