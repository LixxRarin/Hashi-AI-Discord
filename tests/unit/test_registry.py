"""
Unit tests for AI provider registry.
"""

import pytest
from AI.core.registry import (
    ProviderRegistry,
    ProviderMetadata,
    register_provider,
    get_registry
)
from AI.core.base_client import BaseAIClient


class MockAIClient(BaseAIClient):
    """Mock AI client for testing."""

    provider_name = "mock"

    def create_client(self, session, server_id=None):
        return None

    async def generate_response(self, messages, session, server_id, tools=None, tool_context=None, **kwargs):
        return "Mock response"

    def count_tokens(self, text, model):
        return len(text.split())

    async def get_bot_info(self, session, server_id=None):
        return {"name": "mock", "title": "Mock Bot"}


class TestProviderRegistry:
    """Test cases for ProviderRegistry."""

    def test_registry_initialization(self):
        """Test that registry initializes correctly."""
        registry = ProviderRegistry()
        assert registry.get_provider_count() == 0
        assert registry.list_providers() == []

    def test_register_provider(self):
        """Test registering a new provider."""
        registry = ProviderRegistry()
        metadata = ProviderMetadata(
            name="test",
            display_name="Test Provider",
            color="blue",
            icon="🔵",
            default_model="test-model",
            supports_thinking=False,
            description="Test provider"
        )

        registry.register("test", MockAIClient, metadata)

        assert registry.get_provider_count() == 1
        assert "test" in registry.list_providers()
        assert registry.is_registered("test")

    def test_get_client(self):
        """Test getting a client instance."""
        registry = ProviderRegistry()
        metadata = ProviderMetadata(
            name="test",
            display_name="Test Provider",
            color="blue",
            icon="🔵",
            default_model="test-model"
        )

        registry.register("test", MockAIClient, metadata)
        client = registry.get_client("test")

        assert isinstance(client, MockAIClient)
        assert client.provider_name == "mock"

    def test_get_client_singleton(self):
        """Test that get_client returns the same instance."""
        registry = ProviderRegistry()
        metadata = ProviderMetadata(
            name="test",
            display_name="Test Provider",
            color="blue",
            icon="🔵",
            default_model="test-model"
        )

        registry.register("test", MockAIClient, metadata)
        client1 = registry.get_client("test")
        client2 = registry.get_client("test")

        assert client1 is client2

    def test_get_client_not_registered(self):
        """Test getting a client that doesn't exist."""
        registry = ProviderRegistry()

        with pytest.raises(ValueError, match="Provider 'nonexistent' not registered"):
            registry.get_client("nonexistent")

    def test_get_metadata(self):
        """Test getting provider metadata."""
        registry = ProviderRegistry()
        metadata = ProviderMetadata(
            name="test",
            display_name="Test Provider",
            color="blue",
            icon="🔵",
            default_model="test-model",
            supports_thinking=True,
            description="Test provider"
        )

        registry.register("test", MockAIClient, metadata)
        retrieved_metadata = registry.get_metadata("test")

        assert retrieved_metadata.name == "test"
        assert retrieved_metadata.display_name == "Test Provider"
        assert retrieved_metadata.supports_thinking is True

    def test_list_providers(self):
        """Test listing all providers."""
        registry = ProviderRegistry()

        for name in ["provider1", "provider2", "provider3"]:
            metadata = ProviderMetadata(
                name=name,
                display_name=name.title(),
                color="blue",
                icon="🔵",
                default_model="model"
            )
            registry.register(name, MockAIClient, metadata)

        providers = registry.list_providers()
        assert len(providers) == 3
        assert "provider1" in providers
        assert "provider2" in providers
        assert "provider3" in providers

    def test_get_all_metadata(self):
        """Test getting all provider metadata."""
        registry = ProviderRegistry()

        for name in ["provider1", "provider2"]:
            metadata = ProviderMetadata(
                name=name,
                display_name=name.title(),
                color="blue",
                icon="🔵",
                default_model="model"
            )
            registry.register(name, MockAIClient, metadata)

        all_metadata = registry.get_all_metadata()
        assert len(all_metadata) == 2
        assert "provider1" in all_metadata
        assert "provider2" in all_metadata

    def test_case_insensitive_names(self):
        """Test that provider names are case-insensitive."""
        registry = ProviderRegistry()
        metadata = ProviderMetadata(
            name="TestProvider",
            display_name="Test Provider",
            color="blue",
            icon="🔵",
            default_model="model"
        )

        registry.register("TestProvider", MockAIClient, metadata)

        assert registry.is_registered("testprovider")
        assert registry.is_registered("TESTPROVIDER")
        assert registry.is_registered("TestProvider")

        client = registry.get_client("TESTPROVIDER")
        assert isinstance(client, MockAIClient)


class TestProviderMetadata:
    """Test cases for ProviderMetadata."""

    def test_metadata_initialization(self):
        """Test metadata initialization."""
        metadata = ProviderMetadata(
            name="test",
            display_name="Test Provider",
            color="green",
            icon="🟢",
            default_model="test-model",
            supports_thinking=True,
            description="A test provider"
        )

        assert metadata.name == "test"
        assert metadata.display_name == "Test Provider"
        assert metadata.color == "green"
        assert metadata.icon == "🟢"
        assert metadata.default_model == "test-model"
        assert metadata.supports_thinking is True
        assert metadata.description == "A test provider"

    def test_metadata_repr(self):
        """Test metadata string representation."""
        metadata = ProviderMetadata(
            name="test",
            display_name="Test Provider",
            color="blue",
            icon="🔵",
            default_model="model"
        )

        repr_str = repr(metadata)
        assert "test" in repr_str
        assert "Test Provider" in repr_str


class TestGlobalRegistry:
    """Test cases for global registry functions."""

    def test_get_registry_singleton(self):
        """Test that get_registry returns the same instance."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2
