"""
Reply Parser - LLM Reply System

This module provides functionality to parse and process the reply syntax
that the LLM uses to respond to specific messages on Discord.

Syntax: <REPLY:message_id> [response text]

Supports both short IDs and full Discord IDs:
- Short ID: <REPLY:1> Hello!
- Full ID: <REPLY:123456789> Hello!

Example:
    <REPLY:1> Hello! How can I help?
    
Multiple replies:
    <REPLY:1> Hi! <REPLY:2> How are you?
"""

import re
from typing import List, Tuple, Optional
from datetime import datetime, timedelta
import discord

import utils.func as func
from messaging.short_id_manager import get_short_id_manager_sync


class ReplyParser:
    """Parser to extract and process LLM reply syntax."""
    
    # Regex pattern to capture <REPLY:message_id>
    REPLY_PATTERN = r'<REPLY:(\d+)>\s*'
    
    @staticmethod
    def parse_reply_syntax(text: str) -> List[Tuple[Optional[str], str]]:
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
            
            Input: "<REPLY:123> First line\nSecond line"
            Output: [("123", "First line"), (None, "Second line")]
            
            Input: "<REPLY:123> Hi!\nNormal text\n<REPLY:456> Hello!"
            Output: [("123", "Hi!"), (None, "Normal text"), ("456", "Hello!")]
        """
        # If no reply syntax, return full text without reply
        if not re.search(ReplyParser.REPLY_PATTERN, text):
            return [(None, text)]
        
        segments = []
        last_end = 0
        
        # Find all <REPLY:message_id> matches
        for match in re.finditer(ReplyParser.REPLY_PATTERN, text):
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
            next_match = re.search(ReplyParser.REPLY_PATTERN, remaining_text)
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
                func.log.warning(f"Empty text for <REPLY:{message_id}>, skipping")
            
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
        
        # If no valid segments found, return original text without reply
        if not segments:
            func.log.warning("No valid reply segments found, returning original text")
            # Remove invalid reply syntax
            cleaned_text = re.sub(ReplyParser.REPLY_PATTERN, '', text).strip()
            return [(None, cleaned_text if cleaned_text else text)]
        
        return segments
    
    @staticmethod
    def validate_message_id(message_id: str, allow_short_ids: bool = True) -> bool:
        """
        Validate if a message_id has valid format (numeric).
        
        Args:
            message_id: Message ID to validate
            allow_short_ids: Whether to accept short IDs (1-3 digits)
            
        Returns:
            True if ID is valid, False otherwise
        """
        if not message_id:
            return False
        
        # Check if numeric
        if not message_id.isdigit():
            func.log.warning(f"Invalid message_id format: {message_id} (not numeric)")
            return False
        
        id_len = len(message_id)
        
        # Short IDs: 1-3 digits
        if allow_short_ids and 1 <= id_len <= 3:
            return True
        
        # Full Discord IDs: 17-20 digits (snowflakes)
        if 17 <= id_len <= 20:
            return True
        
        func.log.warning(
            f"Invalid message_id length: {message_id} "
            f"(expected 1-3 for short IDs or 17-20 for Discord IDs, got {id_len})"
        )
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
        # Validate ID format first
        if not ReplyParser.validate_message_id(message_id):
            return None
        
        # Convert short ID to Discord ID if needed
        discord_id = message_id
        if len(message_id) <= 3:  # Short ID
            if not server_id or not ai_name:
                func.log.error(
                    f"Short ID {message_id} provided but missing server_id or ai_name for conversion"
                )
                return None
            
            # Convert short ID to Discord ID
            manager = get_short_id_manager_sync()
            discord_id = await manager.get_discord_id(
                server_id, str(channel.id), ai_name, int(message_id)
            )
            
            if not discord_id:
                func.log.warning(
                    f"Short ID {message_id} not found in mapping for {server_id}/{channel.id}/{ai_name}"
                )
                return None
            
        
        try:
            # Try to fetch the message
            message = await channel.fetch_message(int(discord_id))
            return message
            
        except discord.NotFound:
            func.log.warning(f"Message {discord_id} not found in channel {channel.id}")
            return None
        except discord.Forbidden:
            func.log.error(f"No permission to fetch message {discord_id} in channel {channel.id}")
            return None
        except discord.HTTPException as e:
            func.log.error(f"HTTP error fetching message {discord_id}: {e}")
            return None
        except Exception as e:
            func.log.error(f"Unexpected error fetching message {discord_id}: {e}")
            return None
    
    @staticmethod
    def extract_message_ids(text: str) -> List[str]:
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
        matches = re.findall(ReplyParser.REPLY_PATTERN, text)
        return matches
    
    @staticmethod
    def has_reply_syntax(text: str) -> bool:
        """
        Check if text contains reply syntax.
        
        Args:
            text: Text to check
            
        Returns:
            True if contains reply syntax, False otherwise
        """
        return bool(re.search(ReplyParser.REPLY_PATTERN, text))
    
    @staticmethod
    def remove_reply_syntax(text: str) -> str:
        """
        Remove all reply syntax from text, leaving only content.
        
        Useful for fallback when reply system is disabled.
        
        Args:
            text: Text with reply syntax
            
        Returns:
            Text without reply syntax
            
        Example:
            Input: "<REPLY:123> Hello! <REPLY:456> Hi!"
            Output: "Hello! Hi!"
        """
        return re.sub(ReplyParser.REPLY_PATTERN, '', text).strip()
