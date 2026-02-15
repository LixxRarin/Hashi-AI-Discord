"""
Short ID Manager - Maps Discord IDs to Short IDs

This module provides a mapping system to convert long Discord message IDs
(19 digits) to short IDs (1-3 digits) for token optimization.

Key Features:
- Automatic ID assignment (sequential)
- Bidirectional mapping (short <-> long)
- Per-channel scope
- Thread-safe operations (async locks)
"""

import asyncio
import logging
from typing import Dict, Optional

log = logging.getLogger(__name__)


class ShortIDManager:
    """
    Manages mapping between Discord IDs and short IDs.
    
    Structure:
        server_id -> channel_id -> ai_name -> {
            "discord_to_short": {discord_id: short_id},
            "short_to_discord": {short_id: discord_id},
            "next_id": int
        }
    
    Example:
        manager = ShortIDManager()
        
        short_id = await manager.get_short_id(server_id, channel_id, ai_name, "1470059003554824346")
        # Returns: 1
        
        discord_id = await manager.get_discord_id(server_id, channel_id, ai_name, 1)
        # Returns: "1470059003554824346"
    
    """
    
    def __init__(self):
        """Initialize the short ID manager."""
        self._maps: Dict[str, Dict[str, Dict[str, Dict]]] = {}
        self._lock = asyncio.Lock()

    
    def _ensure_path(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> Dict:
        """Ensure the path exists and return the mapping dict. NOT thread-safe - use within lock."""
        if server_id not in self._maps:
            self._maps[server_id] = {}
        if channel_id not in self._maps[server_id]:
            self._maps[server_id][channel_id] = {}
        if ai_name not in self._maps[server_id][channel_id]:
            self._maps[server_id][channel_id][ai_name] = {
                "discord_to_short": {},
                "short_to_discord": {},
                "next_id": 1
            }
        
        return self._maps[server_id][channel_id][ai_name]
    
    async def get_short_id(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        discord_id: str
    ) -> int:
        """
        Get or create a short ID for a Discord ID.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            discord_id: Discord message ID
            
        Returns:
            Short ID (1, 2, 3, ...)
        """
        async with self._lock:
            mapping = self._ensure_path(server_id, channel_id, ai_name)
            
            # Check if already mapped
            if discord_id in mapping["discord_to_short"]:
                return mapping["discord_to_short"][discord_id]
            
            # Create new mapping
            short_id = mapping["next_id"]
            mapping["discord_to_short"][discord_id] = short_id
            mapping["short_to_discord"][short_id] = discord_id
            mapping["next_id"] += 1

            
            return short_id
    
    async def get_discord_id(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        short_id: int
    ) -> Optional[str]:
        """
        Get Discord ID from short ID.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            short_id: Short ID
            
        Returns:
            Discord message ID or None if not found
        """
        async with self._lock:
            mapping = self._ensure_path(server_id, channel_id, ai_name)
            return mapping["short_to_discord"].get(short_id)
    
    async def get_or_create_short_id(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        discord_id: str
    ) -> int:
        """
        Alias for get_short_id for clarity.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            discord_id: Discord message ID
            
        Returns:
            Short ID
        """
        return await self.get_short_id(server_id, channel_id, ai_name, discord_id)
    
    async def clear_mappings(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> None:
        """
        Clear all mappings for a specific AI.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
        """
        async with self._lock:
            mapping = self._ensure_path(server_id, channel_id, ai_name)
            mapping["discord_to_short"].clear()
            mapping["short_to_discord"].clear()
            mapping["next_id"] = 1
            
            log.info(f"Cleared ID mappings for AI {ai_name} in {server_id}/{channel_id}")
    
    async def remove_mapping(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        discord_id: str
    ) -> bool:
        """
        Remove a specific mapping.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            discord_id: Discord message ID to remove
            
        Returns:
            True if mapping was removed, False if not found
        """
        async with self._lock:
            mapping = self._ensure_path(server_id, channel_id, ai_name)
            
            if discord_id in mapping["discord_to_short"]:
                short_id = mapping["discord_to_short"][discord_id]
                del mapping["discord_to_short"][discord_id]
                del mapping["short_to_discord"][short_id]
                
                log.debug(f"Removed mapping: Discord ID {discord_id} -> Short ID {short_id}")
                
                return True
            
            return False
    
    async def skip_next_id(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> None:
        """
        Skip the next ID (for bot messages).
        
        Bot messages implicitly occupy ID slots but don't get visible IDs.
        This ensures user message IDs skip numbers: #1, #3, #5, etc.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
        """
        async with self._lock:
            mapping = self._ensure_path(server_id, channel_id, ai_name)
            skipped_id = mapping["next_id"]
            mapping["next_id"] += 1
            log.debug(f"Skipped ID {skipped_id} for bot message")
    
    async def assign_and_skip_id(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        discord_id: str
    ) -> int:
        """
        Assign a short ID to a bot message and skip to next ID.
        
        Bot messages implicitly occupy ID slots but don't show IDs.
        This creates a mapping so the bot message can be referenced in replies,
        while still maintaining the skip pattern (#1, #3, #5, etc.).
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            discord_id: Discord message ID of bot message
            
        Returns:
            The short ID assigned to the bot message
        """
        async with self._lock:
            mapping = self._ensure_path(server_id, channel_id, ai_name)
            
            # Assign current ID to bot message
            short_id = mapping["next_id"]
            mapping["discord_to_short"][discord_id] = short_id
            mapping["short_to_discord"][short_id] = discord_id
            
            # Skip to next ID
            mapping["next_id"] += 1
            
            
            return short_id
    
    async def get_stats(self) -> Dict:
        """
        Get statistics about ID mappings.
        
        Returns:
            Dictionary with stats
        """
        async with self._lock:
            total_mappings = 0
            total_ais = 0
            
            for server_data in self._maps.values():
                for channel_data in server_data.values():
                    for mapping in channel_data.values():
                        total_ais += 1
                        total_mappings += len(mapping["discord_to_short"])
            
            return {
                "total_mappings": total_mappings,
                "total_ais": total_ais,
                "servers": len(self._maps)
            }


# Global instance
_global_manager: Optional[ShortIDManager] = None


def get_short_id_manager() -> ShortIDManager:
    """
    Get the global short ID manager instance.
    
    Note: Mappings are automatically rebuilt from conversation history
    when ConversationStore loads.
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = ShortIDManager()
    return _global_manager


def get_short_id_manager_sync() -> ShortIDManager:
    """
    Get the global short ID manager instance (synchronous).
    
    This is safe to call because the manager is now in-memory only.
    """
    return get_short_id_manager()
