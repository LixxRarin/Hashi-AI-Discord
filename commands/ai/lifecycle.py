"""
AI Lifecycle Management Commands

This module handles the creation and removal of AI instances.
Extracted from ai_manager.py as part of the modularization effort.

“Every world has its end.
I know that’s kinda sad, but that’s why we gotta live life to the fullest in the time we have.
At least, that’s what I figure.” - Sonic the Hedgehog

"""

import time
import asyncio
import aiohttp
from utils.http_client import create_http_session
import traceback
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

import utils.func as func
from AI.services.chat_service import get_service
from messaging.store import get_store
from commands.shared.autocomplete import AutocompleteHelpers
from commands.shared.avatar_utils import AvatarUtils
from commands.shared.webhook_utils import WebhookUtils
from utils.http_client import create_http_session
from utils.discord.confirmation_ui import confirm_dangerous_action, create_success_embed
from utils.media.thumbnails import get_thumbnail_url


# Module-level autocomplete functions (must be defined before class)
async def ai_name_all_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for all AI names."""
    return await AutocompleteHelpers.ai_name_all(interaction, current)


async def connection_name_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for API connection names."""
    return await AutocompleteHelpers.connection_name(interaction, current)


async def card_name_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for card names."""
    return await AutocompleteHelpers.card_name(interaction, current)


async def preset_name_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for preset names."""
    return await AutocompleteHelpers.preset_name(interaction, current)


