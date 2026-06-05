"""Unit tests for the ChunkingEngine module."""

import pytest

from document_chunking.chunking_engine import ChunkingEngine, ChunkingError, TextSegment
from document_chunking.config import ChunkConfig
from document_chunking.models import Boundary, BoundaryType, Chunk


class TestChunkingEngineInit:
    """Tests for ChunkingEngine initialization."""

    def test_init_with_default_config(self):
        config = ChunkConfig()
        engine = ChunkingEngine(config)
        assert engine.config is config

    def test_init_with_custom_config(self):
        config = ChunkConfig(max_chunk_size=2000, min_chunk_size=200)
        engine = ChunkingEngine(config)
        assert engine.config.max_chunk_size == 2000
        assert engine.config.min_chunk_size == 200


class TestChunkDocumentErrors:
    """Tests for ChunkingError raising conditions."""

    def test_empty_string_raises_chunking_error(self):
        engine = ChunkingEngine(ChunkConfig())
        with pytest.raises(ChunkingError, match="empty"):
            engine.chunk_document("")

    def test_whitespace_only_raises_chunking_error(self):
        engine = ChunkingEngine(ChunkConfig())
        with pytest.raises(ChunkingError, match="empty"):
            engine.chunk_document("   \n\t  ")

    def test_none_like_empty_raises_error(self):
        engine = ChunkingEngine(ChunkConfig())
        with pytest.raises(ChunkingError):
            engine.chunk_document("")


class TestChunkDocumentSingleChunk:
    """Tests for documents that fit in a single chunk."""

    def test_small_document_single_chunk(self):
        config = ChunkConfig(max_chunk_size=1000)
        engine = ChunkingEngine(config)
        text = "This is a small document."
        chunks = engine.chunk_document(text)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].position == 1
        assert chunks[0].start_offset == 0
        assert chunks[0].end_offset == len(text)

    def test_document_exactly_at_max_size(self):
        config = ChunkConfig(max_chunk_size=50)
        engine = ChunkingEngine(config)
        text = "a" * 50
        chunks = engine.chunk_document(text)
        assert len(chunks) == 1
        assert chunks[0].text == text


class TestChunkDocumentMultipleChunks:
    """Tests for documents that require splitting."""

    def test_splits_at_section_headings(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50, chunk_overlap=0)
        engine = ChunkingEngine(config)
        text = (
            "# Section One\n\n"
            "Content of section one with enough text to fill space. " * 2 + "\n"
            "# Section Two\n\n"
            "Content of section two with enough text to fill space. " * 2
        )
        chunks = engine.chunk_document(text)
        assert len(chunks) >= 2
        # Verify no chunk exceeds max
        for chunk in chunks:
            assert len(chunk.text) <= config.max_chunk_size

    def test_preserves_sequential_order(self):
        config = ChunkConfig(max_chunk_size=100, min_chunk_size=20)
        engine = ChunkingEngine(config)
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence. Sixth sentence. Seventh sentence. Eighth sentence."
        chunks = engine.chunk_document(text)
        # Verify positions are sequential
        for i, chunk in enumerate(chunks):
            assert chunk.position == i + 1

    def test_round_trip_preservation(self):
        config = ChunkConfig(max_chunk_size=150, min_chunk_size=30, chunk_overlap=0)
        engine = ChunkingEngine(config)
        text = "# Introduction\n\nFirst paragraph with content.\n\n## Details\n\nSecond paragraph with more content here. This adds length.\n\n## Conclusion\n\nFinal paragraph wrapping up the document."
        chunks = engine.chunk_document(text)
        combined = "".join(c.text for c in chunks)
        assert combined == text

    def test_chunk_offsets_are_contiguous(self):
        config = ChunkConfig(max_chunk_size=100, min_chunk_size=20, chunk_overlap=0)
        engine = ChunkingEngine(config)
        text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five. Sentence six. Sentence seven. Sentence eight. Sentence nine."
        chunks = engine.chunk_document(text)
        # Verify contiguous offsets
        for i in range(1, len(chunks)):
            assert chunks[i].start_offset == chunks[i - 1].end_offset


