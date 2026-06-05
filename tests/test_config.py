"""Unit tests for document_chunking.config module."""

import os
from unittest.mock import patch

import pytest

from document_chunking.config import ChunkConfig, load_config_from_env


class TestChunkConfigDefaults:
    """Test that ChunkConfig has the correct default values."""

    def test_default_values(self):
        config = ChunkConfig()
        assert config.max_chunk_size == 8000
        assert config.min_chunk_size == 500
        assert config.context_window_size == 1500
        assert config.chunk_overlap == 200
        assert config.agent_input_limit == 10000
        assert config.max_retries == 3
        assert config.initial_backoff_seconds == 10
        assert config.invocation_timeout_seconds == 60

    def test_default_config_is_valid(self):
        config = ChunkConfig()
        errors = config.validate()
        assert errors == []


class TestChunkConfigValidation:
    """Test validate() method for parameter range checks."""

    def test_valid_config(self):
        config = ChunkConfig(
            max_chunk_size=10000,
            min_chunk_size=1000,
            context_window_size=2000,
            chunk_overlap=100,
        )
        assert config.validate() == []

    # max_chunk_size range [1000, 50000]
    def test_max_chunk_size_below_range(self):
        config = ChunkConfig(max_chunk_size=999)
        errors = config.validate()
        assert any("max_chunk_size" in e and "1000" in e for e in errors)

    def test_max_chunk_size_above_range(self):
        config = ChunkConfig(max_chunk_size=50001)
        errors = config.validate()
        assert any("max_chunk_size" in e and "50000" in e for e in errors)

    def test_max_chunk_size_at_lower_bound(self):
        config = ChunkConfig(max_chunk_size=1000, min_chunk_size=100, chunk_overlap=0)
        errors = config.validate()
        assert not any("max_chunk_size" in e for e in errors)

    def test_max_chunk_size_at_upper_bound(self):
        config = ChunkConfig(max_chunk_size=50000)
        errors = config.validate()
        assert not any("max_chunk_size" in e for e in errors)

    # min_chunk_size range [100, 5000]
    def test_min_chunk_size_below_range(self):
        config = ChunkConfig(min_chunk_size=99)
        errors = config.validate()
        assert any("min_chunk_size" in e and "100" in e for e in errors)

    def test_min_chunk_size_above_range(self):
        config = ChunkConfig(min_chunk_size=5001)
        errors = config.validate()
        assert any("min_chunk_size" in e and "5000" in e for e in errors)

    def test_min_chunk_size_at_lower_bound(self):
        config = ChunkConfig(min_chunk_size=100, chunk_overlap=0)
        errors = config.validate()
        assert not any("min_chunk_size must be between" in e for e in errors)

    def test_min_chunk_size_at_upper_bound(self):
        config = ChunkConfig(min_chunk_size=5000, max_chunk_size=10000, chunk_overlap=200)
        errors = config.validate()
        assert not any("min_chunk_size must be between" in e for e in errors)

    # context_window_size range [200, 5000]
    def test_context_window_size_below_range(self):
        config = ChunkConfig(context_window_size=199)
        errors = config.validate()
        assert any("context_window_size" in e and "200" in e for e in errors)

    def test_context_window_size_above_range(self):
        config = ChunkConfig(context_window_size=5001)
        errors = config.validate()
        assert any("context_window_size" in e and "5000" in e for e in errors)

    def test_context_window_size_at_lower_bound(self):
        config = ChunkConfig(context_window_size=200)
        errors = config.validate()
        assert not any("context_window_size" in e for e in errors)

    def test_context_window_size_at_upper_bound(self):
        config = ChunkConfig(context_window_size=5000)
        errors = config.validate()
        assert not any("context_window_size" in e for e in errors)

    # chunk_overlap range [0, 2000]
    def test_chunk_overlap_below_range(self):
        config = ChunkConfig(chunk_overlap=-1)
        errors = config.validate()
        assert any("chunk_overlap" in e and "0" in e for e in errors)

    def test_chunk_overlap_above_range(self):
        config = ChunkConfig(chunk_overlap=2001)
        errors = config.validate()
        assert any("chunk_overlap" in e and "2000" in e for e in errors)

    def test_chunk_overlap_at_lower_bound(self):
        config = ChunkConfig(chunk_overlap=0)
        errors = config.validate()
        assert not any("chunk_overlap must be between" in e for e in errors)

    def test_chunk_overlap_at_upper_bound(self):
        config = ChunkConfig(chunk_overlap=2000, min_chunk_size=5000, max_chunk_size=10000)
        errors = config.validate()
        assert not any("chunk_overlap must be between" in e for e in errors)


class TestCrossParameterConstraints:
    """Test cross-parameter constraint checks."""

    def test_min_equals_max_rejected(self):
        config = ChunkConfig(max_chunk_size=5000, min_chunk_size=5000)
        errors = config.validate()
        assert any("min_chunk_size" in e and "less than" in e and "max_chunk_size" in e for e in errors)

    def test_min_greater_than_max_rejected(self):
        config = ChunkConfig(max_chunk_size=3000, min_chunk_size=4000)
        errors = config.validate()
        assert any("min_chunk_size" in e and "less than" in e and "max_chunk_size" in e for e in errors)

    def test_overlap_equals_min_rejected(self):
        config = ChunkConfig(min_chunk_size=500, chunk_overlap=500)
        errors = config.validate()
        assert any("chunk_overlap" in e and "less than" in e and "min_chunk_size" in e for e in errors)

    def test_overlap_greater_than_min_rejected(self):
        config = ChunkConfig(min_chunk_size=500, chunk_overlap=600)
        errors = config.validate()
        assert any("chunk_overlap" in e and "less than" in e and "min_chunk_size" in e for e in errors)

    def test_multiple_errors_reported(self):
        config = ChunkConfig(
            max_chunk_size=100,  # below range
            min_chunk_size=50000,  # above range
            context_window_size=1,  # below range
            chunk_overlap=3000,  # above range
        )
        errors = config.validate()
        assert len(errors) >= 4


class TestLoadConfigFromEnv:
    """Test loading configuration from environment variables."""

    def test_defaults_when_no_env_vars(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_config_from_env()
            assert config.max_chunk_size == 8000
            assert config.min_chunk_size == 500
            assert config.context_window_size == 1500
            assert config.chunk_overlap == 200

    def test_loads_from_env_vars(self):
        env = {
            "CHUNK_MAX_SIZE": "12000",
            "CHUNK_MIN_SIZE": "800",
            "CHUNK_CONTEXT_WINDOW": "2000",
            "CHUNK_OVERLAP": "300",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config_from_env()
            assert config.max_chunk_size == 12000
            assert config.min_chunk_size == 800
            assert config.context_window_size == 2000
            assert config.chunk_overlap == 300

    def test_partial_env_vars(self):
        env = {"CHUNK_MAX_SIZE": "15000"}
        with patch.dict(os.environ, env, clear=True):
            config = load_config_from_env()
            assert config.max_chunk_size == 15000
            assert config.min_chunk_size == 500  # default
            assert config.context_window_size == 1500  # default
            assert config.chunk_overlap == 200  # default

    def test_invalid_env_var_uses_default(self):
        env = {"CHUNK_MAX_SIZE": "not_a_number"}
        with patch.dict(os.environ, env, clear=True):
            config = load_config_from_env()
            assert config.max_chunk_size == 8000  # default

    def test_empty_string_env_var_uses_default(self):
        env = {"CHUNK_MAX_SIZE": ""}
        with patch.dict(os.environ, env, clear=True):
            config = load_config_from_env()
            assert config.max_chunk_size == 8000  # default
