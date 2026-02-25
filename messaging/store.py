"""
Conversation Store - Unified Conversation Storage

This module provides unified storage for conversation history,
replacing the fragmented conversation_history.json system.

Key Features:
- Single source of truth for conversations
- Supports multiple chats per AI
- Automatic truncation
- Rich metadata
- Export/import capabilities
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

log = logging.getLogger(__name__)


@dataclass
class Message:
    """Represents a single message in conversation history."""
    id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: float
    discord_id: Optional[str] = None  # For user messages
    discord_ids: Optional[List[str]] = None  # For assistant messages (can be multiple)
    
    # Metadata for consolidated messages
    author_id: Optional[str] = None
    author_username: Optional[str] = None
    author_display_name: Optional[str] = None
    consolidated_ids: Optional[List[str]] = None  # IDs of consolidated messages
    short_id: Optional[int] = None  # Short ID for this message (persistent)
    
    # Attachments and stickers
    attachments: Optional[List[Dict[str, Any]]] = None  # Image/file attachments
    stickers: Optional[List[Dict[str, Any]]] = None     # Discord stickers
    
    # Reply tracking
    reply_to_id: Optional[str] = None  # Discord ID of message being replied to
    reply_to_short_id: Optional[int] = None  # Short ID of message being replied to
    reply_to_content: Optional[str] = None  # Content of message being replied to (truncated)
    reply_to_author: Optional[str] = None  # Display name of reply target author
    reply_to_is_bot: bool = False  # True if replying to a bot message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "discord_id": self.discord_id,
            "discord_ids": self.discord_ids
        }
        
        # Add optional metadata if present
        if self.author_id:
            result["author_id"] = self.author_id
        if self.author_username:
            result["author_username"] = self.author_username
        if self.author_display_name:
            result["author_display_name"] = self.author_display_name
        if self.consolidated_ids:
            result["consolidated_ids"] = self.consolidated_ids
        if self.short_id is not None:
            result["short_id"] = self.short_id
        if self.attachments:
            result["attachments"] = self.attachments
        if self.stickers:
            result["stickers"] = self.stickers
        
        # Add reply tracking fields
        if self.reply_to_id:
            result["reply_to_id"] = self.reply_to_id
        if self.reply_to_short_id is not None:
            result["reply_to_short_id"] = self.reply_to_short_id
        if self.reply_to_content:
            result["reply_to_content"] = self.reply_to_content
        if self.reply_to_author:
            result["reply_to_author"] = self.reply_to_author
        if self.reply_to_is_bot:
            result["reply_to_is_bot"] = self.reply_to_is_bot
            
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", time.time()),
            discord_id=data.get("discord_id"),
            discord_ids=data.get("discord_ids"),
            author_id=data.get("author_id"),
            author_username=data.get("author_username"),
            author_display_name=data.get("author_display_name"),
            consolidated_ids=data.get("consolidated_ids"),
            short_id=data.get("short_id"),
            attachments=data.get("attachments"),
            stickers=data.get("stickers"),
            reply_to_id=data.get("reply_to_id"),
            reply_to_short_id=data.get("reply_to_short_id"),
            reply_to_content=data.get("reply_to_content"),
            reply_to_author=data.get("reply_to_author"),
            reply_to_is_bot=data.get("reply_to_is_bot", False)
        )


@dataclass
class ChatMetadata:
    """Metadata for a chat session."""
    created_at: float
    updated_at: float
    message_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMetadata':
        """Create from dictionary."""
        return cls(**data)

 
@dataclass
class Chat:
    """Represents a chat session."""
    messages: List[Message] = field(default_factory=list)
    metadata: ChatMetadata = field(default_factory=lambda: ChatMetadata(
        created_at=time.time(),
        updated_at=time.time(),
        message_count=0
    ))
    
    def add_message(self, message: Message) -> None:
        """Add a message to the chat."""
        self.messages.append(message)
        self.metadata.updated_at = time.time()
        self.metadata.message_count = len(self.messages)
    
    def get_messages_for_api(self) -> List[Dict[str, str]]:
        """Get messages in API format (role + content only)."""
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self.messages
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "messages": [msg.to_dict() for msg in self.messages],
            "metadata": self.metadata.to_dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Chat':
        """Create from dictionary."""
        return cls(
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            metadata=ChatMetadata.from_dict(data.get("metadata", {
                "created_at": time.time(),
                "updated_at": time.time(),
                "message_count": 0
            }))
        )


class ConversationStore:
    """
    Unified storage for conversation history.
    
    This replaces conversation_history.json with a cleaner,
    more structured approach.
    
    Structure:
        server_id -> channel_id -> ai_name -> chats -> chat_id -> Chat
    
    Example:
        store = ConversationStore("data/conversations.json")
        await store.load()
        
        # Add messages
        store.add_user_message(server_id, channel_id, ai_name, "Hello!", "123")
        store.add_assistant_message(server_id, channel_id, ai_name, "Hi!", ["456"])
        
        # Get history
        history = store.get_history(server_id, channel_id, ai_name)
        
        # Save
        await store.save()
    """
    
    def __init__(self, file_path: str = "data/conversations.json"):
        """
        Initialize the conversation store.
        
        Args:
            file_path: Path to the conversations file
        """
        self.file_path = file_path
        self._data: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()
        self._save_task: Optional[asyncio.Task] = None
        self._debounce_delay = 1.0
        
    
    def _ensure_path(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> Dict[str, Any]:
        """Ensure the path exists and return the AI data."""
        if server_id not in self._data:
            self._data[server_id] = {}
        if channel_id not in self._data[server_id]:
            self._data[server_id][channel_id] = {}
        if ai_name not in self._data[server_id][channel_id]:
            self._data[server_id][channel_id][ai_name] = {
                "active_chat": "default",
                "chats": {}
            }
        
        return self._data[server_id][channel_id][ai_name]
    
    def _ensure_chat(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: str = "default"
    ) -> Chat:
        """Ensure the chat exists and return it."""
        ai_data = self._ensure_path(server_id, channel_id, ai_name)
        
        if chat_id not in ai_data["chats"]:
            ai_data["chats"][chat_id] = Chat()
        
        chat_data = ai_data["chats"][chat_id]
        if isinstance(chat_data, dict):
            # Convert dict to Chat object
            chat = Chat.from_dict(chat_data)
            ai_data["chats"][chat_id] = chat
            return chat
        
        return chat_data
    
    async def load(self) -> None:
        """Load conversations from file."""
        if not os.path.exists(self.file_path):
            return
        
        try:
            async with self._lock:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for server_id, server_data in data.items():
                    for channel_id, channel_data in server_data.items():
                        for ai_name, ai_data in channel_data.items():
                            self._ensure_path(server_id, channel_id, ai_name)
                            self._data[server_id][channel_id][ai_name] = {
                                "active_chat": ai_data.get("active_chat", "default"),
                                "chats": {
                                    chat_id: Chat.from_dict(chat_data)
                                    for chat_id, chat_data in ai_data.get("chats", {}).items()
                                }
                            }
            
            self._restore_all_short_id_mappings()
            
        except Exception as e:
            log.error("Error loading conversations: %s", e)
    
    def _restore_all_short_id_mappings(self) -> None:
        """
        Restore short ID mappings for all loaded conversations.
        
        This rebuilds the mapping cache from conversation history,
        making the mapping file optional. Now supports BOTH user and bot messages.
        
        NOTE: This is a synchronous method called during load().
        It directly accesses the manager's internal state for performance.
        """
        from messaging.short_id_manager import get_short_id_manager_sync
        manager = get_short_id_manager_sync()
        
        restored_count = 0
        
        for server_id, server_data in self._data.items():
            for channel_id, channel_data in server_data.items():
                for ai_name, ai_data in channel_data.items():
                    for chat in ai_data["chats"].values():
                        for msg in chat.messages:
                            # Restore mapping for ANY message with short_id and discord_id(s)
                            if msg.short_id:
                                mapping = manager._ensure_path(server_id, channel_id, ai_name)
                                
                                if msg.role == "user" and msg.discord_id:
                                    # User message - has single discord_id
                                    mapping["discord_to_short"][msg.discord_id] = msg.short_id
                                    mapping["short_to_discord"][msg.short_id] = msg.discord_id
                                    restored_count += 1
                                    
                                    # Update next_id if needed
                                    if msg.short_id >= mapping["next_id"]:
                                        mapping["next_id"] = msg.short_id + 1
                                        
                                elif msg.role == "assistant" and msg.discord_ids and len(msg.discord_ids) > 0:
                                    # Bot message - has list of discord_ids (multi-part)
                                    # Map the first discord_id to the short_id
                                    first_discord_id = msg.discord_ids[0]
                                    mapping["discord_to_short"][first_discord_id] = msg.short_id
                                    mapping["short_to_discord"][msg.short_id] = first_discord_id
                                    restored_count += 1
                                    
                                    if msg.short_id >= mapping["next_id"]:
                                        mapping["next_id"] = msg.short_id + 1
        
        if restored_count > 0:
            log.debug(f"Restored {restored_count} short ID mappings")
    
    async def _save_debounced(self) -> None:
        """Save with debounce delay."""
        await asyncio.sleep(self._debounce_delay)
        await self.save_immediate()
    
    def schedule_save(self) -> None:
        """Schedule a debounced save."""
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
        
        self._save_task = asyncio.create_task(self._save_debounced())
    
    async def save_immediate(self) -> bool:
        """Save conversations to file immediately.
        
        Returns:
            True if save successful, False otherwise
        """
        try:
            async with self._lock:
                # Convert to serializable format
                data = {}
                for server_id, server_data in self._data.items():
                    data[server_id] = {}
                    for channel_id, channel_data in server_data.items():
                        data[server_id][channel_id] = {}
                        for ai_name, ai_data in channel_data.items():
                            data[server_id][channel_id][ai_name] = {
                                "active_chat": ai_data["active_chat"],
                                "chats": {
                                    chat_id: chat.to_dict()
                                    for chat_id, chat in ai_data["chats"].items()
                                }
                            }
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
                
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            log.error("Error saving conversations: %s", e)
            return False
    
    def _should_consolidate(self, msg1: Message, msg2: Message) -> bool:
        """
        Check if two messages should be consolidated.
        
        Args:
            msg1: First message
            msg2: Second message
            
        Returns:
            True if messages should be consolidated
        """
        # Don't consolidate assistant messages
        if msg1.role == "assistant" or msg2.role == "assistant":
            return False
        
        # Must be from same author
        if msg1.author_id and msg2.author_id:
            if msg1.author_id != msg2.author_id:
                return False
        
        # Must be within 60 seconds
        time_diff = msg2.timestamp - msg1.timestamp
        if time_diff > 60:
            return False
        
        return True
    
    def _consolidate_messages(self, messages: List[Message]) -> List[Message]:
        """
        Consolidate sequential messages from the same user.
        
        Args:
            messages: List of messages to consolidate
            
        Returns:
            List of consolidated messages
        """
        if not messages:
            return messages
        
        consolidated = []
        current_group = []
        
        for msg in messages:
            # Assistant messages are never consolidated
            if msg.role == "assistant":
                # Finalize any pending user group
                if current_group:
                    consolidated.append(self._create_consolidated_message(current_group))
                    current_group = []
                consolidated.append(msg)
                continue
            
            # Check if should consolidate with current group
            if current_group and self._should_consolidate(current_group[-1], msg):
                current_group.append(msg)
            else:
                # Finalize previous group
                if current_group:
                    consolidated.append(self._create_consolidated_message(current_group))
                # Start new group
                current_group = [msg]
        
        # Finalize last group
        if current_group:
            consolidated.append(self._create_consolidated_message(current_group))
        
        return consolidated
    
    def _create_consolidated_message(self, group: List[Message]) -> Message:
        """
        Create a consolidated message from a group of messages.
        
        Args:
            group: List of messages to consolidate
            
        Returns:
            Consolidated message
        """
        if len(group) == 1:
            return group[0]
        
        first = group[0]
        
        # Combine contents with newlines
        combined_content = "\n".join(msg.content for msg in group)
        
        # Collect all discord_ids
        all_ids = [msg.discord_id for msg in group if msg.discord_id]
        
        return Message(
            id=first.id,
            role=first.role,
            content=combined_content,
            timestamp=first.timestamp,
            discord_id=first.discord_id,
            discord_ids=None,
            author_id=first.author_id,
            author_username=first.author_username,
            author_display_name=first.author_display_name,
            consolidated_ids=all_ids if len(all_ids) > 1 else None
        )
    
    async def add_user_message(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        content: str,
        discord_id: str,
        chat_id: str = "default",
        author_id: Optional[str] = None,
        author_username: Optional[str] = None,
        author_display_name: Optional[str] = None,
        short_id: Optional[int] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        stickers: Optional[List[Dict[str, Any]]] = None,
        reply_to_id: Optional[str] = None,
        reply_to_short_id: Optional[int] = None,
        reply_to_content: Optional[str] = None,
        reply_to_author: Optional[str] = None,
        reply_to_is_bot: bool = False
    ) -> str:
        """
        Add a user message to the conversation.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            content: Message content
            discord_id: Discord message ID
            chat_id: Chat ID
            author_id: Author's Discord ID
            author_username: Author's username (e.g., lixxrarin)
            author_display_name: Author's display name (e.g., Rarin)
            short_id: Short ID for this message
            attachments: List of attachment metadata (images, files)
            stickers: List of sticker metadata
            reply_to_id: Discord ID of message being replied to
            reply_to_short_id: Short ID of message being replied to
            reply_to_content: Content of replied message (truncated)
            reply_to_author: Display name of reply target author
            reply_to_is_bot: True if replying to bot message
            
        Returns:
            Message ID
        """
        async with self._lock:
            chat = self._ensure_chat(server_id, channel_id, ai_name, chat_id)
            
            message = Message(
                id=str(uuid.uuid4()),
                role="user",
                content=content,
                timestamp=time.time(),
                discord_id=discord_id,
                author_id=author_id,
                author_username=author_username,
                author_display_name=author_display_name,
                short_id=short_id,
                attachments=attachments,
                stickers=stickers,
                reply_to_id=reply_to_id,
                reply_to_short_id=reply_to_short_id,
                reply_to_content=reply_to_content,
                reply_to_author=reply_to_author,
                reply_to_is_bot=reply_to_is_bot
            )
            
            chat.add_message(message)
            self.schedule_save()
            
            
            return message.id
    
    async def add_assistant_message(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        content: str,
        discord_ids: List[str],
        chat_id: str = "default",
        short_id: Optional[int] = None
    ) -> str:
        """
        Add an assistant message to the conversation.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            content: Message content
            discord_ids: List of Discord message IDs
            chat_id: Chat ID
            short_id: Short ID for this message (for reply references)
            
        Returns:
            Message ID
        """
        async with self._lock:
            chat = self._ensure_chat(server_id, channel_id, ai_name, chat_id)
            
            message = Message(
                id=str(uuid.uuid4()),
                role="assistant",
                content=content,
                timestamp=time.time(),
                discord_ids=discord_ids,
                short_id=short_id
            )
            
            chat.add_message(message)
            self.schedule_save()
            
            
            return message.id
    
    async def get_history(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: str = "default",
        consolidate: bool = True
    ) -> List[Dict[str, str]]:
        """
        Get conversation history in API format.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            chat_id: Chat ID
            consolidate: Whether to consolidate sequential messages
            
        Returns:
            List of messages in API format (role + content)
        """
        async with self._lock:
            chat = self._ensure_chat(server_id, channel_id, ai_name, chat_id)
            messages = chat.messages
            
            # Rebuild short ID mappings from message history using stored short_ids
            # This ensures IDs are persistent across bot restarts
            from messaging.short_id_manager import get_short_id_manager_sync
            manager = get_short_id_manager_sync()
            
            for msg in messages:
                if msg.role == "user" and msg.discord_id and msg.short_id:
                    # Restore the mapping using the stored short_id
                    mapping = manager._ensure_path(server_id, channel_id, ai_name)
                    mapping["discord_to_short"][msg.discord_id] = msg.short_id
                    mapping["short_to_discord"][msg.short_id] = msg.discord_id
                    # Update next_id if needed
                    if msg.short_id >= mapping["next_id"]:
                        mapping["next_id"] = msg.short_id + 1
            
            # Apply consolidation if requested
            if consolidate:
                messages = self._consolidate_messages(messages)
            
            # Convert to API format
            return [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
    
    async def get_full_history(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: str = "default"
    ) -> List[Message]:
        """
        Get full conversation history with all metadata.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            chat_id: Chat ID
            
        Returns:
            List of Message objects
        """
        async with self._lock:
            chat = self._ensure_chat(server_id, channel_id, ai_name, chat_id)
            return chat.messages.copy()
    
    async def clear_history(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: Optional[str] = None,
        keep_greeting: bool = True,
        immediate: bool = False
    ) -> bool:
        """
        Clear conversation history.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            chat_id: Chat ID (None = clear all chats)
            keep_greeting: Keep first assistant message
            immediate: If True, save immediately to disk instead of scheduling
            
        Returns:
            True if cleared successfully
        """
        async with self._lock:
            try:
                ai_data = self._ensure_path(server_id, channel_id, ai_name)
                
                if chat_id is None:
                    # Clear all chats
                    if keep_greeting:
                        # Keep greeting from default chat
                        default_chat = ai_data["chats"].get("default")
                        if default_chat and default_chat.messages:
                            # Find first assistant message
                            greeting = next(
                                (msg for msg in default_chat.messages if msg.role == "assistant"),
                                None
                            )
                            if greeting:
                                new_chat = Chat()
                                new_chat.add_message(greeting)
                                ai_data["chats"] = {"default": new_chat}
                            else:
                                ai_data["chats"] = {}
                        else:
                            ai_data["chats"] = {}
                    else:
                        ai_data["chats"] = {}
                else:
                    # Clear specific chat
                    if chat_id in ai_data["chats"]:
                        chat = ai_data["chats"][chat_id]
                        if keep_greeting and chat.messages:
                            greeting = next(
                                (msg for msg in chat.messages if msg.role == "assistant"),
                                None
                            )
                            if greeting:
                                new_chat = Chat()
                                new_chat.add_message(greeting)
                                ai_data["chats"][chat_id] = new_chat
                            else:
                                del ai_data["chats"][chat_id]
                        else:
                            del ai_data["chats"][chat_id]
                
                from messaging.short_id_manager import get_short_id_manager_sync
                manager = get_short_id_manager_sync()
                await manager.clear_mappings(server_id, channel_id, ai_name)
                
                # Save immediately if requested, otherwise schedule
                if immediate:
                    # Release lock before calling save_immediate (it acquires its own lock)
                    pass  # Lock will be released at end of async with block
                
            except Exception as e:
                log.error("Error clearing history: %s", e)
                return False
        
        # Save outside the lock to avoid deadlock
        if immediate:
            return await self.save_immediate()
        else:
            self.schedule_save()
            return True
    
    async def remove_last_exchange(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: str = "default"
    ) -> bool:
        """
        Remove the last user-assistant exchange (for regeneration).
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            chat_id: Chat ID
            
        Returns:
            True if removed successfully
        """
        async with self._lock:
            try:
                chat = self._ensure_chat(server_id, channel_id, ai_name, chat_id)
                
                if len(chat.messages) >= 2:
                    # Collect messages to remove (for cleaning up short IDs)
                    removed_messages = chat.messages[-2:]
                    
                    # Remove last 2 messages (user + assistant)
                    chat.messages = chat.messages[:-2]
                    chat.metadata.updated_at = time.time()
                    chat.metadata.message_count = len(chat.messages)
                    
                    # CRITICAL FIX: Clean up orphaned short ID mappings
                    from messaging.short_id_manager import get_short_id_manager_sync
                    manager = get_short_id_manager_sync()
                    
                    for msg in removed_messages:
                        if msg.role == "user" and msg.discord_id:
                            await manager.remove_mapping(server_id, channel_id, ai_name, msg.discord_id)
                            log.debug(
                                f"Removed short ID mapping for Discord ID {msg.discord_id} "
                                f"(AI: {ai_name}, chat: {chat_id})"
                            )
                    
                    self.schedule_save()
                    return True
                
                return False
                
            except Exception as e:
                log.error("Error removing last exchange: %s", e)
                return False
    
    async def get_message_by_short_id(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        short_id: int,
        chat_id: str = "default"
    ) -> Optional[Message]:
        """
        Get a message by its short ID.
        
        This allows the bot to look up its own messages or user messages
        by their short ID for reply references.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            short_id: Short ID to look up
            chat_id: Chat ID
            
        Returns:
            Message object if found, None otherwise
        """
        async with self._lock:
            chat = self._ensure_chat(server_id, channel_id, ai_name, chat_id)
            
            # Search through messages for matching short_id
            for msg in chat.messages:
                if msg.short_id == short_id:
                    return msg
            
            return None
    
    async def get_message_content_by_short_id(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        short_id: int,
        chat_id: str = "default"
    ) -> Optional[str]:
        """
        Get message content by short ID.
        
        Convenience method for getting just the content.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            short_id: Short ID to look up
            chat_id: Chat ID
            
        Returns:
            Message content if found, None otherwise
        """
        msg = await self.get_message_by_short_id(
            server_id, channel_id, ai_name, short_id, chat_id
        )
        return msg.content if msg else None
    
    def list_chat_ids(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> List[str]:
        """
        List all chat IDs for a specific AI.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            List of chat IDs sorted by update time (most recent first)
        """
        try:
            ai_data = self._data.get(server_id, {}).get(channel_id, {}).get(ai_name, {})
            chats = ai_data.get("chats", {})
            
            if not chats:
                return []
            
            # Sort by updated_at timestamp (most recent first)
            chat_items = []
            for chat_id, chat in chats.items():
                if isinstance(chat, Chat):
                    updated_at = chat.metadata.updated_at
                elif isinstance(chat, dict):
                    updated_at = chat.get("metadata", {}).get("updated_at", 0)
                else:
                    updated_at = 0
                chat_items.append((chat_id, updated_at))
            
            chat_items.sort(key=lambda x: x[1], reverse=True)
            return [chat_id for chat_id, _ in chat_items]
            
        except Exception as e:
            log.error(f"Error listing chat IDs: {e}")
            return []
    
    def get_chat_info(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: str
    ) -> Dict[str, Any]:
        """
        Get detailed information about a specific chat.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            chat_id: Chat ID
            
        Returns:
            Dictionary with chat information:
            - chat_id: Chat ID
            - message_count: Number of messages
            - created_at: Creation timestamp
            - updated_at: Last update timestamp
            - greeting: First assistant message (if exists)
            - last_messages: Last 3 messages (role and preview)
        """
        try:
            chat = self._ensure_chat(server_id, channel_id, ai_name, chat_id)
            
            # Get greeting (first assistant message)
            greeting = None
            for msg in chat.messages:
                if msg.role == "assistant":
                    greeting = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                    break
            
            # Get last 3 messages
            last_messages = []
            for msg in chat.messages[-3:]:
                preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
                last_messages.append({
                    "role": msg.role,
                    "preview": preview,
                    "timestamp": msg.timestamp
                })
            
            return {
                "chat_id": chat_id,
                "message_count": chat.metadata.message_count,
                "created_at": chat.metadata.created_at,
                "updated_at": chat.metadata.updated_at,
                "greeting": greeting,
                "last_messages": last_messages
            }
            
        except Exception as e:
            log.error(f"Error getting chat info: {e}")
            return {
                "chat_id": chat_id,
                "message_count": 0,
                "created_at": 0,
                "updated_at": 0,
                "greeting": None,
                "last_messages": []
            }
    
    def get_active_chat_id(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> str:
        """
        Get the currently active chat ID for an AI.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            
        Returns:
            Active chat ID (from session data) or "default"
        """
        try:
            import utils.func as func
            channel_data = func.get_session_data(server_id, channel_id)
            if channel_data and ai_name in channel_data:
                return channel_data[ai_name].get("chat_id", "default")
            return "default"
        except Exception as e:
            log.error(f"Error getting active chat ID: {e}")
            return "default"
    
    async def delete_chat(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: str
    ) -> bool:
        """
        Delete a specific chat.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            chat_id: Chat ID to delete
            
        Returns:
            True if deleted successfully
            
        Raises:
            ValueError: If trying to delete active chat or chat doesn't exist
        """
        async with self._lock:
            try:
                # Check if chat exists
                ai_data = self._ensure_path(server_id, channel_id, ai_name)
                if chat_id not in ai_data["chats"]:
                    raise ValueError(f"Chat '{chat_id}' does not exist")
                
                # Check if it's the active chat
                active_chat = self.get_active_chat_id(server_id, channel_id, ai_name)
                if chat_id == active_chat:
                    raise ValueError(f"Cannot delete active chat '{chat_id}'. Switch to another chat first.")
                
                # Delete the chat
                del ai_data["chats"][chat_id]
                
                # Clean up short ID mappings for this chat
                from messaging.short_id_manager import get_short_id_manager_sync
                manager = get_short_id_manager_sync()
                await manager.clear_mappings(server_id, channel_id, ai_name)
                
                log.info(f"Deleted chat '{chat_id}' for AI '{ai_name}' in server {server_id}")
                
            except Exception as e:
                log.error(f"Error deleting chat: {e}")
                return False
        
        # Save outside lock
        return await self.save_immediate()
    
    async def rename_chat(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        old_chat_id: str,
        new_chat_id: str
    ) -> bool:
        """
        Rename a chat.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            old_chat_id: Current chat ID
            new_chat_id: New chat ID
            
        Returns:
            True if renamed successfully
            
        Raises:
            ValueError: If new ID already exists or old chat doesn't exist
        """
        async with self._lock:
            try:
                ai_data = self._ensure_path(server_id, channel_id, ai_name)
                
                # Check if old chat exists
                if old_chat_id not in ai_data["chats"]:
                    raise ValueError(f"Chat '{old_chat_id}' does not exist")
                
                # Check if new ID already exists
                if new_chat_id in ai_data["chats"]:
                    raise ValueError(f"Chat '{new_chat_id}' already exists")
                
                # Rename the chat
                ai_data["chats"][new_chat_id] = ai_data["chats"][old_chat_id]
                del ai_data["chats"][old_chat_id]
                
                # Update active_chat if this was the active one
                if ai_data.get("active_chat") == old_chat_id:
                    ai_data["active_chat"] = new_chat_id
                
                log.info(f"Renamed chat '{old_chat_id}' to '{new_chat_id}' for AI '{ai_name}' in server {server_id}")
                
            except Exception as e:
                log.error(f"Error renaming chat: {e}")
                return False
        
        # Save outside lock
        return await self.save_immediate()
    
    def _find_message_index_by_discord_id(
        self,
        messages: List[Message],
        discord_id: str
    ) -> Optional[int]:
        """
        Find the index of a message by discord_id.
        
        Searches in:
        - msg.discord_id (user messages)
        - msg.discord_ids (bot messages - list)
        
        Args:
            messages: List of messages to search
            discord_id: Discord message ID to find
            
        Returns:
            Index of the message or None if not found
        """
        for i, msg in enumerate(messages):
            # Check user messages (single discord_id)
            if msg.role == "user" and msg.discord_id == discord_id:
                return i
            # Check bot messages (list of discord_ids)
            elif msg.role == "assistant" and msg.discord_ids and discord_id in msg.discord_ids:
                return i
        
        return None
    
    async def update_message_by_discord_id(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        discord_id: str,
        new_content: str,
        chat_id: str = "default"
    ) -> bool:
        """
        Update the content of a message by discord_id.
        
        Behavior:
        - Searches in user messages (discord_id) and bot messages (discord_ids)
        - Updates ONLY the 'content' field
        - Preserves: timestamp, author, short_id, attachments, etc.
        - Updates metadata.updated_at
        - Schedules automatic save
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            discord_id: Discord message ID to update
            new_content: New formatted content
            chat_id: Chat ID (default: "default")
            
        Returns:
            True if found and updated, False otherwise
            
        Edge Cases:
            - Message doesn't exist: returns False
            - Consolidated message: updates only the specific message
            - Multiple AIs: each maintains its own history
        """
        async with self._lock:
            try:
                chat = self._ensure_chat(server_id, channel_id, ai_name, chat_id)
                
                # Find message index
                msg_index = self._find_message_index_by_discord_id(chat.messages, discord_id)
                
                if msg_index is None:
                    log.debug(
                        f"Message {discord_id} not found in history for AI {ai_name} "
                        f"(server: {server_id}, channel: {channel_id}, chat: {chat_id})"
                    )
                    return False
                
                # Update only the content
                old_content = chat.messages[msg_index].content
                chat.messages[msg_index].content = new_content
                
                # Update metadata
                chat.metadata.updated_at = time.time()
                
                # Schedule save
                self.schedule_save()
                
                log.debug(
                    f"Updated message {discord_id} for AI {ai_name} "
                    f"(index: {msg_index}, old length: {len(old_content)}, new length: {len(new_content)})"
                )
                
                return True
                
            except Exception as e:
                log.error(f"Error updating message {discord_id}: {e}")
                return False
    
    async def delete_message_by_discord_id(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        discord_id: str,
        chat_id: str = "default"
    ) -> bool:
        """
        Remove a message from history by discord_id.
        
        Behavior:
        - Removes from chat.messages list
        - Updates metadata.message_count and updated_at
        - Does NOT remove short_id mapping (for historical references)
        - Schedules automatic save
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            discord_id: Discord message ID to delete
            chat_id: Chat ID (default: "default")
            
        Returns:
            True if found and deleted, False otherwise
            
        Edge Cases:
            - Message doesn't exist: returns False
            - Message is greeting (index 0): returns False (protected)
            - Message has replies: replies keep reply_to_id (orphaned)
        """
        async with self._lock:
            try:
                chat = self._ensure_chat(server_id, channel_id, ai_name, chat_id)
                
                # Find message index
                msg_index = self._find_message_index_by_discord_id(chat.messages, discord_id)
                
                if msg_index is None:
                    log.debug(
                        f"Message {discord_id} not found in history for AI {ai_name} "
                        f"(server: {server_id}, channel: {channel_id}, chat: {chat_id})"
                    )
                    return False
                
                # Protect greeting message (index 0, assistant role)
                if msg_index == 0 and chat.messages[msg_index].role == "assistant":
                    log.warning(
                        f"Cannot delete greeting message (index 0) for AI {ai_name} "
                        f"(server: {server_id}, channel: {channel_id}, chat: {chat_id})"
                    )
                    return False
                
                # Remove the message
                removed_msg = chat.messages.pop(msg_index)
                
                # Update metadata
                chat.metadata.updated_at = time.time()
                chat.metadata.message_count = len(chat.messages)
                
                # Schedule save
                self.schedule_save()
                
                log.debug(
                    f"Deleted message {discord_id} for AI {ai_name} "
                    f"(index: {msg_index}, role: {removed_msg.role}, "
                    f"remaining messages: {len(chat.messages)})"
                )
                
                return True
                
            except Exception as e:
                log.error(f"Error deleting message {discord_id}: {e}")
                return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get conversation statistics."""
        total_messages = 0
        total_chats = 0
        total_ais = 0
        
        for server_data in self._data.values():
            for channel_data in server_data.values():
                for ai_data in channel_data.values():
                    total_ais += 1
                    for chat in ai_data["chats"].values():
                        total_chats += 1
                        total_messages += len(chat.messages)
        
        return {
            "total_messages": total_messages,
            "total_chats": total_chats,
            "total_ais": total_ais,
            "servers": len(self._data)
        }


# Global store instance
_global_store: Optional[ConversationStore] = None


def get_store(file_path: str = "data/conversations.json") -> ConversationStore:
    """Get the global conversation store instance."""
    global _global_store
    if _global_store is None:
        _global_store = ConversationStore(file_path)
    return _global_store
