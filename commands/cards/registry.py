"""
Character Card Registry Management Commands

This module handles importing, removing, exporting, and listing character cards.
Extracted from character_card_commands.py as part of the modularization effort.
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from typing import Optional

import utils.func as func
from commands.shared.autocomplete import AutocompleteHelpers


class CardRegistry(commands.Cog):
    """Manages the central registry of character cards."""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def card_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for card names."""
        return await AutocompleteHelpers.card_name(interaction, current)
    
    @app_commands.command(name="import_card", description="Import and register a character card")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        card_url="URL to download the card from (PNG/JSON/CHARX)",
        card_attachment="Upload a card file directly (PNG/JSON/CHARX)",
        card_name="Custom name for the card (optional, uses character name if not provided)",
        force_reload="Re-download even if already cached"
    )
    async def import_card(
        self,
        interaction: discord.Interaction,
        card_url: str = None,
        card_attachment: discord.Attachment = None,
        card_name: str = None,
        force_reload: bool = False
    ):
        """Import and register a character card from URL or file attachment."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        
        # Validate that at least one source is provided
        if not card_url and not card_attachment:
            await interaction.followup.send(
                "❌ **Error:** You must provide either a `card_url` or `card_attachment`.\n\n"
                "💡 **How to use:**\n"
                "• Provide a URL: `/import_card card_url:https://...`\n"
                "• Or upload a file using the `card_attachment` parameter",
                ephemeral=True
            )
            return
        
        # Validate that only one source is provided
        if card_url and card_attachment:
            await interaction.followup.send(
                "❌ **Error:** Please provide only ONE source (either URL or attachment, not both).",
                ephemeral=True
            )
            return
        
        try:
            from utils.ccv3 import download_card
            from utils.ccv3.parser import parse_character_card
            
            character_card = None
            cache_path = None
            source_type = None
            
            # Handle URL download
            if card_url:
                source_type = "URL"
                func.log.info(f"Importing card from URL: {card_url}")
                
                # Check if card with this URL already exists
                cards = func.list_character_cards(server_id)
                for existing_name, existing_info in cards.items():
                    if existing_info.get("card_url") == card_url:
                        if not force_reload:
                            await interaction.followup.send(
                                f"❌ **Error:** A card from this URL is already registered as `{existing_name}`.\n\n"
                                f"💡 Use `force_reload=True` to re-import it.",
                                ephemeral=True
                            )
                            return
                        else:
                            func.log.info(f"Force reloading card '{existing_name}' from URL")
                
                result = await download_card(card_url, force_reload=force_reload)
                if not result:
                    await interaction.followup.send(
                        f"❌ **Error:** Failed to download card from URL.\n\n"
                        f"Please check:\n"
                        f"• URL is accessible\n"
                        f"• File is a valid character card (PNG/JSON/CHARX)\n"
                        f"• File size is under 50MB",
                        ephemeral=True
                    )
                    return
                
                character_card, cache_path = result
            
            # Handle attachment upload
            elif card_attachment:
                source_type = "Attachment"
                func.log.info(f"Importing card from attachment: {card_attachment.filename}")
                
                # Validate file extension
                valid_extensions = ['.png', '.json', '.charx']
                file_ext = Path(card_attachment.filename).suffix.lower()
                
                if file_ext not in valid_extensions:
                    await interaction.followup.send(
                        f"❌ **Error:** Invalid file type `{file_ext}`.\n\n"
                        f"**Supported formats:** PNG, JSON, CHARX",
                        ephemeral=True
                    )
                    return
                
                # Validate file size (50MB limit)
                max_size = 50 * 1024 * 1024  # 50MB
                if card_attachment.size > max_size:
                    await interaction.followup.send(
                        f"❌ **Error:** File too large ({card_attachment.size / 1024 / 1024:.1f}MB).\n\n"
                        f"**Maximum size:** 50MB",
                        ephemeral=True
                    )
                    return
                
                # Download attachment
                try:
                    raw_data = await card_attachment.read()
                    func.log.info(f"Downloaded {len(raw_data)} bytes from attachment")
                except Exception as e:
                    func.log.error(f"Error downloading attachment: {e}")
                    await interaction.followup.send(
                        f"❌ **Error:** Failed to download attachment: {e}",
                        ephemeral=True
                    )
                    return
                
                # Parse card
                character_card = parse_character_card(raw_data)
                if not character_card:
                    await interaction.followup.send(
                        f"❌ **Error:** Failed to parse character card.\n\n"
                        f"The file may be corrupted or not a valid character card.",
                        ephemeral=True
                    )
                    return
                
                # Save to cache with sanitized filename
                import re
                safe_filename = re.sub(r'[^\w\-.]', '_', card_attachment.filename)
                cache_dir = Path("character_cards")
                cache_dir.mkdir(exist_ok=True)
                cache_path = str(cache_dir / safe_filename)
                
                # Check if file already exists
                if Path(cache_path).exists() and not force_reload:
                    # Generate unique filename
                    base_name = Path(safe_filename).stem
                    extension = Path(safe_filename).suffix
                    counter = 1
                    while Path(cache_dir / f"{base_name}_{counter}{extension}").exists():
                        counter += 1
                    cache_path = str(cache_dir / f"{base_name}_{counter}{extension}")
                
                # Save file
                with open(cache_path, 'wb') as f:
                    f.write(raw_data)
                
                func.log.info(f"Saved card to: {cache_path}")
            
            # Determine card name
            if not card_name:
                card_name = character_card.name
            
            # Check if card name already exists
            existing_card = func.get_character_card(server_id, card_name)
            if existing_card and not force_reload:
                await interaction.followup.send(
                    f"❌ **Error:** A card named `{card_name}` already exists.\n\n"
                    f"💡 **Options:**\n"
                    f"• Use a different `card_name` parameter\n"
                    f"• Use `force_reload=True` to replace it",
                    ephemeral=True
                )
                return
            
            # Register card
            registered_name = await func.register_character_card(
                server_id=server_id,
                card_name=card_name,
                card_data=character_card.to_dict()["data"],
                card_url=card_url if card_url else f"attachment://{card_attachment.filename if card_attachment else 'unknown'}",
                cache_path=cache_path,
                registered_by=str(interaction.user.id)
            )
            
            func.log.info(f"Registered card as: {registered_name}")
            
            # Build success message
            card_data = character_card.to_dict()["data"]
            char_name = card_data.get("name", registered_name)
            creator = card_data.get("creator", "Unknown")
            alt_greetings = card_data.get("alternate_greetings") or []
            total_greetings = 1 + len(alt_greetings)
            character_book = card_data.get("character_book")
            lorebook_entries = len(character_book.get("entries", [])) if character_book else 0
            
            success_msg = f"✅ **Character card imported successfully!**\n\n"
            success_msg += f"**Registered as:** `{registered_name}`\n"
            success_msg += f"**Character:** {char_name}\n"
            success_msg += f"**Creator:** {creator}\n"
            success_msg += f"**Source:** {source_type}\n"
            success_msg += f"**Spec Version:** V{character_card.spec_version}\n"
            success_msg += f"**Greetings:** {total_greetings} available\n"
            if lorebook_entries > 0:
                success_msg += f"**Lorebook:** {lorebook_entries} entries\n"
            success_msg += f"**Cached at:** `{Path(cache_path).name}`\n\n"
            success_msg += f"💡 **Next steps:**\n"
            success_msg += f"• Use `/set_card` to apply this card to an AI\n"
            success_msg += f"• Or use `/setup` with `card_name:{registered_name}`"
            
            await interaction.followup.send(success_msg, ephemeral=True)
            
        except Exception as e:
            func.log.error(f"Error importing card: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ **Error:** Failed to import card: {e}",
                ephemeral=True
            )
    
    @app_commands.command(name="remove_card", description="Remove a character card from the registry")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        card_name="Name of the card to remove",
        delete_file="Also delete the cached file (default: False)",
        force="Skip confirmation if card is in use"
    )
    @app_commands.autocomplete(card_name=card_name_autocomplete)
    async def remove_card(
        self,
        interaction: discord.Interaction,
        card_name: str,
        delete_file: bool = False,
        force: bool = False
    ):
        """Remove a character card from the registry."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        
        # Check if card exists
        card_info = func.get_character_card(server_id, card_name)
        if not card_info:
            await interaction.followup.send(
                f"❌ Card `{card_name}` not found in this server.\n\n"
                f"💡 Use `/list_cards` to see available cards.",
                ephemeral=True
            )
            return
        
        # Check if card is in use
        ais_using = func.get_ais_using_card(server_id, card_name)
        
        if ais_using and not force:
            # Build list of AIs using this card
            ai_list = []
            for channel_id, ai_name in ais_using:
                channel_obj = interaction.guild.get_channel(int(channel_id))
                channel_name = channel_obj.name if channel_obj else f"Channel {channel_id}"
                ai_list.append(f"• `{ai_name}` in #{channel_name}")
            
            ai_list_str = "\n".join(ai_list[:10])
            if len(ais_using) > 10:
                ai_list_str += f"\n• ... and {len(ais_using) - 10} more"
            
            # Send confirmation message
            confirm_msg = await interaction.channel.send(
                f"⚠️ **Remove Card Confirmation** (requested by {interaction.user.mention})\n\n"
                f"**Card:** `{card_name}`\n"
                f"**Character:** {card_info.get('name', card_name)}\n"
                f"**In use by:** {len(ais_using)} AI(s)\n\n"
                f"**AIs using this card:**\n{ai_list_str}\n\n"
                f"⚠️ **Removing this card will:**\n"
                f"• Remove it from the registry\n"
                f"• Break references in AIs using it\n"
                f"{'• **DELETE the cached file**\n' if delete_file else '• Keep the cached file\n'}\n\n"
                f"**React with ✅ to confirm or ❌ to cancel.**"
            )
            
            await interaction.followup.send(
                "✅ Confirmation message sent. Please react to confirm or cancel.",
                ephemeral=True
            )
            
            # Add reactions
            try:
                await confirm_msg.add_reaction("✅")
                await confirm_msg.add_reaction("❌")
            except discord.HTTPException as e:
                func.log.error(f"Failed to add reactions: {e}")
                await confirm_msg.edit(content=f"{confirm_msg.content}\n\n❌ Failed to add reactions. Please try again.")
                return
            
            # Wait for reaction
            def check(reaction, user):
                return (
                    user.id == interaction.user.id and
                    str(reaction.emoji) in ["✅", "❌"] and
                    reaction.message.id == confirm_msg.id
                )
            
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                
                if str(reaction.emoji) == "❌":
                    await confirm_msg.edit(content="❌ Card removal cancelled.")
                    return
                
                # User confirmed
                await confirm_msg.edit(content="🔄 Removing card...")
                
            except asyncio.TimeoutError:
                await confirm_msg.edit(content="⏱️ Timeout. Card removal cancelled.")
                return
        else:
            # No confirmation needed (not in use or force=True)
            confirm_msg = None
        
        # Remove from registry
        success = await func.unregister_character_card(server_id, card_name)
        
        if not success:
            msg = f"❌ Failed to remove card from registry."
            if confirm_msg:
                await confirm_msg.edit(content=msg)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return
        
        # Delete file if requested
        file_deleted = False
        if delete_file:
            cache_path = card_info.get("cache_path")
            if cache_path:
                try:
                    file_path = Path(cache_path)
                    if file_path.exists():
                        file_path.unlink()
                        file_deleted = True
                        func.log.info(f"Deleted card file: {cache_path}")
                except Exception as e:
                    func.log.error(f"Error deleting card file: {e}")
        
        # Clean up AI references
        cleaned_ais = []
        if ais_using:
            for channel_id, ai_name in ais_using:
                try:
                    channel_data = func.get_session_data(server_id, channel_id)
                    if channel_data and ai_name in channel_data:
                        # Remove card reference
                        if "character_card_name" in channel_data[ai_name]:
                            del channel_data[ai_name]["character_card_name"]
                        await func.update_session_data(server_id, channel_id, channel_data)
                        cleaned_ais.append(ai_name)
                except Exception as e:
                    func.log.error(f"Error cleaning AI reference for {ai_name}: {e}")
        
        # Build result message
        result_msg = f"✅ **Card removed successfully!**\n\n"
        result_msg += f"**Card:** `{card_name}`\n"
        result_msg += f"**Character:** {card_info.get('name', card_name)}\n"
        result_msg += f"**File deleted:** {'Yes' if file_deleted else 'No'}\n"
        if cleaned_ais:
            result_msg += f"**AI references cleaned:** {len(cleaned_ais)}\n"
        result_msg += f"\n💡 The card has been removed from the registry."
        
        if confirm_msg:
            await confirm_msg.edit(content=result_msg)
        else:
            await interaction.followup.send(result_msg, ephemeral=True)
    
    @app_commands.command(name="export_card", description="Export a registered character card")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        card_name="Name of the card to export"
    )
    @app_commands.autocomplete(card_name=card_name_autocomplete)
    async def export_card(
        self,
        interaction: discord.Interaction,
        card_name: str
    ):
        """Export a registered character card as a file."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        
        # Get card info
        card_info = func.get_character_card(server_id, card_name)
        if not card_info:
            await interaction.followup.send(
                f"❌ Card `{card_name}` not found in this server.\n\n"
                f"💡 Use `/list_cards` to see available cards.",
                ephemeral=True
            )
            return
        
        # Get cache path
        cache_path = card_info.get("cache_path")
        if not cache_path:
            await interaction.followup.send(
                f"❌ Card cache path not found.",
                ephemeral=True
            )
            return
        
        try:
            file_path = Path(cache_path)
            if not file_path.exists():
                await interaction.followup.send(
                    f"❌ Card file not found: `{file_path.name}`\n\n"
                    f"The file may have been deleted from cache.",
                    ephemeral=True
                )
                return
            
            # Check file size (Discord limit is 25MB for non-nitro)
            file_size = file_path.stat().st_size
            max_size = 25 * 1024 * 1024  # 25MB
            
            if file_size > max_size:
                await interaction.followup.send(
                    f"❌ **Error:** File too large to send via Discord ({file_size / 1024 / 1024:.1f}MB).\n\n"
                    f"**Discord limit:** 25MB\n"
                    f"**File location:** `{cache_path}`\n\n"
                    f"💡 You can manually copy the file from the cache directory.",
                    ephemeral=True
                )
                return
            
            # Send file
            char_name = card_info.get("name", card_name)
            await interaction.followup.send(
                f"✅ **Exporting card:** `{card_name}`\n"
                f"**Character:** {char_name}\n"
                f"**File:** `{file_path.name}` ({file_size / 1024:.1f}KB)",
                file=discord.File(cache_path, filename=file_path.name),
                ephemeral=True
            )
            
            func.log.info(f"Exported card '{card_name}' to user {interaction.user.id}")
            
        except Exception as e:
            func.log.error(f"Error exporting card: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ **Error:** Failed to export card: {e}",
                ephemeral=True
            )
    
    @app_commands.command(name="list_cards", description="List all registered character cards in this server")
    @app_commands.default_permissions(administrator=True)
    async def list_cards(self, interaction: discord.Interaction):
        """List all character cards registered in the server with improved visualization."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        cards = func.list_character_cards(server_id)
        
        if not cards:
            await interaction.followup.send(
                "❌ No character cards registered in this server.\n\n"
                "💡 **How to add cards:**\n"
                "• Use `/import_card` to register a card\n"
                "• Or use `/setup` with a `card_url` parameter\n"
                "• Supports PNG, JSON, and CHARX formats\n"
                "• Character Card V3 spec supported",
                ephemeral=True
            )
            return
        
        # Collect card information with usage data
        card_list = []
        for card_name, card_info in cards.items():
            ais_using = func.get_ais_using_card(server_id, card_name)
            card_list.append({
                "card_name": card_name,
                "card_info": card_info,
                "usage_count": len(ais_using),
                "ais_using": ais_using
            })
        
        # Sort: most used first, then alphabetically
        card_list.sort(key=lambda x: (-x["usage_count"], x["card_name"].lower()))
        
        # Create embed with better colors
        embed = discord.Embed(
            title=f"🎭 Character Cards - {interaction.guild.name}",
            description=f"**Total Cards:** {len(cards)} registered",
            color=discord.Color.purple()
        )
        
        # Add card fields with improved formatting
        for idx, card_data in enumerate(card_list, 1):
            card_name = card_data["card_name"]
            card_info = card_data["card_info"]
            usage_count = card_data["usage_count"]
            ais_using = card_data["ais_using"]
            
            char_name = card_info.get("name", card_name)
            creator = card_info.get("creator", "Unknown")
            
            # Determine emoji based on usage
            if usage_count > 0:
                emoji = "🟢"
                status = f"**In use by {usage_count} AI{'s' if usage_count != 1 else ''}**"
            else:
                emoji = "⚪"
                status = "Not in use"
            
            # Build field name
            field_name = f"{emoji} **{card_name}**"
            
            # Build field value
            field_value = f"**Character:** {char_name}\n"
            field_value += f"**Creator:** {creator}\n"
            field_value += f"**Status:** {status}\n"
            
            # Add AI list if in use (max 3)
            if ais_using:
                ai_names = []
                for channel_id, ai_name in ais_using[:3]:
                    channel_obj = interaction.guild.get_channel(int(channel_id))
                    channel_name = channel_obj.name if channel_obj else f"ch-{channel_id[:4]}"
                    ai_names.append(f"`{ai_name}` (#{channel_name})")
                
                field_value += f"**Used by:** {', '.join(ai_names)}"
                if len(ais_using) > 3:
                    field_value += f" +{len(ais_using) - 3} more"
                field_value += "\n"
            
            embed.add_field(
                name=field_name,
                value=field_value,
                inline=False
            )
        
        # Add helpful footer
        embed.set_footer(
            text=f"💡 Use /import_card to add • /set_card to apply • /export_card to download"
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    """Load the CardRegistry cog."""
    await bot.add_cog(CardRegistry(bot))
