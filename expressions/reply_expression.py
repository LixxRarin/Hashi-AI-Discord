"""
Reply Expression - LLM Reply System

This module provides the Reply expression, which allows the LLM to reply
to specific messages on Discord using the <REPLY:ID> syntax.

Syntax: <REPLY:message_id> [response text]

Supports both short IDs and full Discord IDs:
- Short ID: <REPLY:1> Hello!
- Full ID: <REPLY:123456789> Hello!

Example:
    <REPLY:1> Hello! How can I help?
    
Multiple replies:
    <REPLY:1> Hi! <REPLY:2> How are you?

Migrated from: utils/reply_parser.py
"""

import re
from typing import List, Tuple, Optional, Dict, Any
import discord
import logging

from .base import BaseExpression, ExpressionResult

log = logging.getLogger(__name__)


class ReplyExpression(BaseExpression):
    """
    Reply System - Allows AI to reply to specific messages.
    
    This expression enables the LLM to use Discord's reply feature by
    specifying which message to reply to using the <REPLY:ID> syntax.
    """
    
    # Regex pattern to capture <REPLY:message_id>
    REPLY_PATTERN = r'<REPLY:(\d+)>\s*'
    
    @property
    def name(self) -> str:
        return "reply"
    
    @property
    def display_name(self) -> str:
        return "Reply System"
    
    @property
    def description(self) -> str:
        return "Allows AI to reply to specific messages using <REPLY:ID> syntax"
    
    @property
    def syntax_pattern(self) -> str:
        return self.REPLY_PATTERN
    
    @property
    def icon(self) -> str:
        return "💬"
    
    def has_syntax(self, text: str) -> bool:
        """Check if text contains reply syntax."""
        if not text:
            return False
        return bool(re.search(self.REPLY_PATTERN, text))
    
    def parse(self, text: str, config: Dict[str, Any]) -> ExpressionResult:
        """
        Parse reply syntax and extract message segments.
        
        Args:
            text: Text containing reply syntax
            config: AI configuration (not used for reply parsing)
            
        Returns:
            ExpressionResult with text_segments populated
        """
        segments = self.parse_reply_syntax(text)
        
        return ExpressionResult(
            text_segments=segments,
            metadata={"expression": "reply", "segment_count": len(segments)}
        )
    
    def remove_syntax(self, text: str) -> str:
        """Remove all reply syntax from text."""
        if not text:
            return text
        return re.sub(self.REPLY_PATTERN, '', text).strip()
    
    def get_default_prompt(self) -> str:
        """Get the default prompt for the reply system."""
        return """Reply Syntax: <REPLY:ID> [your response]

WHEN TO USE REPLIES (Be proactive):

ALWAYS use <REPLY:ID> when:
• Multiple people are actively talking (group chat) for clarity
• Responding to a message that's not the most recent one
• Answering a specific question from someone
• Continuing a conversation thread from earlier messages
• Any ambiguity about who/what you're responding to

ONLY skip replies when:
• True 1:1 conversation (just you and one person, back-and-forth)
• Making a general statement to everyone
• Starting a new topic

MENTIONS: Use @username when:
• You want to get someone's attention
• Replying to them (combine with <REPLY:ID>)
• Referring to someone in your message

Example: '<REPLY:5> @user This is the user who was asking about XXXX.'

CONTEXT: You'll see quoted content showing what users replied to:
> Author: original message (ID #1)
[time] User (@user) #2 → #1: their reply

Rules:
1. Never use the same <REPLY:id> twice in one response
2. Line breaks (\\n) send separate messages
3. When in doubt, USE the reply - it's better to over-use than under-use

EXAMPLES:
• Group chat: '<REPLY:3> Hello, user.' (ALWAYS reply in groups)
• Older message: '@John about your question earlier, yes!'
• General: 'Hey everyone! How's it going?' (no reply needed)"""
    
    def parse_reply_syntax(self, text: str) -> List[Tuple[Optional[str], str]]:
        """
        Extract message IDs and split text into segments.
        
        Reply tags only apply to text on the same line (until newline).
        
        Args:
            text: LLM response text that may contain reply syntax
            
        Returns:
            List of tuples (message_id or None, segment_text)
            
        Examples:
            Input: "<REPLY:123> Hello! <REPLY:456> How are you?"
            Output: [("123", "Hello!"), ("456", "How are you?")]
            
            Input: "Hello everyone!"
            Output: [(None, "Hello everyone!")]
            
            Input: "<REPLY:123> First line\\nSecond line"
            Output: [("123", "First line"), (None, "Second line")]
            
            Input: "<REPLY:123> Hi!\\nNormal text\\n<REPLY:456> Hello!"
            Output: [("123", "Hi!"), (None, "Normal text"), ("456", "Hello!")]
        """
        # If no reply syntax, return full text without reply
        if not self.has_syntax(text):
            return [(None, text)]
        
        segments = []
        last_end = 0
        
        # Find all <REPLY:message_id> matches
        for match in re.finditer(self.REPLY_PATTERN, text):
            message_id = match.group(1)
            start = match.start()
            end = match.end()
            
            # If there's text before this reply (orphan text)
            if start > last_end:
                orphan_text = text[last_end:start].strip()
                if orphan_text:
                    # Split orphan text by newlines and add as separate segments
                    for line in orphan_text.split('\n'):
                        line = line.strip()
                        if line:
                            segments.append((None, line))
            
            # Find the end of this reply segment (first newline or next reply tag)
            remaining_text = text[end:]
            
            # Look for newline
            newline_pos = remaining_text.find('\n')
            
            # Look for next reply tag
            next_match = re.search(self.REPLY_PATTERN, remaining_text)
            next_reply_pos = next_match.start() if next_match else -1
            
            # Determine segment end: use whichever comes first (newline or next reply)
            if newline_pos != -1 and (next_reply_pos == -1 or newline_pos < next_reply_pos):
                # Newline comes first - reply applies only to this line
                segment_end = end + newline_pos
            elif next_reply_pos != -1:
                # Next reply comes first (no newline before it)
                segment_end = end + next_reply_pos
            else:
                # No newline and no next reply - take until end
                segment_end = len(text)
            
            # Extract text for this segment
            segment_text = text[end:segment_end].strip()
            
            if segment_text:
                segments.append((message_id, segment_text))
            else:
                log.warning(f"Empty text for <REPLY:{message_id}>, skipping")
            
            last_end = segment_end
        
        # Handle any remaining text after the last reply
        if last_end < len(text):
            remaining = text[last_end:].strip()
            if remaining:
                # Split remaining text by newlines
                for line in remaining.split('\n'):
                    line = line.strip()
                    if line:
                        segments.append((None, line))
        
        # If no valid segments found, return cleaned text without reply tags
        if not segments:
            log.warning("No valid reply segments found, returning cleaned text")
            # Remove invalid reply syntax
            cleaned_text = self.remove_syntax(text)
            # Return cleaned text even if empty (will be filtered out by message_sender)
            return [(None, cleaned_text)]
        
        return segments
    
    @staticmethod
    def validate_message_id(message_id: str, allow_short_ids: bool = True) -> bool:
        """
        Validate if a message_id has valid format (numeric).
        
        Args:
            message_id: Message ID to validate
            allow_short_ids: Whether to accept short IDs (1-16 digits)
            
        Returns:
            True if ID is valid, False otherwise
        """
        if not message_id:
            return False
        
        # Check if numeric
        if not message_id.isdigit():
            return False
        
        id_len = len(message_id)
        
        # Short IDs: 1-16 digits (below Discord's 17-20 digit range)
        if allow_short_ids and 1 <= id_len <= 16:
            return True
        
        # Full Discord IDs: 17-20 digits (snowflakes)
        if 17 <= id_len <= 20:
            return True
        
        return False
    
    @staticmethod
    async def fetch_message_safe(
        channel: discord.TextChannel,
        message_id: str,
        server_id: Optional[str] = None,
        ai_name: Optional[str] = None
    ) -> Optional[discord.Message]:
        """
        Safely fetch a message by ID (supports both short and full IDs).
        
        Args:
            channel: Discord channel to fetch message from
            message_id: Message ID to fetch (short or full)
            server_id: Server ID (required for short ID conversion)
            ai_name: AI name (required for short ID conversion)
            
        Returns:
            discord.Message object if found, None otherwise
        """
        from utils.message_cache import fetch_message_cached
        from messaging.short_id_manager import get_short_id_manager_sync
        
        # Validate ID format first
        if not ReplyExpression.validate_message_id(message_id):
            return None
        
        # Convert short ID to Discord ID if needed
        discord_id = message_id
        if len(message_id) < 17:  # Short ID (Discord IDs are 17-20 digits)
            if not server_id or not ai_name:
                log.error(
                    f"Short ID {message_id} provided but missing server_id or ai_name for conversion"
                )
                return None
            
            # Convert short ID to Discord ID
            manager = get_short_id_manager_sync()
            discord_id = await manager.get_discord_id(
                server_id, str(channel.id), ai_name, int(message_id)
            )
            
            if not discord_id:
                log.warning(
                    f"Short ID {message_id} not found in mapping for {server_id}/{channel.id}/{ai_name}"
                )
                return None
        
        # Use cached fetch to reduce API calls
        try:
            message = await fetch_message_cached(channel, discord_id)
            return message
        except Exception as e:
            log.error(f"Error fetching message {discord_id}: {e}")
            return None
    
    def extract_message_ids(self, text: str) -> List[str]:
        """
        Extract all message IDs from text without processing segments.
        
        Useful for quick validation or logging.
        
        Args:
            text: Text containing reply syntax
            
        Returns:
            List of message IDs found
            
        Example:
            Input: "<REPLY:123> Hello! <REPLY:456> Hi!"
            Output: ["123", "456"]
        """
        matches = re.findall(self.REPLY_PATTERN, text)
        return matches
