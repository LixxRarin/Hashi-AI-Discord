import asyncio
import platform
import os

import discord
from colorama import init
from discord.ext import commands

import utils.updater as updater
import utils.AI_utils as AI_utils
import utils.func as func

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
        
        # Callback to send response to Discord using centralized MessageSender
        async def send_callback(response_text, ids_list):
            """Send response to Discord and populate ids_list."""
            from utils.message_sender import get_message_sender
            sender = get_message_sender()
            
            # Ensure session has server_id and ai_name for short ID conversion
            session_with_context = session.copy()
            session_with_context["server_id"] = server_id
            session_with_context["ai_name"] = ai_name
            
            discord_ids = await sender.send(
                response_text=response_text,
                channel=channel,
                session=session_with_context,
                split_message_fn=AI._split_message
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
            # Update reactions using ReactionManager
            if session.get("config", {}).get("auto_add_generation_reactions", False):
                try:
                    from utils.reaction_manager import get_reaction_manager
                    reaction_mgr = get_reaction_manager()
                    await reaction_mgr.update_reactions(
                        channel=channel,
                        old_message_ids=old_message_ids,
                        new_message_ids=discord_ids
                    )
                except Exception as e:
                    func.log.error("Error managing reactions: %s", e)
        
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
        for ai_name in session_data.keys():
            await bot.message_pipeline.handle_typing(server_id, channel_id, ai_name)
            
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
                    await bot.message_pipeline.timing.start_monitoring(
                        server_id,
                        channel_id,
                        ai_name,
                        session,
                        bot.message_pipeline.buffer,
                        callback
                    )

        # Process traditional commands
        await bot.process_commands(message)
        
    except Exception as e:
        func.log.error("Message processing error: %s", e)


@bot.event
async def on_raw_reaction_add(payload):
    """Handle reaction additions for regeneration and navigation"""
    try:
        # Ignore bot's own reactions
        if payload.user_id == bot.user.id:
            return
        
        emoji = str(payload.emoji)
        
        # Use ResponseManager-based handlers
        if emoji == "🔄":
            await AI.handle_regeneration_reaction(bot, payload, bot.message_pipeline.response_manager)
        elif emoji in ["◀️", "▶️"]:
            await AI.handle_generation_navigation(bot, payload, emoji, bot.message_pipeline.response_manager)
    except Exception as e:
        func.log.error("Reaction processing error: %s", e)


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
