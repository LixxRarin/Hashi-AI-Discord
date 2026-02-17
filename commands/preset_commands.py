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
        """List all available presets."""
        presets = self.config_manager.list_presets()
        
        if not presets:
            await interaction.response.send_message(
                "📦 **No presets available**\n\n"
                "You haven't created any presets yet.\n\n"
                "💡 Use `/preset_save` to save an AI's configuration as a preset.",
                ephemeral=True
            )
            return
        
        # Build embed with preset list
        embed = discord.Embed(
            title="📦 Available Configuration Presets",
            description=f"Found {len(presets)} preset(s)",
            color=discord.Color.blue()
        )
        
        for preset in presets[:25]:  # Discord embed field limit
            name = preset["name"]
            description = preset.get("description", "No description")
            author = preset.get("author", "unknown")
            
            embed.add_field(
                name=f"📦 {name}",
                value=f"**Description:** {description}\n**Author:** {author}",
                inline=False
            )
        
        if len(presets) > 25:
            embed.set_footer(text=f"Showing first 25 of {len(presets)} presets")
        
        await interaction.response.send_message(embed=embed, ephemeral=False)
    
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
        
        # Build comprehensive embed
        embed = discord.Embed(
            title=f"📦 {preset_data.get('name', preset_name)}",
            description=preset_data.get("description", "No description available"),
            color=discord.Color.blue()
        )
        
        # Metadata - Count only modified settings (different from defaults)
        defaults = self.config_manager.get_defaults()
        modified_count = sum(1 for key, value in preset_config.items() if defaults.get(key) != value)
        
        metadata_lines = [
            f"**Author:** {preset_data.get('author', 'Unknown')}",
            f"**Version:** {preset_data.get('version', '1.0.0')}",
            f"**Modified Settings:** {modified_count} (from {len(preset_config)} total)"
        ]
        embed.add_field(
            name="ℹ️ Metadata",
            value="\n".join(metadata_lines),
            inline=False
        )
        
        # Display Settings
        display_settings = []
        if "use_card_ai_display_name" in preset_config:
            display_settings.append(f"• Use Card Display Name: `{preset_config['use_card_ai_display_name']}`")
        if "send_the_greeting_message" in preset_config:
            display_settings.append(f"• Send Greeting: `{preset_config['send_the_greeting_message']}`")
        if "send_message_line_by_line" in preset_config:
            display_settings.append(f"• Line by Line: `{preset_config['send_message_line_by_line']}`")
        
        if display_settings:
            embed.add_field(
                name="🎨 Display",
                value="\n".join(display_settings),
                inline=True
            )
        
        # Timing Settings
        timing_settings = []
        if "delay_for_generation" in preset_config:
            timing_settings.append(f"• Generation Delay: `{preset_config['delay_for_generation']}s`")
        if "engaged_delay" in preset_config:
            timing_settings.append(f"• Engaged Delay: `{preset_config['engaged_delay']}s`")
        if "cache_count_threshold" in preset_config:
            timing_settings.append(f"• Cache Threshold: `{preset_config['cache_count_threshold']}`")
        
        if timing_settings:
            embed.add_field(
                name="⏱️ Timing",
                value="\n".join(timing_settings),
                inline=True
            )
        
        # System Features
        system_features = []
        if "enable_reply_system" in preset_config:
            system_features.append(f"• Reply System: `{preset_config['enable_reply_system']}`")
        if "enable_ignore_system" in preset_config:
            system_features.append(f"• Ignore System: `{preset_config['enable_ignore_system']}`")
        if "sleep_mode_enabled" in preset_config:
            system_features.append(f"• Sleep Mode: `{preset_config['sleep_mode_enabled']}`")
        if "use_response_filter" in preset_config:
            system_features.append(f"• Response Filter: `{preset_config['use_response_filter']}`")
        if "auto_add_generation_reactions" in preset_config:
            system_features.append(f"• Auto Reactions: `{preset_config['auto_add_generation_reactions']}`")
        
        if system_features:
            embed.add_field(
                name="⚙️ Systems",
                value="\n".join(system_features),
                inline=False
            )
        
        # Tool Calling
        if "tool_calling" in preset_config:
            tool_config = preset_config["tool_calling"]
            if isinstance(tool_config, dict):
                tool_info = [
                    f"• Enabled: `{tool_config.get('enabled', False)}`",
                    f"• Allowed Tools: `{', '.join(tool_config.get('allowed_tools', ['none']))}`"
                ]
                embed.add_field(
                    name="🔧 Tool Calling",
                    value="\n".join(tool_info),
                    inline=True
                )
        
        # Memory System
        memory_settings = []
        if "enable_memory_system" in preset_config:
            memory_settings.append(f"• Enabled: `{preset_config['enable_memory_system']}`")
        if "memory_max_tokens" in preset_config:
            memory_settings.append(f"• Max Tokens: `{preset_config['memory_max_tokens']}`")
        
        if memory_settings:
            embed.add_field(
                name="🧠 Memory System",
                value="\n".join(memory_settings),
                inline=True
            )
        
        # Character Card Settings
        card_settings = []
        if "user_syntax_replacement" in preset_config:
            card_settings.append(f"• User Syntax: `{preset_config['user_syntax_replacement']}`")
        if "use_lorebook" in preset_config:
            card_settings.append(f"• Use Lorebook: `{preset_config['use_lorebook']}`")
        if "greeting_index" in preset_config:
            card_settings.append(f"• Greeting Index: `{preset_config['greeting_index']}`")
        
        if card_settings:
            embed.add_field(
                name="📇 Character Card",
                value="\n".join(card_settings),
                inline=True
            )
        
        # Context & Prompts
        context_prompts = []
        
        if "tool_calling_prompt" in preset_config:
            prompt = preset_config["tool_calling_prompt"]
            if prompt:
                preview = prompt.strip()[:100] + "..." if len(prompt.strip()) > 100 else prompt.strip()
                context_prompts.append(f"• Tool Calling Prompt: `{preview}`")
        
        if "memory_prompt" in preset_config:
            prompt = preset_config["memory_prompt"]
            if prompt:
                preview = prompt.strip()[:100] + "..." if len(prompt.strip()) > 100 else prompt.strip()
                context_prompts.append(f"• Memory Prompt: `{preview}`")
        
        if "context_order" in preset_config:
            order = preset_config["context_order"]
            if order and isinstance(order, list):
                order_str = " → ".join(order[:5])
                if len(order) > 5:
                    order_str += f" (+{len(order)-5} more)"
                context_prompts.append(f"• Context Order: `{order_str}`")
        
        if context_prompts:
            embed.add_field(
                name="📋 Context & Prompts",
                value="\n".join(context_prompts),
                inline=False
            )
        
        # Text Processing & Error Handling
        text_processing = []
        if "remove_ai_emoji" in preset_config:
            text_processing.append(f"• Remove Emoji: `{preset_config['remove_ai_emoji']}`")
        if "remove_ai_text_from" in preset_config:
            patterns = preset_config['remove_ai_text_from']
            if patterns:
                text_processing.append(f"• Remove Patterns: `{len(patterns)} pattern(s)`")
            else:
                text_processing.append(f"• Remove Patterns: `None`")
        if "error_handling_mode" in preset_config:
            error_mode_display = {
                "friendly": "Friendly",
                "detailed": "Detailed",
                "silent": "Silent"
            }.get(preset_config['error_handling_mode'], preset_config['error_handling_mode'])
            text_processing.append(f"• Error Mode: `{error_mode_display}`")
        if "save_errors_in_history" in preset_config:
            text_processing.append(f"• Save Errors in History: `{preset_config['save_errors_in_history']}`")
        if "send_errors_to_chat" in preset_config:
            text_processing.append(f"• Send Errors to Chat: `{preset_config['send_errors_to_chat']}`")
        
        if text_processing:
            embed.add_field(
                name="✂️ Text & Error Handling",
                value="\n".join(text_processing),
                inline=False
            )
        
        # System Message Preview
        if "system_message" in preset_config:
            sys_msg = preset_config["system_message"]
            if sys_msg:
                preview = sys_msg[:100] + "..." if len(sys_msg) > 100 else sys_msg
                embed.add_field(
                    name="💬 System Message",
                    value=f"```{preview}```",
                    inline=False
                )
        
        embed.set_footer(text=f"Use /preset_apply {preset_name} <ai_name> to apply • /preset_export to share")
        
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
