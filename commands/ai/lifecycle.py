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
    
    @app_commands.command(name="setup", description="Setup an AI for a channel using an API connection.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to use the AI",
        mode="Mode: bot or webhook",
        api_connection="API connection to use (create with /new_api first)",
        card_name="Name of a registered card to use",
        card_attachment="Upload a card file directly (PNG/JSON/CHARX)",
        card_url="URL to Character Card (PNG/JSON/CHARX)",
        greeting_index="Which greeting to use (0=first_mes, 1+=alternate_greetings)",
        preset="Configuration preset to apply (Default Preset, Roleplayer!, Discord-Chat, etc.)"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Webhook", value="webhook"),
            app_commands.Choice(name="Bot", value="bot")
        ]
    )
    @app_commands.autocomplete(
        api_connection=connection_name_autocomplete,
        card_name=card_name_autocomplete,
        preset=preset_name_autocomplete
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        mode: app_commands.Choice[str],
        api_connection: str,
        card_name: str = None,
        card_attachment: discord.Attachment = None,
        card_url: str = None,
        greeting_index: int = 0,
        preset: str = None
    ):
        """
        Setup command to configure an AI for a server channel (bot or webhook mode).
        Supports Character Cards V3 via URL or uses default hashi.png character card.
        """
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)
        
        # Validate that the connection exists
        connection = func.get_api_connection(server_id, api_connection)
        if not connection:
            await interaction.followup.send(
                f"❌ **Error:** API connection '{api_connection}' not found in this server.\n\n"
                f"💡 Use `/new_api` to create a connection first, or `/list_apis` to see available connections.",
                ephemeral=True
            )
            return
        
        provider_value = connection.get("provider", "openai")
        model = connection.get("model")
        
        # Validate that only ONE card source is provided
        card_sources = sum([bool(card_name), bool(card_attachment), bool(card_url)])
        if card_sources > 1:
            await interaction.followup.send(
                f"❌ **Error:** Please provide only ONE card source.\n\n"
                f"**Options:**\n"
                f"• `card_name` - Use a registered card\n"
                f"• `card_attachment` - Upload a card file\n"
                f"• `card_url` - Download from URL\n"
                f"• None - Use default hashi.png",
                ephemeral=True
            )
            return
        
        # Load character card
        result = await self._load_character_card(
            interaction, server_id, card_name, card_attachment, card_url
        )
        
        if not result:
            return  # Error already sent to user
        
        character_card, card_cache_path, card_name_registered, avatar_file_path, card_source_type = result
        
        # Extract ai_name from character card
        ai_name = character_card.name
        func.log.info(f"Using character card name as AI name: {ai_name}")
        
        # Get display name and avatar
        display_name = character_card.nickname or character_card.name
        avatar_bytes = await self.avatar_utils.extract_from_card(avatar_file_path) if avatar_file_path else None
        
        # Fallback: Check for external avatar URL in assets
        avatar_url = None
        if not avatar_bytes:
            for asset in character_card.assets:
                if asset.get("type") == "icon" and asset.get("name") == "main":
                    asset_uri = asset.get("uri", "")
                    if asset_uri.startswith("http"):
                        avatar_url = asset_uri
                        func.log.info(f"Using external avatar URL from assets: {avatar_url}")
                    break
        
        channel_data = func.get_session_data(server_id, channel_id_str) or {}
        
        existing_names = set(channel_data.keys())
        unique_ai_name = self._generate_unique_ai_name(ai_name, existing_names)
        
        if unique_ai_name != ai_name:
            await interaction.followup.send(
                f"⚠️ AI name '{ai_name}' already exists. Using '{unique_ai_name}' instead.",
                ephemeral=True
            )
        
        ai_name = unique_ai_name
        
        # Validate greeting_index
        alt_greetings = character_card.alternate_greetings or []
        total_greetings = 1 + len(alt_greetings)
        
        if greeting_index < 0 or greeting_index >= total_greetings:
            await interaction.followup.send(
                f"❌ **Error:** Invalid greeting index {greeting_index}.\n"
                f"This character has {total_greetings} greetings (0-{total_greetings-1}).",
                ephemeral=True
            )
            return
        
        # Create session
        session = await self._create_ai_session(
            server_id, channel_id_str, ai_name, provider_value, channel.name,
            api_connection, mode.value, character_card, card_cache_path,
            card_url, card_name_registered, greeting_index, preset
        )
        
        # Setup webhook or bot mode
        if mode.value == "webhook":
            success = await self._setup_webhook_mode(
                interaction, channel, ai_name, display_name, avatar_url, avatar_bytes,
                session, server_id, channel_id_str, card_name_registered
            )
        else:
            success = await self._setup_bot_mode(
                interaction, channel, ai_name, display_name, avatar_url, avatar_bytes,
                session, server_id, channel_id_str, card_name_registered
            )
        
        if not success:
            return
        
        # Send success message
        await self._send_setup_success_message(
            interaction, ai_name, character_card, card_source_type,
            card_name_registered, api_connection, provider_value, model,
            connection, channel, mode.value, preset
        )
    
    async def _load_character_card(
        self, interaction, server_id, card_name, card_attachment, card_url
    ):
        """Load character card from various sources."""
        from pathlib import Path
        from utils.ccv3.parser import parse_character_card
        from utils.ccv3 import download_card, load_local_card
        import re
        
        character_card = None
        card_cache_path = None
        card_name_registered = None
        avatar_file_path = None
        card_source_type = None
        
        # Check if user selected the special default card option
        if card_name == "__default__":
            card_name = None
        
        # Option 1: Load from registered card name
        if card_name:
            card_source_type = "Registered Card"
            func.log.info(f"Loading character card from registry: {card_name}")
            
            card_info = func.get_character_card(server_id, card_name)
            if not card_info:
                await interaction.followup.send(
                    f"❌ **Error:** Card `{card_name}` not found in registry.\n\n"
                    f"💡 Use `/list_cards` to see available cards or `/import_card` to add new ones.",
                    ephemeral=True
                )
                return None
            
            card_cache_path = card_info.get("cache_path")
            if not card_cache_path:
                await interaction.followup.send(
                    f"❌ **Error:** Card cache path not found.",
                    ephemeral=True
                )
                return None
            
            card_file_path = Path(card_cache_path)
            if not card_file_path.exists():
                await interaction.followup.send(
                    f"❌ **Error:** Card file not found: `{card_file_path.name}`\n\n"
                    f"The file may have been deleted from cache.",
                    ephemeral=True
                )
                return None
            
            with open(card_file_path, 'rb') as f:
                raw_data = f.read()
            
            character_card = parse_character_card(raw_data)
            if not character_card:
                await interaction.followup.send(
                    f"❌ **Error:** Failed to parse card file.",
                    ephemeral=True
                )
                return None
            
            avatar_file_path = card_cache_path
            card_name_registered = card_name
            func.log.info(f"Successfully loaded registered card: {character_card.name}")
        
        # Option 2: Load from Discord attachment
        elif card_attachment:
            card_source_type = "Attachment Upload"
            func.log.info(f"Loading character card from attachment: {card_attachment.filename}")
            
            valid_extensions = ['.png', '.json', '.charx']
            file_ext = Path(card_attachment.filename).suffix.lower()
            
            if file_ext not in valid_extensions:
                await interaction.followup.send(
                    f"❌ **Error:** Invalid file type `{file_ext}`.\n\n"
                    f"**Supported formats:** PNG, JSON, CHARX",
                    ephemeral=True
                )
                return None
            
            max_size = 50 * 1024 * 1024  # 50MB
            if card_attachment.size > max_size:
                await interaction.followup.send(
                    f"❌ **Error:** File too large ({card_attachment.size / 1024 / 1024:.1f}MB).\n\n"
                    f"**Maximum size:** 50MB",
                    ephemeral=True
                )
                return None
            
            raw_data = await card_attachment.read()
            func.log.info(f"Downloaded {len(raw_data)} bytes from attachment")
            
            character_card = parse_character_card(raw_data)
            if not character_card:
                await interaction.followup.send(
                    f"❌ **Error:** Failed to parse character card.\n\n"
                    f"The file may be corrupted or not a valid character card.",
                    ephemeral=True
                )
                return None
            
            # Save to cache
            safe_filename = re.sub(r'[^\w\-.]', '_', card_attachment.filename)
            cache_dir = Path("character_cards")
            cache_dir.mkdir(exist_ok=True)
            card_cache_path = str(cache_dir / safe_filename)
            
            if Path(card_cache_path).exists():
                base_name = Path(safe_filename).stem
                extension = Path(safe_filename).suffix
                counter = 1
                while Path(cache_dir / f"{base_name}_{counter}{extension}").exists():
                    counter += 1
                card_cache_path = str(cache_dir / f"{base_name}_{counter}{extension}")
            
            with open(card_cache_path, 'wb') as f:
                f.write(raw_data)
            
            avatar_file_path = card_cache_path
            func.log.info(f"Saved card to: {card_cache_path}")
            
            # Register card (non-blocking)
            try:
                card_name_registered = await asyncio.wait_for(
                    func.register_character_card(
                        server_id=server_id,
                        card_name=character_card.name,
                        card_data=character_card.to_dict()["data"],
                        card_url=f"attachment://{card_attachment.filename}",
                        cache_path=card_cache_path,
                        registered_by=str(interaction.user.id)
                    ),
                    timeout=5.0
                )
                func.log.info(f"Registered character card as: {card_name_registered}")
            except (asyncio.TimeoutError, Exception) as e:
                func.log.warning(f"Character card registration failed: {e}")
                card_name_registered = None
        
        # Option 3: Load from URL
        elif card_url:
            card_source_type = "URL Download"
            func.log.info(f"Loading character card from URL: {card_url}")
            
            result = await download_card(card_url)
            if result:
                character_card, card_cache_path = result
                func.log.info(f"Successfully loaded character card: {character_card.name}")
                avatar_file_path = card_cache_path
                
                # Register card (non-blocking)
                try:
                    card_name_registered = await asyncio.wait_for(
                        func.register_character_card(
                            server_id=server_id,
                            card_name=character_card.name,
                            card_data=character_card.to_dict()["data"],
                            card_url=card_url,
                            cache_path=card_cache_path,
                            registered_by=str(interaction.user.id)
                        ),
                        timeout=5.0
                    )
                    func.log.info(f"Registered character card as: {card_name_registered}")
                except (asyncio.TimeoutError, Exception) as e:
                    func.log.warning(f"Character card registration failed: {e}")
                    card_name_registered = None
            else:
                await interaction.followup.send(
                    f"❌ **Error:** Failed to download or parse character card from URL.\n"
                    f"Please check the URL and try again.",
                    ephemeral=True
                )
                return None
        
        # Option 4: Load default hashi.png
        else:
            card_source_type = "Default Card"
            func.log.info("No card source provided, loading default character card: hashi.png")
            
            default_card_path = "character_cards/hashi.png"
            result = await load_local_card(default_card_path)
            
            if result:
                character_card, card_cache_path = result
                avatar_file_path = card_cache_path
                func.log.info(f"Successfully loaded default card: {character_card.name}")
                
                # Register default card (optional)
                try:
                    card_name_registered = await asyncio.wait_for(
                        func.register_character_card(
                            server_id=server_id,
                            card_name=character_card.name,
                            card_data=character_card.to_dict()["data"],
                            card_url="local://hashi.png",
                            cache_path=card_cache_path,
                            registered_by=str(interaction.user.id)
                        ),
                        timeout=5.0
                    )
                    func.log.info(f"Registered default card as: {card_name_registered}")
                except Exception as e:
                    func.log.warning(f"Failed to register default card: {e}")
                    card_name_registered = None
            else:
                await interaction.followup.send(
                    f"❌ **Error:** Default character card 'hashi.png' not found or invalid.\n\n"
                    f"**Solutions:**\n"
                    f"• Add a valid character card file as `character_cards/hashi.png`\n"
                    f"• Or provide a card source (card_name, card_attachment, or card_url)",
                    ephemeral=True
                )
                return None
        
        return (character_card, card_cache_path, card_name_registered, avatar_file_path, card_source_type)
    
    async def _create_ai_session(
        self, server_id, channel_id_str, ai_name, provider_value, channel_name,
        api_connection, mode, character_card, card_cache_path, card_url,
        card_name_registered, greeting_index, preset=None
    ):
        """Create AI session with all necessary configuration."""
        session = func.get_default_ai_session(provider=provider_value, channel_name=channel_name)
        
        # Apply preset if provided
        if preset:
            from utils.ai_config_manager import get_ai_config_manager
            config_manager = get_ai_config_manager()
            preset_config = config_manager.load_preset(preset)
            
            if preset_config:
                # Replace the default config with preset config
                session["config"] = preset_config
                func.log.info(f"Applied preset '{preset}' to AI '{ai_name}'")
            else:
                func.log.warning(f"Preset '{preset}' not found, using default config")
        
        session["api_connection"] = api_connection
        session["mode"] = mode
        session["last_message_time"] = time.time()
        # chat_id will be set by initialize_session_messages -> new_chat_id
        
        session["character_card"] = {
            "spec": character_card.spec,
            "spec_version": character_card.spec_version,
            "data": character_card.to_dict()["data"],
            "cache_path": card_cache_path,
            "card_url": card_url if card_url else "local://hashi.png"
        }
        
        # Set greeting_index
        session["config"]["greeting_index"] = greeting_index
        
        # send_the_greeting_message is controlled by preset/defaults.yml
        preset_info = f" with preset '{preset}'" if preset else ""
        send_greeting = session["config"].get("send_the_greeting_message", True)
        func.log.info(f"Created session for AI '{ai_name}'{preset_info} with greeting_index={greeting_index}, send_greeting={send_greeting}")
        
        return session
    
    async def _setup_webhook_mode(
        self, interaction, channel, ai_name, display_name, avatar_url, avatar_bytes,
        session, server_id, channel_id_str, card_name_registered
    ):
        """Setup AI in webhook mode."""
        WB_url = await self.webhook_utils.create_webhook(
            channel, display_name, avatar_bytes
        )
        
        if WB_url is None:
            func.log.error(f"Failed to create webhook for channel {channel_id_str}")
            return False
        
        session["webhook_url"] = WB_url
        
        if card_name_registered:
            session["character_card_name"] = card_name_registered
        
        channel_data = func.get_session_data(server_id, channel_id_str) or {}
        channel_data[ai_name] = session
        await func.update_session_data(server_id, channel_id_str, channel_data)
        
        service = get_service()
        greetings = await service.initialize_session_messages(
            session, server_id, channel_id_str, "default"
        )
        
        messages_sent = False
        if greetings:
            try:
                await self.webhook_utils.send_message(WB_url, greetings, session)
                func.log.info("Greeting message sent via webhook for AI %s", ai_name)
                messages_sent = True
            except Exception as e:
                func.log.error("Error sending greeting via webhook: %s", e)
        
        if messages_sent or not greetings:
            channel_data[ai_name]["setup_has_already"] = True
            await func.update_session_data(server_id, channel_id_str, channel_data)
        
        return True
    
    async def _setup_bot_mode(
        self, interaction, channel, ai_name, display_name, avatar_url, avatar_bytes,
        session, server_id, channel_id_str, card_name_registered
    ):
        """Setup AI in bot mode."""
        channel_data = func.get_session_data(server_id, channel_id_str) or {}
        
        # Check for existing bot
        existing_bot = None
        for ai_name_existing, ai_data in channel_data.items():
            if ai_data.get("mode") == "bot":
                existing_bot = ai_name_existing
                break
        
        if existing_bot:
            await interaction.followup.send(
                f"❌ Bot mode is already configured for AI '{existing_bot}' in this channel. "
                "Only one bot per channel is allowed.",
                ephemeral=True
            )
            return False
        
        # Update bot profile
        try:
            if not avatar_bytes and avatar_url:
                avatar_bytes = await self.avatar_utils.fetch_from_url(avatar_url)
            
            me = interaction.guild.me
            await me.edit(nick=display_name)
            if avatar_bytes:
                try:
                    await self.bot.user.edit(avatar=avatar_bytes)
                    func.log.info(f"Bot avatar updated in guild {interaction.guild.id}")
                except Exception as e:
                    func.log.warning(f"Failed to update bot avatar: {e}")
            func.log.info(f"Bot profile updated in guild {interaction.guild.id}")
        except Exception as e:
            func.log.error(f"Failed to update bot profile: {e}")
        
        if card_name_registered:
            session["character_card_name"] = card_name_registered
        
        channel_data[ai_name] = session
        await func.update_session_data(server_id, channel_id_str, channel_data)
        
        service = get_service()
        greetings = await service.initialize_session_messages(
            session, server_id, channel_id_str, "default"
        )
        
        messages_sent = False
        if greetings:
            try:
                await channel.send(greetings)
                func.log.info(f"Greeting message sent as bot for AI {ai_name}")
                messages_sent = True
            except Exception as e:
                func.log.error(f"Error sending greeting as bot: {e}")
        
        if messages_sent or not greetings:
            channel_data[ai_name]["setup_has_already"] = True
            await func.update_session_data(server_id, channel_id_str, channel_data)
        
        return True
    
    async def _send_setup_success_message(
        self, interaction, ai_name, character_card, card_source_type,
        card_name_registered, api_connection, provider_value, model,
        connection, channel, mode_value, preset=None
    ):
        """Send success message after setup."""
        success_msg = f"✅ **Setup successful!**\n"
        success_msg += f"**AI Name:** {ai_name}\n"
        success_msg += f"**Character:** {character_card.name}\n"
        success_msg += f"**Card Source:** {card_source_type}"
        if card_name_registered:
            success_msg += f" (`{card_name_registered}`)"
        success_msg += "\n"
        
        if character_card.creator:
            success_msg += f"**Creator:** {character_card.creator}\n"
        alt_greetings_count = len(character_card.alternate_greetings or [])
        total_greetings = 1 + alt_greetings_count
        success_msg += f"**Greetings:** {total_greetings} available\n"
        if character_card.character_book:
            entries_count = len(character_card.character_book.get("entries", []))
            success_msg += f"**Lorebook:** {entries_count} entries\n"
        success_msg += f"**Card Spec:** V{character_card.spec_version}\n"
        
        success_msg += f"**API Connection:** `{api_connection}`\n"
        success_msg += f"**Provider:** {provider_value.upper()}\n"
        success_msg += f"**Model:** `{model}`\n"
        if connection.get("base_url"):
            success_msg += f"**Custom Endpoint:** ✅\n"
        success_msg += f"**Channel:** {channel.mention}\n"
        success_msg += f"**Mode:** {'Webhook' if mode_value == 'webhook' else 'Bot'}\n"
        
        # Show preset information
        if preset:
            success_msg += f"**Configuration Preset:** `{preset}` ✨\n"
        else:
            success_msg += f"**Configuration:** Default settings\n"
        
        success_msg += "\n🎭 Character card loaded successfully!\n"
        success_msg += f"💡 Use `/select_greeting` to change greetings or `/config_*` for more options."
        
        await interaction.followup.send(success_msg, ephemeral=True)
    
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
                    func.log.info(f"Deleted webhook for AI '{ai_name}'")
                except Exception as e:
                    func.log.error(f"Failed to delete webhook: {e}")
        
        # Get service for cleanup operations
        service = get_service()
        
        # Clear ALL conversation history for this AI
        await service.clear_ai_history(server_id, found_channel_id, ai_name, chat_id=None, keep_greeting=False)
        func.log.info(f"Cleared conversation history for AI '{ai_name}'")
        
        # Clear memory files
        try:
            from AI.tools.memory_tools import delete_memory_file
            deleted = delete_memory_file(server_id, found_channel_id, ai_name)  # Deletes all chats for this AI in this channel
            if deleted:
                func.log.info(f"Deleted memory files for AI '{ai_name}' in channel {found_channel_id}")
        except Exception as e:
            func.log.warning(f"Failed to delete memory files for AI '{ai_name}': {e}")
        
        # Clear ResponseManager data
        try:
            if hasattr(self.bot, 'message_pipeline'):
                response_manager = self.bot.message_pipeline.response_manager
                response_manager.clear(server_id, found_channel_id, ai_name)
                func.log.info(f"Cleared response manager data for AI '{ai_name}'")
        except Exception as e:
            func.log.warning(f"Failed to clear response manager data for AI '{ai_name}': {e}")
        
        # Clear MessageBuffer data
        try:
            if hasattr(self.bot, 'message_pipeline'):
                await self.bot.message_pipeline.buffer.clear(server_id, found_channel_id, ai_name)
                func.log.info(f"Cleared message buffer for AI '{ai_name}'")
        except Exception as e:
            func.log.warning(f"Failed to clear message buffer for AI '{ai_name}': {e}")
        
        # Remove from session data
        del channel_data[ai_name]
        
        if not channel_data:
            await func.remove_session_data(server_id, found_channel_id)
        else:
            await func.update_session_data(server_id, found_channel_id, channel_data)
        
        # Get channel name for display
        channel_obj = interaction.guild.get_channel(int(found_channel_id))
        channel_name = f"#{channel_obj.name}" if channel_obj else f"Channel {found_channel_id}"
        
        func.log.info(f"Successfully removed AI '{ai_name}' and all related data from {server_id}/{found_channel_id}")
        
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


async def setup(bot):
    """Load the AILifecycle cog."""
    await bot.add_cog(AILifecycle(bot))