class AILifecycle(commands.Cog):
    """Manages AI lifecycle: creation (setup) and removal."""

    def __init__(self, bot):
        self.bot = bot
        self.avatar_utils = AvatarUtils()
        self.webhook_utils = WebhookUtils()
    
    def _generate_unique_ai_name(self, base_name: str, existing_names: set) -> str:
        """Generate a unique AI name by adding a suffix if the name already exists."""
        if base_name not in existing_names:
            return base_name
        
        counter = 2
        while f"{base_name}_{counter}" in existing_names:
            counter += 1
        
        return f"{base_name}_{counter}"
    
    def _get_default_config(self, provider: str) -> dict:
        """Returns the default configuration based on the provider."""
        return func.get_default_ai_config(provider)
    
    @app_commands.command(
        name="setup",
        description="Setup an AI for a channel (interactive wizard)"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        """
        Interactive setup wizard for AI configuration.
        
        Guides you through:
        1. Channel selection
        2. Mode selection (bot/webhook)
        3. API connection
        4. Character card
        5. Greeting (optional)
        6. Preset (optional)
        7. Confirmation
        """
        from utils.discord.setup_ui import SetupWizardData, Step1_ChannelSelectView, create_step_embed
        
        # Initialize wizard data
        wizard_data = SetupWizardData(
            user_id=interaction.user.id,
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name
        )
        
        # Create initial view (Step 1)
        view = Step1_ChannelSelectView(wizard_data)
        
        embed = create_step_embed(
            step=1,
            title="Select Channel",
            description="Choose the channel where the AI will be active:",
            wizard_data=wizard_data
        )
        
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )
    
    @app_commands.command(name="remove_ai", description="Remove a specific AI from any channel in the server")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(ai_name="Name of the AI to remove")
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def remove_ai(self, interaction: discord.Interaction, ai_name: str):
        """Remove a specific AI (bot or webhook) and delete all related data."""
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        
        # Parse AI identifier from autocomplete (format: "ai_name|||channel_id")
        ai_name, channel_id_hint = AutocompleteHelpers.parse_ai_identifier(ai_name)
        
        # Find AI - use optimized lookup if channel_id is available
        if channel_id_hint:
            # Direct lookup - faster, no iteration
            channel_data = func.get_session_data(server_id, channel_id_hint)
            session = channel_data.get(ai_name) if channel_data else None
            
            if not session:
                await interaction.followup.send(
                    f"❌ AI '{ai_name}' not found in this server.",
                    ephemeral=True
                )
                return
            
            found_channel_id = channel_id_hint
        else:
            # Fallback: Search all channels (for manual input without autocomplete)
            found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
            
            if not found_ai_data:
                await interaction.followup.send(
                    f"❌ AI '{ai_name}' not found in this server.",
                    ephemeral=True
                )
                return
            
            found_channel_id, session = found_ai_data
        
        # Get character card thumbnail if available
        channel_obj = interaction.guild.get_channel(int(found_channel_id))
        thumbnail_url = None
        if channel_obj:
            thumbnail_url = await get_thumbnail_url(
                channel_obj,
                session,
                server_id
            )
        
        # Get channel mention for display
        channel_mention = f"<#{found_channel_id}>" if channel_obj else f"Channel {found_channel_id}"
        
        # Get mode information
        mode = session.get("mode", "bot")
        mode_display = "Webhook" if mode == "webhook" else "Bot"
        
        # Get provider and model info
        provider = session.get("provider", "unknown")
        api_connection = session.get("api_connection")
        model_info = "Unknown"
        connection_display = api_connection if api_connection else None

        if api_connection:
            connection = func.get_api_connection(server_id, api_connection)
            if connection:
                model_info = connection.get("model", "Unknown")
        else:
            model_info = session.get("model", "Unknown")

        # Get provider display name
        if not connection_display:
            from AI.core.registry import get_registry
            try:
                registry = get_registry()
                provider_meta = registry.get_metadata(provider)
                connection_display = provider_meta.display_name
            except:
                connection_display = provider
        
        # Count total chats and messages
        service = get_service()
        try:
            store = get_store(server_id, found_channel_id)
            chat_ids = await store.list_chat_ids(server_id, found_channel_id, ai_name)
            total_chats = len(chat_ids)
            total_messages = 0
            for chat_id in chat_ids:
                info = await store.get_chat_info(server_id, found_channel_id, ai_name, chat_id)
                total_messages += info.get("message_count", 0)
        except:
            total_chats = 0
            total_messages = 0
        
        # Prepare detail fields
        details_fields = [
            {
                "name": "📊 AI Details",
                "value": f"• **AI Name:** {ai_name}\n"
                        f"• **Channel:** <#{found_channel_id}>\n"
                        f"• **Mode:** {mode_display}\n"
                        f"• **Connection:** {connection_display}\n"
                        f"• **Model:** `{model_info}`"
            },
            {
                "name": "💾 Data to be Deleted",
                "value": f"• **Chat Sessions:** {total_chats}\n"
                        f"• **Total Messages:** {total_messages}\n"
                        f"• Session configuration\n"
                        f"• All conversation history\n"
                        f"• Memory files\n"
                        f"• Response manager data\n"
                        f"• Message buffer\n"
                        f"• Webhook (if applicable)"
            },
            {
                "name": "⚠️ Warning",
                "value": "**This will permanently delete the AI and ALL its data!**\n"
                        "All conversation history, memory files, and configurations will be lost forever.\n"
                        "This action cannot be undone."
            }
        ]
        
        # Define confirmation callback
        async def on_confirm(confirm_interaction: discord.Interaction):
            # Get fresh data
            channel_data = func.get_session_data(server_id, found_channel_id)
            
            # Delete webhook if in webhook mode
            if session.get("mode") == "webhook":
                webhook_url = session.get("webhook_url")
                if webhook_url:
                    try:
                        async with create_http_session() as aio_session:
                            webhook_obj = discord.Webhook.from_url(webhook_url, session=aio_session)
                            await webhook_obj.delete(reason=f"AI '{ai_name}' removed from channel")
                        func.log.info(f"Deleted webhook for AI '{ai_name}'")
                    except Exception as e:
                        func.log.error(f"Failed to delete webhook: {e}")
            
            # Clear ALL conversation history for this AI
            await service.clear_ai_history(server_id, found_channel_id, ai_name, chat_id=None, keep_greeting=False)
            func.log.info(f"Cleared conversation history for AI '{ai_name}'")
            
            # Clear memory files
            try:
                from AI.tools.memory_tools import delete_memory_file
                deleted = delete_memory_file(server_id, found_channel_id, ai_name)
                if deleted:
                    func.log.info(f"Deleted memory files for AI '{ai_name}' in channel {found_channel_id}")
            except Exception as e:
                func.log.warning(f"Failed to delete memory files: {e}")
            
            # Clear ResponseManager data
            try:
                if hasattr(self.bot, 'message_pipeline'):
                    response_manager = self.bot.message_pipeline.response_manager
                    response_manager.clear(server_id, found_channel_id, ai_name)
                    func.log.info(f"Cleared response manager data for AI '{ai_name}'")
            except Exception as e:
                func.log.warning(f"Failed to clear response manager data: {e}")
            
            # Clear MessageBuffer data
            try:
                if hasattr(self.bot, 'message_pipeline'):
                    await self.bot.message_pipeline.buffer.clear(server_id, found_channel_id, ai_name)
                    func.log.info(f"Cleared message buffer for AI '{ai_name}'")
            except Exception as e:
                func.log.warning(f"Failed to clear message buffer: {e}")
            
            # Remove from session data
            del channel_data[ai_name]

            if not channel_data:
                await func.remove_session_data(server_id, found_channel_id)

                # Channel is now empty (no more AIs) - cleanup channel directory
                try:
                    await func.cleanup_channel_data(server_id, found_channel_id)
                    func.log.info(f"Channel {found_channel_id} is now empty, removed directory")
                except Exception as e:
                    func.log.warning(f"Failed to cleanup empty channel directory: {e}")
            else:
                await func.update_session_data(server_id, found_channel_id, channel_data)

            func.log.info(f"Successfully removed AI '{ai_name}' and all related data from channel {found_channel_id}")
            
            # Send debug embed
            from utils.core.debug_embed import DebugEmbed
            await DebugEmbed.send(
                guild=interaction.guild,
                event="remove_ai",
                data={
                    "command": "/remove_ai",
                    "ai_name": ai_name,
                    "channel": channel_mention,
                    "executor": f"{interaction.user.name}#{interaction.user.discriminator}",
                    "changes": {
                        "Mode": mode_display,
                        "Connection": connection_display,
                        "Model": model_info,
                        "Chats Deleted": str(total_chats),
                        "Messages Deleted": str(total_messages)
                    },
                    "session": session
                }
            )
            
            # Create success embed
            success_embed = create_success_embed(
                title="✅ AI Removed Successfully",
                description=f"The AI **{ai_name}** has been permanently removed from {channel_mention}.",
                fields=[
                    {
                        "name": "📊 Summary",
                        "value": f"• **AI:** {ai_name}\n"
                                f"• **Channel:** {channel_mention}\n"
                                f"• **Chats Deleted:** {total_chats}\n"
                                f"• **Messages Deleted:** {total_messages}\n"
                                f"• **Removed by:** {interaction.user.mention}"
                    },
                    {
                        "name": "💾 Deleted Data",
                        "value": "• Session configuration\n"
                                "• All conversation history\n"
                                "• Memory files\n"
                                "• Response manager data\n"
                                "• Message buffer\n"
                                "• Webhook (if applicable)"
                    }
                ],
                thumbnail_url=thumbnail_url
            )
            
            await confirm_interaction.response.edit_message(
                embed=success_embed,
                view=None
            )
        
        # Show double confirmation dialog
        await confirm_dangerous_action(
            interaction=interaction,
            action_name="Remove AI",
            warning_message="This will permanently delete the AI and ALL its data!",
            details_fields=details_fields,
            on_confirm=on_confirm,
            thumbnail_url=thumbnail_url
        )


