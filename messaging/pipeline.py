"""
Message Pipeline - Main Orchestrator

Provides the main orchestrator that ties all messaging components together
into a unified pipeline for processing Discord messages and generating AI responses.
"""

import asyncio
import logging
import re
from typing import Dict, Any, Optional, List, Callable, Awaitable, Tuple
import discord

from messaging.buffer import MessageBuffer, PendingMessage, get_buffer
from messaging.intake import MessageIntake, MessageMetadata, get_intake
from messaging.timing import TimingController, get_timing_controller
from messaging.processor import MessageProcessor, get_processor
from messaging.store import ConversationStore, get_store
from messaging.response import ResponseManager, get_response_manager
from AI.response_filter import get_response_filter
from expressions import get_expression_registry

log = logging.getLogger(__name__)


class MessagePipeline:
    """Main orchestrator for the messaging system providing a clean flow: Discord → Intake → Buffer → Timing → Processor → API → Store → Discord"""

    def __init__(
        self,
        buffer: Optional[MessageBuffer] = None,
        intake: Optional[MessageIntake] = None,
        timing: Optional[TimingController] = None,
        processor: Optional[MessageProcessor] = None,
        response_manager: Optional[ResponseManager] = None,
        bot_client: Optional[Any] = None
    ):
        """Initialize the message pipeline with optional component overrides."""
        self.buffer = buffer or get_buffer()
        self.intake = intake or get_intake()
        self.timing = timing or get_timing_controller()
        self.processor = processor or get_processor()
        self.response_manager = response_manager or get_response_manager()
        self.bot_client = bot_client

    async def initialize(self) -> None:
        """Initialize the pipeline and load data."""
        # Stores are now loaded lazily per channel when first accessed
        pass
    
    def _check_wakeup_patterns(
        self,
        message_content: str,
        ai_name: str,
        is_mentioned: bool,
        is_reply_to_bot: bool,
        patterns: List[str]
    ) -> bool:
        """
        Check if message matches any wake-up pattern.
        
        This is a wrapper around the utility function for backward compatibility.
        
        Args:
            message_content: The message content to check
            ai_name: Name of the AI
            is_mentioned: Whether AI was mentioned
            is_reply_to_bot: Whether message is a reply to bot
            patterns: List of wake-up patterns (placeholders or regex)
            
        Returns:
            True if any pattern matches
        """
        from utils.sleep_mode_utils import check_wakeup_patterns
        
        return check_wakeup_patterns(
            message_content,
            ai_name,
            is_mentioned,
            is_reply_to_bot,
            patterns
        )
    
    async def process_message(
        self,
        message: discord.Message,
        bot_user_id: int,
        session_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Process an incoming Discord message and add to buffer for each AI."""
        metadata = await self.intake.process(message, bot_user_id, session_data)
        
        if not metadata:
            return False
        
        if not session_data:
            return False
        
        for ai_name, ai_session in session_data.items():
            # Validate for this specific AI
            if not self.intake.validate_for_ai(metadata, ai_session):
                continue
            
            # Ensure session has server_id, channel_id, ai_name for short ID mapping
            session_with_context = ai_session.copy()
            session_with_context["server_id"] = metadata.server_id
            session_with_context["channel_id"] = metadata.channel_id
            session_with_context["ai_name"] = ai_name
            
            # Create the message object
            msg_to_format = PendingMessage(
                content=metadata.content,
                author_id=metadata.author_id,
                author_name=metadata.author_name,
                author_display_name=metadata.author_display_name,
                timestamp=metadata.timestamp,
                message_id=metadata.message_id,
                reply_to=metadata.reply_to_id,
                attachments=metadata.attachments,
                stickers=metadata.stickers,
                raw_message=metadata.raw_message
            )
            
            # If this is a reply, create a reply_message object
            reply_msg = None
            if metadata.reply_to_id and metadata.reply_to_content:
                # Create a dummy PendingMessage for the reply target
                # Determine author name: if replying to bot, use AI name; otherwise use captured author name
                reply_author_name = ai_name if metadata.reply_to_is_bot else (metadata.reply_to_author_name or "Unknown")
                
                reply_msg = PendingMessage(
                    content=metadata.reply_to_content,
                    author_id="",  # Not available
                    author_name=reply_author_name,
                    author_display_name=reply_author_name,
                    timestamp=metadata.timestamp,  # Use same timestamp
                    message_id=metadata.reply_to_id,
                    reply_to=None,
                    raw_message=None
                )
            
            # Format the message with reply info if available
            formatted_content = await self.processor.format_single_message(
                msg_to_format,
                session_with_context,
                reply_msg
            )
            
            # Create pending message with formatted content
            pending_msg = PendingMessage(
                content=formatted_content,
                author_id=metadata.author_id,
                author_name=metadata.author_name,
                author_display_name=metadata.author_display_name,
                timestamp=metadata.timestamp,
                message_id=metadata.message_id,
                reply_to=metadata.reply_to_id,
                attachments=metadata.attachments,
                stickers=metadata.stickers,
                raw_message=metadata.raw_message,
                reply_to_content=metadata.reply_to_content,
                reply_to_author=metadata.reply_to_author_name,
                reply_to_is_bot=metadata.reply_to_is_bot
            )
            
            # Add to buffer
            await self.buffer.add_message(
                metadata.server_id,
                metadata.channel_id,
                ai_name,
                pending_msg
            )
                      
            # Get the short ID that was assigned during formatting
            short_id = await self.processor.short_id_manager.get_short_id(
                metadata.server_id,
                metadata.channel_id,
                ai_name,
                metadata.message_id
            )
            
            # Resolve reply_to_short_id if this is a reply
            reply_to_short_id = None
            if metadata.reply_to_id:
                reply_to_short_id = await self.processor.short_id_manager.get_short_id(
                    metadata.server_id,
                    metadata.channel_id,
                    ai_name,
                    metadata.reply_to_id
                )
            
            # Save to conversation history immediately
            store = get_store(metadata.server_id, metadata.channel_id)
            await store.add_user_message(
                metadata.server_id,
                metadata.channel_id,
                ai_name,
                formatted_content,  # Formatted content (with timestamps, etc.)
                metadata.message_id,
                session_with_context.get("chat_id", "default"),
                author_id=metadata.author_id,
                author_username=metadata.author_name,
                author_display_name=metadata.author_display_name,
                short_id=short_id,
                attachments=metadata.attachments,
                stickers=metadata.stickers,
                reply_to_id=metadata.reply_to_id,
                reply_to_short_id=reply_to_short_id,
                reply_to_content=metadata.reply_to_content,
                reply_to_author=metadata.reply_to_author_name,
                reply_to_is_bot=metadata.reply_to_is_bot,
                raw_content=metadata.content  # Raw Discord message content (for accurate edit tracking)
            )
        
        return True
    
    async def should_respond(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any]
    ) -> bool:
        """
        Check if AI should respond now.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            session: AI session data
            
        Returns:
            True if should respond
        """
        return await self.timing.should_respond(
            server_id, channel_id, ai_name, session, self.buffer
        )
    
    async def generate_response(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any],
        chat_service,
        send_callback: Callable[[str, List[str]], Awaitable[None]],
        bot_user_id: Optional[int] = None,
        is_regeneration: bool = False
    ) -> Optional[Tuple[str, List[str]]]:
        """
        Generate AI response for pending messages and save to history.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            session: AI session data
            chat_service: Chat service instance
            send_callback: Callback to send response to Discord
            bot_user_id: Bot user ID for mentions/replies
            is_regeneration: If True, preserve existing generations in ResponseManager
        
        Returns:
            Tuple of (response_text, discord_ids) or None
        """
        session_with_context = session.copy()
        session_with_context["server_id"] = server_id
        session_with_context["channel_id"] = channel_id
        session_with_context["ai_name"] = ai_name

        # Processing flag is now set in timing.py BEFORE calling this callback
        # No need to check here - it would block legitimate responses

        pending = await self.buffer.get_pending(server_id, channel_id, ai_name)
        
        if not pending:
            return None
        
        processing_message_ids = [msg.message_id for msg in pending]
        
        config = session_with_context.get("config", {})
        
        # Ensure only one sleep mode system is active at a time
        # Priority: ignore system > response filter
        registry = get_expression_registry()
        ignore_expr = registry.get('ignore')
        ignore_enabled = ignore_expr.is_enabled(config) if ignore_expr else False
        
        if ignore_enabled and config.get("use_response_filter", False):
            log.warning(
                f"Both ignore system and response filter are enabled for AI {ai_name}! "
                f"Disabling response filter (ignore system takes precedence)."
            )
            config["use_response_filter"] = False
        
        # IGNORE SYSTEM SLEEP MODE CHECK
        # This handles sleep mode when using <IGNORE> tags
        if ignore_enabled and config.get("sleep_mode_enabled", False):
            from utils.sleep_mode_utils import should_wake_from_sleep
            
            in_sleep, should_wake = await should_wake_from_sleep(
                server_id,
                channel_id,
                ai_name,
                session_with_context,
                pending,
                bot_user_id
            )
            
            if in_sleep and not should_wake:
                # AI is in sleep mode and no wake-up pattern found
                log.debug("AI staying in ignore-based sleep mode (no wake-up pattern matched)")
                await self.buffer.clear_specific_messages(
                    server_id, channel_id, ai_name, processing_message_ids
                )
                return None
            
            if in_sleep and should_wake:
                # AI is waking up from sleep mode
                log.info("AI waking up from ignore-based sleep mode (wake-up pattern detected)")
                # The should_wake_from_sleep function doesn't modify state, so we need to do it here
                import time
                response_filter = get_response_filter()
                state_key = (server_id, channel_id, ai_name)
                
                if state_key in response_filter.sleep_state:
                    state = response_filter.sleep_state[state_key]
                    state["in_sleep_mode"] = False
                    state["consecutive_refusals"] = 0
                    state["last_activity"] = time.time()
                    response_filter._save_sleep_state(server_id, channel_id, ai_name)
                    
                    # Notify bot status manager
                    try:
                        from utils.bot_status_manager import get_bot_status_manager
                        status_manager = get_bot_status_manager()
                        if status_manager:
                            await status_manager.on_ai_wake(server_id, channel_id, ai_name)
                    except Exception as e:
                        log.debug(f"Failed to notify bot status manager on wake: {e}")
        
        if config.get("use_response_filter", False):
            is_mentioned = False
            is_reply_to_bot = False
            
            if bot_user_id:
                for msg in pending:
                    if msg.raw_message:
                        # Check if bot is mentioned
                        if hasattr(msg.raw_message, 'mentions'):
                            is_mentioned = is_mentioned or any(
                                m.id == bot_user_id for m in msg.raw_message.mentions
                            )
                        
                        # Check if message is a reply to bot
                        if hasattr(msg.raw_message, 'reference') and msg.raw_message.reference:
                            try:
                                ref_msg_id = msg.raw_message.reference.message_id
                                # Check if the referenced message is from the bot
                                # We check against bot_user_id to verify it's actually a reply to the bot
                                try:
                                    from utils.message_cache import fetch_message_cached
                                    ref_msg = await fetch_message_cached(msg.raw_message.channel, str(ref_msg_id))
                                    if ref_msg:
                                        is_reply_to_bot = (ref_msg.author.id == bot_user_id)
                                    else:
                                        # If we can't fetch the message, assume it's a reply to bot
                                        is_reply_to_bot = True
                                except Exception:
                                    # If we can't fetch the message, assume it's a reply to bot
                                    # (better to wake up unnecessarily than miss a wake-up)
                                    is_reply_to_bot = True
                            except Exception:
                                pass

            store = get_store(server_id, channel_id)
            history = await store.get_history(
                server_id, channel_id, ai_name, session_with_context.get("chat_id", "default")
            )
            
            cached_messages = await self.processor.format_messages(pending, session_with_context)
            
            response_filter = get_response_filter()
            should_respond, analysis = await response_filter.should_respond(
                server_id,
                channel_id,
                ai_name,
                session_with_context,
                cached_messages,
                history,
                is_mentioned,
                is_reply_to_bot
            )
            
            if not should_respond:
                await self.buffer.clear_specific_messages(
                    server_id, channel_id, ai_name, processing_message_ids
                )
                return None
        
        await self.buffer.set_processing(server_id, channel_id, ai_name, True)

        try:
            store = get_store(server_id, channel_id)
            history = await store.get_history(
                server_id, channel_id, ai_name, session_with_context.get("chat_id", "default")
            )
            
            # Note: We don't use processor.prepare_for_api() here because
            # chat_service.generate_response() handles message preparation internally.
            # The raw content is passed to chat_service, which formats it properly.
            
            # Extract RAW content from pending messages (not formatted)
            # This prevents duplicate messages in the LLM context
            raw_content_parts = []
            for msg in pending:
                if msg.raw_message and hasattr(msg.raw_message, 'content'):
                    # Use the original Discord message content (unformatted)
                    raw_content_parts.append(msg.raw_message.content)
                else:
                    # Fallback: extract raw content from formatted content
                    # This handles edge cases where raw_message might not be available
                    # Format: "[HH:MM] @username (Display Name) [ID: 123]: actual content"
                    content = msg.content
                    # Try to extract content after the last ": "
                    if ": " in content:
                        content = content.split(": ", 1)[-1]
                    raw_content_parts.append(content)
            
            raw_content = "\n".join(raw_content_parts)
            
            # Collect all attachments from pending messages for vision support
            all_attachments = []
            for msg in pending:
                if hasattr(msg, 'attachments') and msg.attachments:
                    all_attachments.extend(msg.attachments)
            
            real_guild = None
            if self.bot_client:
                try:
                    real_guild = self.bot_client.get_guild(int(server_id))
                except Exception as e:
                    log.warning(f"Failed to get guild from bot: {e}")
            
            class FakeMessage:
                def __init__(self, guild_id, channel_id, author, content, attachments=None):
                    self.guild = type('obj', (object,), {'id': int(guild_id)})()
                    self.channel = type('obj', (object,), {'id': int(channel_id)})()
                    self.author = author
                    self.content = content
                    self.attachments = attachments or []
            
            fake_msg = FakeMessage(
                server_id,
                channel_id,
                pending[0].raw_message.author if pending[0].raw_message else None,
                raw_content,
                all_attachments
            )
            
            if real_guild:
                fake_msg.guild = real_guild
            
            fake_msg._bot_client = self.bot_client
            
            log.debug(
                f"Created FakeMessage with raw content ({len(raw_content)} chars) "
                f"for {len(pending)} pending message(s)"
            )
            
            response = await chat_service.generate_response(
                fake_msg,
                server_id,
                channel_id,
                ai_name,
                session_with_context.get("chat_id", "default"),
                session_with_context
            )
            
            # Check for error control marker
            if isinstance(response, str) and response.startswith("__ERROR_CONTROL__:"):
                # Parse error control: __ERROR_CONTROL__:display|history
                try:
                    parts = response[18:].split("|", 1)  # Skip "__ERROR_CONTROL__:"
                    display_msg = parts[0] if parts[0] else None
                    history_msg = parts[1] if len(parts) > 1 and parts[1] else None
                    
                    # Save to history if configured
                    if history_msg:
                        # Skip short_id for error messages (they don't have Discord IDs)
                        await self.processor.short_id_manager.skip_next_id(
                            server_id, channel_id, ai_name
                        )
                        store = get_store(server_id, channel_id)
                        await store.add_assistant_message(
                            server_id,
                            channel_id,
                            ai_name,
                            history_msg,
                            [],  # No Discord IDs for errors
                            session_with_context.get("chat_id", "default"),
                            short_id=None  # No short_id for error messages
                        )
                        log.debug("Error saved to history")
                    
                    # Send to Discord if configured
                    discord_ids = []
                    if display_msg:
                        await send_callback(display_msg, discord_ids)
                        log.debug("Error sent to chat")
                        
                        # Add error message to ResponseManager so buttons work correctly
                        if discord_ids:
                            formatted_user_content = await self.buffer.get_formatted_content(
                                server_id, channel_id, ai_name
                            )
                            self.response_manager.add_response(
                                server_id,
                                channel_id,
                                ai_name,
                                formatted_user_content,
                                display_msg,
                                discord_ids,
                                is_regeneration=is_regeneration
                            )
                            log.debug("Error message added to ResponseManager")
                    
                    # Clear buffer
                    await self.buffer.clear_specific_messages(
                        server_id, channel_id, ai_name, processing_message_ids
                    )
                    
                    # Return None to indicate error was handled
                    return None
                    
                except Exception as e:
                    log.error(f"Error parsing error control marker: {e}")
                    await self.buffer.clear_specific_messages(
                        server_id, channel_id, ai_name, processing_message_ids
                    )
                    return None
            
            if response is None:
                log.warning("Error response detected by chat_service, not saving to history")
                # Clear only the messages that were processed (prevents race condition)
                await self.buffer.clear_specific_messages(
                    server_id, channel_id, ai_name, processing_message_ids
                )
                return None
            
            if not response:
                log.warning("Empty response from chat_service")
                # Clear only the messages that were processed (prevents race condition)
                await self.buffer.clear_specific_messages(
                    server_id, channel_id, ai_name, processing_message_ids
                )
                return None
            
            # Prepare display response FIRST (remove thinking tags if hide_thinking_tags=True)
            # This must be done BEFORE processing expressions so that reply segments don't contain thinking tags
            display_response = self.processor.prepare_for_display(response, session_with_context)
            
            # Process advanced expressions (Reply, Reaction, Ignore systems)
            # Use display_response so expressions don't see thinking tags
            registry = get_expression_registry()
            expr_result = registry.process_text(display_response, config)
            
            # Handle ignore expression (should_skip = True means <IGNORE> was detected)
            if expr_result.should_skip:
                ignore_type = expr_result.metadata.get("ignore_type")
                
                if ignore_type == "pure":
                    # Pure ignore: save <IGNORE> to history, handle sleep mode
                    log.debug("Expression system: AI sent pure <IGNORE>, skipping message")

                    await self.processor.short_id_manager.skip_next_id(
                        server_id, channel_id, ai_name
                    )

                    store = get_store(server_id, channel_id)
                    await store.add_assistant_message(
                        server_id,
                        channel_id,
                        ai_name,
                        "<IGNORE>",  # Save the tag itself
                        [],  # No Discord IDs (message not sent)
                        session_with_context.get("chat_id", "default"),
                        short_id=None  # No short_id for ignored messages
                    )
                    
                    if config.get("sleep_mode_enabled", False):
                        await self._handle_ignore_for_sleep(
                            server_id, channel_id, ai_name, session_with_context
                        )
                
                elif ignore_type == "impure":
                    # Impure ignore: don't save to history, don't handle sleep mode
                    log.warning(
                        "Expression system: AI sent impure <IGNORE> (with additional content), "
                        "skipping message and not saving to history"
                    )
                    # No history save, no sleep mode handling for impure ignore
                
                await self.buffer.clear_specific_messages(
                    server_id, channel_id, ai_name, processing_message_ids
                )
                return None
            
            # Send display response to Discord (thinking tags removed if configured)
            discord_ids = []
            await send_callback(display_response, discord_ids)
            
            # Prepare responses for different purposes:
            # - Original response (with tags) goes to history so AI can see what it generated
            # - Display response (without thinking tags) already prepared above
            # - Raw response (without any syntax) for accurate edit tracking
            response_without_syntax = registry.remove_all_syntax(response, config)
            
            # Save original response with tags to history (AI needs to see what it generated)
            history_response = self.processor.clean_response(response, session_with_context)
            
            # Raw response for edit tracking (no tags, no formatting)
            raw_response = response_without_syntax
            
            # Reset ignore counter when AI responds normally (not <IGNORE>)
            # This should happen whenever ignore system is enabled, not just when sleep mode is enabled
            if ignore_enabled:
                import time
                
                response_filter = get_response_filter()
                state_key = (server_id, channel_id, ai_name)
                
                if state_key in response_filter.sleep_state:
                    state = response_filter.sleep_state[state_key]
                    was_sleeping = state.get("in_sleep_mode", False)
                    if state["consecutive_refusals"] > 0:
                        log.debug(f"Resetting ignore counter (was {state['consecutive_refusals']})")
                    state["consecutive_refusals"] = 0
                    state["in_sleep_mode"] = False
                    state["last_activity"] = time.time()
                    response_filter._save_sleep_state(server_id, channel_id, ai_name)
                    
                    # Notify bot status manager if AI was sleeping
                    if was_sleeping:
                        try:
                            from utils.bot_status_manager import get_bot_status_manager
                            status_manager = get_bot_status_manager()
                            if status_manager:
                                await status_manager.on_ai_wake(server_id, channel_id, ai_name)
                        except Exception as e:
                            log.debug(f"Failed to notify bot status manager on wake: {e}")
            
            
            formatted_user_content = await self.buffer.get_formatted_content(
                server_id, channel_id, ai_name
            )
            
            bot_short_id = None
            if discord_ids:
                bot_short_id = await self.processor.short_id_manager.assign_and_skip_id(
                    server_id, channel_id, ai_name, discord_ids[0]
                )
            else:
                # Fallback: just skip if no Discord IDs (shouldn't happen normally)
                await self.processor.short_id_manager.skip_next_id(
                    server_id, channel_id, ai_name
                )

            store = get_store(server_id, channel_id)
            await store.add_assistant_message(
                server_id,
                channel_id,
                ai_name,
                history_response,  # Save with tags so AI can see what it generated
                discord_ids,
                session_with_context.get("chat_id", "default"),
                short_id=bot_short_id,
                raw_content=raw_response  # Raw content for accurate edit tracking
            )
            
            self.response_manager.add_response(
                server_id,
                channel_id,
                ai_name,
                formatted_user_content,
                display_response,
                discord_ids,
                is_regeneration=is_regeneration
            )
            
            await self.buffer.clear_specific_messages(
                server_id, channel_id, ai_name, processing_message_ids
            )
            
            return (response, discord_ids)
            
        except Exception as e:
            log.error("Error generating response: %s", e)
            return None
            
        finally:
            # Always clear processing state
            await self.buffer.set_processing(server_id, channel_id, ai_name, False)
    
    async def _handle_ignore_for_sleep(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any]
    ) -> None:
        """
        Handle ignore count for sleep mode integration.
        
        When ignore system is enabled and LLM sends <IGNORE>, this tracks
        consecutive ignores and enters sleep mode if threshold is reached.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            session: AI session data
        """
        import time
        import utils.func as func
        
        response_filter = get_response_filter()
        config = session.get("config", {})
        
        ignore_threshold = config.get("ignore_sleep_threshold", 3)
        
        state_key = (server_id, channel_id, ai_name)
        
        if state_key not in response_filter.sleep_state:
            response_filter.sleep_state[state_key] = {
                "consecutive_refusals": 0,
                "in_sleep_mode": False,
                "last_activity": time.time()
            }
        
        state = response_filter.sleep_state[state_key]
        state["consecutive_refusals"] += 1
        state["last_activity"] = time.time()
        
        if state["consecutive_refusals"] >= ignore_threshold:
            state["in_sleep_mode"] = True
            response_filter._save_sleep_state(server_id, channel_id, ai_name)
            
            # Notify bot status manager
            try:
                from utils.bot_status_manager import get_bot_status_manager
                status_manager = get_bot_status_manager()
                if status_manager:
                    await status_manager.on_ai_sleep(server_id, channel_id, ai_name)
            except Exception as e:
                log.debug(f"Failed to notify bot status manager on sleep: {e}")
            
            log.warning(
                f"AI {ai_name} entering sleep mode after "
                f"{state['consecutive_refusals']} consecutive ignores. "
                f"Will only wake up when mentioned or replied to."
            )
    
    async def _check_if_should_wake(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any],
        bot_user_id: Optional[int] = None
    ) -> bool:
        """
        Verifica se mensagens pendentes devem acordar a IA do sleep mode.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            session: AI session data
            bot_user_id: Bot user ID para verificar menções
            
        Returns:
            True se IA deve acordar (ou não está em sleep), False se deve continuar dormindo
        """
        config = session.get("config", {})
        
        # Se ignore system não está habilitado, sempre acordar
        from expressions import get_expression_registry
        registry = get_expression_registry()
        ignore_expr = registry.get('ignore')
        
        if not ignore_expr or not ignore_expr.is_enabled(config):
            return True
        
        # Se sleep mode não está habilitado, sempre acordar
        if not config.get("sleep_mode_enabled", False):
            return True
        
        # Verificar se IA está em sleep mode
        import time
        from AI.response_filter import get_response_filter
        
        response_filter = get_response_filter()
        state_key = (server_id, channel_id, ai_name)
        
        if state_key not in response_filter.sleep_state:
            # Sem estado de sleep, IA está acordada
            return True
        
        state = response_filter.sleep_state[state_key]
        
        if not state.get("in_sleep_mode", False):
            # IA não está em sleep mode
            return True
        
        # IA está em sleep mode, verificar se deve acordar
        pending = await self.buffer.get_pending(server_id, channel_id, ai_name)
        
        if not pending:
            # Sem mensagens pendentes
            return False
        
        # Verificar wake-up patterns nas mensagens pendentes
        wakeup_patterns = config.get("sleep_wakeup_patterns", ["{ai_mention}", "{reply}"])
        
        is_mentioned = False
        is_reply_to_bot = False
        message_content = ""
        
        if bot_user_id:
            for msg in pending:
                message_content += msg.content + " "
                if msg.raw_message:
                    # Verificar se bot foi mencionado
                    if hasattr(msg.raw_message, 'mentions'):
                        is_mentioned = is_mentioned or any(
                            m.id == bot_user_id for m in msg.raw_message.mentions
                        )
                    
                    if hasattr(msg.raw_message, 'reference') and msg.raw_message.reference:
                        try:
                            from utils.message_cache import fetch_message_cached
                            ref_msg_id = msg.raw_message.reference.message_id
                            ref_msg = await fetch_message_cached(
                                msg.raw_message.channel,
                                str(ref_msg_id)
                            )
                            if ref_msg and ref_msg.author.id == bot_user_id:
                                is_reply_to_bot = True
                        except Exception as e:
                            # This prevents false wake-ups from spam
                            log.debug(f"Could not verify reply target: {e}")
                            pass
        
        # Verificar se algum wake-up pattern corresponde
        should_wake = self._check_wakeup_patterns(
            message_content,
            ai_name,
            is_mentioned,
            is_reply_to_bot,
            wakeup_patterns
        )
        
        return should_wake
    
    async def should_show_typing(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any],
        bot_user_id: Optional[int] = None
    ) -> bool:
        """
        Verifica se deve mostrar indicador de digitação.
        
        Retorna False se a IA está em sleep mode e as mensagens pendentes
        não contêm wake-up patterns.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            session: AI session data
            bot_user_id: Bot user ID para verificar menções
            
        Returns:
            True se deve mostrar "digitando...", False caso contrário
        """
        # Verificar se há mensagens pendentes
        pending = await self.buffer.get_pending(server_id, channel_id, ai_name)
        if not pending:
            return False
        
        # Verificar se IA deve acordar (ou já está acordada)
        should_wake = await self._check_if_should_wake(
            server_id, channel_id, ai_name, session, bot_user_id
        )
        
        return should_wake
    
    async def handle_typing(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any]
    ) -> None:
        """
        Handle user typing event.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            session: AI session data
        """
        await self.timing.update_typing_activity(
            server_id, channel_id, ai_name, self.buffer, session
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        return {
            "buffer": self.buffer.get_stats(),
            "timing": self.timing.get_stats(),
            "response_manager": self.response_manager.get_stats()
        }

    async def shutdown(self) -> None:
        """Shutdown the pipeline gracefully."""
        # Stop all monitoring
        await self.timing.stop_all_monitoring()

        # Save all conversation stores
        from messaging.store import _store_cache
        for (server_id, channel_id), store in _store_cache.items():
            await store.save_immediate()
            log.debug(f"Saved store for {server_id}/{channel_id}")

        log.debug("MessagePipeline shutdown complete")


# Global pipeline instance
_global_pipeline: Optional[MessagePipeline] = None


def get_pipeline() -> MessagePipeline:
    """Get the global message pipeline instance."""
    global _global_pipeline
    if _global_pipeline is None:
        _global_pipeline = MessagePipeline()
    return _global_pipeline


async def init_pipeline(bot=None) -> MessagePipeline:
    """
    Initialize the global message pipeline.
    
    This also initializes the ShortIDManager before loading the store,
    ensuring ID mappings are available when conversations are restored.
    
    Args:
        bot: Discord bot client instance (for tool calling)
    
    Returns:
        The initialized pipeline
    """
    global _global_pipeline
    
    # The store's load() method needs the manager to restore ID mappings
    from messaging.short_id_manager import get_short_id_manager
    manager = get_short_id_manager()
    
    _global_pipeline = MessagePipeline(bot_client=bot)
    await _global_pipeline.initialize()
    return _global_pipeline
