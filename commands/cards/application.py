"""
Character card application commands.

Provides commands to apply character cards to AIs and select greetings.
"""
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from AI.services.chat_service import get_service
from commands.shared.autocomplete import AutocompleteHelpers
from commands.shared.avatar_utils import AvatarUtils, get_character_card_thumbnail_url
from commands.shared.webhook_utils import WebhookUtils
from utils.discord.confirmation_ui import (
    confirm_dangerous_action,
    create_success_embed
)
from utils.discord.guild_profile import set_guild_profile


# Module-level autocomplete functions (must be defined before class)
async def ai_name_all_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for all AI names."""
    return await AutocompleteHelpers.ai_name_all(interaction, current)


async def ai_name_with_cards_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for AI names with character cards."""
    return await AutocompleteHelpers.ai_name_with_cards(interaction, current)


async def card_name_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for card names."""
    return await AutocompleteHelpers.card_name(interaction, current)


class CardApplication(commands.Cog):
    """Commands for applying character cards to AIs."""

    def __init__(self, bot):
        self.bot = bot
        self.avatar_utils = AvatarUtils()
        self.webhook_utils = WebhookUtils()
    
    @app_commands.command(name="select_greeting", description="Select which greeting to use for a character")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI",
        greeting_index="Greeting index (0 = first_mes, 1+ = alternate_greetings)",
        send_to_channel="Send the greeting message to the Discord channel"
    )
    @app_commands.autocomplete(ai_name=ai_name_with_cards_autocomplete)
    async def select_greeting(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        greeting_index: int,
        send_to_channel: bool = True
    ):
        """Select which greeting to use for a character and add it to conversation history."""
        await interaction.response.defer(ephemeral=True)

        server_id = str(interaction.guild.id)

        # Parse AI identifier from autocomplete (format: "ai_name|||channel_id")
        actual_ai_name, channel_id_hint = AutocompleteHelpers.parse_ai_identifier(ai_name)

        # Get AI data - use optimized lookup if channel_id is available
        if channel_id_hint:
            # Direct lookup - faster, no iteration
            channel_data = func.get_session_data(server_id, channel_id_hint)
            session = channel_data.get(actual_ai_name) if channel_data else None

            if not session:
                await interaction.followup.send(
                    f"❌ AI '{actual_ai_name}' not found in the specified channel.",
                    ephemeral=True
                )
                return

            found_channel_id = channel_id_hint
        else:
            # Fallback: Search all channels (for manual input without autocomplete)
            found_ai_data = func.get_ai_session_data_from_all_channels(server_id, actual_ai_name)

            if not found_ai_data:
                await interaction.followup.send(
                    f"❌ AI '{actual_ai_name}' not found in this server.",
                    ephemeral=True
                )
                return

            found_channel_id, session = found_ai_data
        
        # Check if AI has a character card
        card_data = session.get("character_card", {}).get("data", {})
        if not card_data:
            await interaction.followup.send(
                f"❌ AI '{ai_name}' does not have a character card loaded.",
                ephemeral=True
            )
            return
        
        # Validate greeting index
        alt_greetings = card_data.get("alternate_greetings") or []
        total_greetings = 1 + len(alt_greetings)
        
        if greeting_index < 0 or greeting_index >= total_greetings:
            await interaction.followup.send(
                f"❌ Invalid greeting index. This character has {total_greetings} greetings (0-{total_greetings-1}).",
                ephemeral=True
            )
            return
        
        # Get greeting text
        if greeting_index == 0:
            greeting_text = card_data.get("first_mes", "")
        else:
            greeting_text = alt_greetings[greeting_index - 1]
        
        if not greeting_text:
            await interaction.followup.send(
                f"❌ Greeting #{greeting_index} is empty.",
                ephemeral=True
            )
            return
        
        # Check if there's existing conversation history
        service = get_service()
        current_chat_id = session.get("chat_id", "default")
        existing_history = await service.get_ai_history(server_id, found_channel_id, actual_ai_name, current_chat_id)
        
        # Helper function to apply the greeting change
        async def apply_greeting_change(confirm_interaction: discord.Interaction = None):
            """Apply the greeting change and update history."""
            # Process CBS in greeting
            from utils.ccv3 import process_cbs
            char_name = card_data.get("nickname") or card_data.get("name", actual_ai_name)
            user_name = "{{user}}"
            processed_greeting = process_cbs(greeting_text, char_name, user_name, session)
            
            # Update config
            channel_data = func.get_session_data(server_id, found_channel_id)
            if not channel_data or actual_ai_name not in channel_data:
                error_msg = f"❌ Failed to update configuration."
                if confirm_interaction:
                    error_embed = discord.Embed(
                        title="❌ Error",
                        description=error_msg,
                        color=discord.Color.red()
                    )
                    await confirm_interaction.response.edit_message(embed=error_embed, view=None)
                else:
                    await interaction.followup.send(error_msg, ephemeral=True)
                return
            
            channel_data[actual_ai_name]["config"]["greeting_index"] = greeting_index
            
            # Clear conversation history and add new greeting
            await service.clear_ai_history(server_id, found_channel_id, actual_ai_name, current_chat_id, keep_greeting=False)
            await service.append_to_history(server_id, found_channel_id, actual_ai_name, "assistant", processed_greeting, current_chat_id)
            
            # Save updated session
            await func.update_session_data(server_id, found_channel_id, channel_data)
            
            # Send greeting to channel if requested
            if send_to_channel:
                channel = self.bot.get_channel(int(found_channel_id))
                if channel:
                    if session.get("mode") == "webhook":
                        webhook_url = session.get("webhook_url")
                        if webhook_url:
                            await self.webhook_utils.send_message(webhook_url, processed_greeting, session)
                    else:
                        await channel.send(processed_greeting)
            
            # Send success message
            success_msg = f"✅ Greeting #{greeting_index} selected for '{actual_ai_name}'.\nHistory has been cleared and the new greeting has been set."
            
            if confirm_interaction:
                success_embed = create_success_embed(
                    title="✅ Greeting Changed Successfully",
                    description=f"The greeting for **{actual_ai_name}** has been updated.",
                    fields=[
                        {
                            "name": "📊 Summary",
                            "value": f"• **AI:** {actual_ai_name}\n"
                                    f"• **New Greeting:** #{greeting_index}\n"
                                    f"• **Messages Cleared:** {len(existing_history)}\n"
                                    f"• **Changed by:** {interaction.user.mention}"
                        }
                    ]
                )
                await confirm_interaction.response.edit_message(embed=success_embed, view=None)
            else:
                await interaction.followup.send(success_msg, ephemeral=True)
        
        # If there's existing history, ask for confirmation
        if existing_history and len(existing_history) > 1:
            greeting_preview = greeting_text[:200] + "..." if len(greeting_text) > 200 else greeting_text
            
            # Get thumbnail
            thumbnail_url = None
            try:
                channel_obj = interaction.guild.get_channel(int(found_channel_id))
                if channel_obj:
                    thumbnail_url = await get_character_card_thumbnail_url(
                        channel=channel_obj,
                        session=session,
                        server_id=server_id
                    )
            except:
                pass
            
            # Prepare detail fields
            details_fields = [
                {
                    "name": "📊 Details",
                    "value": f"• **AI:** {actual_ai_name}\n"
                            f"• **New Greeting:** #{greeting_index}\n"
                            f"• **Messages in History:** {len(existing_history)}"
                },
                {
                    "name": "📝 New Greeting Preview",
                    "value": greeting_preview
                },
                {
                    "name": "⚠️ Warning",
                    "value": "**This will DELETE ALL conversation history!**\n"
                            "All roleplay and conversation progress will be lost forever.\n"
                            "This action cannot be undone."
                }
            ]
            
            # Show double confirmation dialog
            await confirm_dangerous_action(
                interaction=interaction,
                action_name="Change Greeting",
                warning_message="This will delete all conversation history!",
                details_fields=details_fields,
                on_confirm=apply_greeting_change,
                thumbnail_url=thumbnail_url
            )
            return
        
        # If no history, proceed directly
        await apply_greeting_change()
    
    @app_commands.command(name="set_card", description="Apply a registered character card to an existing AI")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to apply the card to",
        card_name="Name of the registered card to apply",
        greeting_index="Which greeting to use (0=first_mes, 1+=alternate_greetings)",
        update_avatar="Update the AI's avatar (guild-specific for bot, per-webhook for webhook mode)",
        update_display_name="Update the AI's display name (guild nickname for bot, webhook name for webhook mode)",
        clear_history="Clear conversation history and add greeting (default: True)"
    )
    @app_commands.autocomplete(
        ai_name=ai_name_all_autocomplete,
        card_name=card_name_autocomplete
    )
    async def set_card(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        card_name: str,
        greeting_index: int = 0,
        update_avatar: bool = True,
        update_display_name: bool = True,
        clear_history: bool = True
    ):
        """Apply a registered character card to an existing AI."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        
        # Parse AI identifier from autocomplete (format: "ai_name|||channel_id")
        actual_ai_name, channel_id_hint = AutocompleteHelpers.parse_ai_identifier(ai_name)
        
        # Get AI data - use optimized lookup if channel_id is available
        if channel_id_hint:
            # Direct lookup - faster, no iteration
            channel_data = func.get_session_data(server_id, channel_id_hint)
            session = channel_data.get(actual_ai_name) if channel_data else None
            
            if not session:
                await interaction.followup.send(
                    f"❌ AI '{actual_ai_name}' not found in the specified channel.",
                    ephemeral=True
                )
                return
            
            found_channel_id = channel_id_hint
        else:
            # Fallback: Search all channels (for manual input without autocomplete)
            found_ai_data = func.get_ai_session_data_from_all_channels(server_id, actual_ai_name)
            
            if not found_ai_data:
                await interaction.followup.send(
                    f"❌ AI '{actual_ai_name}' not found in this server.\n\n"
                    f"💡 Use `/list_ais` to see available AIs.",
                    ephemeral=True
                )
                return
            
            found_channel_id, session = found_ai_data
        
        # Check if user selected the special default card option
        if card_name == "__default__":
            func.log.info("User selected __default__ card, loading hashi.png")
            
            from pathlib import Path
            from utils.ccv3 import load_local_card
            
            default_card_path = "character_cards/hashi.png"
            
            # Check if default card exists
            if not Path(default_card_path).exists():
                await interaction.followup.send(
                    f"❌ **Error:** Default character card 'hashi.png' not found.\n\n"
                    f"**Solutions:**\n"
                    f"• Add a valid character card file as `character_cards/hashi.png`\n"
                    f"• Or use `/import_card` to register a different card\n"
                    f"• Or select a different card from `/list_cards`",
                    ephemeral=True
                )
                return
            
            # Load the default card
            try:
                result = await load_local_card(default_card_path)
                if not result:
                    await interaction.followup.send(
                        f"❌ **Error:** Failed to parse default card 'hashi.png'.\n\n"
                        f"The file may be corrupted or not a valid character card.",
                        ephemeral=True
                    )
                    return
                
                character_card, cache_path = result
                func.log.info("Successfully loaded default card")
                
                # Check if already registered
                cards = func.list_character_cards(server_id)
                card_name = None
                
                for existing_name, card_info in cards.items():
                    if card_info.get("cache_path") == cache_path:
                        card_name = existing_name
                        func.log.info(f"Default card already registered as: {card_name}")
                        break
                
                # Register if not found
                if not card_name:
                    try:
                        card_name = await func.register_character_card(
                            server_id=server_id,
                            card_name=character_card.name,
                            card_data=character_card.to_dict()["data"],
                            card_url="local://hashi.png",
                            cache_path=cache_path,
                            registered_by=str(interaction.user.id)
                        )
                        func.log.info(f"Registered default card as: {card_name}")
                    except Exception as e:
                        func.log.error(f"Failed to register default card: {e}", exc_info=True)
                        await interaction.followup.send(
                            f"❌ **Error:** Failed to register default card: {e}",
                            ephemeral=True
                        )
                        return
                
            except Exception as e:
                func.log.error(f"Error loading default card: {e}", exc_info=True)
                await interaction.followup.send(
                    f"❌ **Error:** Failed to load default card: {e}",
                    ephemeral=True
                )
                return
        
        # Check if card exists in registry
        card_info = func.get_character_card(server_id, card_name)
        if not card_info:
            await interaction.followup.send(
                f"❌ Card '{card_name}' not found in registry.\n\n"
                f"💡 Use `/list_cards` to see available cards or `/import_card` to add new ones.",
                ephemeral=True
            )
            return
        
        # Get cache path and verify file exists
        cache_path = card_info.get("cache_path")
        if not cache_path:
            await interaction.followup.send(
                f"❌ Card cache path not found.",
                ephemeral=True
            )
            return
        
        from pathlib import Path
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
                    f"❌ Failed to parse card file.\n\n"
                    f"The file may be corrupted.",
                    ephemeral=True
                )
                return
        except Exception as e:
            func.log.error(f"Error parsing card: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error parsing card: {e}",
                ephemeral=True
            )
            return
        
        # Validate greeting index
        card_data = character_card.to_dict()["data"]
        alt_greetings = card_data.get("alternate_greetings") or []
        total_greetings = 1 + len(alt_greetings)
        
        if greeting_index < 0 or greeting_index >= total_greetings:
            await interaction.followup.send(
                f"❌ Invalid greeting index: {greeting_index}\n\n"
                f"This character has {total_greetings} greetings (0-{total_greetings-1}).",
                ephemeral=True
            )
            return
        
        # Get greeting text
        if greeting_index == 0:
            greeting_text = card_data.get("first_mes", "")
        else:
            greeting_text = alt_greetings[greeting_index - 1]
        
        if not greeting_text:
            await interaction.followup.send(
                f"❌ Greeting #{greeting_index} is empty.",
                ephemeral=True
            )
            return
        
        # Check if there's existing conversation history
        service = get_service()
        current_chat_id = session.get("chat_id", "default")
        existing_history = await service.get_ai_history(server_id, found_channel_id, actual_ai_name, current_chat_id)
        
        # Helper function to apply the card
        async def apply_card(confirm_interaction: discord.Interaction = None):
            """Apply the character card and update all settings."""
            # Update session data with new card
            channel_data = func.get_session_data(server_id, found_channel_id)
            if not channel_data or actual_ai_name not in channel_data:
                error_msg = f"❌ Failed to update configuration."
                if confirm_interaction:
                    error_embed = discord.Embed(
                        title="❌ Error",
                        description=error_msg,
                        color=discord.Color.red()
                    )
                    await confirm_interaction.response.edit_message(embed=error_embed, view=None)
                else:
                    await interaction.followup.send(error_msg, ephemeral=True)
                return
            
            # Update character card data
            channel_data[actual_ai_name]["character_card"] = {
                "data": card_data,
                "spec_version": character_card.spec_version,
                "cache_path": cache_path
            }
            channel_data[actual_ai_name]["character_card_name"] = card_name
            channel_data[actual_ai_name]["config"]["greeting_index"] = greeting_index
            
            # Clear conversation history and add new greeting (only if clear_history=True)
            if clear_history:
                # Process CBS in greeting
                from utils.ccv3 import process_cbs
                char_name = card_data.get("nickname") or card_data.get("name", actual_ai_name)
                user_name = "{{user}}"
                processed_greeting = process_cbs(greeting_text, char_name, user_name, session)
                
                await service.clear_ai_history(server_id, found_channel_id, actual_ai_name, current_chat_id, keep_greeting=False)
                await service.append_to_history(server_id, found_channel_id, actual_ai_name, "assistant", processed_greeting, current_chat_id)
            
            # Save updated session
            await func.update_session_data(server_id, found_channel_id, channel_data)
            
            # Update avatar and display name based on mode
            avatar_updated = False
            name_updated = False
            
            if session.get("mode") == "webhook":
                webhook_url = session.get("webhook_url")
                
                if webhook_url and update_avatar:
                    try:
                        avatar_bytes = await self.avatar_utils.extract_from_card(cache_path)
                        if avatar_bytes:
                            await self.webhook_utils.update_avatar(webhook_url, avatar_bytes)
                            avatar_updated = True
                            func.log.info("Updated webhook avatar")
                    except Exception as e:
                        func.log.warning(f"Failed to update webhook avatar: {e}")
                
                if webhook_url and update_display_name:
                    try:
                        display_name = card_data.get("nickname") or card_data.get("name", actual_ai_name)
                        await self.webhook_utils.update_name(webhook_url, display_name)
                        name_updated = True
                        func.log.info("Updated webhook display name")
                    except Exception as e:
                        func.log.warning(f"Failed to update webhook display name: {e}")
            
            elif session.get("mode") == "bot":
                # Update guild-specific profile (both avatar and nickname)
                try:
                    profile_updates = {}
                    
                    if update_display_name:
                        display_name = card_data.get("nickname") or card_data.get("name", actual_ai_name)
                        profile_updates["nick"] = display_name
                    
                    if update_avatar:
                        avatar_bytes = await self.avatar_utils.extract_from_card(cache_path)
                        if avatar_bytes:
                            profile_updates["avatar_bytes"] = avatar_bytes
                    
                    # Apply guild-specific profile
                    if profile_updates:
                        await set_guild_profile(
                            bot=self.bot,
                            guild_id=interaction.guild.id,
                            **profile_updates
                        )
                        
                        # Set flags based on what was updated
                        if "nick" in profile_updates:
                            name_updated = True
                        if "avatar_bytes" in profile_updates:
                            avatar_updated = True
                        
                        func.log.info(f"Updated guild profile for guild {interaction.guild.id}")
                except Exception as e:
                    func.log.warning(f"Failed to update guild profile: {e}")
            
            # Build success message
            creator = card_data.get("creator", "Unknown")
            char_name = card_data.get("nickname") or card_data.get("name", actual_ai_name)
            
            if confirm_interaction:
                # Create success embed for confirmation flow
                success_embed = create_success_embed(
                    title="✅ Character Card Applied Successfully",
                    description=f"The character card has been applied to **{actual_ai_name}**.",
                    fields=[
                        {
                            "name": "📊 Card Details",
                            "value": f"• **Card:** {card_name}\n"
                                    f"• **Character:** {char_name}\n"
                                    f"• **Creator:** {creator}\n"
                                    f"• **Greeting:** #{greeting_index}"
                        },
                        {
                            "name": "🔄 Updates Applied",
                            "value": f"• **Avatar:** {'✅ Updated' if avatar_updated else '⏭️ Skipped'}\n"
                                    f"• **Display Name:** {'✅ Updated' if name_updated else '⏭️ Skipped'}\n"
                                    f"• **History:** {'🗑️ Cleared' if clear_history else '💾 Preserved'}"
                        },
                        {
                            "name": "👤 Applied By",
                            "value": interaction.user.mention
                        }
                    ]
                )
                
                if clear_history:
                    success_embed.add_field(
                        name="💡 Note",
                        value=f"Conversation history cleared. Messages deleted: {len(existing_history)}",
                        inline=False
                    )
                
                await confirm_interaction.response.edit_message(embed=success_embed, view=None)
            else:
                # Simple text message for non-confirmation flow
                success_msg = f"✅ **Character card applied successfully!**\n\n"
                success_msg += f"**AI:** `{actual_ai_name}`\n"
                success_msg += f"**Card:** `{card_name}`\n"
                success_msg += f"**Character:** {char_name}\n"
                success_msg += f"**Creator:** {creator}\n"
                success_msg += f"**Greeting:** #{greeting_index}\n"
                success_msg += f"**Avatar updated:** {'Yes' if avatar_updated else 'No'}\n"
                success_msg += f"**Display name updated:** {'Yes' if name_updated else 'No'}\n\n"
                
                if clear_history:
                    success_msg += f"💡 **History cleared:** The conversation history has been cleared and the new greeting has been set.\n"
                else:
                    success_msg += f"💡 **History preserved:** The conversation history has been kept intact. Only card metadata was updated.\n"
                
                success_msg += f"Use `/character_info ai_name:{actual_ai_name}` to view card details."
                
                await interaction.followup.send(success_msg, ephemeral=True)
        
        # If clear_history is True and there's existing history, ask for confirmation
        if clear_history and existing_history and len(existing_history) > 1:
            char_name = card_data.get("nickname") or card_data.get("name", card_name)
            greeting_preview = greeting_text[:200] + "..." if len(greeting_text) > 200 else greeting_text
            
            # Get thumbnail
            thumbnail_url = None
            try:
                channel_obj = interaction.guild.get_channel(int(found_channel_id))
                if channel_obj:
                    thumbnail_url = await get_character_card_thumbnail_url(
                        channel=channel_obj,
                        session=session,
                        server_id=server_id
                    )
            except:
                pass
            
            # Prepare detail fields
            details_fields = [
                {
                    "name": "📊 Details",
                    "value": f"• **AI:** {actual_ai_name}\n"
                            f"• **New Card:** {card_name}\n"
                            f"• **Character:** {char_name}\n"
                            f"• **Messages in History:** {len(existing_history)}"
                },
                {
                    "name": "📝 New Greeting Preview",
                    "value": greeting_preview
                },
                {
                    "name": "⚠️ Warning",
                    "value": "**This will DELETE ALL conversation history!**\n"
                            "All roleplay and conversation progress will be lost forever.\n"
                            "This action cannot be undone."
                }
            ]
            
            # Show double confirmation dialog
            await confirm_dangerous_action(
                interaction=interaction,
                action_name="Apply Card",
                warning_message="This will delete all conversation history!",
                details_fields=details_fields,
                on_confirm=apply_card,
                thumbnail_url=thumbnail_url
            )
            return
        
        # If no history or clear_history=False, proceed directly
        await apply_card()


async def setup(bot):
    """Load the CardApplication cog."""
    await bot.add_cog(CardApplication(bot))
