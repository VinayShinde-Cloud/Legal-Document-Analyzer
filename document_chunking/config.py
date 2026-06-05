"""Configuration module for document chunking parameters."""

import os
from dataclasses import dataclass


@dataclass
class ChunkConfig:
    """Configuration for document chunking parameters.

    All parameters have sensible defaults and can be overridden via
    environment variables or Streamlit sidebar controls.
    """

    max_chunk_size: int = 8000
    min_chunk_size: int = 500
    context_window_size: int = 1500
    chunk_overlap: int = 200
    agent_input_limit: int = 10000
    max_retries: int = 3
    initial_backoff_seconds: int = 10
    invocation_timeout_seconds: int = 60

    def validate(self) -> list[str]:
        """Validate configuration parameters against defined ranges.

        Returns a list of error messages. An empty list means the
        configuration is valid.

        Parameter ranges:
            - max_chunk_size: [1000, 50000]
            - min_chunk_size: [100, 5000]
            - context_window_size: [200, 5000]
            - chunk_overlap: [0, 2000]

        Cross-parameter constraints:
            - min_chunk_size must be less than max_chunk_size
            - chunk_overlap must be less than min_chunk_size
        """
        errors: list[str] = []

        # Individual parameter range checks
        if not (1000 <= self.max_chunk_size <= 50000):
            errors.append(
                f"max_chunk_size must be between 1000 and 50000, got {self.max_chunk_size}"
            )

        if not (100 <= self.min_chunk_size <= 5000):
            errors.append(
                f"min_chunk_size must be between 100 and 5000, got {self.min_chunk_size}"
            )

        if not (200 <= self.context_window_size <= 5000):
            errors.append(
                f"context_window_size must be between 200 and 5000, got {self.context_window_size}"
            )

        if not (0 <= self.chunk_overlap <= 2000):
            errors.append(
                f"chunk_overlap must be between 0 and 2000, got {self.chunk_overlap}"
            )

        # Cross-parameter constraint checks
        if self.min_chunk_size >= self.max_chunk_size:
            errors.append(
                f"min_chunk_size ({self.min_chunk_size}) must be less than "
                f"max_chunk_size ({self.max_chunk_size})"
            )

        if self.chunk_overlap >= self.min_chunk_size:
            errors.append(
                f"chunk_overlap ({self.chunk_overlap}) must be less than "
                f"min_chunk_size ({self.min_chunk_size})"
            )

        return errors


def load_config_from_env() -> ChunkConfig:
    """Load chunk configuration from environment variables with defaults.

    Environment variables:
        - CHUNK_MAX_SIZE: Maximum chunk size in characters
        - CHUNK_MIN_SIZE: Minimum chunk size in characters
        - CHUNK_CONTEXT_WINDOW: Context window size in characters
        - CHUNK_OVERLAP: Overlap size in characters

    Returns a ChunkConfig instance. If an environment variable is set but
    cannot be parsed as an integer, the default value is used for that
    parameter.
    """
    defaults = ChunkConfig()

    max_chunk_size = _parse_env_int("CHUNK_MAX_SIZE", defaults.max_chunk_size)
    min_chunk_size = _parse_env_int("CHUNK_MIN_SIZE", defaults.min_chunk_size)
    context_window_size = _parse_env_int("CHUNK_CONTEXT_WINDOW", defaults.context_window_size)
    chunk_overlap = _parse_env_int("CHUNK_OVERLAP", defaults.chunk_overlap)

    return ChunkConfig(
        max_chunk_size=max_chunk_size,
        min_chunk_size=min_chunk_size,
        context_window_size=context_window_size,
        chunk_overlap=chunk_overlap,
    )


def _parse_env_int(var_name: str, default: int) -> int:
    """Parse an environment variable as an integer, returning default on failure."""
    value = os.environ.get(var_name)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
