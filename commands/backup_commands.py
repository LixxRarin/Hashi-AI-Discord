"""
Backup Commands

Commands for creating backups of AI configurations.
"""

import discord
from discord import app_commands
from discord.ext import commands
import json
from pathlib import Path

import utils.func as func
from utils.ai_config_manager import get_ai_config_manager


class BackupCommands(commands.Cog):
    """Commands for backing up AI configurations."""
    
    def __init__(self, bot):
        self.bot = bot
        self.config_manager = get_ai_config_manager()
        self.export_dir = Path("config/exports")
        self.export_dir.mkdir(parents=True, exist_ok=True)
    
    @app_commands.command(name="config_backup", description="Create a backup of all AI configurations in this server")
    @app_commands.default_permissions(administrator=True)
    async def config_backup(self, interaction: discord.Interaction):
        """Create a backup of all AI configurations in the server."""
        server_id = str(interaction.guild.id)
        
        await interaction.response.defer(ephemeral=True)
        
        # Get all AIs in the server
        server_data = func.session_cache.get(server_id, {}).get("channels", {})
        
        if not server_data:
            await interaction.followup.send(
                "❌ No AI configurations found in this server.",
                ephemeral=True
            )
            return
        
        # Collect all configurations
        backup_data = {
            "version": "2.0.0",
            "backup_type": "server",
            "server_id": server_id,
            "server_name": interaction.guild.name,
            "backed_up_by": str(interaction.user.name),
            "ais": {}
        }
        
        ai_count = 0
        for channel_id, channel_data in server_data.items():
            for ai_name, session in channel_data.items():
                if session and "config" in session:
                    backup_data["ais"][ai_name] = {
                        "channel_id": channel_id,
                        "provider": session.get("provider", "openai"),
                        "api_connection": session.get("api_connection"),
                        "config": session.get("config", {})
                    }
                    ai_count += 1
        
        if ai_count == 0:
            await interaction.followup.send(
                "❌ No AI configurations found to backup.",
                ephemeral=True
            )
            return
        
        # Save backup file
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"server_backup_{timestamp}.json"
        backup_file = self.export_dir / backup_filename
        
        try:
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)
            
            await interaction.followup.send(
                f"✅ **Server backup created successfully!**\n\n"
                f"🏢 **Server:** {interaction.guild.name}\n"
                f"🤖 **AIs backed up:** {ai_count}\n"
                f"📄 **File:** `{backup_filename}`\n"
                f"💾 **Location:** `{backup_file}`\n\n"
                f"💡 Keep this file safe for disaster recovery.",
                file=discord.File(backup_file),
                ephemeral=True
            )
        except Exception as e:
            func.log.error(f"Error creating backup: {e}")
            await interaction.followup.send(
                f"❌ Failed to create backup: {e}",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(BackupCommands(bot))
