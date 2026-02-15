"""
AI Module - Provider Registration

This module ensures all AI providers are registered when the AI module is imported.
Simply importing this module will trigger the auto-registration of all providers.

Usage:
    import AI  # All providers are now registered
    
    from AI.provider_registry import get_registry
    registry = get_registry()
    client = registry.get_client("openai")
"""

# Import all clients to trigger their auto-registration
from AI.openai_client import OpenAIClient
from AI.deepseek_client import DeepSeekClient
from AI.ollama_client import OllamaClient
from AI.claude_client import ClaudeClient

# Import registry for convenience
from AI.provider_registry import get_registry, register_provider

# Export commonly used items
__all__ = [
    'OpenAIClient',
    'DeepSeekClient',
    'OllamaClient',
    'ClaudeClient',
    'get_registry',
    'register_provider',
]
