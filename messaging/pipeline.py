"""
Message Pipeline - Main Orchestrator

Provides the main orchestrator that ties all messaging components together
into a unified pipeline for processing Discord messages and generating AI responses.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable, Tuple
import discord

from messaging.buffer import MessageBuffer, PendingMessage, get_buffer
from messaging.intake import MessageIntake, MessageMetadata, get_intake
from messaging.timing import TimingController, get_timing_controller
from messaging.processor import MessageProcessor, get_processor
from messaging.store import ConversationStore, get_store
from messaging.response import ResponseManager, get_response_manager
from AI.response_filter import get_response_filter

log = logging.getLogger(__name__)


class MessagePipeline:
    """Main orchestrator for the messaging system providing a clean flow: Discord → Intake → Buffer → Timing → Processor → API → Store → Discord"""
    
    def __init__(
        self,
        buffer: Optional[MessageBuffer] = None,
        intake: Optional[MessageIntake] = None,
        timing: Optional[TimingController] = None,
        processor: Optional[MessageProcessor] = None,
        store: Optional[ConversationStore] = None,
        response_manager: Optional[ResponseManager] = None,
        bot_client: Optional[Any] = None
    ):
        """Initialize the message pipeline with optional component overrides."""
        self.buffer = buffer or get_buffer()
        self.intake = intake or get_intake()
        self.timing = timing or get_timing_controller()
        self.processor = processor or get_processor()
        self.store = store or get_store()
        self.response_manager = response_manager or get_response_manager()
        self.bot_client = bot_client
    
    async def initialize(self) -> None:
        """Initialize the pipeline and load data."""
        await self.store.load()
    
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
            await self.store.add_user_message(
                metadata.server_id,
                metadata.channel_id,
                ai_name,
                formatted_content,  # Already formatted
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
                reply_to_is_bot=metadata.reply_to_is_bot
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
        bot_user_id: Optional[int] = None
    ) -> Optional[Tuple[str, List[str]]]:
        """Generate AI response for pending messages and save to history."""
        session_with_context = session.copy()
        session_with_context["server_id"] = server_id
        session_with_context["channel_id"] = channel_id
        session_with_context["ai_name"] = ai_name
        
        if await self.buffer.is_processing(server_id, channel_id, ai_name):
            return None
        
        pending = await self.buffer.get_pending(server_id, channel_id, ai_name)
        
        if not pending:
            return None
        
        processing_message_ids = [msg.message_id for msg in pending]
        
        config = session_with_context.get("config", {})
        
        if config.get("enable_ignore_system", False) and config.get("use_response_filter", False):
            log.warning(
                f"Both ignore system and response filter are enabled for AI {ai_name}! "
                f"Disabling response filter (ignore system takes precedence)."
            )
            config["use_response_filter"] = False
        
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
                                    ref_msg = await msg.raw_message.channel.fetch_message(ref_msg_id)
                                    is_reply_to_bot = (ref_msg.author.id == bot_user_id)
                                except Exception:
                                    # If we can't fetch the message, assume it's a reply to bot
                                    # (better to wake up unnecessarily than miss a wake-up)
                                    is_reply_to_bot = True
                            except Exception:
                                pass
            
            history = await self.store.get_history(
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
            history = await self.store.get_history(
                server_id, channel_id, ai_name, session_with_context.get("chat_id", "default")
            )
            
            api_messages = await self.processor.prepare_for_api(
                pending,
                session_with_context,
                history,
                pending[0].raw_message.author if pending[0].raw_message else None
            )
            
            formatted_content = "\n".join(msg.content for msg in pending)
            
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
                    log.warning(f"Failed to get guild {server_id} from bot: {e}")
            
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
                formatted_content,
                all_attachments
            )
            
            if real_guild:
                fake_msg.guild = real_guild
            
            fake_msg._bot_client = self.bot_client
            
            response = await chat_service.generate_response(
                fake_msg,
                server_id,
                channel_id,
                ai_name,
                session_with_context.get("chat_id", "default"),
                session_with_context
            )
            
            if response is None:
                log.warning("Error response detected by chat_service for AI %s, not saving to history", ai_name)
                # Clear only the messages that were processed (prevents race condition)
                await self.buffer.clear_specific_messages(
                    server_id, channel_id, ai_name, processing_message_ids
                )
                return None
            
            if not response:
                log.warning("Empty response from chat_service for AI %s", ai_name)
                # Clear only the messages that were processed (prevents race condition)
                await self.buffer.clear_specific_messages(
                    server_id, channel_id, ai_name, processing_message_ids
                )
                return None
            
            # Check for <IGNORE> tag (if ignore system is enabled)
            if config.get("enable_ignore_system", False):
                from utils.ignore_parser import IgnoreParser
                
                if IgnoreParser.is_pure_ignore(response):
                    log.debug(f"AI {ai_name} sent <IGNORE>")
                    

                    await self.processor.short_id_manager.skip_next_id(
                        server_id, channel_id, ai_name
                    )
                    
                    await self.store.add_assistant_message(
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
                    
                    await self.buffer.clear_specific_messages(
                        server_id, channel_id, ai_name, processing_message_ids
                    )
                    return None
            
            cleaned_response = self.processor.clean_response(response, session_with_context)
            
            display_response = self.processor.prepare_for_display(response, session_with_context)
            
            discord_ids = []
            await send_callback(display_response, discord_ids)
            
            
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
            
            await self.store.add_assistant_message(
                server_id,
                channel_id,
                ai_name,
                cleaned_response,
                discord_ids,
                session_with_context.get("chat_id", "default"),
                short_id=bot_short_id
            )
            
            self.response_manager.add_response(
                server_id,
                channel_id,
                ai_name,
                formatted_user_content,
                display_response,
                discord_ids
            )
            
            await self.buffer.clear_specific_messages(
                server_id, channel_id, ai_name, processing_message_ids
            )
            
            return (response, discord_ids)
            
        except Exception as e:
            log.error("Error generating response for AI %s: %s", ai_name, e)
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
            log.warning(
                f"AI {ai_name} entering sleep mode after "
                f"{state['consecutive_refusals']} consecutive ignores. "
                f"Will only wake up when mentioned or replied to."
            )
    
    async def handle_typing(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> None:
        """
        Handle user typing event.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
        """
        await self.timing.update_typing_activity(
            server_id, channel_id, ai_name, self.buffer
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        return {
            "buffer": self.buffer.get_stats(),
            "timing": self.timing.get_stats(),
            "store": self.store.get_stats(),
            "response_manager": self.response_manager.get_stats()
        }
    
    async def shutdown(self) -> None:
        """Shutdown the pipeline gracefully."""
        # Stop all monitoring
        await self.timing.stop_all_monitoring()
        
        # Save conversation store
        await self.store.save_immediate()
        
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
