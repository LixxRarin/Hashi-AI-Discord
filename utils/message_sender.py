"""
Message Sender - Centralized Message Sending Logic

This module provides a unified interface for sending messages to Discord,
eliminating code duplication across app.py, AI_utils.py, and regenerate_commands.py.

Key Features:
- Supports bot mode and webhook mode
- Handles line-by-line and chunked sending
- Parses reply syntax automatically
- Efficient HTTP session management
- Message splitting for Discord's 2000 char limit
"""

import asyncio
import aiohttp
import discord
from typing import List, Optional, Callable
import logging

log = logging.getLogger(__name__)


class MessageSender:
    """
    Centralized message sending logic for Discord.
    
    Handles all the complexity of sending messages in different modes
    (bot vs webhook), with different options (line-by-line vs chunked),
    and with reply syntax parsing.
    
    Example:
        sender = MessageSender()
        discord_ids = await sender.send(
            response_text="Hello!",
            channel=channel,
            session=session,
            split_message_fn=AI._split_message
        )
    """
    
    def __init__(self):
        """Initialize the message sender."""
        pass
    
    async def send(
        self,
        response_text: str,
        channel: discord.TextChannel,
        session: dict,
        split_message_fn: Optional[Callable[[str], List[str]]] = None
    ) -> List[str]:
        """
        Send a message to Discord using the appropriate method.
        
        Args:
            response_text: The text to send
            channel: Discord channel to send to
            session: AI session configuration
            split_message_fn: Optional function to split long messages
                            If None, uses simple 2000-char splitting
            
        Returns:
            List of Discord message IDs that were sent
        """
        mode = session.get("mode", "webhook")
        is_line_by_line = session.get("config", {}).get("send_message_line_by_line", False)
        webhook_url = session.get("webhook_url")
        enable_reply_system = session.get("config", {}).get("enable_reply_system", False)
        
        # Extract context for short ID conversion
        server_id = session.get("server_id")
        ai_name = session.get("ai_name")
        
        # Convert @username mentions to proper Discord mentions
        response_text = await self._convert_username_mentions(response_text, channel)
        
        # Convert :emoji_name: to proper Discord emoji format
        response_text = await self._convert_custom_emojis(response_text, channel)
        
        discord_ids = []
        
        # Parse reply syntax if enabled
        reply_segments = [(None, response_text)]
        if enable_reply_system:
            from utils.reply_parser import ReplyParser
            reply_segments = ReplyParser.parse_reply_syntax(response_text)
        
        # Send each segment
        for segment_message_id, segment_text in reply_segments:
            if not segment_text or segment_text.isspace():
                continue
            
            # Get reference message if needed
            reference_message = None
            if segment_message_id:
                from utils.reply_parser import ReplyParser
                reference_message = await ReplyParser.fetch_message_safe(
                    channel, segment_message_id,
                    server_id=server_id,
                    ai_name=ai_name
                )
            
            # Send based on mode
            if mode == "bot":
                ids = await self._send_as_bot(
                    segment_text, channel, reference_message,
                    is_line_by_line, split_message_fn
                )
                discord_ids.extend(ids)
            else:
                # Webhook mode
                if webhook_url:
                    ids = await self._send_as_webhook(
                        segment_text, webhook_url, reference_message,
                        is_line_by_line, split_message_fn
                    )
                    discord_ids.extend(ids)
                else:
                    log.warning("Webhook mode selected but no webhook_url configured")
        
        return discord_ids
    
    async def _send_as_bot(
        self,
        text: str,
        channel: discord.TextChannel,
        reference: Optional[discord.Message],
        line_by_line: bool,
        split_fn: Optional[Callable[[str], List[str]]]
    ) -> List[str]:
        """Send message as bot."""
        ids = []
        
        if line_by_line:
            for line in text.split('\n'):
                stripped = line.strip()
                if stripped:
                    # Check if line exceeds Discord's 2000 char limit
                    if len(line) > 2000:
                        # Split long line into chunks
                        line_chunks = self._split_message(line, split_fn)
                        for chunk in line_chunks:
                            try:
                                sent_msg = await channel.send(chunk, reference=reference)
                                ids.append(str(sent_msg.id))
                                # Yield control to event loop to prevent heartbeat blocking
                                await asyncio.sleep(0)
                            except Exception as e:
                                log.error(f"Error sending line chunk as bot: {e}")
                    else:
                        try:
                            sent_msg = await channel.send(line, reference=reference)
                            ids.append(str(sent_msg.id))
                            # Yield control to event loop to prevent heartbeat blocking
                            await asyncio.sleep(0)
                        except Exception as e:
                            log.error(f"Error sending line as bot: {e}")
        else:
            chunks = self._split_message(text, split_fn)
            for chunk in chunks:
                try:
                    sent_msg = await channel.send(chunk, reference=reference)
                    ids.append(str(sent_msg.id))
                    # Yield control to event loop
                    await asyncio.sleep(0)
                except Exception as e:
                    log.error(f"Error sending chunk as bot: {e}")
        
        return ids
    
    async def _send_as_webhook(
        self,
        text: str,
        webhook_url: str,
        reference: Optional[discord.Message],
        line_by_line: bool,
        split_fn: Optional[Callable[[str], List[str]]]
    ) -> List[str]:
        """Send message as webhook (reuses single HTTP session)."""
        ids = []
        
        # Reuse single HTTP session for all messages
        async with aiohttp.ClientSession() as http_session:
            webhook = discord.Webhook.from_url(webhook_url, session=http_session)
            
            if line_by_line:
                for line in text.split('\n'):
                    stripped = line.strip()
                    if stripped:
                        # Check if line exceeds Discord's 2000 char limit
                        if len(line) > 2000:
                            # Split long line into chunks
                            line_chunks = self._split_message(line, split_fn)
                            for chunk in line_chunks:
                                try:
                                    sent_msg = await webhook.send(chunk, wait=True)
                                    ids.append(str(sent_msg.id))
                                    # Yield control to event loop to prevent heartbeat blocking
                                    await asyncio.sleep(0)
                                except Exception as e:
                                    log.error(f"Error sending line chunk as webhook: {e}")
                        else:
                            try:
                                sent_msg = await webhook.send(line, wait=True)
                                ids.append(str(sent_msg.id))
                                # Yield control to event loop to prevent heartbeat blocking
                                await asyncio.sleep(0)
                            except Exception as e:
                                log.error(f"Error sending line as webhook: {e}")
            else:
                chunks = self._split_message(text, split_fn)
                for chunk in chunks:
                    try:
                        sent_msg = await webhook.send(chunk, wait=True)
                        ids.append(str(sent_msg.id))
                        # Yield control to event loop
                        await asyncio.sleep(0)
                    except Exception as e:
                        log.error(f"Error sending chunk as webhook: {e}")
        
        return ids
    
    def _split_message(
        self,
        text: str,
        split_fn: Optional[Callable[[str], List[str]]] = None
    ) -> List[str]:
        """
        Split message into chunks that fit Discord's 2000 char limit.
        
        Args:
            text: Text to split
            split_fn: Optional custom split function
            
        Returns:
            List of message chunks
        """
        if split_fn:
            return split_fn(text)
        
        # Simple splitting by 2000 chars
        if len(text) <= 2000:
            return [text]
        
        chunks = []
        for i in range(0, len(text), 2000):
            chunks.append(text[i:i+2000])
        return chunks
    
    def _process_text_for_editing(self, text: str) -> str:
        """
        Process text for editing by removing special syntax.
        
        When editing messages, we can't change Discord message properties
        (like reply references), so we remove special tags from the text.
        
        Uses existing text_processor functions for consistency.
        
        Args:
            text: Original text with potential special syntax
            
        Returns:
            Clean text without special syntax tags
        """
        from utils.text_processor import remove_reply_tags
        
        # Remove reply tags (can't change reply reference when editing)
        clean_text = remove_reply_tags(text)
        
        return clean_text
    
    async def set_generating_placeholder(
        self,
        channel: discord.TextChannel,
        message_ids: List[str],
        mode: str = "bot",
        webhook_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Edit first message to show "Generating..." and delete remaining messages.
        
        This provides visual feedback that a new response is being generated.
        
        Args:
            channel: Discord channel
            message_ids: List of message IDs to process
            mode: "bot" or "webhook"
            webhook_url: Webhook URL (required for webhook mode)
            
        Returns:
            ID of the first message (that was edited), or None if failed
        """
        if not message_ids:
            return None
        
        first_msg_id = message_ids[0]
        
        # Edit first message to "Generating..."
        try:
            if mode == "bot":
                message = await channel.fetch_message(int(first_msg_id))
                await message.edit(content="Generating...")
                log.debug(f"Edited message {first_msg_id} to show 'Generating...'")
            else:
                # Webhook mode
                if not webhook_url:
                    log.warning("Webhook mode selected but no webhook_url provided")
                    return None
                
                async with aiohttp.ClientSession() as http_session:
                    webhook = discord.Webhook.from_url(webhook_url, session=http_session)
                    message = await channel.fetch_message(int(first_msg_id))
                    await webhook.edit_message(int(first_msg_id), content="Generating...")
                    log.debug(f"Edited webhook message {first_msg_id} to show 'Generating...'")
        
        except discord.NotFound:
            log.warning(f"Message {first_msg_id} not found, cannot edit")
            return None
        except discord.Forbidden:
            log.warning(f"No permission to edit message {first_msg_id}")
            return None
        except Exception as e:
            log.error(f"Error editing message {first_msg_id}: {e}")
            return None
        
        # Delete remaining messages
        for msg_id in message_ids[1:]:
            try:
                message = await channel.fetch_message(int(msg_id))
                await message.delete()
                log.debug(f"Deleted extra message {msg_id}")
            except discord.NotFound:
                log.debug(f"Message {msg_id} already deleted")
            except discord.Forbidden:
                log.warning(f"No permission to delete message {msg_id}")
            except Exception as e:
                log.error(f"Error deleting message {msg_id}: {e}")
        
        return first_msg_id
    
    async def edit_messages(
        self,
        channel: discord.TextChannel,
        message_ids: List[str],
        new_text: str,
        mode: str = "bot",
        webhook_url: Optional[str] = None,
        split_message_fn: Optional[Callable[[str], List[str]]] = None
    ) -> List[str]:
        """
        Edit existing messages with new content.
        
        Strategy:
        - If new content fits in existing messages: edit them
        - If new content needs more messages: edit existing + create new
        - If new content needs fewer messages: edit needed + delete extras
        
        Note: Reply tags and other special syntax are stripped since Discord
        doesn't allow changing message properties when editing.
        
        Args:
            channel: Discord channel
            message_ids: List of existing message IDs
            new_text: New text content
            mode: "bot" or "webhook"
            webhook_url: Webhook URL (required for webhook mode)
            split_message_fn: Optional function to split long messages
            
        Returns:
            List of message IDs (edited + newly created)
        """
        if not message_ids:
            log.warning("No message IDs provided for editing, creating new messages")
            # Fallback: create new messages
            return await self._send_new_messages(
                new_text, channel, mode, webhook_url, split_message_fn
            )
        
        # Process text to remove reply tags and other special syntax
        # (can't change reply reference or other properties when editing)
        clean_text = self._process_text_for_editing(new_text)
        
        # Split new text into chunks
        chunks = self._split_message(clean_text, split_message_fn)
        result_ids = []
        
        # Edit existing messages
        for i, chunk in enumerate(chunks):
            if i < len(message_ids):
                # Edit existing message
                msg_id = message_ids[i]
                try:
                    if mode == "bot":
                        message = await channel.fetch_message(int(msg_id))
                        await message.edit(content=chunk)
                        result_ids.append(msg_id)
                        log.debug(f"Edited message {msg_id}")
                    else:
                        # Webhook mode
                        if not webhook_url:
                            log.warning("Webhook mode but no webhook_url, skipping edit")
                            continue
                        
                        async with aiohttp.ClientSession() as http_session:
                            webhook = discord.Webhook.from_url(webhook_url, session=http_session)
                            await webhook.edit_message(int(msg_id), content=chunk)
                            result_ids.append(msg_id)
                            log.debug(f"Edited webhook message {msg_id}")
                    
                    # Yield control to event loop
                    await asyncio.sleep(0)
                    
                except discord.NotFound:
                    log.warning(f"Message {msg_id} not found, creating new message")
                    # Create new message instead
                    new_id = await self._send_single_message(
                        chunk, channel, mode, webhook_url
                    )
                    if new_id:
                        result_ids.append(new_id)
                except discord.Forbidden:
                    log.warning(f"No permission to edit message {msg_id}, creating new")
                    new_id = await self._send_single_message(
                        chunk, channel, mode, webhook_url
                    )
                    if new_id:
                        result_ids.append(new_id)
                except Exception as e:
                    log.error(f"Error editing message {msg_id}: {e}")
                    # Try to create new message
                    new_id = await self._send_single_message(
                        chunk, channel, mode, webhook_url
                    )
                    if new_id:
                        result_ids.append(new_id)
            else:
                # Need more messages, create new ones
                new_id = await self._send_single_message(
                    chunk, channel, mode, webhook_url
                )
                if new_id:
                    result_ids.append(new_id)
        
        # Delete extra messages if new content is shorter
        if len(message_ids) > len(chunks):
            for msg_id in message_ids[len(chunks):]:
                try:
                    message = await channel.fetch_message(int(msg_id))
                    await message.delete()
                    log.debug(f"Deleted extra message {msg_id}")
                except Exception as e:
                    log.debug(f"Could not delete extra message {msg_id}: {e}")
        
        return result_ids
    
    async def _send_single_message(
        self,
        text: str,
        channel: discord.TextChannel,
        mode: str,
        webhook_url: Optional[str]
    ) -> Optional[str]:
        """Send a single message and return its ID."""
        try:
            if mode == "bot":
                sent_msg = await channel.send(text)
                return str(sent_msg.id)
            else:
                if not webhook_url:
                    return None
                async with aiohttp.ClientSession() as http_session:
                    webhook = discord.Webhook.from_url(webhook_url, session=http_session)
                    sent_msg = await webhook.send(text, wait=True)
                    return str(sent_msg.id)
        except Exception as e:
            log.error(f"Error sending single message: {e}")
            return None
    
    async def _send_new_messages(
        self,
        text: str,
        channel: discord.TextChannel,
        mode: str,
        webhook_url: Optional[str],
        split_message_fn: Optional[Callable[[str], List[str]]]
    ) -> List[str]:
        """Fallback: send as new messages."""
        chunks = self._split_message(text, split_message_fn)
        ids = []
        
        for chunk in chunks:
            msg_id = await self._send_single_message(chunk, channel, mode, webhook_url)
            if msg_id:
                ids.append(msg_id)
            await asyncio.sleep(0)
        
        return ids
    
    async def _convert_username_mentions(
        self,
        text: str,
        channel: discord.TextChannel
    ) -> str:
        """
        Convert @username mentions to proper Discord mentions <@user_id>.
        
        Args:
            text: Text containing potential @username mentions
            channel: Discord channel (to access guild members)
            
        Returns:
            Text with @username converted to <@user_id>
        """
        import re
        
        if not channel.guild:
            return text
        
        # Pattern to match @username (but not already formatted mentions)
        # Matches @word but not <@123> or <@!123>
        pattern = r'(?<!<)@([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)(?!\w)'
        
        def replace_mention(match):
            username = match.group(1).lower()
            
            # Search for member by username or display name (case-insensitive)
            for member in channel.guild.members:
                # Check username
                if member.name.lower() == username:
                    return f"<@{member.id}>"
                # Check display name (global_name)
                if hasattr(member, 'global_name') and member.global_name:
                    if member.global_name.lower() == username:
                        return f"<@{member.id}>"
                # Check server nickname
                if hasattr(member, 'nick') and member.nick:
                    if member.nick.lower() == username:
                        return f"<@{member.id}>"
            
            # If no match found, keep original
            return match.group(0)
        
        try:
            converted_text = re.sub(pattern, replace_mention, text)
            return converted_text
        except Exception as e:
            log.error(f"Error converting username mentions: {e}")
            return text


    async def _convert_custom_emojis(
        self,
        text: str,
        channel: discord.TextChannel
    ) -> str:
        """
        Convert :emoji_name: to <:emoji_name:id> or <a:emoji_name:id> for animated.
        
        Args:
            text: Text containing potential :emoji_name: references
            channel: Discord channel (to access guild emojis)
            
        Returns:
            Text with :emoji_name: converted to proper emoji format
        """
        import re
        
        if not channel.guild:
            return text
        
        # Pattern to match :emoji_name: (but not already formatted emojis)
        # Matches :word: but not <:word:id> or <a:word:id>
        pattern = r'(?<!<)(?<!<a):([a-zA-Z0-9_]+):(?!>|\d)'
        
        def replace_emoji(match):
            emoji_name = match.group(1)
            
            # Search for emoji by name (case-insensitive)
            for emoji in channel.guild.emojis:
                if emoji.name.lower() == emoji_name.lower():
                    if emoji.animated:
                        return f"<a:{emoji.name}:{emoji.id}>"
                    else:
                        return f"<:{emoji.name}:{emoji.id}>"
            
            # If no match found, keep original
            return match.group(0)
        
        try:
            converted_text = re.sub(pattern, replace_emoji, text)
            return converted_text
        except Exception as e:
            log.error(f"Error converting custom emojis: {e}")
            return text


# Global sender instance
_global_sender: Optional[MessageSender] = None


def get_message_sender() -> MessageSender:
    """Get the global message sender instance."""
    global _global_sender
    if _global_sender is None:
        _global_sender = MessageSender()
    return _global_sender
