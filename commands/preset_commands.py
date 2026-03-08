"""
Preset Management Commands

Commands for saving, loading, and managing AI configuration presets.
"""

import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from utils.ai_config_manager import get_ai_config_manager
from commands.shared.autocomplete import AutocompleteHelpers


class PresetCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_manager = get_ai_config_manager()
    
    async def ai_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for AI names."""
        return await AutocompleteHelpers.ai_name_all(interaction, current)
    
    async def preset_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for preset names."""
        return await AutocompleteHelpers.preset_name(interaction, current)
    
    @app_commands.command(name="preset_save", description="Save current AI configuration as a preset")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to save configuration from",
        preset_name="Name for the preset (will be used to load it later)",
        description="Optional description of what this preset is for"
    )
    @app_commands.autocomplete(ai_name=ai_name_autocomplete)
    async def preset_save(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        preset_name: str,
        description: str = ""
    ):
        """Save an AI's current configuration as a preset."""
        server_id = str(interaction.guild.id)
        
        # Get AI session data
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        found_channel_id, session = found_ai_data
        
        if session is None:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' session data is invalid or corrupted.",
                ephemeral=True
            )
            return
        
        # Get the config from the session
        config = session.get("config", {})
        
        if not config:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' has no configuration to save.",
                ephemeral=True
            )
            return
        
        # Save the preset
        author = str(interaction.user.name)
        success = self.config_manager.save_preset(
            preset_name=preset_name,
            config=config,
            description=description,
            author=author
        )
        
        if success:
            await interaction.response.send_message(
                f"✅ **Preset saved successfully!**\n\n"
                f"📦 **Name:** `{preset_name}`\n"
                f"📝 **Description:** {description if description else 'None'}\n"
                f"👤 **Author:** {author}\n"
                f"🤖 **Source AI:** {ai_name}\n\n"
                f"💡 Use `/preset_apply {preset_name} <ai_name>` to apply this preset to another AI.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Failed to save preset '{preset_name}'. Check logs for details.",
                ephemeral=True
            )
    
    @app_commands.command(name="preset_apply", description="Apply a saved preset to an AI")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        preset_name="Name of the preset to apply",
        ai_name="Name of the AI to apply the preset to"
    )
    @app_commands.autocomplete(preset_name=preset_name_autocomplete)
    @app_commands.autocomplete(ai_name=ai_name_autocomplete)
    async def preset_apply(
        self,
        interaction: discord.Interaction,
        preset_name: str,
        ai_name: str
    ):
        """Apply a saved preset to an AI."""
        server_id = str(interaction.guild.id)
        
        # Get AI session data
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        found_channel_id, session = found_ai_data
        
        if session is None:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' session data is invalid or corrupted.",
                ephemeral=True
            )
            return
        
        # Load the preset
        preset_config = self.config_manager.load_preset(preset_name)
        
        if preset_config is None:
            await interaction.response.send_message(
                f"❌ Preset '{preset_name}' not found.\n\n"
                f"💡 Use `/preset_list` to see available presets.",
                ephemeral=True
            )
            return
        
        # Apply the preset to the AI
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name]["config"] = preset_config
        
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Preset applied successfully!**\n\n"
            f"📦 **Preset:** `{preset_name}`\n"
            f"🤖 **Applied to:** {ai_name}\n\n"
            f"💡 The AI's configuration has been updated with the preset settings.",
            ephemeral=True
        )
    
    @app_commands.command(name="preset_list", description="List all available configuration presets")
    async def preset_list(self, interaction: discord.Interaction):
        """List all available presets with pagination - one preset per page."""
        await interaction.response.defer(ephemeral=False)
        
        presets = self.config_manager.list_presets()
        
        if not presets:
            await interaction.followup.send(
                "📦 **No presets available**\n\n"
                "You haven't created any presets yet.\n\n"
                "💡 Use `/preset_save` to save an AI's configuration as a preset.",
                ephemeral=True
            )
            return
        
        from utils.pagination import PaginatedView
        
        # Create embeds - one per preset
        embeds = []
        
        for idx, preset in enumerate(presets):
            name = preset["name"]
            description = preset.get("description", "No description")
            author = preset.get("author", "unknown")
            
            # Load full preset to get config preview
            preset_config = self.config_manager.load_preset(name)
            
            # Create embed with preset name as title
            embed = discord.Embed(
                title=name,
                description=f"📦 Configuration Preset • By: {author}",
                color=discord.Color.blue()
            )
            
            # Description field
            embed.add_field(
                name="📝 Description",
                value=description if description else "No description provided",
                inline=False
            )
            
            # Main configurations preview
            if preset_config:
                config_lines = []
                
                # Display settings
                if "use_card_ai_display_name" in preset_config:
                    config_lines.append(f"• Display: Card Name {'✅' if preset_config['use_card_ai_display_name'] else '❌'}")
                if "send_the_greeting_message" in preset_config:
                    config_lines.append(f"• Greeting: {'✅' if preset_config['send_the_greeting_message'] else '❌'}")
                
                # Timing
                if "delay_for_generation" in preset_config:
                    config_lines.append(f"• Delay: {preset_config['delay_for_generation']}s")
                
                # Systems
                if "enable_memory_system" in preset_config:
                    config_lines.append(f"• Memory: {'✅' if preset_config['enable_memory_system'] else '❌'}")
                if "sleep_mode_enabled" in preset_config:
                    config_lines.append(f"• Sleep Mode: {'✅' if preset_config['sleep_mode_enabled'] else '❌'}")
                
                if config_lines:
                    embed.add_field(
                        name="⚙️ Main Settings",
                        value="\n".join(config_lines[:10]),  # Limit to 10 lines
                        inline=False
                    )
            
            # Footer with position and helpful tip
            embed.set_footer(text=f"Preset {idx + 1}/{len(presets)} • Use /preset_info for full details")
            
            embeds.append(embed)
        
        # Send with pagination if multiple presets
        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0], ephemeral=False)
        else:
            view = PaginatedView(embeds, user_id=interaction.user.id)
            message = await interaction.followup.send(
                embed=view.get_current_embed(),
                view=view,
                ephemeral=False
            )
            view.message = message
    
    @app_commands.command(name="preset_delete", description="Delete a configuration preset")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(preset_name="Name of the preset to delete")
    @app_commands.autocomplete(preset_name=preset_name_autocomplete)
    async def preset_delete(
        self,
        interaction: discord.Interaction,
        preset_name: str
    ):
        """Delete a saved preset."""
        success = self.config_manager.delete_preset(preset_name)
        
        if success:
            await interaction.response.send_message(
                f"✅ Preset '{preset_name}' has been deleted.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Preset '{preset_name}' not found or could not be deleted.",
                ephemeral=True
            )
    
    @app_commands.command(name="preset_info", description="Show detailed information about a preset")
    @app_commands.describe(preset_name="Name of the preset to view")
    @app_commands.autocomplete(preset_name=preset_name_autocomplete)
    async def preset_info(
        self,
        interaction: discord.Interaction,
        preset_name: str
    ):
        """Show detailed information about a preset."""
        from pathlib import Path
        from ruamel.yaml import YAML
        
        # Load full preset file (not just config)
        preset_file = self.config_manager.presets_dir / f"{preset_name}.yml"
        
        if not preset_file.exists():
            await interaction.response.send_message(
                f"❌ Preset '{preset_name}' not found.",
                ephemeral=True
            )
            return
        
        try:
            yaml = YAML(typ='rt')
            with open(preset_file, "r", encoding="utf-8") as f:
                preset_data = yaml.load(f)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error loading preset: {e}",
                ephemeral=True
            )
            return
        
        preset_config = preset_data.get("config", {})
        
        # Count only modified settings (different from defaults)
        defaults = self.config_manager.get_defaults()
        modified_count = sum(1 for key, value in preset_config.items() if defaults.get(key) != value)
        
        # Build description with metadata
        description = f"📦 Preset • By: {preset_data.get('author', 'Unknown')}"
        description += f" • v{preset_data.get('version', '1.0.0')}"
        description += f" • {modified_count} modified settings"
        
        # Build comprehensive embed
        embed = discord.Embed(
            title=preset_data.get('name', preset_name),
            description=description,
            color=discord.Color.blue()
        )
        
        # Description field
        preset_description = preset_data.get("description", "No description available")
        embed.add_field(
            name="📝 Description",
            value=preset_description,
            inline=False
        )
        
        # Main Settings - compact inline format
        main_settings = []
        
        # Display settings
        display_parts = []
        if "use_card_ai_display_name" in preset_config:
            display_parts.append(f"Card Name {'✅' if preset_config['use_card_ai_display_name'] else '❌'}")
        if "send_the_greeting_message" in preset_config:
            display_parts.append(f"Greeting {'✅' if preset_config['send_the_greeting_message'] else '❌'}")
        if display_parts:
            main_settings.append(f"• **Display:** {' • '.join(display_parts)}")
        
        # Timing settings
        timing_parts = []
        if "delay_for_generation" in preset_config:
            timing_parts.append(f"Delay {preset_config['delay_for_generation']}s")
        if "engaged_delay" in preset_config:
            timing_parts.append(f"Engaged {preset_config['engaged_delay']}s")
        if timing_parts:
            main_settings.append(f"• **Timing:** {' • '.join(timing_parts)}")
        
        # System features
        systems_parts = []
        if "enable_reply_system" in preset_config:
            systems_parts.append(f"Reply {'✅' if preset_config['enable_reply_system'] else '❌'}")
        if "enable_memory_system" in preset_config:
            systems_parts.append(f"Memory {'✅' if preset_config['enable_memory_system'] else '❌'}")
        if "sleep_mode_enabled" in preset_config:
            systems_parts.append(f"Sleep {'✅' if preset_config['sleep_mode_enabled'] else '❌'}")
        if systems_parts:
            main_settings.append(f"• **Systems:** {' • '.join(systems_parts)}")
        
        if main_settings:
            embed.add_field(
                name="⭐ Main Settings",
                value="\n".join(main_settings),
                inline=False
            )
        
        # AI & Tools field
        ai_tools = []
        
        # Thinking
        if "thinking_budget" in preset_config or "thinking_enabled" in preset_config:
            thinking_enabled = preset_config.get("thinking_enabled", True)
            if thinking_enabled and "thinking_budget" in preset_config:
                ai_tools.append(f"• **Thinking:** Enabled (Budget: {preset_config['thinking_budget']})")
            else:
                ai_tools.append(f"• **Thinking:** {'Enabled' if thinking_enabled else 'Disabled'}")
        
        # Tool Calling
        if "tool_calling" in preset_config:
            tool_config = preset_config["tool_calling"]
            if isinstance(tool_config, dict):
                enabled = tool_config.get('enabled', False)
                ai_tools.append(f"• **Tool Calling:** {'Enabled' if enabled else 'Disabled'}")
        
        # Memory
        if "enable_memory_system" in preset_config:
            memory_enabled = preset_config['enable_memory_system']
            if memory_enabled and "memory_max_tokens" in preset_config:
                ai_tools.append(f"• **Memory:** {preset_config['memory_max_tokens']} tokens")
            else:
                ai_tools.append(f"• **Memory:** {'Enabled' if memory_enabled else 'Disabled'}")
        
        if ai_tools:
            embed.add_field(
                name="🧠 AI & Tools",
                value="\n".join(ai_tools),
                inline=False
            )
        
        # Processing field
        processing = []
        
        if "remove_ai_emoji" in preset_config:
            processing.append(f"• **Remove Emoji:** {'Yes' if preset_config['remove_ai_emoji'] else 'No'}")
        
        if "use_response_filter" in preset_config:
            processing.append(f"• **Response Filter:** {'Yes' if preset_config['use_response_filter'] else 'No'}")
        
        if "error_handling_mode" in preset_config:
            error_mode_display = {
                "friendly": "Friendly",
                "detailed": "Detailed",
                "silent": "Silent"
            }.get(preset_config['error_handling_mode'], preset_config['error_handling_mode'])
            processing.append(f"• **Error Mode:** {error_mode_display}")
        
        if processing:
            embed.add_field(
                name="✂️ Processing",
                value="\n".join(processing),
                inline=False
            )
        
        embed.set_footer(text=f"Use /preset_apply to apply • /preset_export to share")
        
        await interaction.response.send_message(embed=embed, ephemeral=False)
    
    @app_commands.command(name="preset_export", description="Export a preset to a shareable file")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(preset_name="Name of the preset to export")
    @app_commands.autocomplete(preset_name=preset_name_autocomplete)
    async def preset_export(
        self,
        interaction: discord.Interaction,
        preset_name: str
    ):
        """Export a preset to a file that can be shared."""
        from pathlib import Path
        
        preset_file = self.config_manager.presets_dir / f"{preset_name}.yml"
        
        if not preset_file.exists():
            await interaction.response.send_message(
                f"❌ Preset '{preset_name}' not found.\n\n"
                f"💡 Use `/preset_list` to see available presets.",
                ephemeral=True
            )
            return
        
        try:
            await interaction.response.send_message(
                f"✅ **Preset exported successfully!**\n\n"
                f"📦 **Preset:** `{preset_name}`\n"
                f"📄 **File:** `{preset_file.name}`\n\n"
                f"💡 Share this file with others! They can import it with `/preset_import`.",
                file=discord.File(preset_file),
                ephemeral=True
            )
        except Exception as e:
            func.log.error(f"Error exporting preset: {e}")
            await interaction.response.send_message(
                f"❌ Failed to export preset: {e}",
                ephemeral=True
            )
    
    @app_commands.command(name="preset_import", description="Import a preset from a file")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        file="YAML preset file to import",
        preset_name="Optional: rename the preset (leave empty to use original name)"
    )
    async def preset_import(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        preset_name: str = None
    ):
        """Import a preset from a YAML file."""
        await interaction.response.defer(ephemeral=True)
        
        # Validate file type
        if not file.filename.endswith('.yml') and not file.filename.endswith('.yaml'):
            await interaction.followup.send(
                "❌ Invalid file type. Please upload a YAML file (.yml or .yaml).",
                ephemeral=True
            )
            return
        
        # Download and parse file
        try:
            from ruamel.yaml import YAML
            yaml = YAML(typ='rt')
            
            file_bytes = await file.read()
            preset_data = yaml.load(file_bytes.decode('utf-8'))
        except Exception as e:
            await interaction.followup.send(
                f"❌ Invalid YAML file: {e}",
                ephemeral=True
            )
            return
        
        # Validate preset structure
        if "config" not in preset_data:
            await interaction.followup.send(
                "❌ Invalid preset file: missing 'config' field.",
                ephemeral=True
            )
            return
        
        # Determine preset name
        if not preset_name:
            preset_name = preset_data.get("name", file.filename.replace('.yml', '').replace('.yaml', ''))
        
        # Sanitize preset name
        preset_name = "".join(c for c in preset_name if c.isalnum() or c in (' ', '-', '_')).strip()
        preset_name = preset_name.replace(' ', '_')
        
        # Save the preset
        description = preset_data.get("description", "Imported preset")
        author = preset_data.get("author", str(interaction.user.name))
        
        success = self.config_manager.save_preset(
            preset_name=preset_name,
            config=preset_data["config"],
            description=description,
            author=author
        )
        
        if success:
            await interaction.followup.send(
                f"✅ **Preset imported successfully!**\n\n"
                f"📦 **Name:** `{preset_name}`\n"
                f"📝 **Description:** {description}\n"
                f"👤 **Original Author:** {preset_data.get('author', 'Unknown')}\n"
                f"⚙️ **Settings:** {len(preset_data['config'])} configuration(s)\n\n"
                f"💡 Use `/preset_apply {preset_name} <ai_name>` to apply this preset.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ Failed to import preset. Check logs for details.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(PresetCommands(bot))
