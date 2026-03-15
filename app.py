import asyncio
import platform
import os

import discord
from discord import app_commands
from colorama import init
from discord.ext import commands

import utils.updater as updater
import utils.AI_utils as AI_utils
import utils.func as func
from utils.rich_presence import RichPresenceManager, set_rpc_manager

# Initialize colorama for colored logs
init(autoreset=True)

# For Windows compatibility with asyncio
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Set up Discord intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class BridgeBot(commands.Bot):
    """Custom bot class with synchronization control"""

    def __init__(self):
        super().__init__(
            command_prefix="/",
            intents=intents,
            help_command=None
        )
        self.synced = False  # Sync control flag

    async def setup_hook(self):
        """Initial async setup"""

        await self.load_extension('commands.slash_commands')
        await self.load_extension('commands.api_connections')
        await self.load_extension('commands.regenerate_commands')
        await self.load_extension('commands.debug_commands')
        await self.load_extension('commands.preset_commands')
        await self.load_extension('commands.config_commands')
        await self.load_extension('commands.config_view_commands')
        await self.load_extension('commands.backup_commands')
        
        await self.load_extension('commands.ai.lifecycle')
        await self.load_extension('commands.ai.listing')
        await self.load_extension('commands.ai.history')
        await self.load_extension('commands.ai.chat_sessions')
        
        await self.load_extension('commands.cards.registry')
        await self.load_extension('commands.cards.application')
        await self.load_extension('commands.cards.operations')

        # Ensure data directory exists
        os.makedirs("data", exist_ok=True)

        # Ensure session.json exists
        session_file = func.get_session_file()
        if not os.path.exists(session_file):
            func.write_json(session_file, {})

        # Ensure api_connections.json exists
        api_connections_file = func.get_api_connections_file()
        if not os.path.exists(api_connections_file):
            func.write_json(api_connections_file, {})

        # Load session cache
        await func.load_session_cache()

        func.log.debug("Initializing Message System")
        
        # Initialize AI Configuration Manager
        from utils.ai_config_manager import initialize_ai_config
        await initialize_ai_config()
        
        # Initialize new message pipeline (this also loads the conversation store)
        from messaging import init_pipeline
        self.message_pipeline = await init_pipeline(bot=self)
        
        # Sync AI configurations for each webhook
        await AI.sync_config(self)

    async def close(self):
        """Cleanup when bot is shutting down"""
        # Shutdown Rich Presence
        try:
            from utils.rich_presence import get_rpc_manager
            rpc_manager = get_rpc_manager()
            if rpc_manager:
                await rpc_manager.stop()
        except Exception as e:
            func.log.debug(f"Error stopping Rich Presence: {e}")
        
        # Shutdown message pipeline gracefully
        if hasattr(self, 'message_pipeline'):
            await self.message_pipeline.shutdown()
            func.log.debug("Message pipeline shutdown complete")
        
        await super().close()

    async def on_ready(self):
        """Bot ready event handler"""
        if not self.synced:
            await self.tree.sync()  # Sync slash commands
            self.synced = True
            func.log.info("Logged in as %s!", self.user)

            # Initialize all webhooks with their respective character configurations
            await self._initialize_all_webhooks()
            
            # Initialize Rich Presence (if enabled)
            try:
                rpc_manager = RichPresenceManager(self)
                set_rpc_manager(rpc_manager)
                await rpc_manager.connect()
            except Exception as e:
                func.log.warning(f"Failed to initialize Rich Presence: {e}")
                func.log.debug("Bot will continue running without Rich Presence")

    async def _initialize_all_webhooks(self):
        """Initialize all webhooks with their respective character configurations"""
        func.log.debug("Checking webhook configurations...")

        # Iterate over all sessions to verify configuration only
        for server_id, server_data in func.session_cache.items():
            channels = server_data.get("channels", {})
            for channel_id, channel_data in channels.items():
                # Get the channel object (if available)
                channel = self.get_channel(int(channel_id))
                if not channel:
                    func.log.warning(
                        "Channel with ID %s not found.", channel_id)
                    continue

                # Skip if channel_data is None (can happen after removing all AIs)
                if channel_data is None:
                    continue

                # Process each AI in the channel
                for ai_name, session in channel_data.items():
                    provider = session.get("provider", "openai")
                    mode = session.get("mode", "webhook")
                    
                    # Verify webhook URL exists for webhook mode
                    if mode == "webhook" and not session.get("webhook_url"):
                        func.log.warning(
                            "No webhook URL found for AI %s in channel %s in server %s",
                            ai_name, channel_id, server_id
                        )

        func.log.debug("Webhook configuration check complete!")


