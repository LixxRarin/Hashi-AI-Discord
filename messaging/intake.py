"""
Message Intake - Message Validation and Filtering

Handles initial validation and filtering of incoming Discord messages.
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import discord

log = logging.getLogger(__name__)


@dataclass
class MessageMetadata:
    """Metadata extracted from a Discord message."""
    server_id: str
    channel_id: str
    message_id: str
    author_id: str
    author_name: str
    author_display_name: str
    content: str
    timestamp: float
    is_reply: bool
    reply_to_id: Optional[str] = None
    reply_to_content: Optional[str] = None
    reply_to_author_name: Optional[str] = None  # Display name of reply target author
    reply_to_is_bot: bool = False  # True if replying to a bot message
    mentions_bot: bool = False
    attachments: Optional[List[Dict[str, Any]]] = None  # Image/file attachments
    stickers: Optional[List[Dict[str, Any]]] = None     # Discord stickers
    raw_message: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "server_id": self.server_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "author_display_name": self.author_display_name,
            "content": self.content,
            "timestamp": self.timestamp,
            "is_reply": self.is_reply,
            "reply_to_id": self.reply_to_id,
            "reply_to_content": self.reply_to_content,
            "reply_to_author_name": self.reply_to_author_name,
            "reply_to_is_bot": self.reply_to_is_bot,
            "mentions_bot": self.mentions_bot,
            "attachments": self.attachments,
            "stickers": self.stickers
        }


class MessageIntake:
    """
    Validates and filters incoming Discord messages.
    
    This is the entry point for all messages in the pipeline.
    It performs validation and extracts metadata before passing
    messages to the buffer.
    
    Example:
        intake = MessageIntake()
        metadata = await intake.process(discord_message, bot_user_id)
        if metadata:
            # Message is valid, proceed with processing
            pass
    """
    
    def __init__(self):
        """Initialize the message intake."""
        self._ignored_prefixes = ["//"]
    
    def _is_bot_message(self, message: discord.Message) -> bool:
        """
        Check if message is from a bot or webhook.
        
        Args:
            message: Discord message
            
        Returns:
            True if message is from bot/webhook
        """
        return message.author.bot or message.webhook_id is not None
    
    def _has_ignored_prefix(self, content: str) -> bool:
        """
        Check if message starts with an ignored prefix.
        
        Args:
            content: Message content
            
        Returns:
            True if message has ignored prefix
        """
        return any(content.startswith(prefix) for prefix in self._ignored_prefixes)
    
    def _is_user_muted(
        self,
        user_id: int,
        session_data: Dict[str, Any]
    ) -> bool:
        """
        Check if user is muted for any AI in the channel.
        
        Args:
            user_id: Discord user ID
            session_data: Channel session data
            
        Returns:
            True if user is muted
        """
        if not session_data:
            return False
        
        for ai_session in session_data.values():
            muted_users = ai_session.get("muted_users", [])
            if user_id in muted_users:
                return True
        
        return False
    
    async def _extract_reply_info(
        self,
        message: discord.Message,
        bot_user_id: int
    ) -> tuple[Optional[str], Optional[str], Optional[str], bool]:
        """
        Extract reply information if message is a reply.
        
        Args:
            message: Discord message
            bot_user_id: Bot's user ID to detect bot messages
            
        Returns:
            Tuple of (reply_to_id, reply_to_content, reply_to_author_name, reply_to_is_bot)
        """
        if not message.reference:
            return None, None, None, False
        
        try:
            ref_message = await message.channel.fetch_message(
                message.reference.message_id
            )
            
            # Determine if reply is to a bot message
            is_bot = ref_message.author.bot or ref_message.author.id == bot_user_id
            
            # Get author display name (prefer display_name, fallback to name)
            author_name = ref_message.author.display_name or ref_message.author.name
            
            return (
                str(ref_message.id),
                ref_message.content,
                author_name,
                is_bot
            )
        except Exception as e:
            log.warning("Could not fetch referenced message: %s", e)
            return str(message.reference.message_id), None, None, False
    
    def _check_bot_mention(
        self,
        message: discord.Message,
        bot_user_id: int
    ) -> bool:
        """
        Check if bot was mentioned in the message.
        
        Args:
            message: Discord message
            bot_user_id: Bot's user ID
            
        Returns:
            True if bot was mentioned
        """
        if not hasattr(message, 'mentions'):
            return False
        
        return any(user.id == bot_user_id for user in message.mentions)
    
    async def process(
        self,
        message: discord.Message,
        bot_user_id: int,
        session_data: Optional[Dict[str, Any]] = None
    ) -> Optional[MessageMetadata]:
        """
        Process and validate an incoming Discord message.
        
        Args:
            message: Discord message to process
            bot_user_id: Bot's user ID
            session_data: Channel session data for mute checking
            
        Returns:
            MessageMetadata if valid, None if should be ignored
        """
        if not message.guild:
            return None
        
        if self._is_bot_message(message):
            return None
        
        # Allow messages with attachments/stickers even if content is empty
        has_content = message.content and message.content.strip()
        has_attachments = message.attachments and len(message.attachments) > 0
        has_stickers = message.stickers and len(message.stickers) > 0
        
        if not has_content and not has_attachments and not has_stickers:
            return None
        
        if has_content and self._has_ignored_prefix(message.content):
            return None
        
        if self._is_user_muted(message.author.id, session_data):
            return None
        
        reply_to_id, reply_to_content, reply_to_author_name, reply_to_is_bot = await self._extract_reply_info(message, bot_user_id)
        mentions_bot = self._check_bot_mention(message, bot_user_id)
        
        # Capture attachments
        attachments = None
        if has_attachments:
            attachments = []
            for att in message.attachments:
                attachments.append({
                    "filename": att.filename,
                    "url": att.url,
                    "content_type": att.content_type or "unknown",
                    "size": att.size
                })
        
        # Capture stickers
        stickers = None
        if has_stickers:
            stickers = []
            for sticker in message.stickers:
                stickers.append({
                    "name": sticker.name,
                    "id": str(sticker.id),
                    "url": sticker.url,
                    "format": str(sticker.format)
                })
        
        metadata = MessageMetadata(
            server_id=str(message.guild.id),
            channel_id=str(message.channel.id),
            message_id=str(message.id),
            author_id=str(message.author.id),
            author_name=message.author.name,
            author_display_name=message.author.global_name or message.author.name,
            content=message.content or "",  # Empty string if no content
            timestamp=message.created_at.timestamp(),
            is_reply=reply_to_id is not None,
            reply_to_id=reply_to_id,
            reply_to_content=reply_to_content,
            reply_to_author_name=reply_to_author_name,
            reply_to_is_bot=reply_to_is_bot,
            mentions_bot=mentions_bot,
            attachments=attachments,
            stickers=stickers,
            raw_message=message
        )
        
        return metadata
    
    def validate_for_ai(
        self,
        metadata: MessageMetadata,
        ai_session: Dict[str, Any]
    ) -> bool:
        """
        Validate if message should be processed for a specific AI.
        
        Args:
            metadata: Message metadata
            ai_session: AI session configuration
            
        Returns:
            True if message should be processed for this AI
        """
        # Check if user is muted for this specific AI
        muted_users = ai_session.get("muted_users", [])
        if int(metadata.author_id) in muted_users:
            return False
        
        return True
    
    def set_ignored_prefixes(self, prefixes: List[str]) -> None:
        """
        Set custom ignored prefixes.
        
        Args:
            prefixes: List of prefixes to ignore
        """
        self._ignored_prefixes = prefixes
        log.info("Updated ignored prefixes: %s", prefixes)
    
    def add_ignored_prefix(self, prefix: str) -> None:
        """
        Add a prefix to the ignored list.
        
        Args:
            prefix: Prefix to ignore
        """
        if prefix not in self._ignored_prefixes:
            self._ignored_prefixes.append(prefix)
            log.info("Added ignored prefix: %s", prefix)


# Global intake instance
_global_intake: Optional[MessageIntake] = None


def get_intake() -> MessageIntake:
    """Get the global message intake instance."""
    global _global_intake
    if _global_intake is None:
        _global_intake = MessageIntake()
    return _global_intake
