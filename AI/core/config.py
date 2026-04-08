"""
Configuration Manager for AI Providers

Centralized configuration resolution with caching and validation.
Handles per-server API connections and configuration hierarchy.
"""

import time
import hashlib
from typing import Dict, Any, Optional
import logging

import utils.func as func

log = logging.getLogger(__name__)


class ProviderConfigManager:
    """
    Centralized provider configuration management.

    Handles configuration resolution from api_connections.json with caching
    and validation. Supports per-server API keys via /api_connection command.
    """

    def __init__(self):
        """Initialize the config manager with empty cache."""
        self._config_cache: Dict[str, tuple[Dict[str, Any], float]] = {}
        self._cache_ttl = 300  # 5 minutes cache TTL

    def get_provider_config(
        self,
        provider_name: str,
        server_id: str,
        connection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get configuration for a provider from api_connections.json.

        Args:
            provider_name: Provider name (e.g., "openai", "claude")
            server_id: Discord server ID
            connection_name: Optional API connection name

        Returns:
            Configuration dictionary with resolved values
        """
        cache_key = self._make_cache_key(provider_name, server_id, connection_name)

        # Check cache
        if cache_key in self._config_cache:
            config, timestamp = self._config_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                log.debug(f"Using cached config for {provider_name} (server: {server_id})")
                return config.copy()

        # Resolve configuration
        config = self._resolve_config(provider_name, server_id, connection_name)

        # Cache the result
        self._config_cache[cache_key] = (config.copy(), time.time())

        return config

    def _resolve_config(
        self,
        provider_name: str,
        server_id: str,
        connection_name: Optional[str]
    ) -> Dict[str, Any]:
        """
        Resolve configuration from api_connections.json.

        Args:
            provider_name: Provider name
            server_id: Server ID
            connection_name: API connection name

        Returns:
            Resolved configuration dictionary
        """
        config = {}

        # Get connection if specified
        if connection_name:
            connection = func.get_api_connection(server_id, connection_name)
            if connection:
                config = connection.copy()
                log.debug(f"Loaded config from connection '{connection_name}'")
            else:
                log.warning(
                    f"API connection '{connection_name}' not found for server {server_id}"
                )

        return config

    def get_api_key(
        self,
        provider_name: str,
        server_id: str,
        connection_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Get API key from server-specific configuration.

        Args:
            provider_name: Provider name
            server_id: Server ID
            connection_name: API connection name

        Returns:
            API key or None if not found
        """
        config = self.get_provider_config(provider_name, server_id, connection_name)
        return config.get("api_key")

    def get_model(
        self,
        provider_name: str,
        server_id: str,
        connection_name: Optional[str] = None,
        default_model: str = "unknown"
    ) -> str:
        """
        Get model name from configuration.

        Args:
            provider_name: Provider name
            server_id: Server ID
            connection_name: API connection name
            default_model: Default model if not configured

        Returns:
            Model name
        """
        config = self.get_provider_config(provider_name, server_id, connection_name)
        return config.get("model", default_model)

    def get_base_url(
        self,
        provider_name: str,
        server_id: str,
        connection_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Get base URL from configuration.

        Args:
            provider_name: Provider name
            server_id: Server ID
            connection_name: API connection name

        Returns:
            Base URL or None if not configured
        """
        config = self.get_provider_config(provider_name, server_id, connection_name)
        return config.get("base_url")

    def get_llm_params(
        self,
        provider_name: str,
        server_id: str,
        connection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get LLM parameters from configuration.

        Args:
            provider_name: Provider name
            server_id: Server ID
            connection_name: API connection name

        Returns:
            Dictionary of LLM parameters
        """
        config = self.get_provider_config(provider_name, server_id, connection_name)

        # Extract LLM parameters
        llm_params = {
            "max_tokens": config.get("max_tokens", 1000),
            "temperature": config.get("temperature", 0.7),
            "top_p": config.get("top_p", 1.0),
            "frequency_penalty": config.get("frequency_penalty", 0.0),
            "presence_penalty": config.get("presence_penalty", 0.0),
            "think_switch": config.get("think_switch", False),
            "think_depth": config.get("think_depth", 3),
            "hide_thinking_tags": config.get("hide_thinking_tags", True),
            "save_thinking_in_history": config.get("save_thinking_in_history", True),
            "custom_extra_body": config.get("custom_extra_body"),
        }

        return llm_params

    def invalidate_cache(self, server_id: Optional[str] = None):
        """
        Invalidate configuration cache.

        Call this when /api_connection updates configuration.

        Args:
            server_id: Optional server ID to invalidate only that server's cache.
                      If None, invalidates entire cache.
        """
        if server_id is None:
            # Invalidate entire cache
            self._config_cache.clear()
            log.info("Invalidated entire config cache")
        else:
            # Invalidate only entries for this server
            keys_to_remove = [
                key for key in self._config_cache.keys()
                if server_id in key
            ]
            for key in keys_to_remove:
                del self._config_cache[key]
            log.info(f"Invalidated config cache for server {server_id}")

    def _make_cache_key(
        self,
        provider_name: str,
        server_id: str,
        connection_name: Optional[str]
    ) -> str:
        """
        Create a cache key for configuration.

        Args:
            provider_name: Provider name
            server_id: Server ID
            connection_name: API connection name

        Returns:
            Cache key string
        """
        key_parts = [provider_name, server_id, connection_name or ""]
        key_string = ":".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def validate_config(
        self,
        provider_name: str,
        config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate provider configuration.

        Args:
            provider_name: Provider name
            config: Configuration dictionary

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for required API key (except for Ollama which is local)
        if provider_name.lower() != "ollama":
            if not config.get("api_key"):
                return False, f"API key is required for {provider_name}"

        # Validate model is specified
        if not config.get("model"):
            return False, "Model name is required"

        # Validate numeric parameters
        numeric_params = ["max_tokens", "temperature", "top_p", "frequency_penalty", "presence_penalty"]
        for param in numeric_params:
            if param in config:
                try:
                    float(config[param])
                except (ValueError, TypeError):
                    return False, f"Parameter '{param}' must be a number"

        return True, None


# Global instance
_config_manager = ProviderConfigManager()


def get_config_manager() -> ProviderConfigManager:
    """
    Get the global configuration manager instance.

    Returns:
        Global ProviderConfigManager instance
    """
    return _config_manager
