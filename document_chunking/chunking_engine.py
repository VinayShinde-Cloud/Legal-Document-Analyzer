"""Chunking engine module for splitting documents at semantic boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass

from document_chunking.config import ChunkConfig
from document_chunking.models import Boundary, BoundaryType, Chunk


class ChunkingError(Exception):
    """Raised when a document cannot be chunked.

    This occurs for empty content or unrecognized document formats.
    """

    pass


@dataclass
class TextSegment:
    """An intermediate text segment produced during chunking.

    Attributes:
        text: The segment text content.
        start_offset: Character offset of the segment start in the original document.
        end_offset: Character offset of the segment end in the original document.
        section_heading: Optional section heading associated with this segment.
    """

    text: str
    start_offset: int
    end_offset: int
    section_heading: str | None = None


# Compiled regex patterns for boundary detection
_SECTION_HEADING_PATTERN = re.compile(
    r"^(#{1,6}\s|ARTICLE\s|SECTION\s|Part\s)\d*", re.MULTILINE
)
_CLAUSE_NUMBER_PATTERN = re.compile(r"^\s*(\d+\.)+\d*\s", re.MULTILINE)
_PAGE_BREAK_PATTERN = re.compile(r"\f|^---$", re.MULTILINE)
_PARAGRAPH_BREAK_PATTERN = re.compile(r"\n{2,}")
_SENTENCE_ENDING_PATTERN = re.compile(r"[.?!]\s+|[.?!]$", re.MULTILINE)


class ChunkingEngine:
    """Splits extracted document text into semantically meaningful chunks.

    The engine detects semantic boundaries in priority order and splits
    text at the highest-priority boundaries that keep chunks within
    the configured max_chunk_size.
    """

    def __init__(self, config: ChunkConfig) -> None:
        """Initialize with chunk configuration parameters.

        Args:
            config: ChunkConfig instance with chunking parameters.
        """
        self.config = config

    def chunk_document(self, text: str) -> list[Chunk]:
        """Split document text into semantic chunks.

        Args:
            text: Full extracted document text.

        Returns:
            Ordered list of Chunk objects.

        Raises:
            ChunkingError: If document is empty or cannot be parsed.
        """
        if not text or not text.strip():
            raise ChunkingError("Document is empty or contains only whitespace.")

        # If the entire text fits within max_chunk_size, return a single chunk
        if len(text) <= self.config.max_chunk_size:
            heading = self._extract_section_heading(text)
            return [
                Chunk(
                    position=1,
                    text=text,
                    start_offset=0,
                    end_offset=len(text),
                    section_heading=heading,
                )
            ]

        # Split text into segments at detected boundaries
        segments = self._split_at_boundaries(text)

        # Handle oversized segments
        split_segments: list[TextSegment] = []
        for segment in segments:
            if len(segment.text) > self.config.max_chunk_size:
                sub_segments = self._split_oversized_segment(segment)
                split_segments.extend(sub_segments)
            else:
                split_segments.append(segment)

        # Merge small segments that are below min_chunk_size
        merged_segments = self._merge_small_segments(split_segments)

        # Convert segments to chunks with sequential positions
        chunks: list[Chunk] = []
        for i, segment in enumerate(merged_segments):
            chunk = Chunk(
                position=i + 1,
                text=segment.text,
                start_offset=segment.start_offset,
                end_offset=segment.end_offset,
                section_heading=segment.section_heading,
            )
            chunks.append(chunk)

        # Apply overlap between adjacent chunks
        chunks = self._apply_overlap(chunks)

        return chunks

    def _detect_boundaries(self, text: str) -> list[Boundary]:
        """Detect semantic boundaries in the text.

        Boundaries are detected in priority order:
        section headings > clause numbers > page breaks > paragraph breaks > sentence endings.

        Args:
            text: The document text to scan.

        Returns:
            List of Boundary objects sorted by position.
        """
        boundaries: list[Boundary] = []

        # Section headings (priority 1)
        for match in _SECTION_HEADING_PATTERN.finditer(text):
            boundaries.append(
                Boundary(position=match.start(), boundary_type=BoundaryType.SECTION_HEADING)
            )

        # Clause numbers (priority 2)
        for match in _CLAUSE_NUMBER_PATTERN.finditer(text):
            boundaries.append(
                Boundary(position=match.start(), boundary_type=BoundaryType.CLAUSE_NUMBER)
            )

        # Page breaks (priority 3)
        for match in _PAGE_BREAK_PATTERN.finditer(text):
            boundaries.append(
                Boundary(position=match.start(), boundary_type=BoundaryType.PAGE_BREAK)
            )

        # Paragraph breaks (priority 4)
        for match in _PARAGRAPH_BREAK_PATTERN.finditer(text):
            boundaries.append(
                Boundary(position=match.start(), boundary_type=BoundaryType.PARAGRAPH_BREAK)
            )

        # Sentence endings (priority 5)
        for match in _SENTENCE_ENDING_PATTERN.finditer(text):
            # Position after the sentence ending punctuation (end of the match)
            boundaries.append(
                Boundary(position=match.end(), boundary_type=BoundaryType.SENTENCE_ENDING)
            )

        # Sort by position
        boundaries.sort(key=lambda b: b.position)
        return boundaries

    def _split_at_boundaries(self, text: str) -> list[TextSegment]:
        """Split text at the highest-priority boundaries within max_chunk_size.

        This method uses a greedy approach: it accumulates text until adding
        more would exceed max_chunk_size, then splits at the highest-priority
        boundary found within the current segment.

        Args:
            text: Full document text.

        Returns:
            List of TextSegment objects.
        """
        max_size = self.config.max_chunk_size
        boundaries = self._detect_boundaries(text)

        segments: list[TextSegment] = []
        current_start = 0

        while current_start < len(text):
            # If remaining text fits in one chunk, take it all
            if len(text) - current_start <= max_size:
                segment_text = text[current_start:]
                heading = self._extract_section_heading(segment_text)
                segments.append(
                    TextSegment(
                        text=segment_text,
                        start_offset=current_start,
                        end_offset=len(text),
                        section_heading=heading,
                    )
                )
                break

            # Find the best boundary within the allowed range
            segment_end = current_start + max_size
            # Get boundaries within the range (current_start, segment_end]
            # We want boundaries that would create a split point
            candidates = [
                b
                for b in boundaries
                if current_start < b.position <= segment_end
            ]

            if candidates:
                # Select the highest-priority (lowest enum value) boundary
                # Among boundaries of the same priority, prefer the one closest
                # to max_size to maximize chunk utilization
                best_boundary = self._select_best_boundary(candidates)
                split_pos = best_boundary.position
            else:
                # No boundary found within range - force split at max_size
                split_pos = segment_end

            segment_text = text[current_start:split_pos]
            heading = self._extract_section_heading(segment_text)
            segments.append(
                TextSegment(
                    text=segment_text,
                    start_offset=current_start,
                    end_offset=split_pos,
                    section_heading=heading,
                )
            )
            current_start = split_pos

        return segments

    def _select_best_boundary(self, candidates: list[Boundary]) -> Boundary:
        """Select the best boundary from candidates based on priority.

        Among boundaries of the same highest priority, selects the one
        with the largest position (closest to max_chunk_size) to maximize
        chunk utilization.

        Args:
            candidates: List of boundary candidates within the valid range.

        Returns:
            The best boundary to split at.
        """
        # Find the highest priority (lowest BoundaryType value)
        highest_priority = min(b.boundary_type.value for b in candidates)

        # Among those with the highest priority, pick the latest position
        best_candidates = [
            b for b in candidates if b.boundary_type.value == highest_priority
        ]

        # Return the one with the largest position (maximize chunk size)
        return max(best_candidates, key=lambda b: b.position)

    def _merge_small_segments(self, segments: list[TextSegment]) -> list[TextSegment]:
        """Merge adjacent segments below minimum threshold without exceeding maximum.

        Iterates through segments sequentially. If a segment's text length is
        below min_chunk_size, attempts to merge it with the next segment. If
        the merged result would exceed max_chunk_size, the segments are retained
        as separate chunks regardless of minimum threshold.

        Args:
            segments: List of TextSegment objects to potentially merge.

        Returns:
            List of TextSegment objects after merging.
        """
        if not segments:
            return segments

        min_size = self.config.min_chunk_size
        max_size = self.config.max_chunk_size

        merged: list[TextSegment] = []
        i = 0

        while i < len(segments):
            current = segments[i]

            # If current segment is below min and there's a next segment to merge with
            if len(current.text) < min_size and i + 1 < len(segments):
                next_seg = segments[i + 1]
                combined_length = len(current.text) + len(next_seg.text)

                if combined_length <= max_size:
                    # Merge current with next
                    merged_text = current.text + next_seg.text
                    heading = current.section_heading or next_seg.section_heading
                    merged_segment = TextSegment(
                        text=merged_text,
                        start_offset=current.start_offset,
                        end_offset=next_seg.end_offset,
                        section_heading=heading,
                    )
                    # Replace the pair with the merged segment and continue
                    # from that merged segment (it might still be below min)
                    segments = segments[:i] + [merged_segment] + segments[i + 2:]
                    # Don't increment i - re-check the merged segment
                    continue
                else:
                    # Can't merge without exceeding max, keep as separate
                    merged.append(current)
            else:
                merged.append(current)

            i += 1

        return merged

    def _apply_overlap(self, chunks: list[Chunk]) -> list[Chunk]:
        """Apply configured character overlap between adjacent chunks.

        For each chunk after the first, prepends chunk_overlap characters from
        the end of the previous chunk's text to the start of the current chunk.
        The start_offset is adjusted back by the overlap amount to reflect the
        overlapping region in the original document.

        If chunk_overlap is 0, returns chunks unchanged.

        Args:
            chunks: Ordered list of Chunk objects.

        Returns:
            List of Chunk objects with overlap applied.
        """
        overlap = self.config.chunk_overlap

        if overlap == 0 or len(chunks) <= 1:
            return chunks

        result: list[Chunk] = [chunks[0]]

        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            current_chunk = chunks[i]

            # Get the overlap text from the end of the previous chunk
            # Use the actual available text (may be less than configured overlap)
            actual_overlap = min(overlap, len(prev_chunk.text))
            overlap_text = prev_chunk.text[-actual_overlap:]

            # Prepend overlap text to current chunk
            new_text = overlap_text + current_chunk.text
            new_start_offset = current_chunk.start_offset - actual_overlap

            result.append(
                Chunk(
                    position=current_chunk.position,
                    text=new_text,
                    start_offset=new_start_offset,
                    end_offset=current_chunk.end_offset,
                    section_heading=current_chunk.section_heading,
                )
            )

        return result

    def _split_oversized_segment(self, segment: TextSegment) -> list[TextSegment]:
        """Split a segment exceeding max size at sentence boundaries.

        Sentence boundaries are defined as [.?!] followed by whitespace
        or end-of-text.

        Args:
            segment: A TextSegment whose text exceeds max_chunk_size.

        Returns:
            List of TextSegment objects, each within max_chunk_size.
        """
        text = segment.text
        max_size = self.config.max_chunk_size
        base_offset = segment.start_offset

        # Find all sentence boundaries in the segment
        sentence_boundary_pattern = re.compile(r"[.?!](?:\s+|$)")
        sentence_ends: list[int] = []
        for match in sentence_boundary_pattern.finditer(text):
            sentence_ends.append(match.end())

        segments: list[TextSegment] = []
        current_start = 0

        while current_start < len(text):
            # If remaining text fits, take it all
            if len(text) - current_start <= max_size:
                sub_text = text[current_start:]
                heading = self._extract_section_heading(sub_text)
                segments.append(
                    TextSegment(
                        text=sub_text,
                        start_offset=base_offset + current_start,
                        end_offset=base_offset + len(text),
                        section_heading=heading or segment.section_heading,
                    )
                )
                break

            # Find the latest sentence boundary within max_size
            limit = current_start + max_size
            valid_ends = [e for e in sentence_ends if current_start < e <= limit]

            if valid_ends:
                split_pos = max(valid_ends)
            else:
                # No sentence boundary found - force split at max_size
                split_pos = limit

            sub_text = text[current_start:split_pos]
            heading = self._extract_section_heading(sub_text)
            segments.append(
                TextSegment(
                    text=sub_text,
                    start_offset=base_offset + current_start,
                    end_offset=base_offset + split_pos,
                    section_heading=heading or segment.section_heading,
                )
            )
            current_start = split_pos

        return segments

    def _extract_section_heading(self, text: str) -> str | None:
        """Extract the section heading from the beginning of a text segment.

        Args:
            text: Text to check for a section heading at the start.

        Returns:
            The section heading string if found, None otherwise.
        """
        # Check if text starts with a section heading pattern
        match = _SECTION_HEADING_PATTERN.match(text)
        if match:
            # Get the full line containing the heading
            line_end = text.find("\n", match.start())
            if line_end == -1:
                return text[match.start():].strip()
            return text[match.start():line_end].strip()
        return None
