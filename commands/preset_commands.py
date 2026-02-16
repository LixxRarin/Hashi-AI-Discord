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
    
    async def ai_name_all_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for all AI names."""
        return await AutocompleteHelpers.ai_name_all(interaction, current)
    
    async def preset_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete function for preset names."""
        try:
            presets = self.config_manager.list_presets()
            
            if not presets:
                return []
            
            choices = []
            for preset in presets:
                name = preset["name"]
                if current.lower() in name.lower():
                    description = preset.get("description", "")
                    author = preset.get("author", "unknown")
                    display = f"{name} - {description[:30]}" if description else f"{name} (by {author})"
                    choices.append(app_commands.Choice(name=display[:100], value=name))
            
            return choices[:25]
        except Exception as e:
            func.log.error(f"Error in preset_name_autocomplete: {e}")
            return []
    
    @app_commands.command(name="preset_save", description="Save current AI configuration as a preset")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to save configuration from",
        preset_name="Name for the preset (will be used to load it later)",
        description="Optional description of what this preset is for"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
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
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
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
        preset_config = self.config_manager.load_preset(preset_name)
        
        if preset_config is None:
            await interaction.response.send_message(
                f"❌ Preset '{preset_name}' not found.",
                ephemeral=True
            )
            return
        
        # Build embed with preset details
        embed = discord.Embed(
            title=f"📦 Preset: {preset_name}",
            color=discord.Color.blue()
        )
        
        # Count configurations by category
        config_count = len(preset_config)
        
        # Show some key configurations
        key_configs = []
        if "delay_for_generation" in preset_config:
            key_configs.append(f"• Delay: `{preset_config['delay_for_generation']}s`")
        if "use_response_filter" in preset_config:
            key_configs.append(f"• Response Filter: `{preset_config['use_response_filter']}`")
        if "enable_reply_system" in preset_config:
            key_configs.append(f"• Reply System: `{preset_config['enable_reply_system']}`")
        if "auto_add_generation_reactions" in preset_config:
            key_configs.append(f"• Auto Reactions: `{preset_config['auto_add_generation_reactions']}`")
        
        embed.add_field(
            name="📊 Configuration Summary",
            value=f"**Total Settings:** {config_count}\n" + "\n".join(key_configs[:10]),
            inline=False
        )
        
        embed.set_footer(text=f"Use /preset_apply {preset_name} <ai_name> to apply this preset")
        
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
