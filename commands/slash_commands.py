import time
import discord
from discord import app_commands
from discord.ext import commands
from typing import List

import utils.func as func
from commands.shared.autocomplete import AutocompleteHelpers
from utils.pagination import PaginatedView

# Import AI module to trigger provider registration
import AI
from AI.provider_registry import get_registry


class SlashCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def ai_name_all_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for all AI names."""
        return await AutocompleteHelpers.ai_name_all(interaction, current)
    
    async def card_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for card names."""
        return await AutocompleteHelpers.card_name(interaction, current)
    
    async def connection_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete function for API connection names."""
        try:
            server_id = str(interaction.guild.id)
            connections = func.list_api_connections(server_id)
            
            if not connections:
                return []
            
            choices = []
            for conn_name, conn_data in connections.items():
                if current.lower() in conn_name.lower():
                    provider = conn_data.get("provider", "unknown").upper()
                    model = conn_data.get("model", "unknown")
                    display_name = f"{conn_name} [{provider}] ({model})"
                    choices.append(app_commands.Choice(name=display_name[:100], value=conn_name))
            
            return choices[:25]
        except Exception as e:
            func.log.error(f"Error in connection_name_autocomplete: {e}")
            return []

    @app_commands.command(name="character_info", description="Show detailed Character Card V3 information.")
    @app_commands.describe(
        ai_name="Name of the AI to view Character Card information (optional if card_name is provided)",
        card_name="Name of a registered card to view (optional if ai_name is provided)"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete, card_name=card_name_autocomplete)
    async def character_info(
        self,
        interaction: discord.Interaction,
        ai_name: str = None,
        card_name: str = None
    ):
        """
        Display detailed Character Card V3 information with image.
        Can be used with either ai_name or card_name.
        """
        await interaction.response.defer()

        server_id = str(interaction.guild.id)
        
        # Validate that at least one parameter is provided
        if not ai_name and not card_name:
            await interaction.followup.send(
                "❌ **Error:** You must provide either `ai_name` or `card_name`.\n\n"
                "**Usage:**\n"
                "• `/character_info ai_name:MyBot` - View card from an active AI\n"
                "• `/character_info card_name:MyCard` - View a registered card directly",
                ephemeral=True
            )
            return
        
        # Validate that only one parameter is provided
        if ai_name and card_name:
            await interaction.followup.send(
                "❌ **Error:** Please provide only ONE parameter (either `ai_name` or `card_name`, not both).",
                ephemeral=True
            )
            return
        
        card_data = None
        session = None
        found_channel_id = None
        card_info = None
        display_ai_name = None
        
        # Option 1: Load from AI name
        if ai_name:
            # Get AI session data
            found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
            
            if not found_ai_data:
                await interaction.followup.send(
                    f"❌ AI '{ai_name}' not found in this server.\n\n"
                    f"💡 Use `/list_ais` to see available AIs.",
                    ephemeral=True
                )
                return
            
            found_channel_id, session = found_ai_data
            
            # Verify session data is valid
            if session is None:
                await interaction.followup.send(
                    f"❌ AI '{ai_name}' session data is invalid or corrupted.",
                    ephemeral=True
                )
                return
            
            # Check if AI has a character card loaded
            card_data = session.get("character_card", {}).get("data", {})
            if not card_data:
                await interaction.followup.send(
                    f"❌ AI '{ai_name}' does not have a Character Card loaded.\n\n"
                    f"💡 Use `/setup` with a card source to load a Character Card.",
                    ephemeral=True
                )
                return
            
            # Get character card metadata
            registered_card_name = session.get("character_card_name")
            if registered_card_name:
                card_info = func.get_character_card(server_id, registered_card_name)
            
            display_ai_name = ai_name
        
        # Option 2: Load from card name
        elif card_name:
            # Get card from registry
            card_info = func.get_character_card(server_id, card_name)
            
            if not card_info:
                await interaction.followup.send(
                    f"❌ Card '{card_name}' not found in this server.\n\n"
                    f"💡 Use `/list_cards` to see available cards or `/import_card` to add new ones.",
                    ephemeral=True
                )
                return
            
            # Load card data from cache
            cache_path = card_info.get("cache_path")
            if not cache_path:
                await interaction.followup.send(
                    f"❌ Card cache path not found for '{card_name}'.",
                    ephemeral=True
                )
                return
            
            from pathlib import Path
            card_file = Path(cache_path)
            
            if not card_file.exists():
                await interaction.followup.send(
                    f"❌ Card file not found: `{card_file.name}`\n\n"
                    f"The file may have been deleted from cache.",
                    ephemeral=True
                )
                return
            
            # Parse card file
            from utils.ccv3.parser import parse_character_card
            with open(card_file, 'rb') as f:
                raw_data = f.read()
            
            character_card = parse_character_card(raw_data)
            if not character_card:
                await interaction.followup.send(
                    f"❌ Failed to parse card file for '{card_name}'.",
                    ephemeral=True
                )
                return
            
            card_data = character_card.to_dict()["data"]
            
            # Create a minimal session-like dict for the embed builder
            session = {
                "character_card": {
                    "data": card_data,
                    "spec_version": character_card.spec_version,
                    "cache_path": cache_path
                },
                "character_card_name": card_name,
                "config": {"greeting_index": 0},
                "mode": "N/A"
            }
            
            display_ai_name = f"Card: {card_name}"
        
        # Build Character Card V3 embed with information
        embed, file = await self._build_character_card_embed(
            card_data, display_ai_name, session, card_info, server_id, found_channel_id
        )
        
        # Send embed with image file if available
        if file:
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

    async def _build_character_card_embed(
        self,
        card_data: dict,
        ai_name: str,
        session: dict,
        card_info: dict,
        server_id: str,
        channel_id: str
    ) -> tuple:
        """
        Build a detailed Character Card V3 embed.
        
        Returns:
            tuple: (embed, file) where file is the character image or None
        """
        
        # Extract Character Card V3 fields
        char_name = card_data.get("name", ai_name)
        nickname = card_data.get("nickname")
        display_name = nickname or char_name
        
        creator = card_data.get("creator", "Unknown")
        character_version = card_data.get("character_version", "N/A")
        description = card_data.get("description", "No description available.")
        personality = card_data.get("personality", "")
        scenario = card_data.get("scenario", "")
        tags = card_data.get("tags", [])
        
        # Greeting information
        first_mes = card_data.get("first_mes", "")
        alternate_greetings = card_data.get("alternate_greetings") or []
        group_only_greetings = card_data.get("group_only_greetings") or []
        total_greetings = 1 + len(alternate_greetings)
        current_greeting_index = session.get("config", {}).get("greeting_index", 0)
        
        # Lorebook information
        character_book = card_data.get("character_book")
        lorebook_entries = len(character_book.get("entries", [])) if character_book else 0
        
        # Metadata
        spec_version = session.get("character_card", {}).get("spec_version", "3.0")
        creation_date = card_data.get("creation_date")
        modification_date = card_data.get("modification_date")
        source = card_data.get("source", [])
        
        # Creator notes
        creator_notes = card_data.get("creator_notes", "")
        
        # Build compact description with metadata
        embed_description = f"🎭 Character Card V{spec_version}\n**By:** {creator}"
        if character_version != "N/A":
            embed_description += f"\n**Version:** {character_version}"
        
        # Create embed with character name as title
        embed = discord.Embed(
            title=display_name,
            description=embed_description,
            color=discord.Color.purple()
        )
        
        # Add character card image
        file = None
        avatar_path = None
        
        # Extract avatar from card file
        if session.get("character_card"):
            cache_path = session.get("character_card", {}).get("cache_path")
            if cache_path:
                from pathlib import Path
                import tempfile
                
                card_file = Path(cache_path)
                func.log.debug(f"Extracting avatar from card file: {card_file}")
                
                try:
                    if card_file.exists():
                        # For PNG files, the file itself is the avatar
                        if card_file.suffix.lower() == '.png':
                            avatar_path = str(card_file)
                            func.log.debug(f"Using PNG card file as avatar: {avatar_path}")
                        # For CHARX files, extract from ZIP
                        elif card_file.suffix.lower() == '.charx':
                            import zipfile
                            try:
                                with zipfile.ZipFile(card_file, 'r') as zf:
                                    # Look for avatar in assets
                                    for name in zf.namelist():
                                        if 'icon' in name.lower() or 'avatar' in name.lower():
                                            # Extract to temp file
                                            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                                                tmp.write(zf.read(name))
                                                avatar_path = tmp.name
                                            func.log.debug(f"Extracted avatar from CHARX to: {avatar_path}")
                                            break
                            except Exception as e:
                                func.log.warning(f"Failed to extract avatar from CHARX: {e}")
                except Exception as e:
                    func.log.error(f"Error extracting avatar from card file: {e}")
        
        # Try to load the avatar if we have a path
        if avatar_path:
            try:
                from pathlib import Path
                avatar_file = Path(avatar_path)
                
                if avatar_file.exists():
                    file = discord.File(avatar_file, filename="character_avatar.png")
                    embed.set_image(url="attachment://character_avatar.png")
                    func.log.debug(f"Loaded character image from {avatar_path}")
                else:
                    func.log.warning(f"Avatar file does not exist at: {avatar_file}")
            except Exception as e:
                func.log.error(f"Error loading character image: {e}")
        
        # About field - short description preview (200 chars)
        if description:
            desc_preview = description[:200]
            if len(description) > 200:
                desc_preview += "..."
            embed.add_field(
                name="📝 About",
                value=desc_preview,
                inline=False
            )
        
        # Personality field - short preview (150 chars)
        if personality:
            personality_preview = personality[:150]
            if len(personality) > 150:
                personality_preview += "..."
            embed.add_field(
                name="💭 Personality",
                value=personality_preview,
                inline=False
            )
        
        # Configuration field - AI, channel, greetings, lorebook
        config_lines = []
        
        # AI name and channel
        if channel_id:
            try:
                channel_obj = self.bot.get_channel(int(channel_id))
                channel_name = channel_obj.name if channel_obj else "Unknown"
                config_lines.append(f"• **AI:** {ai_name}")
                config_lines.append(f"• **Channel:** #{channel_name}")
            except Exception as e:
                func.log.warning(f"Could not get channel name: {e}")
                config_lines.append(f"• **AI:** {ai_name}")
        else:
            # Card is being viewed directly from registry
            config_lines.append(f"• **Status:** Registered card (not in use)")
        
        # Greetings
        config_lines.append(f"• **Greetings:** {total_greetings} available")
        
        # Lorebook
        if lorebook_entries > 0:
            config_lines.append(f"• **Lorebook:** {lorebook_entries} entries")
        
        embed.add_field(
            name="⚙️ Configuration",
            value="\n".join(config_lines),
            inline=False
        )
        
        # Dates field (inline)
        if creation_date or modification_date:
            date_lines = []
            if creation_date and creation_date > 0:
                date_lines.append(f"**Created:** <t:{creation_date}:D>")
            if modification_date and modification_date > 0:
                date_lines.append(f"**Modified:** <t:{modification_date}:D>")
            
            if date_lines:
                embed.add_field(
                    name="📊 Details",
                    value="\n".join(date_lines),
                    inline=True
                )
        
        embed.set_footer(text="Use /select_greeting to change greeting")
        
        return embed, file

    @app_commands.command(name="ping", description="Displays latency and possible connection issues.")
    async def ping(self, interaction: discord.Interaction):
        # Defer immediately to avoid timeout
        await interaction.response.defer()
        
        # Measure API latency
        start = time.perf_counter()
        await interaction.followup.send("Calculating ping...", ephemeral=True)
        end = time.perf_counter()
        api_ping = round((end - start) * 1000)

        # Get gateway latency
        gateway_ping = round(self.bot.latency * 1000)

        # Determine connection status
        if gateway_ping < 100 and api_ping < 200:
            speed_status = "Your connection is very fast!"
        elif gateway_ping < 200 and api_ping < 350:
            speed_status = "Your connection is stable."
        elif gateway_ping < 300 and api_ping < 500:
            speed_status = "Your connection is somewhat slow."
        else:
            speed_status = "Your connection is very slow! Expect delays."

        # Check for warnings
        warnings = []
        if gateway_ping > 400:
            warnings.append("High gateway latency! The bot may be slow to respond.")
        if api_ping > 700:
            warnings.append("High API latency! Discord's response times may be delayed.")
        if gateway_ping > 500 and api_ping > 800:
            warnings.append("**Severe connection issues detected!** Commands may be very slow.")

        warning_message = "\n".join(warnings) if warnings else "No connection issues detected."

        # Build final message
        message = (
            f"🏓 **Pong!**\n"
            f"📡 **Gateway Ping:** `{gateway_ping}ms`\n"
            f"⚡ **API Ping:** `{api_ping}ms`\n"
            f"🌐 **Connection Speed:** {speed_status}\n"
            f"🚨 **Warnings:** {warning_message}"
        )

        # Edit the initial response
        await interaction.edit_original_response(content=message)

    @app_commands.command(name="copy_config", description="Copies all settings from one AI to another!")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        from_ai_name="Name of the source AI",
        to_ai_name="Name of the target AI"
    )
    @app_commands.autocomplete(from_ai_name=ai_name_all_autocomplete)
    @app_commands.autocomplete(to_ai_name=ai_name_all_autocomplete)
    async def copy_config(self, interaction: discord.Interaction, from_ai_name: str, to_ai_name: str):
        server_id = str(interaction.guild.id)
        
        from_ai_data = func.get_ai_session_data_from_all_channels(server_id, from_ai_name)
        to_ai_data = func.get_ai_session_data_from_all_channels(server_id, to_ai_name)

        if not from_ai_data:
            await interaction.response.send_message(
                f"⚠️ AI '{from_ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        if not to_ai_data:
            await interaction.response.send_message(
                f"⚠️ AI '{to_ai_name}' not found in this server.",
                ephemeral=True
            )
            return

        from_channel_id, from_session = from_ai_data
        to_channel_id, to_session = to_ai_data
        
        # Verify session data is valid
        if from_session is None:
            await interaction.response.send_message(
                f"❌ AI '{from_ai_name}' session data is invalid or corrupted.",
                ephemeral=True
            )
            return
        if to_session is None:
            await interaction.response.send_message(
                f"❌ AI '{to_ai_name}' session data is invalid or corrupted.",
                ephemeral=True
            )
            return

        from_provider = from_session.get("provider", "openai")
        to_provider = to_session.get("provider", "openai")

        # Warn if copying between different providers
        if from_provider != to_provider:
            await interaction.response.send_message(
                f"⚠️ Warning: Copying config from {from_provider.upper()} to {to_provider.upper()}. "
                "Provider-specific settings may not be compatible.",
                ephemeral=True
            )

        to_channel_data = func.get_session_data(server_id, to_channel_id)
        to_channel_data[to_ai_name]["config"] = from_session.get("config", {}).copy()
        
        await func.update_session_data(server_id, to_channel_id, to_channel_data)

        await interaction.response.send_message(
            f"✅ Settings successfully copied from AI '{from_ai_name}' to AI '{to_ai_name}'!",
            ephemeral=True
        )

    @app_commands.command(name="mute", description="Mute a user so the AI does not capture their messages")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to mute user for",
        user="User to mute"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def mute(self, interaction: discord.Interaction, ai_name: str, user: discord.Member):
        server_id = str(interaction.guild.id)
        
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        found_channel_id, session = found_ai_data
        
        # Verify session data is valid
        if session is None:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' session data is invalid or corrupted.",
                ephemeral=True
            )
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)

        muted_users = session.setdefault("muted_users", [])
        if user.id not in muted_users:
            muted_users.append(user.id)
            channel_data[ai_name] = session
            await func.update_session_data(server_id, found_channel_id, channel_data)
            await interaction.response.send_message(
                f"✅ {user.mention} has been muted for AI '{ai_name}'.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⚠️ {user.mention} is already muted for AI '{ai_name}'.",
                ephemeral=True
            )

    @app_commands.command(name="unmute", description="Unmute a user so the AI captures their messages")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to unmute user for",
        user="User to unmute"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def unmute(self, interaction: discord.Interaction, ai_name: str, user: discord.Member):
        server_id = str(interaction.guild.id)
        
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        found_channel_id, session = found_ai_data
        
        # Verify session data is valid
        if session is None:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' session data is invalid or corrupted.",
                ephemeral=True
            )
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)

        muted_users = session.get("muted_users", [])
        if user.id in muted_users:
            muted_users.remove(user.id)
            channel_data[ai_name] = session
            await func.update_session_data(server_id, found_channel_id, channel_data)
            await interaction.response.send_message(
                f"✅ {user.mention} has been unmuted for AI '{ai_name}'.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⚠️ {user.mention} is not muted for AI '{ai_name}'.",
                ephemeral=True
            )

    @app_commands.command(name="list_muted", description="List all muted users for a specific AI")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(ai_name="Name of the AI to list muted users for")
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def list_muted(self, interaction: discord.Interaction, ai_name: str):
        """List all muted users for an AI."""
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.followup.send(
                f"❌ AI '{ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        found_channel_id, session = found_ai_data
        
        # Verify session data is valid
        if session is None:
            await interaction.followup.send(
                f"❌ AI '{ai_name}' session data is invalid or corrupted.",
                ephemeral=True
            )
            return
        
        muted_users = session.get("muted_users", [])

        if not muted_users:
            await interaction.followup.send(
                f"✅ No users are currently muted for AI '{ai_name}'.",
                ephemeral=True
            )
            return

        # Create embed with simplified layout
        embed = discord.Embed(
            title="Muted Users",
            description=f"AI: {ai_name} • {len(muted_users)} muted users",
            color=discord.Color.red()
        )
        
        # Add users inline (more compact) - group in chunks of 5 per line
        user_lines = []
        for i in range(0, len(muted_users), 5):
            chunk = muted_users[i:i+5]
            mentions = [f"<@{user_id}>" for user_id in chunk]
            user_lines.append("• " + " ".join(mentions))
        
        # Join all lines, respecting Discord's 1024 char limit per field
        users_text = "\n".join(user_lines)
        
        # If text is too long, split into multiple fields
        if len(users_text) <= 1024:
            embed.add_field(
                name="👥 List",
                value=users_text,
                inline=False
            )
        else:
            # Split into multiple fields if needed
            current_text = ""
            field_num = 1
            for line in user_lines:
                if len(current_text) + len(line) + 1 > 1024:
                    embed.add_field(
                        name=f"👥 List (part {field_num})",
                        value=current_text,
                        inline=False
                    )
                    current_text = line
                    field_num += 1
                else:
                    if current_text:
                        current_text += "\n"
                    current_text += line
            
            # Add remaining text
            if current_text:
                embed.add_field(
                    name=f"👥 List (part {field_num})",
                    value=current_text,
                    inline=False
                )
        
        embed.set_footer(text="Use /unmute to unmute")
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SlashCommands(bot))