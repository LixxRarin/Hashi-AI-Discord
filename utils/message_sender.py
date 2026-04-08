"""
Message Sender - Centralized Message Sending Logic

This module provides a unified interface for sending messages to Discord,
eliminating code duplication across app.py, AI_utils.py, and regenerate_commands.py.

Key Features:
- Supports bot mode and webhook mode
- Handles line-by-line and chunked sending
- Parses reply syntax automatically (via expressions system)
- Efficient HTTP session management
- Message splitting for Discord's 2000 char limit
"""

import asyncio
import aiohttp
import discord
from typing import List, Optional, Callable
import logging

from expressions import get_expression_registry
from expressions.reply_expression import ReplyExpression
from expressions.poll_expression import PollExpression
from expressions.block_expression import BlockExpression
from expressions.embed_expression import EmbedExpression
from utils.http_client import create_http_session, retry_on_network_error

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
        
        Uses the new expressions system to parse reactions.
        
        Args:
            response_text: Response text with possible reaction syntax
            channel: Discord channel
            session: AI session
            
        Returns:
            Tuple (clean_text, reactions_list)
            where reactions_list = [(message_id, emoji), ...]
        """
        config = session.get("config", {})
        registry = get_expression_registry()
        
        # Get reaction expression
        reaction_expr = registry.get('reaction')
        
        # Check if system is enabled
        if not reaction_expr or not reaction_expr.is_enabled(config):
            return response_text, []
        
        # Check if there's reaction syntax
        if not reaction_expr.has_syntax(response_text):
            return response_text, []
        
        # Parse reactions using expression system
        expr_result = reaction_expr.parse(response_text, config)
        reactions = expr_result.reactions
        
        # Remove syntax from text
        clean_text = reaction_expr.remove_syntax(response_text)
        
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
        try:
            # Fetch message (supports short IDs) using ReplyExpression
            message = await ReplyExpression.fetch_message_safe(
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
    
    async def _process_polls(
        self,
        response_text: str,
        channel: discord.TextChannel,
        session: dict
    ) -> tuple[str, List[str]]:
        """
        Process poll syntax, create polls, and return clean text + poll message IDs.
        
        Returns:
            Tuple (clean_text, poll_message_ids)
        """
        config = session.get("config", {})
        registry = get_expression_registry()
        
        poll_expr = registry.get('poll')
        
        if not poll_expr or not poll_expr.is_enabled(config):
            return response_text, []
        
        if not poll_expr.has_syntax(response_text):
            return response_text, []
        
        # Parse polls
        expr_result = poll_expr.parse(response_text, config)
        polls = expr_result.metadata.get('polls', [])
        
        poll_message_ids = []
        
        # Create each poll
        for poll_data in polls:
            if not poll_data.get('valid', False):
                log.warning(f"Skipping invalid poll: {poll_data.get('error')}")
                continue
            
            try:
                # Create Discord poll
                poll_msg_id = await self._create_discord_poll(
                    channel, poll_data
                )
                if poll_msg_id:
                    poll_message_ids.append(poll_msg_id)
            except Exception as e:
                log.error(f"Error creating poll: {e}", exc_info=True)
        
        # Remove poll syntax from text
        clean_text = poll_expr.remove_syntax(response_text)
        
        return clean_text, poll_message_ids
    
    async def _create_discord_poll(
        self,
        channel: discord.TextChannel,
        poll_data: dict
    ) -> Optional[str]:
        """
        Create a Discord poll and return its message ID.
        """
        try:
            import datetime
            
            question = poll_data['question']
            options = poll_data['options']
            duration_hours = poll_data['duration_hours']
            allow_multiple = poll_data['allow_multiple']
            
            # Create poll (discord.py 2.7+ API)
            poll = discord.Poll(
                question=question,
                duration=datetime.timedelta(hours=duration_hours),
                multiple=allow_multiple
            )
            
            # Add answers using poll.add_answer()
            for opt in options:
                poll.add_answer(text=opt)
            
            # Send poll
            message = await channel.send(poll=poll)
            
            log.info(f"Created poll '{question}' with {len(options)} options, {duration_hours}h duration")
            
            return str(message.id)
            
        except Exception as e:
            log.error(f"Error creating Discord poll: {e}", exc_info=True)
            return None
    
    async def _process_embeds(
        self,
        response_text: str,
        channel: discord.TextChannel,
        session: dict
    ) -> tuple[str, List[str]]:
        """
        Process embed syntax, create embeds, and return clean text + embed message IDs.
        
        Returns:
            Tuple (clean_text, embed_message_ids)
        """
        config = session.get("config", {})
        registry = get_expression_registry()
        
        embed_expr = registry.get('embed')
        
        if not embed_expr or not embed_expr.is_enabled(config):
            return response_text, []
        
        if not embed_expr.has_syntax(response_text):
            return response_text, []
        
        # Parse embeds
        expr_result = embed_expr.parse(response_text, config)
        embeds = expr_result.metadata.get('embeds', [])
        
        embed_message_ids = []
        
        # Create each embed
        for embed_data in embeds:
            if not embed_data.get('valid', False):
                log.warning(f"Skipping invalid embed: {embed_data.get('error')}")
                continue
            
            try:
                # Create Discord embed
                embed_msg_id = await self._create_discord_embed(
                    channel, embed_data['json_data']
                )
                if embed_msg_id:
                    embed_message_ids.append(embed_msg_id)
            except Exception as e:
                log.error(f"Error creating embed: {e}", exc_info=True)
        
        # Remove embed syntax from text
        clean_text = embed_expr.remove_syntax(response_text)
        
        return clean_text, embed_message_ids
    
    async def _create_discord_embed(
        self,
        channel: discord.TextChannel,
        embed_data: dict
    ) -> Optional[str]:
        """
        Create a Discord embed and return its message ID.
        """
        try:
            embed = discord.Embed()
            
            # Set basic properties
            if 'title' in embed_data:
                embed.title = embed_data['title']
            
            if 'description' in embed_data:
                embed.description = embed_data['description']
            
            if 'color' in embed_data:
                embed.color = discord.Color(embed_data['color'])
            
            if 'url' in embed_data:
                embed.url = embed_data['url']
            
            # Add fields
            if 'fields' in embed_data:
                for field in embed_data['fields']:
                    embed.add_field(
                        name=field['name'],
                        value=field['value'],
                        inline=field.get('inline', False)
                    )
            
            # Set footer
            if 'footer' in embed_data:
                footer = embed_data['footer']
                embed.set_footer(
                    text=footer.get('text', ''),
                    icon_url=footer.get('icon_url')
                )
            
            # Set author
            if 'author' in embed_data:
                author = embed_data['author']
                embed.set_author(
                    name=author.get('name', ''),
                    url=author.get('url'),
                    icon_url=author.get('icon_url')
                )
            
            # Set thumbnail
            if 'thumbnail' in embed_data:
                embed.set_thumbnail(url=embed_data['thumbnail']['url'])
            
            # Set image
            if 'image' in embed_data:
                embed.set_image(url=embed_data['image']['url'])
            
            # Send embed
            message = await channel.send(embed=embed)
            
            log.info(f"Created embed: {embed_data.get('title', 'Untitled')}")
            
            return str(message.id)
            
        except Exception as e:
            log.error(f"Error creating Discord embed: {e}", exc_info=True)
            return None
    
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
        config = session.get("config", {})
        
        # Extract context for short ID conversion
        server_id = session.get("server_id")
        ai_name = session.get("ai_name")
        
        # Process reactions FIRST (before emoji conversion)
        # This extracts reaction syntax and returns clean text + reactions list
        response_text, reactions = await self._process_reactions(response_text, channel, session)
        
        # Process polls (creates poll messages)
        response_text, poll_ids = await self._process_polls(response_text, channel, session)
        
        # Process embeds (creates embed messages)
        response_text, embed_ids = await self._process_embeds(response_text, channel, session)
        
        
        # Convert @username mentions to proper Discord mentions
        response_text = await self._convert_username_mentions(response_text, channel)
        
        # Convert :emoji_name: to proper Discord emoji format
        response_text = await self._convert_custom_emojis(response_text, channel)
        
        discord_ids = []
        
        # Add poll and embed message IDs to the list
        discord_ids.extend(poll_ids)
        discord_ids.extend(embed_ids)
        
        # Process BLOCK tags BEFORE reply parsing
        # This prevents reply parsing from splitting BLOCK tags across segments
        registry = get_expression_registry()
        block_expr = registry.get('block')
        
        block_segments = []  # List of (text, is_block, needs_reply_parsing)
        
        if block_expr and block_expr.has_syntax(response_text):
            if is_line_by_line:
                # Split by BLOCK boundaries, tags are removed by split_text_with_blocks
                raw_segments = block_expr.split_text_with_blocks(response_text, is_line_by_line)
                for segment_text, is_block in raw_segments:
                    # BLOCK segments: no reply parsing
                    # Non-BLOCK segments: need reply parsing
                    block_segments.append((segment_text, is_block, not is_block))
                log.debug(f"Split text into {len(block_segments)} BLOCK segments")
            else:
                # line_by_line disabled: just remove BLOCK tags
                response_text = block_expr.remove_syntax(response_text)
                block_segments.append((response_text, False, True))
                log.debug("Removed BLOCK tags (line_by_line=False)")
        else:
            # No BLOCK tags: process normally
            block_segments.append((response_text, False, True))
        
        # Process each BLOCK segment
        # First pass: detect REPLY tags before BLOCK segments and merge them
        processed_segments = []
        skip_next = False
        
        for i, (segment_text, is_block, needs_reply_parsing) in enumerate(block_segments):
            # Skip if marked from previous iteration
            if skip_next:
                skip_next = False
                continue
                
            if not segment_text or segment_text.isspace():
                continue
            
            # Check if this is a non-BLOCK segment with only REPLY tag(s)
            if not is_block and needs_reply_parsing:
                reply_expr = registry.get('reply')
                if reply_expr and reply_expr.has_syntax(segment_text):
                    # Check if text after removing REPLY is empty/whitespace
                    text_without_reply = reply_expr.remove_syntax(segment_text)
                    if not text_without_reply or text_without_reply.isspace():
                        # This segment is ONLY reply tags
                        # Check if next segment is BLOCK BEFORE parsing (to avoid warnings)
                        has_block_following = False
                        if i + 1 < len(block_segments):
                            next_segment = block_segments[i + 1]
                            has_block_following = next_segment[1]  # next is a BLOCK
                        
                        if has_block_following:
                            # Transfer REPLY to the BLOCK segment
                            # Extract reply ID using regex to avoid parse warnings
                            import re
                            reply_match = re.search(r'<REPLY:(\d+)>', segment_text)
                            if reply_match:
                                reply_id = reply_match.group(1)
                                # Add BLOCK with reply info
                                processed_segments.append((block_segments[i + 1][0], True, False, reply_id))
                                # Skip the next segment since we already processed it
                                skip_next = True
                                log.debug(f"Merged REPLY:{reply_id} with following BLOCK segment")
                                continue
                        
                        # REPLY-only segment with no BLOCK following - skip it silently
                        # (LLM probably made a mistake - wanted to reply but provided no content)
                        log.debug(f"Skipping REPLY-only segment with no content and no following BLOCK")
                        continue
            
            processed_segments.append((segment_text, is_block, needs_reply_parsing, None))
        
        # Second pass: send messages
        for segment_text, is_block, needs_reply_parsing, reply_id_for_block in processed_segments:
            if not segment_text or segment_text.isspace():
                continue
            
            if needs_reply_parsing:
                # Parse reply syntax for non-BLOCK segments
                reply_expr = registry.get('reply')
                reply_segments = [(None, segment_text)]
                if reply_expr and reply_expr.is_enabled(config):
                    reply_segments = reply_expr.parse_reply_syntax(segment_text)
                
                # Send each reply segment
                for segment_message_id, segment_reply_text in reply_segments:
                    if not segment_reply_text or segment_reply_text.isspace():
                        continue
                    
                    # Get reference message if needed
                    reference_message = None
                    if segment_message_id:
                        reference_message = await ReplyExpression.fetch_message_safe(
                            channel, segment_message_id,
                            server_id=server_id,
                            ai_name=ai_name
                        )
                    
                    # Send based on mode
                    if mode == "bot":
                        ids = await self._send_as_bot(
                            segment_reply_text, channel, reference_message,
                            is_line_by_line, split_message_fn, view=None
                        )
                        discord_ids.extend(ids)
                    else:
                        # Webhook mode
                        if webhook_url:
                            ids = await self._send_as_webhook(
                                segment_reply_text, webhook_url, reference_message,
                                is_line_by_line, split_message_fn, view=None
                            )
                            discord_ids.extend(ids)
                        else:
                            log.warning("Webhook mode selected but no webhook_url configured")
            else:
                # BLOCK segment: send directly without reply parsing or line splitting
                # Remove any REPLY tags that might be inside BLOCK segments
                # (BLOCK segments don't support reply functionality inside them)
                reply_expr = registry.get('reply')
                clean_segment_text = segment_text
                if reply_expr and reply_expr.has_syntax(segment_text):
                    clean_segment_text = reply_expr.remove_syntax(segment_text)
                    log.debug("Removed REPLY tags from inside BLOCK segment")
                
                # Check if this BLOCK should be sent as a reply (from preceding REPLY tag)
                reference_message = None
                if reply_id_for_block:
                    reference_message = await ReplyExpression.fetch_message_safe(
                        channel, reply_id_for_block,
                        server_id=server_id,
                        ai_name=ai_name
                    )
                    log.debug(f"BLOCK segment will reply to message {reply_id_for_block}")
                
                # Send based on mode
                if mode == "bot":
                    ids = await self._send_as_bot(
                        clean_segment_text, channel, reference_message,
                        False, split_message_fn, view=None  # Force line_by_line=False for blocks
                    )
                    discord_ids.extend(ids)
                else:
                    # Webhook mode
                    if webhook_url:
                        ids = await self._send_as_webhook(
                            clean_segment_text, webhook_url, reference_message,
                            False, split_message_fn, view=None  # Force line_by_line=False for blocks
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
                    from utils.discord.message_actions import MessageActionsView
                    
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
        """
        Send message as bot. View is attached to last message only.
        
        Note: BLOCK processing is now handled in send() before this method is called.
        """
        ids = []
        
        if line_by_line:
            # Send line by line
            for line in text.split('\n'):
                stripped = line.strip()
                if stripped:
                    if len(line) > 2000:
                        line_chunks = self._split_message(line, split_fn)
                        for chunk in line_chunks:
                            try:
                                sent_msg = await channel.send(chunk, reference=reference)
                                ids.append(str(sent_msg.id))
                                await asyncio.sleep(0)
                            except Exception as e:
                                log.error(f"Error sending line chunk as bot: {e}")
                    else:
                        try:
                            sent_msg = await channel.send(line, reference=reference)
                            ids.append(str(sent_msg.id))
                            await asyncio.sleep(0)
                        except Exception as e:
                            log.error(f"Error sending line as bot: {e}")
        else:
            # Send as chunks
            chunks = self._split_message(text, split_fn)
            for chunk in chunks:
                try:
                    sent_msg = await channel.send(chunk, reference=reference)
                    ids.append(str(sent_msg.id))
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
        """
        Send message as webhook (reuses single HTTP session). View is attached to last message only.
        
        Note: BLOCK processing is now handled in send() before this method is called.
        """
        ids = []
        
        # Reuse single HTTP session for all messages with proper configuration
        async with create_http_session() as http_session:
            webhook = discord.Webhook.from_url(webhook_url, session=http_session)
            
            if line_by_line:
                # Send line by line
                for line in text.split('\n'):
                    stripped = line.strip()
                    if stripped:
                        if len(line) > 2000:
                            line_chunks = self._split_message(line, split_fn)
                            for chunk in line_chunks:
                                try:
                                    sent_msg = await self._send_webhook_with_retry(webhook, chunk)
                                    if sent_msg:
                                        ids.append(str(sent_msg.id))
                                    await asyncio.sleep(0)
                                except Exception as e:
                                    log.error(f"Error sending line chunk as webhook: {e}", exc_info=True)
                        else:
                            try:
                                sent_msg = await self._send_webhook_with_retry(webhook, line)
                                if sent_msg:
                                    ids.append(str(sent_msg.id))
                                await asyncio.sleep(0)
                            except Exception as e:
                                log.error(f"Error sending line as webhook: {e}", exc_info=True)
            else:
                # Send as chunks
                chunks = self._split_message(text, split_fn)
                for chunk in chunks:
                    try:
                        sent_msg = await self._send_webhook_with_retry(webhook, chunk)
                        if sent_msg:
                            ids.append(str(sent_msg.id))
                        await asyncio.sleep(0)
                    except Exception as e:
                        log.error(f"Error sending chunk as webhook: {e}", exc_info=True)
        
        return ids
    
    @retry_on_network_error(max_attempts=3, base_delay=1.0)
    async def _send_webhook_with_retry(
        self,
        webhook: discord.Webhook,
        content: str
    ) -> Optional[discord.Message]:
        """
        Send a webhook message with automatic retry on network errors.
        
        Args:
            webhook: Discord webhook object
            content: Message content to send
            
        Returns:
            Sent message or None if failed
        """
        try:
            return await webhook.send(content, wait=True)
        except discord.HTTPException as e:
            log.error(f"Discord HTTP error sending webhook message: {e}")
            # Don't retry on Discord API errors (rate limits, permissions, etc)
            return None
        except Exception as e:
            log.error(f"Unexpected error sending webhook message: {e}")
            raise
    
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
        from utils.text.processor import remove_reply_tags
        
        # Remove reply tags (can't change reply reference when editing)
        clean_text = remove_reply_tags(text)
        
        # Remove BLOCK tags (tags should never be visible in Discord)
        registry = get_expression_registry()
        block_expr = registry.get('block')
        if block_expr and block_expr.has_syntax(clean_text):
            clean_text = block_expr.remove_syntax(clean_text)
        
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
                    await message.edit(content="> Generating...")
                    log.debug(f"Edited message {first_msg_id} to show 'Generating...'")
            else:
                # Webhook mode
                if not webhook_url:
                    log.warning("Webhook mode selected but no webhook_url provided")
                    return None
                
                async with create_http_session() as http_session:
                    webhook = discord.Webhook.from_url(webhook_url, session=http_session)
                    message = await fetch_message_cached(channel, first_msg_id)
                    if message:
                        await webhook.edit_message(int(first_msg_id), content="> Generating...")
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
        - If new content needs more messages: edit existing create new
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
                        
                        async with create_http_session() as http_session:
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
                async with create_http_session() as http_session:
                    webhook = discord.Webhook.from_url(webhook_url, session=http_session)
                    sent_msg = await self._send_webhook_with_retry(webhook, text)
                    return str(sent_msg.id) if sent_msg else None
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
    
    async def send_with_attachment(
        self,
        channel: discord.TextChannel,
        file: discord.File,
        content: Optional[str] = None,
        reference: Optional[discord.Message] = None,
        spoiler: bool = False,
        session: Optional[dict] = None
    ) -> Optional[str]:
        """
        Send a message with an attachment.
        
        Args:
            channel: Discord channel to send to
            file: discord.File object to send
            content: Optional text content
            reference: Optional message to reply to
            spoiler: Mark attachment as spoiler
            session: Optional session for mode detection
            
        Returns:
            Message ID or None if failed
        """
        try:
            # Set spoiler if requested
            if spoiler:
                file.spoiler = True
            
            # Determine mode
            mode = "bot"
            webhook_url = None
            if session:
                mode = session.get("mode", "bot")
                webhook_url = session.get("webhook_url")
            
            # Send based on mode
            if mode == "bot":
                # Bot mode: use channel.send
                sent_msg = await channel.send(
                    content=content,
                    file=file,
                    reference=reference
                )
                log.info(f"Sent attachment via bot: {file.filename} ({sent_msg.id})")
                return str(sent_msg.id)
            else:
                # Webhook mode
                if not webhook_url:
                    log.error("Webhook mode selected but no webhook_url provided")
                    return None
                
                async with create_http_session() as http_session:
                    webhook = discord.Webhook.from_url(webhook_url, session=http_session)
                    
                    # Note: Webhooks don't support reply references
                    # We'll send without reference in webhook mode
                    sent_msg = await webhook.send(
                        content=content,
                        file=file,
                        wait=True
                    )
                    log.info(f"Sent attachment via webhook: {file.filename} ({sent_msg.id})")
                    return str(sent_msg.id)
        
        except discord.HTTPException as e:
            log.error(f"Discord HTTP error sending attachment: {e}")
            return None
        except Exception as e:
            log.error(f"Error sending attachment: {e}", exc_info=True)
            return None


# Global sender instance
_global_sender: Optional[MessageSender] = None


def get_message_sender() -> MessageSender:
    """Get the global message sender instance."""
    global _global_sender
    if _global_sender is None:
        _global_sender = MessageSender()
    return _global_sender
