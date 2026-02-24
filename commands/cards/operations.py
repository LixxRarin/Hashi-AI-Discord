"""
AI Operations Commands

This module handles advanced operations with AIs, such as copying them between channels.
Extracted from character_card_commands.py as part of the modularization effort.
"""

import copy
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from typing import Optional

import utils.func as func
from AI.chat_service import get_service
from commands.shared.autocomplete import AutocompleteHelpers
from commands.shared.avatar_utils import AvatarUtils
from commands.shared.webhook_utils import WebhookUtils


class AIOperations(commands.Cog):
    """Handles advanced AI operations like copying between channels."""
    
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
    
    @app_commands.command(name="copy_ai", description="Copy an AI to another channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to copy",
        target_channel="Channel to copy the AI to",
        new_ai_name="Name for the copied AI (optional - will use original name)",
        mode="Mode for the copied AI (bot or webhook)",
        copy_history="Copy conversation history to the new AI",
        copy_config="Copy configuration settings to the new AI"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    @app_commands.choices(mode=[
        app_commands.Choice(name="Webhook", value="webhook"),
        app_commands.Choice(name="Bot", value="bot")
    ])
    async def copy_ai(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        target_channel: discord.TextChannel,
        new_ai_name: str = None,
        mode: app_commands.Choice[str] = None,
        copy_history: bool = False,
        copy_config: bool = True
    ):
        """Copy an AI to another channel with various options."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        target_channel_id = str(target_channel.id)
        
        # Get source AI
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        if not found_ai_data:
            await interaction.followup.send(
                f"❌ AI '{ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        source_channel_id, source_session = found_ai_data
        
        # Determine new AI name
        if not new_ai_name:
            new_ai_name = ai_name
        
        # Check if AI already exists in target channel
        target_channel_data = func.get_session_data(server_id, target_channel_id) or {}
        
        # Generate unique name if needed
        if new_ai_name in target_channel_data:
            counter = 2
            base_name = new_ai_name
            while f"{base_name}_{counter}" in target_channel_data:
                counter += 1
            new_ai_name = f"{base_name}_{counter}"
            await interaction.followup.send(
                f"⚠️ AI name '{ai_name}' already exists in target channel. Using '{new_ai_name}' instead.",
                ephemeral=True
            )
        
        # Determine mode
        target_mode = mode.value if mode else source_session.get("mode", "webhook")
        
        # Create new session (deep copy of source)
        new_session = copy.deepcopy(source_session)
        new_session["mode"] = target_mode
        new_session["setup_has_already"] = False
        new_session["awaiting_response"] = False
        
        # Copy or reset config
        if copy_config:
            new_session["config"] = copy.deepcopy(source_session.get("config", {}))
        else:
            provider = source_session.get("provider", "openai")
            new_session["config"] = func.get_default_ai_config(provider)
        
        # Handle webhook/bot setup
        if target_mode == "webhook":
            # Create new webhook
            card_data = source_session.get("character_card", {}).get("data", {})
            display_name = card_data.get("nickname") or card_data.get("name", new_ai_name)
            
            # Get avatar if available
            avatar_bytes = None
            if source_session.get("character_card"):
                card_name = source_session.get("character_card_name")
                if card_name:
                    card_info = func.get_character_card(server_id, card_name)
                    if card_info:
                        cache_path = card_info.get("cache_path")
                        if cache_path:
                            try:
                                card_file = Path(cache_path)
                                
                                if card_file.exists():
                                    # For PNG files, the file itself is the avatar
                                    if card_file.suffix.lower() == '.png':
                                        with open(card_file, 'rb') as f:
                                            avatar_bytes = f.read()
                                    # For CHARX files, extract from ZIP
                                    elif card_file.suffix.lower() == '.charx':
                                        import zipfile
                                        try:
                                            with zipfile.ZipFile(card_file, 'r') as zf:
                                                # Look for avatar in assets
                                                for name in zf.namelist():
                                                    if 'icon' in name.lower() or 'avatar' in name.lower():
                                                        avatar_bytes = zf.read(name)
                                                        break
                                        except Exception as e:
                                            func.log.warning(f"Failed to extract avatar from CHARX: {e}")
                            except Exception as e:
                                func.log.error(f"Error loading avatar: {e}")
            
            # Create webhook
            try:
                webhook_obj = await target_channel.create_webhook(
                    name=display_name,
                    avatar=avatar_bytes if avatar_bytes else None,
                    reason=f"Copied from AI '{ai_name}'"
                )
                new_session["webhook_url"] = webhook_obj.url
                func.log.info(f"Created webhook for copied AI '{new_ai_name}'")
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Failed to create webhook: {e}",
                    ephemeral=True
                )
                return
        else:
            # Bot mode - check if another bot already exists in target channel
            for existing_ai_name, existing_session in target_channel_data.items():
                if existing_session.get("mode") == "bot":
                    await interaction.followup.send(
                        f"❌ Bot mode is already configured for AI '{existing_ai_name}' in target channel. "
                        "Only one bot per channel is allowed.",
                        ephemeral=True
                    )
                    return
            
            # Remove webhook_url if switching from webhook to bot
            if "webhook_url" in new_session:
                del new_session["webhook_url"]
        
        # Copy or clear history
        service = get_service()
        # Get chat_ids from sessions
        source_chat_id = source_session.get("chat_id", "default")
        new_chat_id = new_session.get("chat_id", "default")
        
        if copy_history:
            source_history = service.get_ai_history(server_id, source_channel_id, ai_name, source_chat_id)
            if source_history:
                # Copy history to new AI
                new_history = copy.deepcopy(source_history)
                await service.set_ai_history(server_id, target_channel_id, new_ai_name, new_history, new_chat_id)
                func.log.info(f"Copied {len(source_history)} messages to new AI '{new_ai_name}'")
        else:
            # Clear history for new AI
            await service.clear_ai_history(server_id, target_channel_id, new_ai_name, new_chat_id, keep_greeting=False)
        
        # Save new session
        target_channel_data[new_ai_name] = new_session
        await func.update_session_data(server_id, target_channel_id, target_channel_data)
        
        # Send greeting if configured and not copying history
        if not copy_history and new_session.get("config", {}).get("send_the_greeting_message"):
            greeting_msg = await service.initialize_session_messages(
                new_session, server_id, target_channel_id, new_chat_id
            )
            
            if greeting_msg:
                try:
                    if target_mode == "webhook":
                        webhook_url = new_session.get("webhook_url")
                        if webhook_url:
                            await self.webhook_utils.send_message(webhook_url, greeting_msg, new_session)
                    else:
                        await target_channel.send(greeting_msg)
                    
                    # Mark as setup
                    target_channel_data[new_ai_name]["setup_has_already"] = True
                    await func.update_session_data(server_id, target_channel_id, target_channel_data)
                except Exception as e:
                    func.log.error(f"Error sending greeting: {e}")
        
        # Build success message
        source_channel_obj = interaction.guild.get_channel(int(source_channel_id))
        source_channel_name = source_channel_obj.name if source_channel_obj else f"Channel {source_channel_id}"
        
        success_msg = f"✅ **AI copied successfully!**\n\n"
        success_msg += f"**Source AI:** {ai_name} (#{source_channel_name})\n"
        success_msg += f"**New AI:** {new_ai_name}\n"
        success_msg += f"**Target Channel:** {target_channel.mention}\n"
        success_msg += f"**Mode:** {target_mode.capitalize()}\n"
        success_msg += f"**Config Copied:** {'Yes' if copy_config else 'No'}\n"
        success_msg += f"**History Copied:** {'Yes' if copy_history else 'No'}\n"
        
        if source_session.get("character_card"):
            card_name = source_session.get("character_card_name", "Unknown")
            success_msg += f"**Character Card:** {card_name}\n"
        
        success_msg += f"\n💡 The AI is now active in {target_channel.mention}!"
        
        await interaction.followup.send(success_msg, ephemeral=True)


async def setup(bot):
    """Load the AIOperations cog."""
    await bot.add_cog(AIOperations(bot))
