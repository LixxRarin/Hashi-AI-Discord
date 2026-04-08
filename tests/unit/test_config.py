"""
Unit tests for provider configuration manager.
"""

import pytest
from unittest.mock import patch, MagicMock
from AI.core.config import ProviderConfigManager, get_config_manager


class TestProviderConfigManager:
    """Test cases for ProviderConfigManager."""

    def test_initialization(self):
        """Test config manager initialization."""
        manager = ProviderConfigManager()
        assert manager._config_cache == {}
        assert manager._cache_ttl == 300

    @patch('AI.core.config.func.get_api_connection')
    def test_get_provider_config(self, mock_get_connection):
        """Test getting provider configuration."""
        mock_get_connection.return_value = {
            "api_key": "test_key",
            "model": "gpt-3.5-turbo",
            "max_tokens": 1000
        }

        manager = ProviderConfigManager()
        config = manager.get_provider_config("openai", "server123", "test_conn")

        assert config["api_key"] == "test_key"
        assert config["model"] == "gpt-3.5-turbo"
        assert config["max_tokens"] == 1000
        mock_get_connection.assert_called_once_with("server123", "test_conn")

    @patch('AI.core.config.func.get_api_connection')
    def test_config_caching(self, mock_get_connection):
        """Test that configuration is cached."""
        mock_get_connection.return_value = {"api_key": "test_key"}

        manager = ProviderConfigManager()

        # First call
        config1 = manager.get_provider_config("openai", "server123", "test_conn")
        # Second call (should use cache)
        config2 = manager.get_provider_config("openai", "server123", "test_conn")

        # Should only call the function once due to caching
        assert mock_get_connection.call_count == 1
        assert config1 == config2

    @patch('AI.core.config.func.get_api_connection')
    def test_get_api_key(self, mock_get_connection):
        """Test getting API key from configuration."""
        mock_get_connection.return_value = {"api_key": "secret_key_123"}

        manager = ProviderConfigManager()
        api_key = manager.get_api_key("openai", "server123", "test_conn")

        assert api_key == "secret_key_123"

    @patch('AI.core.config.func.get_api_connection')
    def test_get_model(self, mock_get_connection):
        """Test getting model from configuration."""
        mock_get_connection.return_value = {"model": "gpt-4"}

        manager = ProviderConfigManager()
        model = manager.get_model("openai", "server123", "test_conn", "default-model")

        assert model == "gpt-4"

    @patch('AI.core.config.func.get_api_connection')
    def test_get_model_default(self, mock_get_connection):
        """Test getting model with default fallback."""
        mock_get_connection.return_value = {}

        manager = ProviderConfigManager()
        model = manager.get_model("openai", "server123", "test_conn", "default-model")

        assert model == "default-model"

    @patch('AI.core.config.func.get_api_connection')
    def test_get_base_url(self, mock_get_connection):
        """Test getting base URL from configuration."""
        mock_get_connection.return_value = {"base_url": "https://api.example.com"}

        manager = ProviderConfigManager()
        base_url = manager.get_base_url("openai", "server123", "test_conn")

        assert base_url == "https://api.example.com"

    @patch('AI.core.config.func.get_api_connection')
    def test_get_llm_params(self, mock_get_connection):
        """Test getting LLM parameters from configuration."""
        mock_get_connection.return_value = {
            "max_tokens": 2000,
            "temperature": 0.8,
            "top_p": 0.9,
            "think_switch": True,
            "think_depth": 5
        }

        manager = ProviderConfigManager()
        params = manager.get_llm_params("openai", "server123", "test_conn")

        assert params["max_tokens"] == 2000
        assert params["temperature"] == 0.8
        assert params["top_p"] == 0.9
        assert params["think_switch"] is True
        assert params["think_depth"] == 5

    @patch('AI.core.config.func.get_api_connection')
    def test_get_llm_params_defaults(self, mock_get_connection):
        """Test LLM parameters with default values."""
        mock_get_connection.return_value = {}

        manager = ProviderConfigManager()
        params = manager.get_llm_params("openai", "server123", "test_conn")

        assert params["max_tokens"] == 1000
        assert params["temperature"] == 0.7
        assert params["top_p"] == 1.0
        assert params["frequency_penalty"] == 0.0
        assert params["presence_penalty"] == 0.0
        assert params["think_switch"] is False

    def test_invalidate_cache_all(self):
        """Test invalidating entire cache."""
        manager = ProviderConfigManager()
        manager._config_cache = {
            "key1": ({"data": "value1"}, 123.0),
            "key2": ({"data": "value2"}, 456.0)
        }

        manager.invalidate_cache()

        assert len(manager._config_cache) == 0

    def test_invalidate_cache_server(self):
        """Test invalidating cache for specific server."""
        manager = ProviderConfigManager()
        manager._config_cache = {
            "abc123:server1:conn": ({"data": "value1"}, 123.0),
            "def456:server2:conn": ({"data": "value2"}, 456.0),
            "ghi789:server1:other": ({"data": "value3"}, 789.0)
        }

        manager.invalidate_cache("server1")

        # Should only remove server1 entries
        assert "def456:server2:conn" in manager._config_cache
        assert "abc123:server1:conn" not in manager._config_cache
        assert "ghi789:server1:other" not in manager._config_cache

    def test_validate_config_valid(self):
        """Test validating a valid configuration."""
        manager = ProviderConfigManager()
        config = {
            "api_key": "test_key",
            "model": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7
        }

        is_valid, error = manager.validate_config("openai", config)

        assert is_valid is True
        assert error is None

    def test_validate_config_missing_api_key(self):
        """Test validation fails without API key."""
        manager = ProviderConfigManager()
        config = {"model": "gpt-3.5-turbo"}

        is_valid, error = manager.validate_config("openai", config)

        assert is_valid is False
        assert "API key is required" in error

    def test_validate_config_ollama_no_key(self):
        """Test Ollama doesn't require API key."""
        manager = ProviderConfigManager()
        config = {"model": "llama3"}

        is_valid, error = manager.validate_config("ollama", config)

        assert is_valid is True
        assert error is None

    def test_validate_config_missing_model(self):
        """Test validation fails without model."""
        manager = ProviderConfigManager()
        config = {"api_key": "test_key"}

        is_valid, error = manager.validate_config("openai", config)

        assert is_valid is False
        assert "Model name is required" in error

    def test_validate_config_invalid_numeric(self):
        """Test validation fails with invalid numeric parameter."""
        manager = ProviderConfigManager()
        config = {
            "api_key": "test_key",
            "model": "gpt-3.5-turbo",
            "temperature": "not_a_number"
        }

        is_valid, error = manager.validate_config("openai", config)

        assert is_valid is False
        assert "temperature" in error
        assert "must be a number" in error


class TestGlobalConfigManager:
    """Test cases for global config manager functions."""

    def test_get_config_manager_singleton(self):
        """Test that get_config_manager returns the same instance."""
        manager1 = get_config_manager()
        manager2 = get_config_manager()

        assert manager1 is manager2
        assert isinstance(manager1, ProviderConfigManager)