# Initialize the AI bot helper class from AI_utils
AI = AI_utils.discord_AI_bot()

# Initialize bot instance
bot = BridgeBot()

async def _generate_ai_response(bot, message, server_id, channel_id, ai_name, session):
    """
    This function bridge the new pipeline with existing Discord sending logic.
    """
    try:
        from AI.chat_service import get_service
        from utils.message_cache import fetch_message_cached, get_message_cache
        
        chat_service = get_service()
        channel = bot.get_channel(int(channel_id))
        
        if not channel:
            func.log.error("Channel %s not found", channel_id)
            return
        
        # Check if should show typing indicator (respects sleep mode)
        should_show = await bot.message_pipeline.should_show_typing(
            server_id, channel_id, ai_name, session, bot.user.id
        )
        
        # Capture old message IDs BEFORE generating new response
        old_message_ids = bot.message_pipeline.response_manager.get_previous_discord_ids(
            server_id, channel_id, ai_name
        )
        
        # Disable buttons from previous message before sending new one
        if old_message_ids:
            try:
                # Get the last message ID (where buttons are attached)
                last_old_msg_id = old_message_ids[-1]
                try:
                    # Use cached fetch to reduce API calls
                    old_msg = await fetch_message_cached(channel, last_old_msg_id)
                    # Remove buttons by setting view to None
                    if old_msg and old_msg.components:
                        await old_msg.edit(view=None)
                        func.log.debug(f"Removed buttons from previous message {last_old_msg_id}")
                except discord.NotFound:
                    func.log.debug(f"Previous message {last_old_msg_id} not found")
                except Exception as e:
                    func.log.warning(f"Could not remove buttons from {last_old_msg_id}: {e}")
            except Exception as e:
                func.log.error(f"Error removing buttons from previous messages: {e}")
        
        # Callback to send response to Discord using centralized MessageSender
        async def send_callback(response_text, ids_list):
            """Send response to Discord and populate ids_list."""
            from utils.message_sender import get_message_sender
            sender = get_message_sender()
            
            # Ensure session has server_id and ai_name for short ID conversion
            session_with_context = session.copy()
            session_with_context["server_id"] = server_id
            session_with_context["ai_name"] = ai_name
            
            discord_ids, view = await sender.send(
                response_text=response_text,
                channel=channel,
                session=session_with_context,
                split_message_fn=AI._split_message,
                bot=bot,
                attach_buttons=False
            )
            ids_list.extend(discord_ids)
        
        # Generate response using pipeline (with or without typing indicator)
        if should_show:
            # Show typing indicator while generating response
            async with channel.typing():
                result = await bot.message_pipeline.generate_response(
                    server_id,
                    channel_id,
                    ai_name,
                    session,
                    chat_service,
                    send_callback,
                    bot_user_id=bot.user.id
                )
        else:
            # Don't show typing indicator (AI in sleep mode without wake-up patterns)
            result = await bot.message_pipeline.generate_response(
                server_id,
                channel_id,
                ai_name,
                session,
                chat_service,
                send_callback,
                bot_user_id=bot.user.id
            )
        
        if result:
            response, discord_ids = result
            
            # NOW attach buttons AFTER ResponseManager has been updated
            if discord_ids:
                try:
                    button_config = session.get("config", {}).get("message_action_buttons", {})
                    if button_config.get("enabled", False):
                        from utils.message_actions import MessageActionsView
                        from utils.message_cache import fetch_message_cached, get_message_cache
                        
                        view = MessageActionsView(
                            bot=bot,
                            server_id=server_id,
                            channel_id=channel_id,
                            ai_name=ai_name,
                            session=session,
                            timeout=None
                        )
                        
                        # Attach to last message - use cached fetch
                        last_msg_id = discord_ids[-1]
                        last_msg = await fetch_message_cached(channel, last_msg_id)
                        if last_msg:
                            await last_msg.edit(view=view)
                            func.log.debug(f"Attached buttons after ResponseManager update for AI {ai_name}")
                except Exception as e:
                    func.log.error(f"Error attaching buttons after generation: {e}")
        
    except Exception as e:
        func.log.error("Error in _generate_ai_response for AI %s: %s", ai_name, e)


