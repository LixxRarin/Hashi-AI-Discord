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
    
    async def _process_reactions(
        self,
        response_text: str,
        channel: discord.TextChannel,
        session: dict
    ) -> tuple[str, List[tuple[str, str]]]:
        """
        Process reaction syntax and return clean text + list of reactions.
        
        Args:
            response_text: Response text with possible reaction syntax
            channel: Discord channel
            session: AI session
            
        Returns:
            Tuple (clean_text, reactions_list)
            where reactions_list = [(message_id, emoji), ...]
        """
        from utils.reaction_parser import ReactionParser
        
        # Check if system is enabled
        enable_reaction_system = session.get("config", {}).get("enable_reaction_system", False)
        
        if not enable_reaction_system:
            return response_text, []
        
        # Check if there's reaction syntax
        if not ReactionParser.has_reaction_syntax(response_text):
            return response_text, []
        
        # Extract reactions
        reactions = ReactionParser.parse_reactions(response_text)
        
        # Remove syntax from text
        clean_text = ReactionParser.remove_reaction_syntax(response_text)
        
        log.debug(f"Extracted {len(reactions)} reaction(s) from response")
        
        return clean_text, reactions
    
    async def _process_emoji_for_reaction(
        self,
        emoji: str,
        channel: discord.TextChannel
    ) -> Optional[str]:
        """
        Process emoji to appropriate format for add_reaction().
        
        Args:
            emoji: Emoji in :name: format or unicode
            channel: Discord channel
            
        Returns:
            Processed emoji or None if invalid
        """
        # If it's a custom emoji (:name:)
        if emoji.startswith(':') and emoji.endswith(':'):
            emoji_name = emoji[1:-1]  # Remove the :
            
            if not channel.guild:
                return None
            
            # Search for emoji in guild
            for guild_emoji in channel.guild.emojis:
                if guild_emoji.name.lower() == emoji_name.lower():
                    return guild_emoji
            
            # Custom emoji not found
            log.warning(f"Custom emoji {emoji} not found in guild")
            return None
        
        # It's a standard emoji (unicode)
        return emoji
    
    async def _add_reaction_to_message(
        self,
        channel: discord.TextChannel,
        message_id: str,
        emoji: str,
        server_id: str,
        ai_name: str
    ) -> bool:
        """
        Add a reaction to a specific message.
        
        Args:
            channel: Discord channel
            message_id: Message ID (short or full)
            emoji: Emoji to react with (:name: or unicode)
            server_id: Server ID
            ai_name: AI name
            
        Returns:
            True if successful, False if failed
        """
        from utils.reply_parser import ReplyParser
        
        try:
            # Fetch message (supports short IDs)
            message = await ReplyParser.fetch_message_safe(
                channel, message_id,
                server_id=server_id,
                ai_name=ai_name
            )
            
            if not message:
                log.warning(f"Message {message_id} not found for reaction")
                return False
            
            # Process emoji
            processed_emoji = await self._process_emoji_for_reaction(emoji, channel)
            
            if not processed_emoji:
                log.warning(f"Invalid emoji: {emoji}")
                return False
            
            # Add reaction
            await message.add_reaction(processed_emoji)
            log.debug(f"Added reaction {emoji} to message {message_id}")
            return True
            
        except discord.Forbidden:
            log.warning(f"No permission to add reaction to message {message_id}")
            return False
        except discord.HTTPException as e:
            log.error(f"HTTP error adding reaction: {e}")
            return False
        except Exception as e:
            log.error(f"Error adding reaction to message {message_id}: {e}")
            return False
    
    async def send(
        self,
        response_text: str,
        channel: discord.TextChannel,
        session: dict,
        split_message_fn: Optional[Callable[[str], List[str]]] = None,
        bot = None,
        attach_buttons: bool = True
    ) -> tuple[List[str], Optional[discord.ui.View]]:
        """
        Send a message to Discord using the appropriate method.
        
        Args:
            response_text: The text to send
            channel: Discord channel to send to
            session: AI session configuration
            split_message_fn: Optional function to split long messages
                            If None, uses simple 2000-char splitting
            bot: Bot instance (required for action buttons)
            attach_buttons: Whether to attach buttons immediately (default: True)
            
        Returns:
            Tuple of (discord_ids, view) where view is the MessageActionsView or None
        """
        mode = session.get("mode", "webhook")
        is_line_by_line = session.get("config", {}).get("send_message_line_by_line", False)
        webhook_url = session.get("webhook_url")
        enable_reply_system = session.get("config", {}).get("enable_reply_system", False)
        
        # Extract context for short ID conversion
        server_id = session.get("server_id")
        ai_name = session.get("ai_name")
        
        # Process reactions FIRST (before emoji conversion)
        # This extracts reaction syntax and returns clean text + reactions list
        response_text, reactions = await self._process_reactions(response_text, channel, session)
        
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
            
            # Send based on mode (without view for now)
            if mode == "bot":
                ids = await self._send_as_bot(
                    segment_text, channel, reference_message,
                    is_line_by_line, split_message_fn, view=None
                )
                discord_ids.extend(ids)
            else:
                # Webhook mode
                if webhook_url:
                    ids = await self._send_as_webhook(
                        segment_text, webhook_url, reference_message,
                        is_line_by_line, split_message_fn, view=None
                    )
                    discord_ids.extend(ids)
                else:
                    log.warning("Webhook mode selected but no webhook_url configured")
        
        # Create and attach view to the last message if buttons are enabled
        view = None
        if discord_ids and bot and attach_buttons:
            button_config = session.get("config", {}).get("message_action_buttons", {})
            if button_config.get("enabled", False):
                try:
                    from utils.message_actions import MessageActionsView
                    
                    view = MessageActionsView(
                        bot=bot,
                        server_id=server_id,
                        channel_id=str(channel.id),
                        ai_name=ai_name,
                        session=session,
                        timeout=None  # Persistent buttons
                    )
                    
                    # Edit the last message to attach the view
                    last_msg_id = discord_ids[-1]
                    try:
                        from utils.message_cache import fetch_message_cached
                        last_msg = await fetch_message_cached(channel, last_msg_id)
                        if last_msg:
                            await last_msg.edit(view=view)
                            log.debug(f"Attached action buttons to message {last_msg_id}")
                        else:
                            view = None
                    except Exception as e:
                        log.error(f"Error attaching buttons to message: {e}")
                        view = None
                        
                except Exception as e:
                    log.error(f"Error creating MessageActionsView: {e}")
                    view = None
        
        # Add reactions to target messages (if any)
        if reactions:
            log.debug(f"Processing {len(reactions)} reaction(s)")
            for message_id, emoji in reactions:
                await self._add_reaction_to_message(
                    channel, message_id, emoji, server_id, ai_name
                )
        
        return discord_ids, view
    
    async def _send_as_bot(
        self,
        text: str,
        channel: discord.TextChannel,
        reference: Optional[discord.Message],
        line_by_line: bool,
        split_fn: Optional[Callable[[str], List[str]]],
        view: Optional[discord.ui.View] = None
    ) -> List[str]:
        """Send message as bot. View is attached to last message only."""
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
        split_fn: Optional[Callable[[str], List[str]]],
        view: Optional[discord.ui.View] = None
    ) -> List[str]:
        """Send message as webhook (reuses single HTTP session). View is attached to last message only."""
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
            from utils.message_cache import fetch_message_cached
            
            if mode == "bot":
                message = await fetch_message_cached(channel, first_msg_id)
                if message:
                    await message.edit(content="Generating...")
                    log.debug(f"Edited message {first_msg_id} to show 'Generating...'")
            else:
                # Webhook mode
                if not webhook_url:
                    log.warning("Webhook mode selected but no webhook_url provided")
                    return None
                
                async with aiohttp.ClientSession() as http_session:
                    webhook = discord.Webhook.from_url(webhook_url, session=http_session)
                    message = await fetch_message_cached(channel, first_msg_id)
                    if message:
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
                from utils.message_cache import fetch_message_cached
                message = await fetch_message_cached(channel, msg_id)
                if message:
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
                    from utils.message_cache import fetch_message_cached
                    
                    if mode == "bot":
                        message = await fetch_message_cached(channel, msg_id)
                        if message:
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
                    from utils.message_cache import fetch_message_cached
                    message = await fetch_message_cached(channel, msg_id)
                    if message:
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
