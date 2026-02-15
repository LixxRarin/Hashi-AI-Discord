"""
Response Manager - AI Response Management

This module manages AI responses, including tracking Discord message IDs,
handling multiple generations, and managing regeneration.

Key Features:
- Tracks Discord message IDs for deletion
- Manages multiple generations per response
- Navigation between generations
- Regeneration support
"""

import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class Generation:
    """Represents a single generation of a response."""
    text: str
    timestamp: float
    discord_ids: List[str]  # Can be multiple for line-by-line
    group_id: str  # UUID to group related messages
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "timestamp": self.timestamp,
            "discord_ids": self.discord_ids,
            "group_id": self.group_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Generation':
        """Create from dictionary."""
        return cls(
            text=data["text"],
            timestamp=data["timestamp"],
            discord_ids=data["discord_ids"],
            group_id=data.get("group_id", str(uuid.uuid4()))
        )


@dataclass
class ResponseState:
    """State of responses for an AI."""
    user_message: str = ""
    generations: List[Generation] = field(default_factory=list)
    current_index: int = 0
    max_generations: int = 10
    sleep_state: Dict[str, Any] = field(default_factory=dict)
    
    def add_generation(
        self,
        text: str,
        discord_ids: List[str],
        group_id: Optional[str] = None
    ) -> None:
        """Add a new generation."""
        if group_id is None:
            group_id = str(uuid.uuid4())
        
        generation = Generation(
            text=text,
            timestamp=time.time(),
            discord_ids=discord_ids,
            group_id=group_id
        )
        
        self.generations.append(generation)
        
        # Limit to max_generations
        if len(self.generations) > self.max_generations:
            removed = len(self.generations) - self.max_generations
            self.generations = self.generations[-self.max_generations:]
            # Adjust current_index
            if self.current_index >= removed:
                self.current_index -= removed
            else:
                self.current_index = 0
        
        # Set current to new generation
        self.current_index = len(self.generations) - 1
    
    def get_current(self) -> Optional[Generation]:
        """Get current generation."""
        if 0 <= self.current_index < len(self.generations):
            return self.generations[self.current_index]
        return None
    
    def navigate(self, direction: int) -> Optional[Generation]:
        """Navigate to previous/next generation."""
        new_index = self.current_index + direction
        
        if 0 <= new_index < len(self.generations):
            self.current_index = new_index
            return self.generations[new_index]
        
        return None
    
    def get_info(self) -> Dict[str, Any]:
        """Get generation info."""
        return {
            "current_index": self.current_index,
            "total_count": len(self.generations),
            "has_previous": self.current_index > 0,
            "has_next": self.current_index < len(self.generations) - 1,
            "current_number": self.current_index + 1
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_message": self.user_message,
            "generations": [g.to_dict() for g in self.generations],
            "current_index": self.current_index,
            "max_generations": self.max_generations,
            "sleep_state": self.sleep_state
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResponseState':
        """Create from dictionary."""
        return cls(
            user_message=data.get("user_message", ""),
            generations=[Generation.from_dict(g) for g in data.get("generations", [])],
            current_index=data.get("current_index", 0),
            max_generations=data.get("max_generations", 10),
            sleep_state=data.get("sleep_state", {})
        )


class ResponseManager:
    """
    Manages AI responses and their variations.
    
    This combines functionality from:
    - MessageTrackingManager (tracking Discord IDs)
    - GenerationCacheManager (multiple generations)
    
    Example:
        manager = ResponseManager()
        
        # Track a response
        manager.add_response(
            server_id, channel_id, ai_name,
            user_message="Hello",
            response_text="Hi!",
            discord_ids=["123"]
        )
        
        # Navigate
        prev_gen = manager.navigate(server_id, channel_id, ai_name, -1)
        
        # Get for regeneration
        state = manager.get_state(server_id, channel_id, ai_name)
    """
    
    def __init__(self):
        """Initialize the response manager."""
        self._responses: Dict[str, Dict[str, Dict[str, ResponseState]]] = {}
        # Cleanup tracking to prevent memory leaks
        self._last_cleanup = 0.0  # Timestamp of last cleanup
        self._cleanup_interval = 3600  # Check every 1 hour
        self._max_inactive_time = 86400  # Remove states inactive for 24 hours
    
    async def _cleanup_old_states(self):
        """
        Remove response states that have been inactive for too long.
        
        This prevents memory leaks from accumulating states for inactive channels.
        Called periodically during add_response() operations.
        """
        import time
        
        now = time.time()
        
        # Only cleanup if interval has passed
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        # Find states to remove
        to_remove = []
        for server_id, server_data in self._responses.items():
            for channel_id, channel_data in server_data.items():
                for ai_name, state in channel_data.items():
                    # Check if state has any generations
                    if state.generations:
                        # Get timestamp of most recent generation
                        last_activity = state.generations[-1].timestamp
                        if now - last_activity > self._max_inactive_time:
                            to_remove.append((server_id, channel_id, ai_name))
                    else:
                        # No generations, remove immediately
                        to_remove.append((server_id, channel_id, ai_name))
        
        # Remove old states
        for server_id, channel_id, ai_name in to_remove:
            try:
                del self._responses[server_id][channel_id][ai_name]
                # Clean up empty dictionaries
                if not self._responses[server_id][channel_id]:
                    del self._responses[server_id][channel_id]
                if not self._responses[server_id]:
                    del self._responses[server_id]
            except KeyError:
                pass  # Already removed
        
        self._last_cleanup = now
        
        if to_remove:
            log.info(
                f"[RESPONSE MANAGER CLEANUP] Removed {len(to_remove)} inactive response states "
                f"(inactive > {self._max_inactive_time/3600:.1f} hours)"
            )
    
    def _ensure_path(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> ResponseState:
        """Ensure path exists and return ResponseState."""
        if server_id not in self._responses:
            self._responses[server_id] = {}
        if channel_id not in self._responses[server_id]:
            self._responses[server_id][channel_id] = {}
        if ai_name not in self._responses[server_id][channel_id]:
            self._responses[server_id][channel_id][ai_name] = ResponseState()
        
        return self._responses[server_id][channel_id][ai_name]
    
    def add_response(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        user_message: str,
        response_text: str,
        discord_ids: List[str],
        group_id: Optional[str] = None
    ) -> None:
        """
        Add a new response.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            user_message: User message that prompted this response
            response_text: AI response text
            discord_ids: List of Discord message IDs
            group_id: Optional group ID for related messages
        """
        # Periodic cleanup of old states (prevents memory leaks)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._cleanup_old_states())
        except Exception:
            pass  # Ignore if no event loop
        
        state = self._ensure_path(server_id, channel_id, ai_name)
        
        # If user message changed, clear old generations
        if state.user_message != user_message:
            state.user_message = user_message
            state.generations.clear()
            state.current_index = 0
        
        state.add_generation(response_text, discord_ids, group_id)
        
        log.debug(
            "Added response for AI %s (total generations: %d)",
            ai_name, len(state.generations)
        )
    
    def get_current(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> Optional[Generation]:
        """
        Get current generation.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            Current generation or None
        """
        state = self._ensure_path(server_id, channel_id, ai_name)
        return state.get_current()
    
    def navigate(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        direction: int
    ) -> Optional[Generation]:
        """
        Navigate to previous/next generation.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            direction: -1 for previous, +1 for next
            
        Returns:
            New current generation or None if can't navigate
        """
        state = self._ensure_path(server_id, channel_id, ai_name)
        return state.navigate(direction)
    
    def get_info(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> Dict[str, Any]:
        """
        Get generation info.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            Generation info dictionary
        """
        state = self._ensure_path(server_id, channel_id, ai_name)
        return state.get_info()
    
    def get_state(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> ResponseState:
        """
        Get full response state.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            ResponseState object
        """
        return self._ensure_path(server_id, channel_id, ai_name)
    
    def clear(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> None:
        """
        Clear all responses for an AI.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
        """
        if (server_id in self._responses and
            channel_id in self._responses[server_id] and
            ai_name in self._responses[server_id][channel_id]):
            
            del self._responses[server_id][channel_id][ai_name]
            log.debug("Cleared responses for AI %s", ai_name)
    
    def get_discord_ids_for_current(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> List[str]:
        """
        Get Discord message IDs for current generation.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            List of Discord message IDs
        """
        current = self.get_current(server_id, channel_id, ai_name)
        if current:
            return current.discord_ids
        return []
    
    def get_previous_discord_ids(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> List[str]:
        """
        Get Discord message IDs from the current generation (before adding new one).
        
        This is used to remove reactions from the previous generation when
        a new generation is created.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            List of Discord message IDs from current generation,
            or empty list if no current generation exists
        """
        current = self.get_current(server_id, channel_id, ai_name)
        if current:
            return current.discord_ids
        return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get response manager statistics."""
        total_responses = 0
        total_generations = 0
        
        for server_data in self._responses.values():
            for channel_data in server_data.values():
                for state in channel_data.values():
                    total_responses += 1
                    total_generations += len(state.generations)
        
        return {
            "total_responses": total_responses,
            "total_generations": total_generations,
            "servers": len(self._responses)
        }


# Global manager instance
_global_manager: Optional[ResponseManager] = None


def get_response_manager() -> ResponseManager:
    """Get the global response manager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = ResponseManager()
    return _global_manager