@bot.event
async def on_typing(channel, user, when):
    """Handle user typing events"""
    try:
        # Ignore DMs and bot's own typing
        if not hasattr(channel, "guild") or not channel.guild or user == bot.user:
            return
        
        server_id = str(channel.guild.id)
        channel_id = str(channel.id)
        
        # Get session data
        session_data = func.get_session_data(server_id, channel_id)
        if not session_data:
            return
        
        # Update typing for all AIs in channel using new pipeline
        for ai_name, session in session_data.items():
            await bot.message_pipeline.handle_typing(server_id, channel_id, ai_name, session)
            
    except Exception as e:
        func.log.error("Typing event error: %s", e)


@bot.event
async def on_message(message):
    """Process incoming messages"""
    try:
        # Skip messages from the bot itself
        if message.author.id == bot.user.id:
            return
        
        # Skip if not in a guild
        if not message.guild:
            return
        
        # Skip messages starting with // (hidden messages)
        if message.content.startswith("//"):
            return
        
        server_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        
        # Get session data
        session_data = func.get_session_data(server_id, channel_id)
        
        if session_data:

            processed = await bot.message_pipeline.process_message(
                message,
                bot.user.id,
                session_data
            )
            
            if processed:
                # Start monitoring for each AI in the channel
                # The TimingController handles duplicate prevention internally
                for ai_name, session in session_data.items():
                    # Create callback that captures current loop variables
                    async def create_callback(s_id, c_id, a_name, sess, msg):
                        async def trigger_response():
                            await _generate_ai_response(bot, msg, s_id, c_id, a_name, sess)
                        return trigger_response
                    
                    callback = await create_callback(server_id, channel_id, ai_name, session, message)
                    
                    # Start monitoring - TimingController prevents duplicate tasks
                    # Pass bot.user.id for sleep mode wake-up detection
                    await bot.message_pipeline.timing.start_monitoring(
                        server_id,
                        channel_id,
                        ai_name,
                        session,
                        bot.message_pipeline.buffer,
                        callback,
                        bot_user_id=bot.user.id
                    )

        # Process traditional commands
        await bot.process_commands(message)
        
    except Exception as e:
        func.log.error("Message processing error: %s", e)


@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    """
    Handle message deletions and update conversation histories.
    
    When a user deletes a message, this removes it from:
    - MessageBuffer (if not yet processed)
    - ConversationStore (all AIs in the channel)
    """
    try:
        from utils.message_cache import get_message_cache
        
        # Ignore if no guild (DM)
        if not payload.guild_id:
            return
        
        server_id = str(payload.guild_id)
        channel_id = str(payload.channel_id)
        message_id = str(payload.message_id)
        
        # Invalidate cache for deleted message
        cache = get_message_cache()
        await cache.invalidate(channel_id, message_id)
        
        # Get session data for the channel
        session_data = func.get_session_data(server_id, channel_id)
        
        if not session_data:
            # No AIs configured in this channel
            return
        
        # Track how many histories were updated
        removed_from_buffer = 0
        removed_from_history = 0
        
        # Process for each AI in the channel
        for ai_name, session in session_data.items():
            chat_id = session.get("chat_id", "default")
            
            # Try to remove from buffer (if message not yet processed)
            if await bot.message_pipeline.buffer.remove_message_by_discord_id(
                server_id, channel_id, ai_name, message_id
            ):
                removed_from_buffer += 1
                func.log.debug(
                    f"Removed message {message_id} from buffer for AI {ai_name}"
                )
            
            # Try to remove from conversation history
            from messaging.store import get_store
            store = get_store()
            
            if await store.delete_message_by_discord_id(
                server_id, channel_id, ai_name, message_id, chat_id
            ):
                removed_from_history += 1
                func.log.debug(
                    f"Removed message {message_id} from history for AI {ai_name}"
                )
        
        # Log summary if any updates were made
        if removed_from_buffer > 0 or removed_from_history > 0:
            func.log.info(
                f"Message {message_id} deleted - removed from {removed_from_buffer} buffer(s) "
                f"and {removed_from_history} history(ies)"
            )
        
    except Exception as e:
        func.log.error(f"Error processing message deletion: {e}")


