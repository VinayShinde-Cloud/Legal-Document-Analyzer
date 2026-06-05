"""Tests for the DocumentProcessor class.

Covers document routing, pass-through invocation, file size validation,
elapsed time formatting, time estimation, and retry logic.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from document_chunking.config import ChunkConfig
from document_chunking.document_processor import DocumentProcessor
from document_chunking.models import ProcessingResult, ProgressCallback


@pytest.fixture
def default_config() -> ChunkConfig:
    """Return a default ChunkConfig for testing."""
    return ChunkConfig()


@pytest.fixture
def simple_agent_invoker():
    """Return an agent invoker that echoes input back."""
    return lambda text: f"Analysis of: {text[:50]}"


class TestDocumentRouting:
    """Test size-based routing: ≤10000 → direct, >10000 → chunked."""

    def test_small_document_routes_to_direct(
        self, default_config: ChunkConfig, simple_agent_invoker
    ):
        """Documents ≤ 10000 chars should route to direct invocation."""
        processor = DocumentProcessor(default_config, simple_agent_invoker)
        text = "A" * 10000  # Exactly at the limit
        result = processor.process_document(text, "test.txt")

        assert result.was_chunked is False
        assert result.total_chunks == 0

    def test_large_document_routes_to_chunked(self, default_config: ChunkConfig):
        """Documents > 10000 chars should route to chunked pipeline."""
        # Create text that will produce multiple chunks
        # Use paragraph breaks to create nice boundaries
        paragraphs = []
        for i in range(20):
            paragraphs.append(f"Section {i}. " + "This is a paragraph of text. " * 50)
        text = "\n\n".join(paragraphs)
        assert len(text) > 10000

        agent_invoker = lambda t: "Analysis result summary for chunk."
        processor = DocumentProcessor(default_config, agent_invoker)
        result = processor.process_document(text, "test.txt")

        assert result.was_chunked is True
        assert result.total_chunks > 0
        assert result.successful_chunks > 0

    def test_boundary_10000_chars_is_direct(
        self, default_config: ChunkConfig, simple_agent_invoker
    ):
        """Exactly 10000 chars should use direct invocation."""
        processor = DocumentProcessor(default_config, simple_agent_invoker)
        text = "x" * 10000
        result = processor.process_document(text, "test.txt")
        assert result.was_chunked is False

    def test_boundary_10001_chars_is_chunked(self, default_config: ChunkConfig):
        """10001 chars should use chunked pipeline."""
        agent_invoker = lambda t: "Analysis result."
        processor = DocumentProcessor(default_config, agent_invoker)
        # Create text with boundaries so chunking can work
        text = ("Sentence one. " * 715)  # ~10000+ chars with sentence boundaries
        # Ensure it's over 10000
        while len(text) <= 10000:
            text += "More text here. "
        result = processor.process_document(text, "test.txt")
        assert result.was_chunked is True


class TestDirectInvocation:
    """Test pass-through single invocation returns correct ProcessingResult."""

    def test_direct_invocation_returns_agent_response(
        self, default_config: ChunkConfig
    ):
        """Direct path should return agent response as the report."""
        expected_response = "This is the agent analysis response."
        agent_invoker = lambda text: expected_response
        processor = DocumentProcessor(default_config, agent_invoker)

        result = processor.process_document("Short document.", "test.txt")

        assert result.report == expected_response
        assert result.was_chunked is False
        assert result.total_chunks == 0
        assert result.successful_chunks == 0
        assert result.failed_chunks == 0
        assert result.processing_time_seconds >= 0

    def test_direct_invocation_with_none_response(
        self, default_config: ChunkConfig
    ):
        """Direct path with None response returns empty string report."""
        agent_invoker = lambda text: None
        processor = DocumentProcessor(default_config, agent_invoker)

        result = processor.process_document("Short doc.", "test.txt")

        assert result.report == ""
        assert result.was_chunked is False

    def test_direct_invocation_calls_on_complete(
        self, default_config: ChunkConfig
    ):
        """Direct path should call on_complete callback."""
        callback = MagicMock(spec=ProgressCallback)
        agent_invoker = lambda text: "Response"
        processor = DocumentProcessor(default_config, agent_invoker, callback)

        result = processor.process_document("Small doc.", "test.txt")

        callback.on_complete.assert_called_once_with(result)


class TestFileSizeValidation:
    """Test file size validation: accept 1-25MB, reject 0 and >25MB."""

    def test_valid_minimum_size(self, default_config: ChunkConfig):
        """1 byte should be accepted."""
        processor = DocumentProcessor(default_config, lambda t: t)
        assert processor.validate_file_size(1) is None

    def test_valid_maximum_size(self, default_config: ChunkConfig):
        """25,000,000 bytes should be accepted."""
        processor = DocumentProcessor(default_config, lambda t: t)
        assert processor.validate_file_size(25_000_000) is None

    def test_valid_middle_size(self, default_config: ChunkConfig):
        """A typical file size should be accepted."""
        processor = DocumentProcessor(default_config, lambda t: t)
        assert processor.validate_file_size(5_000_000) is None

    def test_reject_zero_bytes(self, default_config: ChunkConfig):
        """0 bytes should be rejected."""
        processor = DocumentProcessor(default_config, lambda t: t)
        result = processor.validate_file_size(0)
        assert result is not None
        assert "empty" in result.lower() or "0 bytes" in result.lower()

    def test_reject_negative_bytes(self, default_config: ChunkConfig):
        """Negative file size should be rejected."""
        processor = DocumentProcessor(default_config, lambda t: t)
        result = processor.validate_file_size(-1)
        assert result is not None

    def test_reject_over_25mb(self, default_config: ChunkConfig):
        """Over 25MB should be rejected."""
        processor = DocumentProcessor(default_config, lambda t: t)
        result = processor.validate_file_size(25_000_001)
        assert result is not None
        assert "25MB" in result or "25,000,000" in result

    def test_reject_way_over_limit(self, default_config: ChunkConfig):
        """100MB should be rejected with descriptive message."""
        processor = DocumentProcessor(default_config, lambda t: t)
        result = processor.validate_file_size(100_000_000)
        assert result is not None
        assert "exceeds" in result.lower()


class TestElapsedTimeFormatting:
    """Test format_elapsed_time static method."""

    def test_zero_seconds(self):
        """0 seconds → '00:00'."""
        assert DocumentProcessor.format_elapsed_time(0) == "00:00"

    def test_under_one_minute(self):
        """45 seconds → '00:45'."""
        assert DocumentProcessor.format_elapsed_time(45) == "00:45"

    def test_exact_one_minute(self):
        """60 seconds → '01:00'."""
        assert DocumentProcessor.format_elapsed_time(60) == "01:00"

    def test_minutes_and_seconds(self):
        """125 seconds → '02:05'."""
        assert DocumentProcessor.format_elapsed_time(125) == "02:05"

    def test_just_under_one_hour(self):
        """3599 seconds → '59:59'."""
        assert DocumentProcessor.format_elapsed_time(3599) == "59:59"

    def test_exactly_one_hour(self):
        """3600 seconds → '01:00:00'."""
        assert DocumentProcessor.format_elapsed_time(3600) == "01:00:00"

    def test_over_one_hour(self):
        """3661 seconds → '01:01:01'."""
        assert DocumentProcessor.format_elapsed_time(3661) == "01:01:01"

    def test_multiple_hours(self):
        """7384 seconds → '02:03:04'."""
        assert DocumentProcessor.format_elapsed_time(7384) == "02:03:04"

    def test_fractional_seconds_truncated(self):
        """45.9 seconds → '00:45' (truncated, not rounded)."""
        assert DocumentProcessor.format_elapsed_time(45.9) == "00:45"

    def test_large_hours(self):
        """36000 seconds → '10:00:00'."""
        assert DocumentProcessor.format_elapsed_time(36000) == "10:00:00"


class TestTimeEstimation:
    """Test _estimate_remaining_time method."""

    def test_estimate_with_half_complete(self, default_config: ChunkConfig):
        """With 5/10 chunks done in 50s, estimate 50s remaining."""
        processor = DocumentProcessor(default_config, lambda t: t)
        remaining = processor._estimate_remaining_time(
            elapsed=50.0, completed=5, total=10
        )
        assert remaining == pytest.approx(50.0)

    def test_estimate_with_one_complete(self, default_config: ChunkConfig):
        """With 1/4 chunks done in 10s, estimate 30s remaining."""
        processor = DocumentProcessor(default_config, lambda t: t)
        remaining = processor._estimate_remaining_time(
            elapsed=10.0, completed=1, total=4
        )
        assert remaining == pytest.approx(30.0)

    def test_estimate_all_complete(self, default_config: ChunkConfig):
        """With all chunks done, estimate 0s remaining."""
        processor = DocumentProcessor(default_config, lambda t: t)
        remaining = processor._estimate_remaining_time(
            elapsed=100.0, completed=10, total=10
        )
        assert remaining == 0.0

    def test_estimate_none_complete(self, default_config: ChunkConfig):
        """With no chunks done, estimate 0s remaining (can't estimate)."""
        processor = DocumentProcessor(default_config, lambda t: t)
        remaining = processor._estimate_remaining_time(
            elapsed=0.0, completed=0, total=10
        )
        assert remaining == 0.0


class TestRetryLogic:
    """Test _invoke_with_retry with mocked time.sleep."""

    @patch("document_chunking.document_processor.time.sleep")
    def test_success_on_first_attempt(
        self, mock_sleep, default_config: ChunkConfig
    ):
        """Should return response on first successful call."""
        agent_invoker = MagicMock(return_value="Success")
        processor = DocumentProcessor(default_config, agent_invoker)

        result = processor._invoke_with_retry("test input", 1)

        assert result == "Success"
        mock_sleep.assert_not_called()
        agent_invoker.assert_called_once_with("test input")

    @patch("document_chunking.document_processor.time.sleep")
    def test_retry_on_throttling_then_success(
        self, mock_sleep, default_config: ChunkConfig
    ):
        """Should retry on throttling error and succeed on next attempt."""
        agent_invoker = MagicMock(
            side_effect=[
                Exception("ThrottlingException: rate exceeded"),
                "Success after retry",
            ]
        )
        processor = DocumentProcessor(default_config, agent_invoker)

        result = processor._invoke_with_retry("test input", 1)

        assert result == "Success after retry"
        mock_sleep.assert_called_once_with(10)  # Initial backoff
        assert agent_invoker.call_count == 2

    @patch("document_chunking.document_processor.time.sleep")
    def test_retry_exponential_backoff(
        self, mock_sleep, default_config: ChunkConfig
    ):
        """Should double backoff on each retry: 10s, 20s."""
        agent_invoker = MagicMock(
            side_effect=[
                Exception("throttling error"),
                Exception("throttling error"),
                "Success after two retries",
            ]
        )
        processor = DocumentProcessor(default_config, agent_invoker)

        result = processor._invoke_with_retry("test input", 1)

        assert result == "Success after two retries"
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(10)  # First backoff
        mock_sleep.assert_any_call(20)  # Second backoff (doubled)

    @patch("document_chunking.document_processor.time.sleep")
    def test_exhausted_retries_returns_none(
        self, mock_sleep, default_config: ChunkConfig
    ):
        """Should return None after exhausting all retry attempts."""
        agent_invoker = MagicMock(
            side_effect=Exception("throttling error")
        )
        processor = DocumentProcessor(default_config, agent_invoker)

        result = processor._invoke_with_retry("test input", 1)

        assert result is None
        assert agent_invoker.call_count == 3  # max_retries = 3
        assert mock_sleep.call_count == 2  # Sleep between attempts (not after last)

    @patch("document_chunking.document_processor.time.sleep")
    def test_non_throttling_error_no_retry(
        self, mock_sleep, default_config: ChunkConfig
    ):
        """Non-throttling errors should not trigger retries."""
        agent_invoker = MagicMock(
            side_effect=Exception("Connection refused")
        )
        processor = DocumentProcessor(default_config, agent_invoker)

        result = processor._invoke_with_retry("test input", 1)

        assert result is None
        mock_sleep.assert_not_called()
        agent_invoker.assert_called_once()

    @patch("document_chunking.document_processor.time.sleep")
    def test_none_response_returns_none(
        self, mock_sleep, default_config: ChunkConfig
    ):
        """Agent returning None should be treated as failure (no retry)."""
        agent_invoker = MagicMock(return_value=None)
        processor = DocumentProcessor(default_config, agent_invoker)

        result = processor._invoke_with_retry("test input", 1)

        assert result is None
        mock_sleep.assert_not_called()


class TestProgressCallbacks:
    """Test that progress callbacks are invoked correctly during chunked processing."""

    def test_chunked_processing_calls_callbacks(self, default_config: ChunkConfig):
        """Chunked processing should invoke progress callbacks."""
        callback = MagicMock(spec=ProgressCallback)
        agent_invoker = lambda t: "Chunk analysis result."

        # Create a document large enough to be chunked
        paragraphs = []
        for i in range(15):
            paragraphs.append(f"Section {i}. " + "Legal content here. " * 60)
        text = "\n\n".join(paragraphs)
        assert len(text) > 10000

        processor = DocumentProcessor(default_config, agent_invoker, callback)
        result = processor.process_document(text, "test.txt")

        # Verify callbacks were called
        assert callback.on_chunk_complete.call_count == result.total_chunks
        callback.on_synthesis_start.assert_called_once()
        callback.on_complete.assert_called_once()
