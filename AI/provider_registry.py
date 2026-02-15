"""
Provider Registry - AI Provider Registration System

This module provides a centralized registry for all AI providers.
Allows adding new providers without modifying existing code.

Classes:
    - ProviderMetadata: Metadata for a provider
    - ProviderRegistry: Centralized provider registry

Functions:
    - register_provider(): Registers a new provider
    - get_registry(): Gets the global registry instance
"""

from typing import Dict, Any, Type, Optional, List
import logging

log = logging.getLogger(__name__)


class ProviderMetadata:
    """
    Metadata for an AI provider.
    
    Stores display and configuration information for a provider.
    """
    
    def __init__(
        self,
        name: str,
        display_name: str,
        color: str,
        icon: str,
        default_model: str,
        supports_thinking: bool = False,
        description: str = ""
    ):
        """
        Initializes the provider metadata.
        
        Args:
            name: Internal provider name (lowercase)
            display_name: Display name
            color: Color for Discord ("green", "blue", "red", etc.)
            icon: Emoji icon ("🟢", "🔵", etc.)
            default_model: Default provider model
            supports_thinking: Whether it supports thinking/reasoning
            description: Provider description
        """
        self.name = name.lower()
        self.display_name = display_name
        self.color = color
        self.icon = icon
        self.default_model = default_model
        self.supports_thinking = supports_thinking
        self.description = description
    
    def __repr__(self) -> str:
        return f"ProviderMetadata(name='{self.name}', display_name='{self.display_name}')"


class ProviderRegistry:
    """
    Centralized AI provider registry.
    
    Allows providers to register automatically and provides
    unified access to clients and metadata.
    
    Example:
        >>> registry = get_registry()
        >>> client = registry.get_client("openai")
        >>> metadata = registry.get_metadata("openai")
        >>> print(metadata.display_name)  # "OpenAI"
    """
    
    def __init__(self):
        """Initializes empty registry."""
        self._providers: Dict[str, Dict[str, Any]] = {}
        self._instances: Dict[str, Any] = {}
    
    def register(
        self,
        name: str,
        client_class: Type,
        metadata: ProviderMetadata
    ) -> None:
        """
        Registers a new provider.
        
        Args:
            name: Provider name (e.g., "openai", "deepseek")
            client_class: Client class (e.g., OpenAIClient)
            metadata: Provider metadata
        """
        name_lower = name.lower()
        
        if name_lower in self._providers:
            log.warning(f"Provider '{name}' already registered, overwriting")
        
        self._providers[name_lower] = {
            'client_class': client_class,
            'metadata': metadata
        }
        
        log.info(f"Registered provider: {metadata.display_name} ({name_lower})")
    
    def get_client(self, name: str):
        """
        Gets a client instance for the provider.
        
        Uses instance cache (singleton per provider).
        
        Args:
            name: Provider name
            
        Returns:
            Client instance
            
        Raises:
            ValueError: If the provider is not registered
        """
        name_lower = name.lower()
        
        if name_lower not in self._providers:
            available = ', '.join(self._providers.keys())
            raise ValueError(
                f"Provider '{name}' not registered. "
                f"Available providers: {available}"
            )
        
        # Instance cache (singleton per provider)
        if name_lower not in self._instances:
            client_class = self._providers[name_lower]['client_class']
            self._instances[name_lower] = client_class()
            log.debug(f"Created new instance for provider: {name_lower}")
        
        return self._instances[name_lower]
    
    def get_metadata(self, name: str) -> ProviderMetadata:
        """
        Gets the metadata for a provider.
        
        Args:
            name: Provider name
            
        Returns:
            Provider metadata
            
        Raises:
            ValueError: If the provider is not registered
        """
        name_lower = name.lower()
        
        if name_lower not in self._providers:
            available = ', '.join(self._providers.keys())
            raise ValueError(
                f"Provider '{name}' not registered. "
                f"Available providers: {available}"
            )
        
        return self._providers[name_lower]['metadata']
    
    def list_providers(self) -> List[str]:
        """
        Lists all registered providers.
        
        Returns:
            List of provider names (lowercase)
        """
        return list(self._providers.keys())
    
    def get_all_metadata(self) -> Dict[str, ProviderMetadata]:
        """
        Gets metadata for all providers.
        
        Returns:
            Dictionary {name: metadata}
        """
        return {
            name: data['metadata']
            for name, data in self._providers.items()
        }
    
    def is_registered(self, name: str) -> bool:
        """
        Checks if a provider is registered.
        
        Args:
            name: Provider name
            
        Returns:
            True if registered, False otherwise
        """
        return name.lower() in self._providers
    
    def get_provider_count(self) -> int:
        """
        Returns the number of registered providers.
        
        Returns:
            Number of providers
        """
        return len(self._providers)


_registry = ProviderRegistry()


def register_provider(
    name: str,
    client_class: Type,
    display_name: str,
    color: str = "blue",
    icon: str = "🔵",
    default_model: str = "unknown",
    supports_thinking: bool = False,
    description: str = ""
) -> None:
    """
    Convenience function to register a provider.
    
    This is the main function that clients should use to register.
    
    Args:
        name: Provider name (e.g., "openai")
        client_class: Client class
        display_name: Display name (e.g., "OpenAI")
        color: Color for Discord (e.g., "green", "blue")
        icon: Emoji icon (e.g., "🟢", "🔵")
        default_model: Default model
        supports_thinking: Whether it supports thinking/reasoning
        description: Provider description
        
    Example:
        >>> from AI.provider_registry import register_provider
        >>> from AI.openai_client import OpenAIClient
        >>> 
        >>> register_provider(
        ...     name="openai",
        ...     client_class=OpenAIClient,
        ...     display_name="OpenAI",
        ...     color="green",
        ...     icon="🟢",
        ...     default_model="gpt-3.5-turbo",
        ...     supports_thinking=True
        ... )
    """
    metadata = ProviderMetadata(
        name=name,
        display_name=display_name,
        color=color,
        icon=icon,
        default_model=default_model,
        supports_thinking=supports_thinking,
        description=description
    )
    
    _registry.register(name, client_class, metadata)


def get_registry() -> ProviderRegistry:
    """
    Gets the global registry instance.
    
    Returns:
        Global instance of ProviderRegistry
        
    Example:
        >>> from AI.provider_registry import get_registry
        >>> registry = get_registry()
        >>> client = registry.get_client("openai")
    """
    return _registry
