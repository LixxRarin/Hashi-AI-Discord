"""
AI Operations Commands

This module handles advanced operations with AIs, such as copying them between channels.
Extracted from character_card_commands.py as part of the modularization effort.
"""

import copy
import re
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

import utils.func as func
from AI.chat_service import get_service
from AI.tools.memory_tools import _count_tokens
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
    
    async def card_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for card names."""
        return await AutocompleteHelpers.card_name(interaction, current)
    
    async def ai_name_with_cards_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for AI names with character cards."""
        return await AutocompleteHelpers.ai_name_with_cards(interaction, current)
    
    @app_commands.command(name="view_greetings", description="View greetings from a character card")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        card_name="Name of the registered card",
        ai_name="Name of the AI with a character card",
        greeting_index="Specific greeting index to view (optional)"
    )
    @app_commands.autocomplete(
        card_name=card_name_autocomplete,
        ai_name=ai_name_with_cards_autocomplete
    )
    async def view_greetings(
        self,
        interaction: discord.Interaction,
        card_name: str = None,
        ai_name: str = None,
        greeting_index: int = None
    ):
        """View greetings from a character card."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        
        # Validate parameters - exactly one of card_name or ai_name must be provided
        if (card_name and ai_name) or (not card_name and not ai_name):
            await interaction.followup.send(
                "❌ **Error:** Provide exactly one parameter\n\n"
                "💡 **Usage:**\n"
                "• `card_name`: View greetings from a registered card\n"
                "• `ai_name`: View greetings from an active AI\n\n"
                "**Examples:**\n"
                "• `/view_greetings card_name:Hashi`\n"
                "• `/view_greetings ai_name:MyAI greeting_index:1`",
                ephemeral=True
            )
            return
        
        # Get character card data
        card_data = None
        active_greeting_index = None
        source_type = None
        
        if card_name:
            # Get card from registry (reusing existing pattern from set_card)
            card_info = func.get_character_card(server_id, card_name)
            if not card_info:
                await interaction.followup.send(
                    f"❌ Card `{card_name}` not found in this server.\n\n"
                    f"💡 Use `/list_cards` to see available cards.",
                    ephemeral=True
                )
                return
            
            # Get cache path and verify file exists
            cache_path = card_info.get("cache_path")
            if not cache_path:
                await interaction.followup.send(
                    "❌ Card cache path not found.",
                    ephemeral=True
                )
                return
            
            card_file_path = Path(cache_path)
            if not card_file_path.exists():
                await interaction.followup.send(
                    f"❌ Card file not found: `{card_file_path.name}`\n\n"
                    f"The file may have been deleted from cache.",
                    ephemeral=True
                )
                return
            
            # Parse character card
            from utils.ccv3.parser import parse_character_card
            try:
                with open(card_file_path, 'rb') as f:
                    raw_data = f.read()
                
                character_card = parse_character_card(raw_data)
                if not character_card:
                    await interaction.followup.send(
                        "❌ Failed to parse card file.\n\n"
                        "The file may be corrupted.",
                        ephemeral=True
                    )
                    return
                
                card_data = character_card.to_dict()["data"]
                source_type = "card"
                
            except Exception as e:
                func.log.error(f"Error parsing card: {e}", exc_info=True)
                await interaction.followup.send(
                    f"❌ Error parsing card: {e}",
                    ephemeral=True
                )
                return
        
        elif ai_name:
            # Get card from AI (reusing existing pattern)
            found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
            if not found_ai_data:
                await interaction.followup.send(
                    f"❌ AI `{ai_name}` not found in this server.\n\n"
                    f"💡 Use `/list_ais` to see available AIs.",
                    ephemeral=True
                )
                return
            
            channel_id, session = found_ai_data
            
            # Check if AI has character card
            card_data = session.get("character_card", {}).get("data", {})
            if not card_data:
                await interaction.followup.send(
                    f"❌ AI `{ai_name}` doesn't have a character card loaded.\n\n"
                    f"💡 Use `/set_card` to apply a card to this AI.",
                    ephemeral=True
                )
                return
            
            active_greeting_index = session.get("config", {}).get("greeting_index", 0)
            source_type = "ai"
        
        # Extract greetings
        greetings = self._extract_greetings(card_data)
        
        if greetings["total_count"] == 0:
            await interaction.followup.send(
                "⚠️ This character card has no greetings configured.",
                ephemeral=True
            )
            return
        
        # Validate greeting_index if provided
        if greeting_index is not None:
            if greeting_index < 0 or greeting_index >= greetings["total_count"]:
                await interaction.followup.send(
                    f"❌ Greeting index `{greeting_index}` is invalid.\n\n"
                    f"This character has **{greetings['total_count']}** greetings (indices 0-{greetings['total_count']-1}).\n\n"
                    f"💡 Use `/view_greetings` without index to see all available greetings.",
                    ephemeral=True
                )
                return
            
            # Get specific greeting
            greeting_text, greeting_type = self._get_greeting_by_index(greetings, greeting_index)
            
            if not greeting_text:
                await interaction.followup.send(
                    f"⚠️ Greeting #{greeting_index} is empty in the character card.\n\n"
                    f"This may indicate an issue with the card.",
                    ephemeral=True
                )
                return
            
            # Build detailed embed
            is_active = (active_greeting_index == greeting_index) if active_greeting_index is not None else False
            embed = self._build_detail_embed(
                card_data, greeting_text, greeting_index, greeting_type, is_active, source_type
            )
        else:
            # Build list embed
            embed = self._build_list_embed(card_data, greetings, active_greeting_index, source_type)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    def _extract_greetings(self, card_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract all greetings from character card data.
        
        Returns:
            Dictionary with greeting information
        """
        first_mes = card_data.get("first_mes", "")
        alternate_greetings = card_data.get("alternate_greetings") or []
        group_only_greetings = card_data.get("group_only_greetings") or []
        
        total_count = (1 if first_mes else 0) + len(alternate_greetings) + len(group_only_greetings)
        
        return {
            "first_mes": first_mes,
            "alternate_greetings": alternate_greetings,
            "group_only_greetings": group_only_greetings,
            "total_count": total_count
        }
    
    def _get_greeting_by_index(self, greetings: Dict[str, Any], index: int) -> Tuple[str, str]:
        """
        Get greeting text and type by index.
        
        Returns:
            Tuple of (greeting_text, greeting_type)
        """
        if index == 0 and greetings["first_mes"]:
            return (greetings["first_mes"], "first_mes")
        
        # Adjust index for alternate greetings
        alt_index = index - 1
        if 0 <= alt_index < len(greetings["alternate_greetings"]):
            return (greetings["alternate_greetings"][alt_index], f"alternate_{alt_index}")
        
        # Adjust index for group_only greetings
        group_index = alt_index - len(greetings["alternate_greetings"])
        if 0 <= group_index < len(greetings["group_only_greetings"]):
            return (greetings["group_only_greetings"][group_index], f"group_only_{group_index}")
        
        return ("", "unknown")
    
    def _build_list_embed(
        self,
        card_data: Dict[str, Any],
        greetings: Dict[str, Any],
        active_index: Optional[int],
        source_type: str
    ) -> discord.Embed:
        """Build embed showing list of all greetings."""
        char_name = card_data.get("nickname") or card_data.get("name", "Unknown")
        creator = card_data.get("creator", "Unknown")
        
        embed = discord.Embed(
            title=f"🎭 Greetings - {char_name}",
            description=f"**Creator:** {creator}\n**Total:** {greetings['total_count']} greetings",
            color=discord.Color.purple()
        )
        
        greeting_list = []
        current_index = 0
        
        # Add first_mes
        if greetings["first_mes"]:
            emoji = "🟢" if active_index == 0 else "⚪"
            text = greetings["first_mes"]
            preview = text[:100] + "..." if len(text) > 100 else text
            tokens = _count_tokens(text)
            greeting_list.append(
                f"{emoji} **Greeting #{current_index}** (first_mes)\n"
                f"```{preview}```\n"
                f"*~{tokens} tokens*"
            )
            current_index += 1
        
        # Add alternate greetings
        for i, text in enumerate(greetings["alternate_greetings"]):
            emoji = "🟢" if active_index == current_index else "⚪"
            preview = text[:100] + "..." if len(text) > 100 else text
            tokens = _count_tokens(text)
            greeting_list.append(
                f"{emoji} **Greeting #{current_index}** (alternate)\n"
                f"```{preview}```\n"
                f"*~{tokens} tokens*"
            )
            current_index += 1
        
        # Add group_only greetings
        for i, text in enumerate(greetings["group_only_greetings"]):
            emoji = "⚪"  # Group greetings are never active in normal mode
            preview = text[:100] + "..." if len(text) > 100 else text
            tokens = _count_tokens(text)
            greeting_list.append(
                f"{emoji} **Greeting #{current_index}** (group_only)\n"
                f"```{preview}```\n"
                f"*~{tokens} tokens*"
            )
            current_index += 1
        
        # Add greetings to embed
        greetings_text = "\n\n".join(greeting_list)
        
        # Discord embed description limit is 4096 characters
        if len(greetings_text) > 3900:
            greetings_text = greetings_text[:3900] + "\n\n... (list truncated)"
        
        embed.description += f"\n\n{greetings_text}"
        
        # Add footer with helpful tip
        if source_type == "ai":
            embed.set_footer(text="💡 Use greeting_index to see details • /select_greeting to change • /new_chat to start fresh")
        else:
            embed.set_footer(text="💡 Use greeting_index to see details • /set_card to apply")
        
        return embed
    
    def _build_detail_embed(
        self,
        card_data: Dict[str, Any],
        greeting_text: str,
        greeting_index: int,
        greeting_type: str,
        is_active: bool,
        source_type: str
    ) -> discord.Embed:
        """Build embed showing detailed view of a specific greeting."""
        char_name = card_data.get("nickname") or card_data.get("name", "Unknown")
        
        # Choose color based on active status
        color = discord.Color.green() if is_active else discord.Color.purple()
        
        # Prepare greeting text for description (max 4096 characters)
        max_text_length = 3900  # Leave room for code block markers and warning
        
        if len(greeting_text) <= max_text_length:
            description = f"```{greeting_text}```"
        else:
            # Truncate if too long
            truncated = greeting_text[:max_text_length]
            description = f"```{truncated}```\n⚠️ *Text truncated - showing first {max_text_length} of {len(greeting_text)} characters*"
        
        embed = discord.Embed(
            title=f"🎭 Greeting #{greeting_index} - {char_name}",
            description=description,
            color=color
        )
        
        # Add type field
        type_display = {
            "first_mes": "🌟 Main Greeting (first_mes)",
            "alternate": "🔄 Alternate Greeting",
            "group_only": "👥 Group-Only Greeting"
        }
        
        if greeting_type.startswith("alternate_"):
            type_text = type_display["alternate"]
        elif greeting_type.startswith("group_only_"):
            type_text = type_display["group_only"]
        else:
            type_text = type_display.get(greeting_type, greeting_type)
        
        embed.add_field(name="📋 Type", value=type_text, inline=True)
        
        # Add status field (only for AI source)
        if source_type == "ai":
            status_text = "✅ In use" if is_active else "⚪ Not in use"
            embed.add_field(name="📊 Status", value=status_text, inline=True)
        
        # Add statistics
        stats = self._get_greeting_stats(greeting_text)
        stats_text = f"**Tokens:** ~{stats['tokens']}\n"
        stats_text += f"**Words:** {stats['words']}\n"
        stats_text += f"**Lines:** {stats['lines']}"
        embed.add_field(name="📈 Statistics", value=stats_text, inline=True)
        
        # Detect CBS variables
        cbs_vars = self._detect_cbs_variables(greeting_text)
        if cbs_vars:
            vars_text = ", ".join([f"`{var}`" for var in cbs_vars])
            embed.add_field(name="🔧 CBS Variables Detected", value=vars_text, inline=False)
        
        # Add footer with helpful tip
        if source_type == "ai":
            if not is_active:
                embed.set_footer(text="💡 /select_greeting to activate • /new_chat to start fresh")
            else:
                embed.set_footer(text="✅ Currently active • /new_chat to start fresh")
        else:
            embed.set_footer(text="💡 Use /set_card to apply this card to an AI")
        
        return embed
    
    def _detect_cbs_variables(self, text: str) -> List[str]:
        """
        Detect CBS (Character Book System) variables in text.
        
        Returns:
            List of unique variable names found
        """
        # Pattern to match {{variable}} or {{variable::default}}
        pattern = r'\{\{([^}:]+)(?:::([^}]+))?\}\}'
        matches = re.findall(pattern, text)
        
        # Extract unique variable names
        variables = list(set([match[0] for match in matches]))
        variables.sort()
        
        return variables
    
    def _get_greeting_stats(self, text: str) -> Dict[str, int]:
        """
        Calculate statistics for greeting text.
        
        Returns:
            Dictionary with token, word, and line counts
        """
        return {
            "tokens": _count_tokens(text),
            "words": len(text.split()),
            "lines": text.count('\n') + 1
        }


async def setup(bot):
    """Load the AIOperations cog."""
    await bot.add_cog(AIOperations(bot))