async def execute_setup_from_wizard(
    bot: commands.Bot,
    wizard_data,
    interaction: discord.Interaction
) -> tuple[bool, str]:
    """
    Executes the setup using the data collected from the wizard.

    Args:
        bot: Bot instance
        wizard_data: SetupWizardData with all configurations
        interaction: Discord interaction

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        from pathlib import Path
        from utils.cc_format.parser import parse_character_card
        from utils.discord.guild_profile import set_guild_profile
        from commands.shared.avatar_utils import AvatarUtils
        from commands.shared.webhook_utils import WebhookUtils
        
        avatar_utils = AvatarUtils()
        webhook_utils = WebhookUtils()
        
        server_id = str(wizard_data.guild_id)
        channel_id = wizard_data.channel_id
        
        # 1. Load character card
        func.log.info(f"Loading character card: source={wizard_data.card_source}, name={wizard_data.card_name}")
        
        character_card = None
        card_cache_path = wizard_data.card_cache_path
        avatar_file_path = card_cache_path
        
        if wizard_data.card_source in ["registered", "url", "default"]:
            card_file = Path(card_cache_path)
            if not card_file.exists():
                return False, f"❌ Card file not found: {card_file.name}"
            
            with open(card_file, 'rb') as f:
                raw_data = f.read()
            character_card = parse_character_card(raw_data)
        
        if not character_card:
            return False, "❌ Failed to load character card"
        
        # 2. Generate unique AI name
        ai_name = character_card.name
        channel_data = func.get_session_data(server_id, channel_id) or {}
        existing_names = set(channel_data.keys())
        
        counter = 2
        unique_ai_name = ai_name
        while unique_ai_name in existing_names:
            unique_ai_name = f"{ai_name}_{counter}"
            counter += 1
        
        ai_name = unique_ai_name
        func.log.info(f"Using AI name: {ai_name}")
        
        # 3. Get display name and avatar
        display_name = character_card.nickname or character_card.name
        avatar_bytes = await avatar_utils.extract_from_card(avatar_file_path) if avatar_file_path else None
        
        # Fallback: Check for external avatar URL
        avatar_url = None
        if not avatar_bytes:
            for asset in character_card.assets:
                if asset.get("type") == "icon" and asset.get("name") == "main":
                    asset_uri = asset.get("uri", "")
                    if asset_uri.startswith("http"):
                        avatar_url = asset_uri
                        break
        
        # 4. Create session
        provider = wizard_data.api_connection_data.get("provider", "openai")
        channel_obj = bot.get_channel(int(channel_id))
        channel_name = channel_obj.name if channel_obj else "unknown"
        
        session = func.get_default_ai_session(provider=provider, channel_name=channel_name)
        
        # Apply preset if provided
        if wizard_data.preset_name:
            from utils.config.ai_manager import get_ai_config_manager
            config_manager = get_ai_config_manager()
            preset_config = config_manager.load_preset(wizard_data.preset_name)
            
            if preset_config:
                session["config"] = preset_config
                func.log.info(f"Applied preset '{wizard_data.preset_name}'")
        
        session["api_connection"] = wizard_data.api_connection_name
        session["mode"] = wizard_data.mode
        session["last_message_time"] = time.time()
        
        session["character_card"] = {
            "spec": character_card.spec,
            "spec_version": character_card.spec_version,
            "data": character_card.raw_data,
            "cache_path": card_cache_path,
            "card_url": wizard_data.card_url if wizard_data.card_url else "local://default"
        }
        
        # Set greeting_index
        session["config"]["greeting_index"] = wizard_data.greeting_index
        
        if wizard_data.card_name:
            session["character_card_name"] = wizard_data.card_name
        
        func.log.info(f"Created session with greeting_index={wizard_data.greeting_index}")
        
        # 5. Setup mode
        if wizard_data.mode == "bot":
            # Bot mode with guild-specific profile
            try:
                # Set guild-specific profile
                await set_guild_profile(
                    bot=bot,
                    guild_id=wizard_data.guild_id,
                    nick=display_name,
                    avatar_bytes=avatar_bytes
                )
                func.log.info(f"Guild profile updated for guild {wizard_data.guild_id}")
            except Exception as e:
                func.log.warning(f"Failed to update guild profile: {e}")
                # Continue anyway
            
            # Save session
            channel_data[ai_name] = session
            await func.update_session_data(server_id, channel_id, channel_data)
            
            # Initialize messages
            service = get_service()
            greetings = await service.initialize_session_messages(
                session, server_id, channel_id, "default"
            )
            
            # Send greeting
            if greetings and channel_obj:
                try:
                    # Split greeting if it exceeds Discord's 2000 char limit
                    if len(greetings) > 2000:
                        greeting_chunks = WebhookUtils.split_text(greetings)
                        func.log.info(f"Greeting message split into {len(greeting_chunks)} chunks (total: {len(greetings)} chars)")
                        for chunk in greeting_chunks:
                            await channel_obj.send(chunk)
                    else:
                        await channel_obj.send(greetings)
                    func.log.info("Greeting message sent as bot")
                except Exception as e:
                    func.log.error(f"Error sending greeting: {e}")
            
            channel_data[ai_name]["setup_has_already"] = True
            await func.update_session_data(server_id, channel_id, channel_data)
            
        else:
            # Webhook mode
            WB_url = await webhook_utils.create_webhook(
                channel_obj, display_name, avatar_bytes
            )
            
            if WB_url is None:
                return False, "❌ Failed to create webhook"
            
            session["webhook_url"] = WB_url
            
            channel_data[ai_name] = session
            await func.update_session_data(server_id, channel_id, channel_data)
            
            # Initialize messages
            service = get_service()
            greetings = await service.initialize_session_messages(
                session, server_id, channel_id, "default"
            )
            
            # Send greeting
            if greetings:
                try:
                    await webhook_utils.send_message(WB_url, greetings, session)
                    func.log.info("Greeting message sent via webhook")
                except Exception as e:
                    func.log.error(f"Error sending greeting: {e}")
            
            channel_data[ai_name]["setup_has_already"] = True
            await func.update_session_data(server_id, channel_id, channel_data)
        
        # 6. Build success message
        mode_emoji = "🤖" if wizard_data.mode == "bot" else "🔗"

        # Get provider display name
        provider_raw = wizard_data.api_connection_data.get("provider", "unknown")
        try:
            from AI.core.registry import get_registry
            registry = get_registry()
            provider_meta = registry.get_metadata(provider_raw)
            provider_display = provider_meta.display_name
        except:
            provider_display = provider_raw

        model = wizard_data.api_connection_data.get("model", "Unknown")

        success_msg = f"**AI Name:** {ai_name}\n"
        success_msg += f"**Character:** {character_card.name}\n"
        success_msg += f"**Channel:** <#{channel_id}>\n"
        success_msg += f"**Mode:** {mode_emoji} {wizard_data.mode.title()}\n"
        success_msg += f"**API:** {wizard_data.api_connection_name} ({provider_display} - {model})\n"
        success_msg += f"**Greeting:** {wizard_data.greeting_index + 1}/{wizard_data.total_greetings}\n"
        
        if wizard_data.preset_name:
            success_msg += f"**Preset:** {wizard_data.preset_name}\n"
        
        success_msg += f"\n🎉 AI is now active in <#{channel_id}>!"
        
        func.log.info(f"Setup completed successfully for AI '{ai_name}'")
        
        return True, success_msg
    
    except Exception as e:
        func.log.error(f"Error in execute_setup_from_wizard: {e}\n{traceback.format_exc()}")
        return False, f"❌ Setup failed: {str(e)}"


async def setup(bot):
    """Load the AILifecycle cog."""
    await bot.add_cog(AILifecycle(bot))