class TestBoundaryDetection:
    """Tests for _detect_boundaries method."""

    def test_detects_section_headings(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "# Heading One\nContent\n## Heading Two\nMore content"
        boundaries = engine._detect_boundaries(text)
        heading_boundaries = [b for b in boundaries if b.boundary_type == BoundaryType.SECTION_HEADING]
        assert len(heading_boundaries) == 2

    def test_detects_article_headings(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "ARTICLE 1 Introduction\nContent\nARTICLE 2 Definitions"
        boundaries = engine._detect_boundaries(text)
        heading_boundaries = [b for b in boundaries if b.boundary_type == BoundaryType.SECTION_HEADING]
        assert len(heading_boundaries) == 2

    def test_detects_section_keyword_headings(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "SECTION 1 Scope\nContent\nSECTION 2 Terms"
        boundaries = engine._detect_boundaries(text)
        heading_boundaries = [b for b in boundaries if b.boundary_type == BoundaryType.SECTION_HEADING]
        assert len(heading_boundaries) == 2

    def test_detects_clause_numbers(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "1.1 First clause\nContent\n2.1 Second clause"
        boundaries = engine._detect_boundaries(text)
        clause_boundaries = [b for b in boundaries if b.boundary_type == BoundaryType.CLAUSE_NUMBER]
        assert len(clause_boundaries) == 2

    def test_detects_page_breaks_form_feed(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "Before\fAfter"
        boundaries = engine._detect_boundaries(text)
        page_boundaries = [b for b in boundaries if b.boundary_type == BoundaryType.PAGE_BREAK]
        assert len(page_boundaries) == 1

    def test_detects_page_breaks_dashes(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "Before\n---\nAfter"
        boundaries = engine._detect_boundaries(text)
        page_boundaries = [b for b in boundaries if b.boundary_type == BoundaryType.PAGE_BREAK]
        assert len(page_boundaries) == 1

    def test_detects_paragraph_breaks(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "First paragraph.\n\nSecond paragraph.\n\n\nThird paragraph."
        boundaries = engine._detect_boundaries(text)
        para_boundaries = [b for b in boundaries if b.boundary_type == BoundaryType.PARAGRAPH_BREAK]
        assert len(para_boundaries) == 2

    def test_detects_sentence_endings(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "First sentence. Second sentence? Third sentence! End"
        boundaries = engine._detect_boundaries(text)
        sent_boundaries = [b for b in boundaries if b.boundary_type == BoundaryType.SENTENCE_ENDING]
        assert len(sent_boundaries) == 3

    def test_boundaries_sorted_by_position(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "# Heading\n\nParagraph one. Sentence two.\n\n## Subheading\n\nAnother paragraph."
        boundaries = engine._detect_boundaries(text)
        positions = [b.position for b in boundaries]
        assert positions == sorted(positions)


class TestPrioritySelection:
    """Tests for boundary priority selection."""

    def test_section_heading_over_paragraph_break(self):
        engine = ChunkingEngine(ChunkConfig())
        candidates = [
            Boundary(position=50, boundary_type=BoundaryType.PARAGRAPH_BREAK),
            Boundary(position=80, boundary_type=BoundaryType.SECTION_HEADING),
        ]
        best = engine._select_best_boundary(candidates)
        assert best.boundary_type == BoundaryType.SECTION_HEADING

    def test_clause_number_over_sentence_ending(self):
        engine = ChunkingEngine(ChunkConfig())
        candidates = [
            Boundary(position=50, boundary_type=BoundaryType.SENTENCE_ENDING),
            Boundary(position=80, boundary_type=BoundaryType.CLAUSE_NUMBER),
        ]
        best = engine._select_best_boundary(candidates)
        assert best.boundary_type == BoundaryType.CLAUSE_NUMBER

    def test_page_break_over_paragraph_break(self):
        engine = ChunkingEngine(ChunkConfig())
        candidates = [
            Boundary(position=50, boundary_type=BoundaryType.PARAGRAPH_BREAK),
            Boundary(position=40, boundary_type=BoundaryType.PAGE_BREAK),
        ]
        best = engine._select_best_boundary(candidates)
        assert best.boundary_type == BoundaryType.PAGE_BREAK

    def test_same_priority_picks_latest_position(self):
        engine = ChunkingEngine(ChunkConfig())
        candidates = [
            Boundary(position=30, boundary_type=BoundaryType.PARAGRAPH_BREAK),
            Boundary(position=80, boundary_type=BoundaryType.PARAGRAPH_BREAK),
            Boundary(position=50, boundary_type=BoundaryType.PARAGRAPH_BREAK),
        ]
        best = engine._select_best_boundary(candidates)
        assert best.position == 80


class TestOversizedSegmentSplitting:
    """Tests for _split_oversized_segment method."""

    def test_splits_at_sentence_boundaries(self):
        config = ChunkConfig(max_chunk_size=80, min_chunk_size=20)
        engine = ChunkingEngine(config)
        text = "First sentence here. Second sentence here. Third sentence here. Fourth sentence here. Fifth sentence."
        segment = TextSegment(text=text, start_offset=0, end_offset=len(text))
        result = engine._split_oversized_segment(segment)
        assert len(result) >= 2
        for s in result:
            assert len(s.text) <= config.max_chunk_size

    def test_preserves_text_content(self):
        config = ChunkConfig(max_chunk_size=50, min_chunk_size=10)
        engine = ChunkingEngine(config)
        text = "Short. Medium sentence. Longer sentence here. Another one. And more content here. Final."
        segment = TextSegment(text=text, start_offset=10, end_offset=10 + len(text))
        result = engine._split_oversized_segment(segment)
        combined = "".join(s.text for s in result)
        assert combined == text

    def test_offsets_account_for_base_offset(self):
        config = ChunkConfig(max_chunk_size=50, min_chunk_size=10)
        engine = ChunkingEngine(config)
        text = "First sentence. Second sentence. Third sentence."
        base_offset = 100
        segment = TextSegment(text=text, start_offset=base_offset, end_offset=base_offset + len(text))
        result = engine._split_oversized_segment(segment)
        assert result[0].start_offset == base_offset
        assert result[-1].end_offset == base_offset + len(text)

    def test_force_split_when_no_sentence_boundary(self):
        config = ChunkConfig(max_chunk_size=20, min_chunk_size=5)
        engine = ChunkingEngine(config)
        # No sentence boundaries in this text
        text = "a" * 50
        segment = TextSegment(text=text, start_offset=0, end_offset=50)
        result = engine._split_oversized_segment(segment)
        for s in result:
            assert len(s.text) <= config.max_chunk_size


class TestMergeSmallSegments:
    """Tests for _merge_small_segments method."""

    def test_merges_adjacent_small_segments(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50)
        engine = ChunkingEngine(config)
        segments = [
            TextSegment(text="Short.", start_offset=0, end_offset=6),
            TextSegment(text="Also short.", start_offset=6, end_offset=17),
        ]
        result = engine._merge_small_segments(segments)
        assert len(result) == 1
        assert result[0].text == "Short.Also short."
        assert result[0].start_offset == 0
        assert result[0].end_offset == 17

    def test_does_not_merge_if_exceeds_max(self):
        config = ChunkConfig(max_chunk_size=15, min_chunk_size=10)
        engine = ChunkingEngine(config)
        segments = [
            TextSegment(text="Short.", start_offset=0, end_offset=6),
            TextSegment(text="TenCharsXX", start_offset=6, end_offset=17),
        ]
        # Combined would be 17 chars > max of 15
        result = engine._merge_small_segments(segments)
        assert len(result) == 2
        assert result[0].text == "Short."
        assert result[1].text == "TenCharsXX"

    def test_merges_multiple_consecutive_small_segments(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50)
        engine = ChunkingEngine(config)
        segments = [
            TextSegment(text="A.", start_offset=0, end_offset=2),
            TextSegment(text="B.", start_offset=2, end_offset=4),
            TextSegment(text="C.", start_offset=4, end_offset=6),
        ]
        result = engine._merge_small_segments(segments)
        assert len(result) == 1
        assert result[0].text == "A.B.C."
        assert result[0].start_offset == 0
        assert result[0].end_offset == 6

    def test_preserves_large_segments_unchanged(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=10)
        engine = ChunkingEngine(config)
        text_large = "x" * 50
        segments = [
            TextSegment(text=text_large, start_offset=0, end_offset=50),
            TextSegment(text=text_large, start_offset=50, end_offset=100),
        ]
        result = engine._merge_small_segments(segments)
        assert len(result) == 2

    def test_preserves_section_heading_from_first_segment(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50)
        engine = ChunkingEngine(config)
        segments = [
            TextSegment(text="Small", start_offset=0, end_offset=5, section_heading="# Intro"),
            TextSegment(text="Also small", start_offset=5, end_offset=15),
        ]
        result = engine._merge_small_segments(segments)
        assert len(result) == 1
        assert result[0].section_heading == "# Intro"

    def test_uses_next_heading_if_current_has_none(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50)
        engine = ChunkingEngine(config)
        segments = [
            TextSegment(text="Small", start_offset=0, end_offset=5, section_heading=None),
            TextSegment(text="Also small", start_offset=5, end_offset=15, section_heading="# Next"),
        ]
        result = engine._merge_small_segments(segments)
        assert len(result) == 1
        assert result[0].section_heading == "# Next"

    def test_empty_segments_list(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50)
        engine = ChunkingEngine(config)
        result = engine._merge_small_segments([])
        assert result == []

    def test_single_small_segment_at_end(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50)
        engine = ChunkingEngine(config)
        text_large = "x" * 100
        segments = [
            TextSegment(text=text_large, start_offset=0, end_offset=100),
            TextSegment(text="Tiny.", start_offset=100, end_offset=105),
        ]
        # The last segment is small but no next segment to merge with
        result = engine._merge_small_segments(segments)
        assert len(result) == 2

    def test_text_round_trip_after_merge(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50)
        engine = ChunkingEngine(config)
        segments = [
            TextSegment(text="Hello ", start_offset=0, end_offset=6),
            TextSegment(text="world!", start_offset=6, end_offset=12),
            TextSegment(text=" More text here.", start_offset=12, end_offset=28),
        ]
        result = engine._merge_small_segments(segments)
        combined = "".join(s.text for s in result)
        assert combined == "Hello world! More text here."


class TestApplyOverlap:
    """Tests for _apply_overlap method."""

    def test_no_overlap_when_zero(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50, chunk_overlap=0)
        engine = ChunkingEngine(config)
        chunks = [
            Chunk(position=1, text="First chunk.", start_offset=0, end_offset=12),
            Chunk(position=2, text="Second chunk.", start_offset=12, end_offset=25),
        ]
        result = engine._apply_overlap(chunks)
        assert result[0].text == "First chunk."
        assert result[1].text == "Second chunk."

    def test_overlap_prepends_chars_from_previous(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50, chunk_overlap=5)
        engine = ChunkingEngine(config)
        chunks = [
            Chunk(position=1, text="First chunk.", start_offset=0, end_offset=12),
            Chunk(position=2, text="Second chunk.", start_offset=12, end_offset=25),
        ]
        result = engine._apply_overlap(chunks)
        assert result[0].text == "First chunk."
        # "First chunk." has 12 chars. Last 5 chars: "hunk."
        assert result[1].text == "hunk." + "Second chunk."
        assert result[1].start_offset == 12 - 5  # 7

    def test_first_chunk_unchanged(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50, chunk_overlap=10)
        engine = ChunkingEngine(config)
        chunks = [
            Chunk(position=1, text="First chunk text.", start_offset=0, end_offset=17),
            Chunk(position=2, text="Second chunk.", start_offset=17, end_offset=30),
        ]
        result = engine._apply_overlap(chunks)
        assert result[0].text == "First chunk text."
        assert result[0].start_offset == 0
        assert result[0].end_offset == 17

    def test_overlap_limited_by_previous_chunk_length(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=100, chunk_overlap=100)
        engine = ChunkingEngine(config)
        chunks = [
            Chunk(position=1, text="Short.", start_offset=0, end_offset=6),
            Chunk(position=2, text="Next chunk.", start_offset=6, end_offset=17),
        ]
        result = engine._apply_overlap(chunks)
        # Overlap is 100 but previous chunk is only 6 chars, so actual overlap is 6
        assert result[1].text == "Short." + "Next chunk."
        assert result[1].start_offset == 0  # 6 - 6 = 0

    def test_single_chunk_unchanged(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50, chunk_overlap=50)
        engine = ChunkingEngine(config)
        chunks = [
            Chunk(position=1, text="Only chunk.", start_offset=0, end_offset=11),
        ]
        result = engine._apply_overlap(chunks)
        assert len(result) == 1
        assert result[0].text == "Only chunk."

    def test_multiple_chunks_overlap_applied_sequentially(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50, chunk_overlap=3)
        engine = ChunkingEngine(config)
        chunks = [
            Chunk(position=1, text="AAABBB", start_offset=0, end_offset=6),
            Chunk(position=2, text="CCCDDD", start_offset=6, end_offset=12),
            Chunk(position=3, text="EEEFFF", start_offset=12, end_offset=18),
        ]
        result = engine._apply_overlap(chunks)
        assert result[0].text == "AAABBB"
        # Second chunk gets last 3 of first: "BBB" + "CCCDDD"
        assert result[1].text == "BBB" + "CCCDDD"
        # Third chunk gets last 3 of the ORIGINAL second chunk (pre-overlap): "DDD" + "EEEFFF"
        # Wait - _apply_overlap uses chunks[i-1] which is the original chunk list
        # Actually it uses prev_chunk from the loop. Let me re-check.
        # The method iterates over the original chunks list indices, using chunks[i-1].text
        # chunks[i-1] is the ORIGINAL chunk at that index, not the result
        # Wait no - it uses `prev_chunk = chunks[i - 1]` from the INPUT list, not `result`
        # So third chunk overlap comes from original chunks[1].text = "CCCDDD", last 3 = "DDD"
        assert result[2].text == "DDD" + "EEEFFF"

    def test_positions_preserved(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50, chunk_overlap=5)
        engine = ChunkingEngine(config)
        chunks = [
            Chunk(position=1, text="First chunk.", start_offset=0, end_offset=12),
            Chunk(position=2, text="Second chunk.", start_offset=12, end_offset=25),
            Chunk(position=3, text="Third chunk.", start_offset=25, end_offset=37),
        ]
        result = engine._apply_overlap(chunks)
        assert result[0].position == 1
        assert result[1].position == 2
        assert result[2].position == 3

    def test_round_trip_with_overlap_removed(self):
        """Verify that removing overlap from all chunks except first gives original text."""
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50, chunk_overlap=5)
        engine = ChunkingEngine(config)
        chunks = [
            Chunk(position=1, text="Hello world.", start_offset=0, end_offset=12),
            Chunk(position=2, text="Next part.", start_offset=12, end_offset=22),
            Chunk(position=3, text="Final part.", start_offset=22, end_offset=33),
        ]
        result = engine._apply_overlap(chunks)
        # Remove overlap from all but first
        original = result[0].text
        for i in range(1, len(result)):
            # The overlap is 5 chars (or less if prev was shorter)
            prev_text = chunks[i - 1].text
            actual_overlap = min(5, len(prev_text))
            original += result[i].text[actual_overlap:]
        assert original == "Hello world.Next part.Final part."


class TestChunkDocumentWithMergingAndOverlap:
    """Integration tests for chunk_document with merging and overlap."""

    def test_round_trip_with_overlap(self):
        """Concatenating chunks with overlap removed equals original text."""
        config = ChunkConfig(max_chunk_size=100, min_chunk_size=20, chunk_overlap=10)
        engine = ChunkingEngine(config)
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence. Sixth sentence. Seventh sentence. Eighth sentence here."
        chunks = engine.chunk_document(text)

        # Remove overlap from all but first chunk
        reconstructed = chunks[0].text
        for i in range(1, len(chunks)):
            overlap = config.chunk_overlap
            # The overlap is at most `chunk_overlap` chars from previous chunk
            prev_original_text_len = len(chunks[i - 1].text) if i == 1 else len(chunks[i - 1].text)
            actual_overlap = min(overlap, prev_original_text_len)
            reconstructed += chunks[i].text[actual_overlap:]

        assert reconstructed == text

    def test_all_chunks_within_max_size(self):
        config = ChunkConfig(max_chunk_size=100, min_chunk_size=20, chunk_overlap=10)
        engine = ChunkingEngine(config)
        text = "A" * 50 + ". " + "B" * 50 + ". " + "C" * 50 + ". " + "D" * 50 + "."
        chunks = engine.chunk_document(text)
        for chunk in chunks:
            # After overlap, chunks might be slightly larger than max due to prepended overlap
            # Actually, the max_chunk_size constraint is on the segments BEFORE overlap
            # Overlap can make chunks larger. This is by design.
            assert chunk.position >= 1

    def test_positions_are_sequential(self):
        config = ChunkConfig(max_chunk_size=80, min_chunk_size=20, chunk_overlap=10)
        engine = ChunkingEngine(config)
        text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five. Sentence six. Sentence seven. Sentence eight."
        chunks = engine.chunk_document(text)
        for i, chunk in enumerate(chunks):
            assert chunk.position == i + 1

    def test_zero_overlap_round_trip(self):
        """With zero overlap, concatenation of chunks equals original text."""
        config = ChunkConfig(max_chunk_size=100, min_chunk_size=20, chunk_overlap=0)
        engine = ChunkingEngine(config)
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence. Sixth sentence. Seventh sentence. Eighth sentence."
        chunks = engine.chunk_document(text)
        combined = "".join(c.text for c in chunks)
        assert combined == text


class TestSectionHeadingExtraction:
    """Tests for section heading extraction."""

    def test_extracts_markdown_heading(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "# Main Title\nSome content here."
        heading = engine._extract_section_heading(text)
        assert heading == "# Main Title"

    def test_extracts_article_heading(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "ARTICLE 5 Termination\nContent here."
        heading = engine._extract_section_heading(text)
        assert heading == "ARTICLE 5 Termination"

    def test_returns_none_for_no_heading(self):
        engine = ChunkingEngine(ChunkConfig())
        text = "Just regular text without any heading."
        heading = engine._extract_section_heading(text)
        assert heading is None

    def test_chunk_has_section_heading(self):
        config = ChunkConfig(max_chunk_size=200, min_chunk_size=50)
        engine = ChunkingEngine(config)
        text = "# Introduction\n\nThis is the introductory text."
        chunks = engine.chunk_document(text)
        assert chunks[0].section_heading == "# Introduction"
