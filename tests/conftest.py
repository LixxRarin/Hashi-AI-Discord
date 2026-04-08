"""
Pytest configuration and fixtures for Hashi AI Discord Bot tests.
"""

import pytest
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def mock_server_id():
    """Mock Discord server ID for testing."""
    return "123456789012345678"


@pytest.fixture
def mock_channel_id():
    """Mock Discord channel ID for testing."""
    return "987654321098765432"


@pytest.fixture
def mock_session():
    """Mock AI session data for testing."""
    return {
        "provider": "openai",
        "api_connection": "test_connection",
        "model": "gpt-3.5-turbo",
        "config": {
            "max_tokens": 1000,
            "temperature": 0.7,
        }
    }


@pytest.fixture
def mock_api_connection():
    """Mock API connection data for testing."""
    return {
        "name": "test_connection",
        "provider": "openai",
        "api_key": "test_api_key_12345",
        "model": "gpt-3.5-turbo",
        "base_url": None,
        "max_tokens": 1000,
        "temperature": 0.7,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    }


@pytest.fixture
def mock_messages():
    """Mock message history for testing."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi! How can I help you today?"},
    ]
