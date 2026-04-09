"""
Data Paths Module - Centralized path resolution for hierarchical data storage.

This module provides a single source of truth for all data file paths
in the new hierarchical structure: data/{server_id}/{channel_id}/
"""

import os


class DataPaths:
    """Centralized data path management for hierarchical storage."""

    def __init__(self, base_dir: str = "data"):
        """
        Initialize DataPaths with a base directory.

        Args:
            base_dir: Base directory for all data files (default: "data")
        """
        self.base_dir = base_dir

    # ==================== Per-Channel Paths ====================

    def get_conversations_file(self, server_id: str, channel_id: str) -> str:
        """
        Get path to conversations file for a specific channel.

        Args:
            server_id: Discord server (guild) ID
            channel_id: Discord channel ID

        Returns:
            Path to conversations.json for this channel
        """
        return f"{self.base_dir}/{server_id}/{channel_id}/conversations.json"

    def get_session_file(self, server_id: str, channel_id: str) -> str:
        """
        Get path to session file for a specific channel.

        Args:
            server_id: Discord server (guild) ID
            channel_id: Discord channel ID

        Returns:
            Path to session.json for this channel
        """
        return f"{self.base_dir}/{server_id}/{channel_id}/session.json"

    def get_memory_dir(self, server_id: str, channel_id: str) -> str:
        """
        Get path to memory directory for a specific channel.

        Args:
            server_id: Discord server (guild) ID
            channel_id: Discord channel ID

        Returns:
            Path to memory directory for this channel
        """
        return f"{self.base_dir}/{server_id}/{channel_id}/memory"

    def get_memory_file(self, server_id: str, channel_id: str,
                       ai_name: str, chat_id: str = "default") -> str:
        """
        Get path to memory file for a specific AI chat.

        Args:
            server_id: Discord server (guild) ID
            channel_id: Discord channel ID
            ai_name: Name of the AI (will be sanitized for filename)
            chat_id: Chat session ID (default: "default")

        Returns:
            Path to memory Markdown file for this AI chat
        """
        memory_dir = self.get_memory_dir(server_id, channel_id)
        # Sanitize ai_name for filename (remove emojis and special chars)
        safe_ai_name = "".join(c for c in ai_name if c.isalnum() or c in "_-")
        return f"{memory_dir}/{safe_ai_name}_{chat_id}.md"

    # ==================== Server-Level Paths ====================

    def get_api_connections_file(self, server_id: str) -> str:
        """
        Get path to API connections file for a server.

        Args:
            server_id: Discord server (guild) ID

        Returns:
            Path to api_connections.json for this server
        """
        return f"{self.base_dir}/{server_id}/api_connections.json"

    def get_character_cards_file(self, server_id: str) -> str:
        """
        Get path to character cards file for a server.

        Args:
            server_id: Discord server (guild) ID

        Returns:
            Path to character_cards.json for this server
        """
        return f"{self.base_dir}/{server_id}/character_cards.json"

    def get_debug_config_file(self, server_id: str) -> str:
        """
        Get path to debug config file for a server.

        Args:
            server_id: Discord server (guild) ID

        Returns:
            Path to debug_config.json for this server
        """
        return f"{self.base_dir}/{server_id}/debug_config.json"

    # ==================== Utility Methods ====================

    def ensure_directory(self, file_path: str) -> None:
        """
        Ensure the parent directory exists for a file path.

        Args:
            file_path: Path to a file (directory will be created for its parent)
        """
        directory = os.path.dirname(file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def get_migration_marker(self) -> str:
        """Get path to migration completion marker file."""
        return f"{self.base_dir}/.migration_complete"

    def list_servers(self) -> list[str]:
        """
        List all server IDs in the data directory.

        Returns:
            List of server ID strings
        """
        if not os.path.exists(self.base_dir):
            return []

        servers = []
        for item in os.listdir(self.base_dir):
            item_path = os.path.join(self.base_dir, item)
            # Skip hidden files/dirs and non-directories
            if item.startswith('.') or not os.path.isdir(item_path):
                continue
            servers.append(item)

        return servers

    def list_channels(self, server_id: str) -> list[str]:
        """
        List all channel IDs for a specific server.

        Args:
            server_id: Discord server (guild) ID

        Returns:
            List of channel ID strings
        """
        server_path = f"{self.base_dir}/{server_id}"
        if not os.path.exists(server_path):
            return []

        channels = []
        for item in os.listdir(server_path):
            item_path = os.path.join(server_path, item)
            # Skip files and non-directories
            if not os.path.isdir(item_path):
                continue
            channels.append(item)

        return channels
