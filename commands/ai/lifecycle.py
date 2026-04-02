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
import traceback
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

import utils.func as func
from AI.chat_service import get_service
from commands.shared.autocomplete import AutocompleteHelpers
from commands.shared.avatar_utils import AvatarUtils
from commands.shared.webhook_utils import WebhookUtils


class AILifecycle(commands.Cog):
    """Manages AI lifecycle: creation (setup) and removal."""
    
    def __init__(self, bot):
        self.bot = bot
        self.avatar_utils = AvatarUtils()
        self.webhook_utils = WebhookUtils()
    
    async def ai_name_all_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for all AI names."""
        return await AutocompleteHelpers.ai_name_all(interaction, current)
    
    async def connection_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for API connection names."""
        return await AutocompleteHelpers.connection_name(interaction, current)
    
    async def card_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for card names."""
        return await AutocompleteHelpers.card_name(interaction, current)
    
    async def preset_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for preset names."""
        return await AutocompleteHelpers.preset_name(interaction, current)
    
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
        from utils.setup_ui_components import SetupWizardData, Step1_ChannelSelectView, create_step_embed
        
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
        
        # Find AI across all channels in the server
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.followup.send(
                f"❌ AI '{ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        found_channel_id, session = found_ai_data
        channel_data = func.get_session_data(server_id, found_channel_id)
        
        # Delete webhook if in webhook mode
        if session.get("mode") == "webhook":
            webhook_url = session.get("webhook_url")
            if webhook_url:
                try:
                    async with aiohttp.ClientSession() as aio_session:
                        webhook_obj = discord.Webhook.from_url(webhook_url, session=aio_session)
                        await webhook_obj.delete(reason=f"AI '{ai_name}' removed from channel")
                    func.log.info("Deleted webhook for AI")
                except Exception as e:
                    func.log.error(f"Failed to delete webhook: {e}")
        
        # Get service for cleanup operations
        service = get_service()
        
        # Clear ALL conversation history for this AI
        await service.clear_ai_history(server_id, found_channel_id, ai_name, chat_id=None, keep_greeting=False)
        func.log.info("Cleared conversation history for AI")
        
        # Clear memory files
        try:
            from AI.tools.memory_tools import delete_memory_file
            deleted = delete_memory_file(server_id, found_channel_id, ai_name)  # Deletes all chats for this AI in this channel
            if deleted:
                func.log.info(f"Deleted memory files in channel {found_channel_id}")
        except Exception as e:
            func.log.warning(f"Failed to delete memory files: {e}")
        
        # Clear ResponseManager data
        try:
            if hasattr(self.bot, 'message_pipeline'):
                response_manager = self.bot.message_pipeline.response_manager
                response_manager.clear(server_id, found_channel_id, ai_name)
                func.log.info("Cleared response manager data")
        except Exception as e:
            func.log.warning(f"Failed to clear response manager data: {e}")
        
        # Clear MessageBuffer data
        try:
            if hasattr(self.bot, 'message_pipeline'):
                await self.bot.message_pipeline.buffer.clear(server_id, found_channel_id, ai_name)
                func.log.info("Cleared message buffer")
        except Exception as e:
            func.log.warning(f"Failed to clear message buffer: {e}")
        
        # Remove from session data
        del channel_data[ai_name]
        
        if not channel_data:
            await func.remove_session_data(server_id, found_channel_id)
        else:
            await func.update_session_data(server_id, found_channel_id, channel_data)
        
        # Get channel name for display
        channel_obj = interaction.guild.get_channel(int(found_channel_id))
        channel_name = f"#{channel_obj.name}" if channel_obj else f"Channel {found_channel_id}"
        
        func.log.info(f"Successfully removed AI and all related data from channel {found_channel_id}")
        
        await interaction.followup.send(
            f"✅ **AI '{ai_name}' successfully removed!**\n\n"
            f"**Channel:** {channel_name}\n"
            f"**Deleted data:**\n"
            f"• Session configuration\n"
            f"• Conversation history (all chats)\n"
            f"• Memory files\n"
            f"• Response manager data (generations)\n"
            f"• Message buffer\n"
            f"• Webhook (if applicable)\n\n"
            f"All data for this AI has been permanently deleted.\n"
            f"-# Sayonara... {ai_name}...",
            ephemeral=True
        )


async def execute_setup_from_wizard(
    bot: commands.Bot,
    wizard_data,
    interaction: discord.Interaction
) -> tuple[bool, str]:
    """
    Executa o setup com os dados coletados do wizard.
    
    Args:
        bot: Bot instance
        wizard_data: SetupWizardData com todas as configurações
        interaction: Discord interaction
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        from pathlib import Path
        from utils.ccv3.parser import parse_character_card
        from utils.guild_profile import set_guild_profile
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
            from utils.ai_config_manager import get_ai_config_manager
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
            "data": character_card.to_dict()["data"],
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
        provider = wizard_data.api_connection_data.get("provider", "unknown").upper()
        model = wizard_data.api_connection_data.get("model", "Unknown")
        
        success_msg = f"**AI Name:** {ai_name}\n"
        success_msg += f"**Character:** {character_card.name}\n"
        success_msg += f"**Channel:** <#{channel_id}>\n"
        success_msg += f"**Mode:** {mode_emoji} {wizard_data.mode.title()}\n"
        success_msg += f"**API:** {wizard_data.api_connection_name} ({provider} - {model})\n"
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
