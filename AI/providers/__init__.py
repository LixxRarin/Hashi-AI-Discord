"""
AI Providers Module

Individual AI provider implementations.
Importing this module triggers auto-registration of all providers.
"""

# Import all providers to trigger auto-registration
from AI.providers.openai import OpenAIClient
from AI.providers.claude import ClaudeClient
from AI.providers.deepseek import DeepSeekClient
from AI.providers.ollama import OllamaClient
from AI.providers.gemini import GeminiClient

__all__ = [
    'OpenAIClient',
    'ClaudeClient',
    'DeepSeekClient',
    'OllamaClient',
    'GeminiClient',
]
