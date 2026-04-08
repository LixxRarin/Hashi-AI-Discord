"""
AI Core Module

Core abstractions and registry for AI providers.
"""

from AI.core.base_client import BaseAIClient
from AI.core.registry import (
    ProviderRegistry,
    ProviderMetadata,
    register_provider,
    get_registry
)

__all__ = [
    'BaseAIClient',
    'ProviderRegistry',
    'ProviderMetadata',
    'register_provider',
    'get_registry',
]
