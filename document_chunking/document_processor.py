"""Document Processor module orchestrating the full document analysis pipeline.

Handles document routing (pass-through vs chunked), sequential chunk processing
with retry logic, progress reporting, and file size validation.
"""

from __future__ import annotations

import time
from typing import Callable

from document_chunking.chunking_engine import ChunkingEngine
from document_chunking.config import ChunkConfig
from document_chunking.context_manager import ContextManager
from document_chunking.models import (
    ChunkAnalysis,
    FailedChunk,
    ProcessingResult,
    ProgressCallback,
)
from document_chunking.synthesis_engine import SynthesisEngine


# File size constants
_MIN_FILE_SIZE_BYTES = 1
_MAX_FILE_SIZE_BYTES = 25_000_000  # 25MB


class DocumentProcessor:
    """Orchestrate the full document processing pipeline.

    Routes documents by size: small documents (≤ agent_input_limit) go through
    direct single invocation; larger documents go through the chunked pipeline
    with context management, retry logic, and synthesis.
    """

    def __init__(
        self,
        config: ChunkConfig,
        agent_invoker: Callable[[str], str | None],
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Initialize with configuration, agent invoker, and optional progress callback.

        Args:
            config: ChunkConfig instance with chunking and retry parameters.
            agent_invoker: Callable that takes a prompt string and returns the
                agent's response string, or None on failure.
            progress_callback: Optional callback implementing ProgressCallback
                protocol for UI progress updates.
        """
        self._config = config
        self._agent_invoker = agent_invoker
        self._progress_callback = progress_callback

    def process_document(self, text: str, filename: str) -> ProcessingResult:
        """Full document processing pipeline.

        If text ≤ agent_input_limit (10,000 chars): call agent directly,
        return ProcessingResult(was_chunked=False).
        Otherwise: chunk → process each chunk sequentially with context →
        synthesize → return ProcessingResult(was_chunked=True).

        Args:
            text: The full extracted document text.
            filename: The original filename (for metadata/logging).

        Returns:
            ProcessingResult with the analysis report and processing metadata.
        """
        start_time = time.time()

        # Route by document size
        if len(text) <= self._config.agent_input_limit:
            return self._process_direct(text, start_time)
        else:
            return self._process_chunked(text, start_time)

    def validate_file_size(self, file_size_bytes: int) -> str | None:
        """Validate file size is within acceptable range.

        Args:
            file_size_bytes: The file size in bytes.

        Returns:
            None if the file size is valid (1 to 25,000,000 bytes inclusive).
            A descriptive error message string if the file is rejected.
        """
        if file_size_bytes <= 0:
            return (
                "File is empty (0 bytes). Please upload a file with content."
            )
        if file_size_bytes > _MAX_FILE_SIZE_BYTES:
            return (
                f"File size ({file_size_bytes:,} bytes) exceeds the maximum "
                f"allowed size of 25MB ({_MAX_FILE_SIZE_BYTES:,} bytes). "
                f"Please reduce the file size and try again."
            )
        return None

    def _process_direct(self, text: str, start_time: float) -> ProcessingResult:
        """Process a small document via direct single invocation.

        Args:
            text: The document text (≤ agent_input_limit).
            start_time: The processing start timestamp.

        Returns:
            ProcessingResult with was_chunked=False and the agent response.
        """
        response = self._agent_invoker(text)
        elapsed = time.time() - start_time

        report = response if response is not None else ""

        result = ProcessingResult(
            report=report,
            was_chunked=False,
            total_chunks=0,
            successful_chunks=0,
            failed_chunks=0,
            processing_time_seconds=elapsed,
        )

        if self._progress_callback is not None:
            self._progress_callback.on_complete(result)

        return result

    def _process_chunked(self, text: str, start_time: float) -> ProcessingResult:
        """Process a large document through the chunked pipeline.

        Steps:
        1. Chunk the document with ChunkingEngine
        2. Process each chunk sequentially with ContextManager
        3. Synthesize results with SynthesisEngine
        4. Return ProcessingResult

        Args:
            text: The document text (> agent_input_limit).
            start_time: The processing start timestamp.

        Returns:
            ProcessingResult with was_chunked=True and the synthesis report.
        """
        # Step 1: Chunk the document
        chunking_engine = ChunkingEngine(self._config)
        chunks = chunking_engine.chunk_document(text)
        total_chunks = len(chunks)

        # Step 2: Process each chunk sequentially
        context_manager = ContextManager(self._config)
        chunk_analyses: dict[int, ChunkAnalysis] = {}
        failed_chunks: list[FailedChunk] = []
        preceding_summary = ""

        for chunk in chunks:
            # Build context window for this chunk
            if chunk.position == 1:
                context_window = ""
            else:
                context_window = context_manager.build_context_window(
                    chunk_position=chunk.position,
                    total_chunks=total_chunks,
                    preceding_summary=preceding_summary,
                    current_chunk_text=chunk.text,
                )

            # Prepare input: context window + chunk text
            if context_window:
                input_text = context_window + "\n\n" + chunk.text
            else:
                input_text = chunk.text

            # Invoke agent with retry
            response = self._invoke_with_retry(input_text, chunk.position)

            if response is not None:
                # Successful analysis
                # Generate a summary from the response (first 500 chars as summary)
                summary = response[:500] if len(response) > 500 else response

                analysis = ChunkAnalysis(
                    chunk_position=chunk.position,
                    analysis_text=response,
                    summary=summary,
                )
                chunk_analyses[chunk.position] = analysis

                # Update context manager
                if chunk.position == 1:
                    context_manager.initialize_from_first_chunk(response)
                else:
                    context_manager.update_from_analysis(chunk.position, response)

                # Store preceding summary for next chunk
                context_manager.store_preceding_summary(chunk.position, summary)
                preceding_summary = summary
            else:
                # Failed chunk
                failed_chunk = FailedChunk(
                    chunk_position=chunk.position,
                    section_heading=chunk.section_heading,
                    error_category="agent_error",
                    error_message=f"Chunk {chunk.position} failed after exhausting retry attempts.",
                )
                failed_chunks.append(failed_chunk)

                # Notify progress callback of failure
                if self._progress_callback is not None:
                    self._progress_callback.on_chunk_failed(
                        chunk.position, chunk.section_heading
                    )

            # Notify progress callback of chunk completion
            elapsed = time.time() - start_time
            if self._progress_callback is not None:
                self._progress_callback.on_chunk_complete(
                    chunk.position, total_chunks, elapsed
                )

        # Step 3: Synthesis
        if self._progress_callback is not None:
            self._progress_callback.on_synthesis_start()

        synthesis_engine = SynthesisEngine(self._agent_invoker)
        report = synthesis_engine.synthesize(chunk_analyses, failed_chunks)

        elapsed = time.time() - start_time

        result = ProcessingResult(
            report=report,
            was_chunked=True,
            total_chunks=total_chunks,
            successful_chunks=len(chunk_analyses),
            failed_chunks=len(failed_chunks),
            processing_time_seconds=elapsed,
        )

        if self._progress_callback is not None:
            self._progress_callback.on_complete(result)

        return result

    def _invoke_with_retry(
        self, input_text: str, chunk_position: int
    ) -> str | None:
        """Invoke agent with exponential backoff retry for transient errors.

        Retry strategy:
        - Initial backoff: 10 seconds
        - Doubles per attempt: 10s, 20s, 40s
        - Max 3 retry attempts
        - Retryable errors (throttling, model timeouts, dependency failures) trigger retries
        - Non-retryable errors cause immediate failure

        Args:
            input_text: The prompt text to send to the agent.
            chunk_position: 1-based position of the chunk (for error recording).

        Returns:
            The agent response string on success, None on exhausted retries
            or non-retryable failure.
        """
        max_retries = self._config.max_retries
        backoff = self._config.initial_backoff_seconds

        for attempt in range(max_retries):
            try:
                response = self._agent_invoker(input_text)
                if response is not None:
                    return response
                # None response treated as a non-throttling failure
                return None
            except Exception as e:
                error_message = str(e)
                if self._is_retryable_error(error_message):
                    # Retryable error - retry with backoff
                    if attempt < max_retries - 1:
                        time.sleep(backoff)
                        backoff *= 2
                    # If last attempt, fall through to return None
                else:
                    # Non-retryable error - skip immediately
                    return None

        return None

    def _is_retryable_error(self, error_message: str) -> bool:
        """Determine if an error message indicates a retryable error.

        Retryable errors include throttling, model timeouts, and transient
        dependency failures (common with EU cross-region inference).

        Args:
            error_message: The exception message string.

        Returns:
            True if the error is retryable, False otherwise.
        """
        lower_msg = error_message.lower()
        retryable_patterns = [
            "throttling",
            "throttlingexception",
            "dependencyfailedexception",
            "model timeout",
            "timeout",
            "try the request again",
            "service unavailable",
            "internal server error",
        ]
        return any(pattern in lower_msg for pattern in retryable_patterns)

    def _estimate_remaining_time(
        self, elapsed: float, completed: int, total: int
    ) -> float:
        """Estimate remaining processing time based on average time per chunk.

        Args:
            elapsed: Total elapsed time in seconds since processing started.
            completed: Number of chunks completed so far.
            total: Total number of chunks to process.

        Returns:
            Estimated remaining time in seconds. Returns 0.0 if completed is 0
            or all chunks are done.
        """
        if completed <= 0 or completed >= total:
            return 0.0

        avg_time_per_chunk = elapsed / completed
        remaining_chunks = total - completed
        return avg_time_per_chunk * remaining_chunks

    @staticmethod
    def format_elapsed_time(seconds: float) -> str:
        """Format elapsed time as a human-readable string.

        Args:
            seconds: Non-negative elapsed time in seconds.

        Returns:
            "MM:SS" for values < 3600, "HH:MM:SS" for values ≥ 3600.
            All components are zero-padded to 2 digits.
        """
        total_seconds = int(seconds)

        if total_seconds < 3600:
            minutes = total_seconds // 60
            secs = total_seconds % 60
            return f"{minutes:02d}:{secs:02d}"
        else:
            hours = total_seconds // 3600
            remaining = total_seconds % 3600
            minutes = remaining // 60
            secs = remaining % 60
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
