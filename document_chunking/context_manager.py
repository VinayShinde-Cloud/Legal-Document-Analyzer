"""Context Manager for maintaining cross-chunk context in document processing.

This module provides the ContextManager class which builds and maintains
context across chunks including document summary, defined terms, party
tracking, and preceding chunk summaries.
"""

from __future__ import annotations

import re

from document_chunking.config import ChunkConfig


# Document type classification keywords
_DOCUMENT_TYPE_KEYWORDS = [
    "Contract",
    "Agreement",
    "Legal",
    "Email",
    "Memorandum",
    "Letter",
    "Notice",
    "Policy",
    "Report",
    "Lease",
    "License",
    "Amendment",
    "Addendum",
    "Affidavit",
    "Brief",
    "Complaint",
    "Deed",
    "Order",
    "Resolution",
    "Statute",
    "Will",
    "Trust",
]

# Max number of defined terms to track
_MAX_DEFINED_TERMS = 50

# Max document summary length in characters
_MAX_SUMMARY_LENGTH = 2000

# Max preceding summary length in characters
_MAX_PRECEDING_SUMMARY_LENGTH = 500

# Compressed preceding summary length for size reduction
_COMPRESSED_SUMMARY_LENGTH = 200


class ContextManager:
    """Build and maintain cross-chunk context for document processing.

    The ContextManager tracks document-level information (type, parties,
    defined terms) and provides context windows for each chunk to ensure
    the Bedrock Agent can interpret chunks in the context of the full document.
    """

    def __init__(self, config: ChunkConfig) -> None:
        """Initialize with chunk configuration parameters.

        Args:
            config: ChunkConfig instance with context_window_size and other params.
        """
        self._config = config
        self._document_summary: str = ""
        self._defined_terms: dict[str, str] = {}
        self._party_names: list[str] = []
        self._section_references: dict[int, str] = {}
        self._preceding_summaries: dict[int, str] = {}

    def initialize_from_first_chunk(self, first_analysis: str) -> None:
        """Extract document type, parties, and defined terms from first chunk analysis.

        Parses the first chunk's analysis to identify:
        - Document type (from classification keywords)
        - Party names (capitalized names near contract/party language)
        - Defined terms (via regex patterns for legal definitions)

        Generates a document-level summary ≤ 2000 characters.

        Args:
            first_analysis: The analysis text from the first chunk.
        """
        if not first_analysis or not first_analysis.strip():
            self._document_summary = "Document Type: Unknown"
            return

        document_type = self._detect_document_type(first_analysis)
        parties = self._extract_parties(first_analysis)
        terms = self._extract_defined_terms(first_analysis)

        # Store extracted data
        self._party_names = parties[:_MAX_DEFINED_TERMS]
        for term_name, term_def in terms.items():
            if len(self._defined_terms) >= _MAX_DEFINED_TERMS:
                break
            self._defined_terms[term_name] = term_def

        # Generate summary
        self._document_summary = self._generate_summary(
            document_type, self._party_names, self._defined_terms
        )

    def update_from_analysis(self, chunk_position: int, analysis: str) -> None:
        """Update tracked defined terms and parties from subsequent chunk analyses.

        Extracts any new defined terms and party names from the analysis,
        adding them to the tracked state (capped at 50 terms).

        Args:
            chunk_position: 1-based position of the chunk.
            analysis: The analysis text for this chunk.
        """
        if not analysis or not analysis.strip():
            return

        # Extract new defined terms
        new_terms = self._extract_defined_terms(analysis)
        for term_name, term_def in new_terms.items():
            if len(self._defined_terms) >= _MAX_DEFINED_TERMS:
                break
            if term_name not in self._defined_terms:
                self._defined_terms[term_name] = term_def

        # Extract new parties
        new_parties = self._extract_parties(analysis)
        for party in new_parties:
            if len(self._party_names) >= _MAX_DEFINED_TERMS:
                break
            if party not in self._party_names:
                self._party_names.append(party)

        # Regenerate summary with updated info
        document_type = self._detect_document_type(
            self._document_summary + " " + analysis
        )
        self._document_summary = self._generate_summary(
            document_type, self._party_names, self._defined_terms
        )

    def build_context_window(
        self,
        chunk_position: int,
        total_chunks: int,
        preceding_summary: str,
        current_chunk_text: str,
    ) -> str:
        """Build the Context_Window string to prepend to a chunk.

        Constructs a context window containing:
        - Document-level summary
        - Chunk position indicator (e.g., "Chunk 3 of 12")
        - Preceding chunk summary (≤ 500 chars)

        Ensures combined size (context + chunk) does not exceed agent_input_limit.
        Compresses context if necessary by truncating preceding summary to 200 chars
        and removing unreferenced defined terms from the document summary.

        Args:
            chunk_position: 1-based position of the current chunk.
            total_chunks: Total number of chunks in the document.
            preceding_summary: Summary of the preceding chunk's analysis (≤ 500 chars).
            current_chunk_text: The text content of the current chunk.

        Returns:
            The context window string to prepend to the chunk.
        """
        # Truncate preceding summary to 500 chars
        if len(preceding_summary) > _MAX_PRECEDING_SUMMARY_LENGTH:
            preceding_summary = preceding_summary[:_MAX_PRECEDING_SUMMARY_LENGTH]

        # Build the context window parts
        doc_summary = self.get_document_summary()
        position_indicator = f"Chunk {chunk_position} of {total_chunks}"

        context_window = self._assemble_context_window(
            doc_summary, position_indicator, preceding_summary
        )

        # Size safety check
        combined_size = len(context_window) + len(current_chunk_text)
        if combined_size <= self._config.agent_input_limit:
            return context_window

        # Compression step 1: truncate preceding summary to 200 chars
        compressed_summary = preceding_summary[:_COMPRESSED_SUMMARY_LENGTH]
        context_window = self._assemble_context_window(
            doc_summary, position_indicator, compressed_summary
        )

        combined_size = len(context_window) + len(current_chunk_text)
        if combined_size <= self._config.agent_input_limit:
            return context_window

        # Compression step 2: remove defined terms not referenced in current chunk
        reduced_doc_summary = self._remove_unreferenced_terms(
            doc_summary, current_chunk_text
        )
        context_window = self._assemble_context_window(
            reduced_doc_summary, position_indicator, compressed_summary
        )

        # Final truncation to guarantee size constraint
        combined_size = len(context_window) + len(current_chunk_text)
        if combined_size > self._config.agent_input_limit:
            max_context_size = self._config.agent_input_limit - len(current_chunk_text)
            if max_context_size > 0:
                context_window = context_window[:max_context_size]
            else:
                context_window = ""

        return context_window

    def get_preceding_summary(self, chunk_position: int) -> str:
        """Return summary of the preceding chunk's analysis (max 500 chars).

        Returns the stored summary for the chunk immediately before the given
        position (i.e., chunk_position - 1).

        Args:
            chunk_position: 1-based position of the current chunk.

        Returns:
            Summary string ≤ 500 characters, or empty string if no preceding
            summary is stored (e.g., for the first chunk).
        """
        preceding_pos = chunk_position - 1
        if preceding_pos < 1:
            return ""

        summary = self._preceding_summaries.get(preceding_pos, "")
        if len(summary) > _MAX_PRECEDING_SUMMARY_LENGTH:
            return summary[:_MAX_PRECEDING_SUMMARY_LENGTH]
        return summary

    def store_preceding_summary(self, chunk_position: int, summary: str) -> None:
        """Store a chunk's summary for use as preceding context for the next chunk.

        Truncates the summary to 500 characters if longer.

        Args:
            chunk_position: 1-based position of the chunk whose summary is being stored.
            summary: The summary text to store.
        """
        if len(summary) > _MAX_PRECEDING_SUMMARY_LENGTH:
            summary = summary[:_MAX_PRECEDING_SUMMARY_LENGTH]
        self._preceding_summaries[chunk_position] = summary

    def get_document_summary(self) -> str:
        """Return current document-level summary (max 2000 chars).

        Returns:
            The document summary string, guaranteed to be ≤ 2000 characters.
        """
        if len(self._document_summary) > _MAX_SUMMARY_LENGTH:
            return self._document_summary[:_MAX_SUMMARY_LENGTH]
        return self._document_summary

    def _detect_document_type(self, text: str) -> str:
        """Detect document type from classification keywords.

        Args:
            text: Text to search for document type keywords.

        Returns:
            The detected document type string, or "Unknown" if none found.
        """
        text_lower = text.lower()
        for keyword in _DOCUMENT_TYPE_KEYWORDS:
            if keyword.lower() in text_lower:
                return keyword
        return "Unknown"

    def _extract_parties(self, text: str) -> list[str]:
        """Extract party names from analysis text.

        Looks for party names in contexts like:
        - "parties:" followed by names
        - Capitalized names near contract/agreement language
        - "between X and Y" patterns

        Args:
            text: Text to search for party names.

        Returns:
            List of unique party name strings.
        """
        parties: list[str] = []

        # Pattern 1: "parties:" followed by names (comma or "and" separated)
        parties_section = re.search(
            r"(?:parties|party)\s*:\s*([^\n]+)", text, re.IGNORECASE
        )
        if parties_section:
            names_text = parties_section.group(1)
            # Split by comma or "and"
            names = re.split(r"\s*,\s*|\s+and\s+", names_text)
            for name in names:
                cleaned = name.strip().strip(".")
                if cleaned and len(cleaned) > 1 and cleaned[0].isupper():
                    if cleaned not in parties:
                        parties.append(cleaned)

        # Pattern 2: "between X and Y" near agreement/contract language
        between_pattern = re.finditer(
            r"between\s+([A-Z][A-Za-z\s,.]+?)\s+and\s+([A-Z][A-Za-z\s,.]+?)(?:\.|,|\s*\()",
            text,
        )
        for match in between_pattern:
            for group_idx in (1, 2):
                name = match.group(group_idx).strip().strip(",.")
                if name and name not in parties:
                    parties.append(name)

        # Cap at 50
        return parties[:_MAX_DEFINED_TERMS]

    def _extract_defined_terms(self, text: str) -> dict[str, str]:
        """Extract defined terms using legal definition patterns.

        Detects terms defined via:
        - "X" hereinafter referred to as / means / is defined as
        - hereinafter referred to as / means / defined as "X"

        Args:
            text: Text to search for defined terms.

        Returns:
            Dictionary mapping term names to their definition context.
        """
        terms: dict[str, str] = {}

        # Pattern 1: "term" followed by definition keyword
        # e.g., "Confidential Information" means ...
        pattern1 = re.finditer(
            r'"([^"]+)"\s*(hereinafter referred to as|means|is defined as)\s*([^.]*)',
            text,
            re.IGNORECASE,
        )
        for match in pattern1:
            term_name = match.group(1).strip()
            definition = match.group(3).strip() if match.group(3) else ""
            if term_name and term_name not in terms:
                terms[term_name] = definition

        # Pattern 2: definition keyword followed by "term"
        # e.g., hereinafter referred to as "the Company"
        pattern2 = re.finditer(
            r"(?:hereinafter referred to as|means|defined as)\s+\"([^\"]+)\"",
            text,
            re.IGNORECASE,
        )
        for match in pattern2:
            term_name = match.group(1).strip()
            if term_name and term_name not in terms:
                terms[term_name] = ""

        return terms

    def _generate_summary(
        self,
        document_type: str,
        parties: list[str],
        defined_terms: dict[str, str],
    ) -> str:
        """Generate a document-level summary string.

        Format:
            Document Type: X
            Parties: A, B
            Defined Terms: term1, term2...

        If no parties or terms found, only includes document type.
        Summary is guaranteed ≤ 2000 characters.

        Args:
            document_type: Detected document type.
            parties: List of identified party names.
            defined_terms: Dictionary of defined terms.

        Returns:
            Summary string ≤ 2000 characters.
        """
        parts: list[str] = [f"Document Type: {document_type}"]

        if parties:
            parties_str = ", ".join(parties)
            parts.append(f"Parties: {parties_str}")

        if defined_terms:
            terms_str = ", ".join(defined_terms.keys())
            parts.append(f"Defined Terms: {terms_str}")

        summary = "\n".join(parts)

        # Enforce max length
        if len(summary) > _MAX_SUMMARY_LENGTH:
            summary = summary[:_MAX_SUMMARY_LENGTH]

        return summary

    def _assemble_context_window(
        self,
        doc_summary: str,
        position_indicator: str,
        preceding_summary: str,
    ) -> str:
        """Assemble the context window string from its parts.

        Args:
            doc_summary: The document-level summary.
            position_indicator: e.g., "Chunk 3 of 12".
            preceding_summary: Summary of the preceding chunk.

        Returns:
            Formatted context window string.
        """
        parts = [doc_summary, f"[Position: {position_indicator}]"]
        if preceding_summary:
            parts.append(f"[Previous chunk summary: {preceding_summary}]")
        return "\n\n".join(parts)

    def _remove_unreferenced_terms(
        self, doc_summary: str, current_chunk_text: str
    ) -> str:
        """Remove defined terms from the summary that are not referenced in the chunk.

        Args:
            doc_summary: The current document summary string.
            current_chunk_text: The text of the current chunk.

        Returns:
            Reduced summary with unreferenced defined terms removed.
        """
        # Check if summary has a "Defined Terms:" line
        if "Defined Terms:" not in doc_summary:
            return doc_summary

        lines = doc_summary.split("\n")
        new_lines: list[str] = []
        chunk_text_lower = current_chunk_text.lower()

        for line in lines:
            if line.startswith("Defined Terms:"):
                # Filter out terms not referenced in the current chunk
                terms_part = line[len("Defined Terms:"):].strip()
                terms = [t.strip() for t in terms_part.split(",")]
                referenced_terms = [
                    t for t in terms if t.lower() in chunk_text_lower
                ]
                if referenced_terms:
                    new_lines.append(
                        "Defined Terms: " + ", ".join(referenced_terms)
                    )
                # If no referenced terms, omit the line entirely
            else:
                new_lines.append(line)

        return "\n".join(new_lines)
