"""
Message Buffer - In-Memory Message Storage

This module provides an in-memory buffer for pending messages,
replacing the disk-based messages_cache.json system.

Key Features:
- All operations in memory (no disk I/O)
- Thread-safe operations
- Automatic cleanup of old messages
- Optional crash recovery persistence
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class PendingMessage:
    """Represents a message waiting to be processed."""
    content: str
    author_id: str
    author_name: str
    author_display_name: str  # Display name (e.g., "Rarin")
    timestamp: float
    message_id: str
    reply_to: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None  # Image/file attachments
    stickers: Optional[List[Dict[str, Any]]] = None     # Discord stickers
    raw_message: Any = None  # Discord message object
    # Reply tracking metadata
    reply_to_content: Optional[str] = None  # Content of message being replied to
    reply_to_author: Optional[str] = None  # Display name of reply target author
    reply_to_is_bot: bool = False  # True if replying to bot message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "content": self.content,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "author_display_name": self.author_display_name,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "reply_to": self.reply_to,
            "attachments": self.attachments,
            "stickers": self.stickers,
            "reply_to_content": self.reply_to_content,
            "reply_to_author": self.reply_to_author,
            "reply_to_is_bot": self.reply_to_is_bot
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PendingMessage':
        """Create from dictionary."""
        return cls(
            content=data["content"],
            author_id=data["author_id"],
            author_name=data["author_name"],
            author_display_name=data.get("author_display_name", data["author_name"]),
            timestamp=data["timestamp"],
            message_id=data["message_id"],
            reply_to=data.get("reply_to"),
            attachments=data.get("attachments"),
            stickers=data.get("stickers"),
            reply_to_content=data.get("reply_to_content"),
            reply_to_author=data.get("reply_to_author"),
            reply_to_is_bot=data.get("reply_to_is_bot", False)
        )


@dataclass
class BufferState:
    """State of the buffer for a specific AI."""
    pending_messages: List[PendingMessage] = field(default_factory=list)
    last_activity: float = field(default_factory=time.time)
    processing: bool = False
    typing_until: float = 0.0
    
    def add_message(self, message: PendingMessage) -> None:
        """Add a message to the buffer."""
        self.pending_messages.append(message)
        self.last_activity = time.time()
    
    def clear(self) -> None:
        """Clear all pending messages."""
        self.pending_messages.clear()
    
    def get_count(self) -> int:
        """Get number of pending messages."""
        return len(self.pending_messages)
    
    def get_formatted_content(self) -> str:
        """Get all messages formatted as a single string."""
        return "\n".join(msg.content for msg in self.pending_messages)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for crash recovery."""
        return {
            "pending_messages": [msg.to_dict() for msg in self.pending_messages],
            "last_activity": self.last_activity,
            "processing": self.processing,
            "typing_until": self.typing_until
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BufferState':
        """Create from dictionary."""
        return cls(
            pending_messages=[PendingMessage.from_dict(m) for m in data.get("pending_messages", [])],
            last_activity=data.get("last_activity", time.time()),
            processing=data.get("processing", False),
            typing_until=data.get("typing_until", 0.0)
        )


class MessageBuffer:
    """
    In-memory buffer for pending messages.
    
    This replaces the disk-based messages_cache.json system with a fast,
    memory-based buffer that only persists for crash recovery.
    
    Structure:
        server_id -> channel_id -> ai_name -> BufferState
    
    Example:
        buffer = MessageBuffer()
        buffer.add_message(server_id, channel_id, ai_name, message)
        pending = buffer.get_pending(server_id, channel_id, ai_name)
        buffer.clear(server_id, channel_id, ai_name)
    """
    
    def __init__(self, enable_crash_recovery: bool = False):
        """
        Initialize the message buffer.
        
        Args:
            enable_crash_recovery: If True, periodically saves buffer to disk
        """
        self._buffer: Dict[str, Dict[str, Dict[str, BufferState]]] = {}
        self._lock = asyncio.Lock()
        self._enable_crash_recovery = enable_crash_recovery
        self._crash_recovery_task: Optional[asyncio.Task] = None
        
        log.debug("MessageBuffer initialized (crash_recovery=%s)", enable_crash_recovery)
    
    def _ensure_path(self, server_id: str, channel_id: str, ai_name: str) -> BufferState:
        """Ensure the path exists and return the BufferState."""
        if server_id not in self._buffer:
            self._buffer[server_id] = {}
        if channel_id not in self._buffer[server_id]:
            self._buffer[server_id][channel_id] = {}
        if ai_name not in self._buffer[server_id][channel_id]:
            self._buffer[server_id][channel_id][ai_name] = BufferState()
        
        return self._buffer[server_id][channel_id][ai_name]
    
    async def add_message(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        message: PendingMessage
    ) -> None:
        """
        Add a message to the buffer.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            message: Message to add
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            state.add_message(message)
    
    async def get_pending(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> List[PendingMessage]:
        """
        Get all pending messages for an AI.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            List of pending messages
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            return state.pending_messages.copy()
    
    async def get_count(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> int:
        """
        Get number of pending messages.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            Number of pending messages
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            return state.get_count()
    
    async def get_formatted_content(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> str:
        """
        Get all messages formatted as a single string.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            Formatted message content
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            return state.get_formatted_content()
    
    async def clear(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> None:
        """
        Clear all pending messages for an AI.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            count = state.get_count()
            state.clear()
    
    async def clear_specific_messages(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        message_ids: List[str]
    ) -> None:
        """
        Clear only specific messages from the buffer by their IDs.
        
        This prevents race conditions where messages that arrive during
        API processing get accidentally cleared.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            message_ids: List of message IDs to clear
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            
            # Filter out messages with matching IDs
            original_count = state.get_count()
            state.pending_messages = [
                msg for msg in state.pending_messages
                if msg.message_id not in message_ids
            ]
            cleared_count = original_count - state.get_count()
            preserved_count = state.get_count()
            
            log.debug(
                "Cleared %d message(s) from buffer for AI %s (preserved: %d)",
                cleared_count, ai_name, preserved_count
            )
    
    async def set_processing(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        processing: bool
    ) -> None:
        """
        Set processing state for an AI.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            processing: Processing state
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            state.processing = processing
    
    async def is_processing(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> bool:
        """
        Check if AI is currently processing.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            True if processing
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            return state.processing
    
    async def get_last_activity(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> float:
        """
        Get timestamp of last activity.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            Timestamp of last activity
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            return state.last_activity
    
    async def update_typing(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        typing_until: float
    ) -> None:
        """
        Update typing indicator timestamp.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            typing_until: Timestamp until user is typing
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            state.typing_until = typing_until
            state.last_activity = time.time()
    
    async def is_typing(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> bool:
        """
        Check if user is currently typing.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            True if user is typing
        """
        async with self._lock:
            state = self._ensure_path(server_id, channel_id, ai_name)
            return time.time() < state.typing_until
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get buffer statistics.
        
        Returns:
            Dictionary with buffer stats
        """
        total_messages = 0
        total_ais = 0
        
        for server_data in self._buffer.values():
            for channel_data in server_data.values():
                for state in channel_data.values():
                    total_ais += 1
                    total_messages += state.get_count()
        
        return {
            "total_messages": total_messages,
            "total_ais": total_ais,
            "servers": len(self._buffer)
        }
    
    async def save_crash_recovery(self, file_path: str) -> None:
        """
        Save buffer state for crash recovery.
        
        Args:
            file_path: Path to save recovery file
        """
        if not self._enable_crash_recovery:
            return
        
        async with self._lock:
            data = {}
            for server_id, server_data in self._buffer.items():
                data[server_id] = {}
                for channel_id, channel_data in server_data.items():
                    data[server_id][channel_id] = {}
                    for ai_name, state in channel_data.items():
                        data[server_id][channel_id][ai_name] = state.to_dict()
            
            # Save to file (async)
            import json
            import aiofiles
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2))
    
    async def load_crash_recovery(self, file_path: str) -> None:
        """
        Load buffer state from crash recovery.
        
        Args:
            file_path: Path to recovery file
        """
        try:
            import json
            import aiofiles
            import os
            
            if not os.path.exists(file_path):
                return
            
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
            
            async with self._lock:
                for server_id, server_data in data.items():
                    for channel_id, channel_data in server_data.items():
                        for ai_name, state_data in channel_data.items():
                            state = BufferState.from_dict(state_data)
                            self._ensure_path(server_id, channel_id, ai_name)
                            self._buffer[server_id][channel_id][ai_name] = state
            
            log.debug("Loaded crash recovery data from %s", file_path)
            
        except Exception as e:
            log.error("Error loading crash recovery: %s", e)


# Global buffer instance
_global_buffer: Optional[MessageBuffer] = None


def get_buffer() -> MessageBuffer:
    """Get the global message buffer instance."""
    global _global_buffer
    if _global_buffer is None:
        _global_buffer = MessageBuffer(enable_crash_recovery=False)
    return _global_buffer


def init_buffer(enable_crash_recovery: bool = False) -> MessageBuffer:
    """
    Initialize the global message buffer.
    
    Args:
        enable_crash_recovery: Enable crash recovery persistence
        
    Returns:
        The initialized buffer
    """
    global _global_buffer
    _global_buffer = MessageBuffer(enable_crash_recovery=enable_crash_recovery)
    return _global_buffer
