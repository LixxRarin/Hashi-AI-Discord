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
from typing import Optional, List

import utils.func as func
from commands.shared.autocomplete import AutocompleteHelpers
from utils.pagination import PaginatedView
from utils.media.thumbnails import get_thumbnail_for_card_registry
from utils.discord.confirmation_ui import confirm_dangerous_action, create_success_embed


# Module-level autocomplete functions (must be defined before class)
async def card_name_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for card names."""
    return await AutocompleteHelpers.card_name(interaction, current)


class CardRegistry(commands.Cog):
    """Manages the central registry of character cards."""

    def __init__(self, bot):
        self.bot = bot
    
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
            
            # Upload initial thumbnail to CDN cache (if PNG and no avatar URL)
            thumbnail_cached = False
            if cache_path and Path(cache_path).suffix.lower() == '.png':
                try:
                    from utils.media.thumbnails import upload_to_cdn_cache, update_thumbnail_cache, get_avatar_url_from_card, validate_cdn_url

                    # Check if card has avatar URL - if yes, skip CDN upload
                    card_data_wrapped = {"data": character_card.to_dict()["data"]}
                    avatar_url = get_avatar_url_from_card(card_data_wrapped)

                    should_upload = True
                    if avatar_url:
                        func.log.info("Card has avatar URL, validating...")
                        if await validate_cdn_url(avatar_url):
                            func.log.info("Avatar URL is valid, skipping CDN upload")
                            should_upload = False
                        else:
                            func.log.warning("Avatar URL validation failed, will upload to CDN")

                    if should_upload:
                        func.log.info("Uploading initial thumbnail to CDN cache...")
                        cdn_url = await upload_to_cdn_cache(
                            interaction.channel,
                            cache_path,
                            server_id
                        )

                        if cdn_url:
                            # Save to cache
                            thumbnail_cached = await update_thumbnail_cache(
                                server_id,
                                registered_name,
                                cdn_url
                            )
                            if thumbnail_cached:
                                func.log.info(f"Thumbnail cached for card '{registered_name}'")
                except Exception as e:
                    func.log.warning(f"Failed to cache thumbnail during import: {e}")
                    # Don't fail the import if thumbnail caching fails
            
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
        
        # Get character card thumbnail
        thumbnail_url = await get_thumbnail_for_card_registry(
            interaction.channel,
            card_name,
            server_id
        )
        
        # Get character info
        char_name = card_info.get('name', card_name)
        creator = card_info.get('creator', 'Unknown')
        
        # Build AI usage list
        ai_usage_text = ""
        if ais_using:
            ai_list = []
            for channel_id, ai_name in ais_using[:5]:
                channel_obj = interaction.guild.get_channel(int(channel_id))
                channel_mention = f"<#{channel_id}>" if channel_obj else f"Channel {channel_id}"
                ai_list.append(f"• `{ai_name}` in {channel_mention}")
            
            ai_usage_text = "\n".join(ai_list)
            if len(ais_using) > 5:
                ai_usage_text += f"\n• ... and {len(ais_using) - 5} more"
        
        # Prepare detail fields
        details_fields = [
            {
                "name": "📊 Card Details",
                "value": f"• **Card ID:** `{card_name}`\n"
                        f"• **Character:** {char_name}\n"
                        f"• **Creator:** {creator}\n"
                        f"• **In Use:** {len(ais_using)} AI(s)"
            }
        ]
        
        # Add usage information if card is in use
        if ais_using:
            details_fields.append({
                "name": "🤖 AIs Using This Card",
                "value": ai_usage_text
            })
        
        # Add what will be deleted
        deletion_info = "• Remove from registry\n"
        if ais_using:
            deletion_info += f"• Clean {len(ais_using)} AI reference(s)\n"
        if delete_file:
            deletion_info += "• **DELETE the cached file**\n"
        else:
            deletion_info += "• Keep the cached file\n"
        
        details_fields.append({
            "name": "💾 Actions to Perform",
            "value": deletion_info
        })
        
        details_fields.append({
            "name": "⚠️ Warning",
            "value": "**This will permanently remove the card from the registry!**\n"
                    + ("The cached file will also be deleted.\n" if delete_file else "")
                    + ("AIs using this card will have broken references.\n" if ais_using else "")
                    + "This action cannot be undone."
        })
        
        # Define confirmation callback
        async def on_confirm(confirm_interaction: discord.Interaction):
            # Remove from registry
            success = await func.unregister_character_card(server_id, card_name)
            
            if not success:
                from utils.discord.confirmation_ui import create_error_embed
                error_embed = create_error_embed(
                    title="❌ Removal Failed",
                    description="Failed to remove card from registry. Check logs for details."
                )
                await confirm_interaction.response.edit_message(
                    embed=error_embed,
                    view=None
                )
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
                        func.log.error(f"Error cleaning AI reference: {e}")
            
            func.log.info(f"Removed card '{card_name}' from server {server_id}")
            
            # Create success embed
            success_fields = [
                {
                    "name": "📊 Summary",
                    "value": f"• **Card:** `{card_name}`\n"
                            f"• **Character:** {char_name}\n"
                            f"• **File Deleted:** {'Yes' if file_deleted else 'No'}\n"
                            f"• **AI References Cleaned:** {len(cleaned_ais)}\n"
                            f"• **Removed by:** {interaction.user.mention}"
                }
            ]
            
            success_embed = create_success_embed(
                title="✅ Card Removed Successfully",
                description=f"The character card **{char_name}** has been removed from the registry.",
                fields=success_fields,
                thumbnail_url=thumbnail_url
            )
            
            await confirm_interaction.response.edit_message(
                embed=success_embed,
                view=None
            )
        
        # Show double confirmation dialog
        await confirm_dangerous_action(
            interaction=interaction,
            action_name="Remove Card",
            warning_message="This will permanently remove the card from the registry!",
            details_fields=details_fields,
            on_confirm=on_confirm,
            thumbnail_url=thumbnail_url
        )
    
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
        """List all character cards registered in the server, separated by usage status with pagination."""
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
        cards_in_use = []
        cards_available = []
        
        for card_name, card_info in cards.items():
            ais_using = func.get_ais_using_card(server_id, card_name)
            card_data = {
                "card_name": card_name,
                "card_info": card_info,
                "usage_count": len(ais_using),
                "ais_using": ais_using
            }
            
            if len(ais_using) > 0:
                cards_in_use.append(card_data)
            else:
                cards_available.append(card_data)
        
        # Sort each category alphabetically
        cards_in_use.sort(key=lambda x: x["card_name"].lower())
        cards_available.sort(key=lambda x: x["card_name"].lower())
        
        # Upload thumbnails to Discord CDN before creating embeds
        # Since we show 1 card per page, upload thumbnail for EACH card
        thumbnail_urls = {}  # card_name -> thumbnail_url
        
        # Upload thumbnail for each card in use
        for card_data in cards_in_use:
            card_name = card_data["card_name"]
            thumbnail_url = await get_thumbnail_for_card_registry(
                interaction.channel,
                card_name,
                server_id
            )
            if thumbnail_url:
                thumbnail_urls[card_name] = thumbnail_url
        
        # Upload thumbnail for each available card
        for card_data in cards_available:
            card_name = card_data["card_name"]
            thumbnail_url = await get_thumbnail_for_card_registry(
                interaction.channel,
                card_name,
                server_id
            )
            if thumbnail_url:
                thumbnail_urls[card_name] = thumbnail_url
        
        # Create embeds list
        embeds = []
        
        # Combine all cards for unified pagination
        all_cards = cards_in_use + cards_available
        total_cards = len(all_cards)
        
        # Create one embed per card
        for idx, card_data in enumerate(all_cards):
            card_name = card_data["card_name"]
            card_info = card_data["card_info"]
            usage_count = card_data["usage_count"]
            ais_using = card_data["ais_using"]
            
            char_name = card_info.get("name", card_name)
            creator = card_info.get("creator", "Unknown")
            
            # Determine status and color
            if usage_count > 0:
                status_emoji = "🟢"
                status_text = f"In Use • {usage_count} AI{'s' if usage_count != 1 else ''} using this card"
                color = discord.Color.green()
            else:
                status_emoji = "⚪"
                status_text = "Available • Ready to use"
                color = discord.Color.greyple()
            
            # Create embed with character name as title
            embed = discord.Embed(
                title=f"{char_name}",
                description=f"{status_emoji} {status_text}",
                color=color
            )
            
            # Add main information field
            info_value = f"• **Character:** {char_name}\n"
            info_value += f"• **Creator:** {creator}\n"
            info_value += f"• **Card ID:** `{card_name}`"
            
            embed.add_field(
                name="📊 Information",
                value=info_value,
                inline=False
            )
            
            # Add usage information if card is in use
            if usage_count > 0:
                # Build channel list
                channel_list = []
                for channel_id, ai_name in ais_using[:3]:
                    channel_obj = interaction.guild.get_channel(int(channel_id))
                    if channel_obj:
                        channel_list.append(f"<#{channel_id}>")
                
                usage_value = f"• **AIs:** {', '.join([f'`{ai}`' for _, ai in ais_using[:3]])}\n"
                usage_value += f"• **Channels:** {', '.join(channel_list)}"
                
                if len(ais_using) > 3:
                    usage_value += f"\n• **+{len(ais_using) - 3} more**"
                
                embed.add_field(
                    name="🤖 Current Usage",
                    value=usage_value,
                    inline=False
                )
            
            # Add thumbnail if available
            if card_name in thumbnail_urls:
                embed.set_thumbnail(url=thumbnail_urls[card_name])
            
            # Footer with position and helpful tip
            embed.set_footer(text=f"Card {idx + 1}/{total_cards} • Use /set_card to apply • /character_info for details")
            
            embeds.append(embed)
        
        # Send with pagination if multiple embeds
        if len(embeds) == 0:
            await interaction.followup.send(
                "❌ No character cards registered in this server.",
                ephemeral=True
            )
        elif len(embeds) == 1:
            # Single embed, send directly
            await interaction.followup.send(embed=embeds[0], ephemeral=True)
        else:
            # Multiple embeds, use pagination (thumbnails work via CDN URLs)
            view = PaginatedView(embeds, user_id=interaction.user.id)
            message = await interaction.followup.send(
                embed=view.get_current_embed(),
                view=view,
                ephemeral=True
            )
            view.message = message


async def setup(bot):
    """Load the CardRegistry cog."""
    await bot.add_cog(CardRegistry(bot))