@bot.event
async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent):
    """
    Handle message edits and update conversation histories.
    
    When a user edits a message, this updates the content in:
    - ConversationStore (all AIs in the channel)
    
    Note: Messages in buffer are not updated (they'll be processed with old content)
    """
    try:
        from utils.message_cache import fetch_message_cached, get_message_cache
        
        # Ignore if no guild (DM)
        if not payload.guild_id:
            return
        
        server_id = str(payload.guild_id)
        channel_id = str(payload.channel_id)
        message_id = str(payload.message_id)
        
        # Get the channel object
        channel = bot.get_channel(int(channel_id))
        if not channel:
            func.log.warning(f"Channel {channel_id} not found for message edit")
            return
        
        # Fetch the updated message using cache (reduces API calls for recent messages)
        try:
            message = await fetch_message_cached(channel, message_id)
        except discord.NotFound:
            func.log.debug(f"Message {message_id} not found (may have been deleted)")
            return
        except discord.Forbidden:
            func.log.warning(f"No permission to fetch message {message_id}")
            return
        except Exception as e:
            func.log.warning(f"Failed to fetch edited message {message_id}: {e}")
            return
        
        if not message:
            return
        
        # Ignore bot's own messages
        if message.author.id == bot.user.id:
            return
        
        # Invalidate cache for this message since it was edited
        cache = get_message_cache()
        await cache.invalidate(channel_id, message_id)
        
        # Get session data for the channel
        session_data = func.get_session_data(server_id, channel_id)
        
        if not session_data:
            # No AIs configured in this channel
            return
        
        # Track how many histories were updated
        updated_count = 0
        
        # Process for each AI in the channel
        for ai_name, session in session_data.items():
            chat_id = session.get("chat_id", "default")
            
            # Ensure session has context for MessageProcessor
            session_with_context = session.copy()
            session_with_context["server_id"] = server_id
            session_with_context["channel_id"] = channel_id
            session_with_context["ai_name"] = ai_name
            
            # Re-format the message using MessageProcessor
            from messaging.buffer import PendingMessage
            from messaging.intake import get_intake
            
            # Process message to get metadata
            intake = get_intake()
            metadata = await intake.process(message, bot.user.id, session_data)
            
            if not metadata:
                continue
            
            # Create pending message for formatting
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
            
            # Handle reply if present
            reply_msg = None
            if metadata.reply_to_id and metadata.reply_to_content:
                reply_author_name = ai_name if metadata.reply_to_is_bot else (metadata.reply_to_author_name or "Unknown")
                
                reply_msg = PendingMessage(
                    content=metadata.reply_to_content,
                    author_id="",
                    author_name=reply_author_name,
                    author_display_name=reply_author_name,
                    timestamp=metadata.timestamp,
                    message_id=metadata.reply_to_id,
                    reply_to=None,
                    raw_message=None
                )
            
            # Format the message
            formatted_content = await bot.message_pipeline.processor.format_single_message(
                msg_to_format,
                session_with_context,
                reply_msg
            )
            
            # Update in conversation history
            from messaging.store import get_store
            store = get_store()
            
            if await store.update_message_by_discord_id(
                server_id, channel_id, ai_name, message_id, formatted_content, chat_id
            ):
                updated_count += 1
                func.log.debug(
                    f"Updated message {message_id} in history for AI {ai_name} "
                    f"(new length: {len(formatted_content)})"
                )
        
        # Log summary if any updates were made
        if updated_count > 0:
            func.log.info(
                f"Message {message_id} edited - updated in {updated_count} history(ies)"
            )
        
    except Exception as e:
        func.log.error(f"Error processing message edit: {e}")


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    # Silently ignore CommandNotFound errors
    if isinstance(error, commands.CommandNotFound):
        return
    
    # Log other errors normally
    func.log.error("Command error in %s: %s", ctx.command, error)


# Start the bot
if __name__ == "__main__":
    # Run boot sequence (startup screen, updates, etc.)
    asyncio.run(updater.boot())
    
    try:
        bot.run(func.config_yaml["Discord"]["token"])
    except discord.LoginFailure:
        func.log.critical("Invalid authentication token!")
    except Exception as e:
        func.log.critical("Fatal runtime error: %s", e)
    finally:
        input("Press Enter to exit...")
