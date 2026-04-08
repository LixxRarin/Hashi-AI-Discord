"""
AI Module - Provider Registration

This module ensures all AI providers are registered when the AI module is imported.
Simply importing this module will trigger the auto-registration of all providers.

Usage:
    import AI  # All providers are now registered

    from AI.core.registry import get_registry
    registry = get_registry()
    client = registry.get_client("openai")
"""

# Import all clients to trigger their auto-registration
from AI.providers.openai import OpenAIClient
from AI.providers.deepseek import DeepSeekClient
from AI.providers.ollama import OllamaClient
from AI.providers.claude import ClaudeClient

# Import registry for convenience
from AI.core.registry import get_registry, register_provider

# Export commonly used items
__all__ = [
    'OpenAIClient',
    'ClaudeClient',
    'DeepSeekClient',
    'OllamaClient',
    'get_registry',
    'register_provider',
]
