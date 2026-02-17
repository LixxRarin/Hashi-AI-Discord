"""
Categorized Configuration Commands

New organized commands to replace the monolithic /config command.
Commands are grouped by category for better usability.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

import utils.func as func
from commands.shared.autocomplete import AutocompleteHelpers


class ConfigCommands(commands.Cog):
    """Categorized configuration commands for AI behavior."""
    
    def __init__(self, bot):
        self.bot = bot
    
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
    
    @app_commands.command(name="config_display", description="Configure AI display and messaging settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        use_display_name="Use character card display name for webhooks",
        send_greeting="Send greeting message when starting chat",
        line_by_line="Send messages one line at a time"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def config_display(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        use_display_name: bool = None,
        send_greeting: bool = None,
        line_by_line: bool = None
    ):
        """Configure display and messaging settings."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.setdefault("config", {})
        changes = []
        
        if use_display_name is not None:
            config["use_card_ai_display_name"] = use_display_name
            changes.append(f"• Use Display Name: `{use_display_name}`")
        
        if send_greeting is not None:
            config["send_the_greeting_message"] = send_greeting
            changes.append(f"• Send Greeting: `{send_greeting}`")
        
        if line_by_line is not None:
            config["send_message_line_by_line"] = line_by_line
            changes.append(f"• Line by Line: `{line_by_line}`")
        
        if not changes:
            await interaction.response.send_message("❌ No changes specified.", ephemeral=True)
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Display settings updated for '{ai_name}':**\n" + "\n".join(changes),
            ephemeral=True
        )
    
    @app_commands.command(name="config_timing", description="Configure AI response timing settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        delay="Base delay in seconds before responding",
        cache_threshold="Number of messages before triggering response",
        engaged_delay="Delay when conversation is active",
        engaged_threshold="Messages needed to activate engaged mode"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def config_timing(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        delay: float = None,
        cache_threshold: int = None,
        engaged_delay: float = None,
        engaged_threshold: int = None
    ):
        """Configure timing settings."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.setdefault("config", {})
        changes = []
        
        if delay is not None:
            if delay < 0 or delay > 60:
                await interaction.response.send_message("❌ Delay must be between 0 and 60 seconds.", ephemeral=True)
                return
            config["delay_for_generation"] = delay
            changes.append(f"• Base Delay: `{delay}s`")
        
        if cache_threshold is not None:
            if cache_threshold < 1 or cache_threshold > 50:
                await interaction.response.send_message("❌ Cache threshold must be between 1 and 50.", ephemeral=True)
                return
            config["cache_count_threshold"] = cache_threshold
            changes.append(f"• Cache Threshold: `{cache_threshold}`")
        
        if engaged_delay is not None:
            if engaged_delay <= 0 or engaged_delay > 60:
                await interaction.response.send_message("❌ Engaged delay must be between 0 and 60 seconds.", ephemeral=True)
                return
            config["engaged_delay"] = engaged_delay
            changes.append(f"• Engaged Delay: `{engaged_delay}s`")
        
        if engaged_threshold is not None:
            if engaged_threshold <= 0 or engaged_threshold > 20:
                await interaction.response.send_message("❌ Engaged threshold must be between 1 and 20.", ephemeral=True)
                return
            config["engaged_message_threshold"] = engaged_threshold
            changes.append(f"• Engaged Threshold: `{engaged_threshold}`")
        
        if not changes:
            await interaction.response.send_message("❌ No changes specified.", ephemeral=True)
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Timing settings updated for '{ai_name}':**\n" + "\n".join(changes),
            ephemeral=True
        )
    
    @app_commands.command(name="config_text", description="Configure text processing settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        remove_patterns="Comma-separated regex patterns to remove (or 'none')",
        remove_emoji="Remove emojis from AI responses",
        error_mode="How to handle LLM errors",
        save_errors_in_history="Save error messages in conversation history",
        send_errors_to_chat="Send error messages to Discord channel"
    )
    @app_commands.choices(error_mode=[
        app_commands.Choice(name="Friendly (user-friendly messages)", value="friendly"),
        app_commands.Choice(name="Detailed (show exception type and message)", value="detailed"),
        app_commands.Choice(name="Silent (don't send error messages)", value="silent")
    ])
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def config_text(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        remove_patterns: str = None,
        remove_emoji: bool = None,
        error_mode: app_commands.Choice[str] = None,
        save_errors_in_history: bool = None,
        send_errors_to_chat: bool = None
    ):
        """Configure text processing settings."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.setdefault("config", {})
        changes = []
        
        if remove_patterns is not None:
            if remove_patterns.lower() == "none":
                config["remove_ai_text_from"] = []
                changes.append("• Remove Patterns: `None`")
            else:
                patterns = [p.strip() for p in remove_patterns.split(",")]
                config["remove_ai_text_from"] = patterns
                changes.append(f"• Remove Patterns: `{len(patterns)} pattern(s)`")
        
        if remove_emoji is not None:
            config["remove_ai_emoji"] = remove_emoji
            changes.append(f"• Remove Emoji: `{remove_emoji}`")
        
        if error_mode is not None:
            config["error_handling_mode"] = error_mode.value
            mode_display = {
                "friendly": "Friendly (user-friendly messages)",
                "detailed": "Detailed (show exception details)",
                "silent": "Silent (don't send errors)"
            }.get(error_mode.value, error_mode.value)
            changes.append(f"• Error Handling Mode: `{mode_display}`")
        
        if save_errors_in_history is not None:
            config["save_errors_in_history"] = save_errors_in_history
            changes.append(f"• Save Errors in History: `{save_errors_in_history}`")
        
        if send_errors_to_chat is not None:
            config["send_errors_to_chat"] = send_errors_to_chat
            changes.append(f"• Send Errors to Chat: `{send_errors_to_chat}`")
        
        if not changes:
            await interaction.response.send_message("❌ No changes specified.", ephemeral=True)
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Text processing updated for '{ai_name}':**\n" + "\n".join(changes),
            ephemeral=True
        )
    
    @app_commands.command(name="config_card", description="Configure Character Card V3 settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        greeting_index="Which greeting to use (0=first, 1+=alternates)",
        user_replacement="How to replace {{user}} placeholder",
        use_lorebook="Enable lorebook entries",
        lorebook_depth="Messages to scan for lorebook triggers"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    @app_commands.choices(user_replacement=[
        app_commands.Choice(name="None (don't replace)", value="none"),
        app_commands.Choice(name="Username", value="username"),
        app_commands.Choice(name="Display Name", value="display_name"),
        app_commands.Choice(name="Mention (@user)", value="mention"),
        app_commands.Choice(name="User ID", value="id")
    ])
    async def config_card(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        greeting_index: int = None,
        user_replacement: app_commands.Choice[str] = None,
        use_lorebook: bool = None,
        lorebook_depth: int = None
    ):
        """Configure Character Card settings."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.setdefault("config", {})
        changes = []
        
        if greeting_index is not None:
            if greeting_index < 0:
                await interaction.response.send_message("❌ Greeting index must be 0 or greater.", ephemeral=True)
                return
            config["greeting_index"] = greeting_index
            changes.append(f"• Greeting Index: `{greeting_index}`")
        
        if user_replacement is not None:
            config["user_syntax_replacement"] = user_replacement.value
            changes.append(f"• {{{{user}}}} Replacement: `{user_replacement.value}`")
        
        if use_lorebook is not None:
            config["use_lorebook"] = use_lorebook
            changes.append(f"• Use Lorebook: `{use_lorebook}`")
        
        if lorebook_depth is not None:
            if lorebook_depth < 1 or lorebook_depth > 100:
                await interaction.response.send_message("❌ Lorebook depth must be between 1 and 100.", ephemeral=True)
                return
            config["lorebook_scan_depth"] = lorebook_depth
            changes.append(f"• Lorebook Depth: `{lorebook_depth}`")
        
        if not changes:
            await interaction.response.send_message("❌ No changes specified.", ephemeral=True)
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Character Card settings updated for '{ai_name}':**\n" + "\n".join(changes),
            ephemeral=True
        )

    @app_commands.command(name="config_filter", description="Configure intelligent response filter")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        enabled="Enable response filter",
        api_connection="API connection for filter (must support Tool Calling)",
        fallback="What to do if filter fails",
        timeout="Filter timeout in seconds"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    @app_commands.autocomplete(api_connection=connection_name_autocomplete)
    @app_commands.choices(fallback=[
        app_commands.Choice(name="Respond (always respond if filter fails)", value="respond"),
        app_commands.Choice(name="Ignore (don't respond if filter fails)", value="ignore")
    ])
    async def config_filter(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        enabled: bool = None,
        api_connection: str = None,
        fallback: app_commands.Choice[str] = None,
        timeout: float = None
    ):
        """Configure response filter settings."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.setdefault("config", {})
        changes = []
        
        if enabled is not None:
            # Check for mutual exclusivity with ignore system
            if enabled and config.get("enable_ignore_system", False):
                config["enable_ignore_system"] = False
                changes.append("⚠️ Ignore system automatically disabled (mutually exclusive)")
            
            config["use_response_filter"] = enabled
            changes.append(f"• Filter Enabled: `{enabled}`")
        
        if api_connection is not None:
            conn = func.get_api_connection(server_id, api_connection)
            if not conn:
                await interaction.response.send_message(
                    f"❌ API connection '{api_connection}' not found.\n💡 Use `/list_apis` to see available connections.",
                    ephemeral=True
                )
                return
            
            provider = conn.get("provider", "")
            if provider not in ["openai", "deepseek"]:
                await interaction.response.send_message(
                    f"❌ Provider '{provider}' doesn't support Tool Calling.\nResponse filter requires OpenAI or DeepSeek.",
                    ephemeral=True
                )
                return
            
            config["response_filter_api_connection"] = api_connection
            changes.append(f"• API Connection: `{api_connection}`")
        
        if fallback is not None:
            config["response_filter_fallback"] = fallback.value
            changes.append(f"• Fallback: `{fallback.value}`")
        
        if timeout is not None:
            if timeout <= 0 or timeout > 30:
                await interaction.response.send_message("❌ Timeout must be between 1 and 30 seconds.", ephemeral=True)
                return
            config["response_filter_timeout"] = timeout
            changes.append(f"• Timeout: `{timeout}s`")
        
        if not changes:
            await interaction.response.send_message("❌ No changes specified.", ephemeral=True)
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Response filter updated for '{ai_name}':**\n" + "\n".join(changes),
            ephemeral=True
        )
     
    @app_commands.command(name="config_reply", description="Configure LLM reply system")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        enabled="Enable reply system",
        custom_prompt="Custom reply prompt (or 'default' for default)"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def config_reply(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        enabled: bool = None,
        custom_prompt: str = None
    ):
        """Configure reply system settings."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.setdefault("config", {})
        changes = []
        
        if enabled is not None:
            config["enable_reply_system"] = enabled
            changes.append(f"• Reply System: `{enabled}`")
        
        if custom_prompt is not None:
            if custom_prompt.lower() == "default":
                config["reply_prompt"] = func.get_default_ai_config()["reply_prompt"]
                changes.append("• Prompt: `Reset to default`")
            else:
                config["reply_prompt"] = custom_prompt
                changes.append(f"• Prompt: `Custom ({len(custom_prompt)} chars)`")
        
        if not changes:
            await interaction.response.send_message("❌ No changes specified.", ephemeral=True)
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Reply system updated for '{ai_name}':**\n" + "\n".join(changes),
            ephemeral=True
        )
    
    @app_commands.command(name="config_sleep", description="Configure sleep mode settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        enabled="Enable sleep mode",
        threshold="Refusals before entering sleep mode"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def config_sleep(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        enabled: bool = None,
        threshold: int = None
    ):
        """Configure sleep mode settings."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.setdefault("config", {})
        changes = []
        
        if enabled is not None:
            config["sleep_mode_enabled"] = enabled
            changes.append(f"• Sleep Mode: `{enabled}`")
        
        if threshold is not None:
            if threshold <= 0 or threshold > 20:
                await interaction.response.send_message("❌ Threshold must be between 1 and 20.", ephemeral=True)
                return
            config["sleep_mode_threshold"] = threshold
            changes.append(f"• Threshold: `{threshold}`")
        
        if not changes:
            await interaction.response.send_message("❌ No changes specified.", ephemeral=True)
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Sleep mode updated for '{ai_name}':**\n" + "\n".join(changes),
            ephemeral=True
        )
    
    @app_commands.command(name="config_ignore", description="Configure ignore system settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        enabled="Enable ignore system (LLM decides during generation)",
        sleep_threshold="Consecutive ignores before entering sleep mode"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def config_ignore(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        enabled: Optional[bool] = None,
        sleep_threshold: Optional[int] = None
    ):
        """Configure ignore system settings."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.setdefault("config", {})
        changes = []
        
        if enabled is not None:
            # Check for mutual exclusivity with response filter
            if enabled and config.get("use_response_filter", False):
                config["use_response_filter"] = False
                changes.append("⚠️ Response filter automatically disabled (mutually exclusive)")
            
            config["enable_ignore_system"] = enabled
            changes.append(f"• Ignore System: `{enabled}`")
        
        if sleep_threshold is not None:
            if sleep_threshold <= 0 or sleep_threshold > 20:
                await interaction.response.send_message("❌ Threshold must be between 1 and 20.", ephemeral=True)
                return
            config["ignore_sleep_threshold"] = sleep_threshold
            changes.append(f"• Sleep Threshold: `{sleep_threshold}`")
        
        if not changes:
            await interaction.response.send_message("❌ No changes specified.", ephemeral=True)
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Ignore system updated for '{ai_name}':**\n" + "\n".join(changes),
            ephemeral=True
        )
    
    @app_commands.command(name="config_advanced", description="Configure advanced settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        api_connection="API connection to use",
        system_message="System message (or 'default' for default)",
        new_chat_on_reset="Create new chat on reset",
        auto_reactions="Auto-add navigation reactions"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    @app_commands.autocomplete(api_connection=connection_name_autocomplete)
    async def config_advanced(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        api_connection: str = None,
        system_message: str = None,
        new_chat_on_reset: bool = None,
        auto_reactions: bool = None
    ):
        """Configure advanced settings."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.setdefault("config", {})
        changes = []
        
        if api_connection is not None:
            connection = func.get_api_connection(server_id, api_connection)
            if not connection:
                await interaction.response.send_message(
                    f"❌ API connection '{api_connection}' not found.\n💡 Use `/list_apis` to see available connections.",
                    ephemeral=True
                )
                return
            
            old_connection = session.get("api_connection", "None")
            new_provider = connection.get("provider", "openai")
            
            session["api_connection"] = api_connection
            session["provider"] = new_provider
            
            changes.append(f"• API Connection: `{api_connection}` ({new_provider.upper()})")
        
        if system_message is not None:
            if system_message.lower() == "default":
                config["system_message"] = func.get_default_ai_config()["system_message"]
                changes.append("• System Message: `Reset to default`")
            else:
                config["system_message"] = system_message
                changes.append(f"• System Message: `Custom ({len(system_message)} chars)`")
        
        if new_chat_on_reset is not None:
            config["new_chat_on_reset"] = new_chat_on_reset
            changes.append(f"• New Chat on Reset: `{new_chat_on_reset}`")
        
        if auto_reactions is not None:
            config["auto_add_generation_reactions"] = auto_reactions
            changes.append(f"• Auto Reactions: `{auto_reactions}`")
        
        if not changes:
            await interaction.response.send_message("❌ No changes specified.", ephemeral=True)
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Advanced settings updated for '{ai_name}':**\n" + "\n".join(changes),
            ephemeral=True
        )


    @app_commands.command(name="config_tool_calling", description="Configure AI tool calling (function calling) settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        enabled="Enable or disable tool calling",
        tools="Comma-separated list of allowed tools, or 'all' for all tools"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def config_tool_calling(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        enabled: bool = None,
        tools: str = None
    ):
        """Configure tool calling settings for an AI."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.setdefault("config", {})
        tool_config = config.setdefault("tool_calling", {})
        changes = []
        
        if enabled is not None:
            tool_config["enabled"] = enabled
            changes.append(f"• Tool Calling Enabled: `{enabled}`")
        
        if tools is not None:
            # Parse tools list
            if tools.lower().strip() == "all":
                tool_config["allowed_tools"] = ["all"]
                changes.append(f"• Allowed Tools: `all`")
            else:
                # Split by comma and clean up
                tool_list = [t.strip() for t in tools.split(",") if t.strip()]
                
                # Validate tool names
                from AI.tools import get_tool_names
                available_tools = get_tool_names()
                invalid_tools = [t for t in tool_list if t not in available_tools]
                
                if invalid_tools:
                    await interaction.response.send_message(
                        f"❌ Invalid tool names: {', '.join(invalid_tools)}\n"
                        f"Available tools: {', '.join(available_tools)}",
                        ephemeral=True
                    )
                    return
                
                tool_config["allowed_tools"] = tool_list
                changes.append(f"• Allowed Tools: `{', '.join(tool_list)}`")
        
        if not changes:
            await interaction.response.send_message("❌ No changes specified.", ephemeral=True)
            return
        
        channel_data = func.get_session_data(server_id, found_channel_id)
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        await interaction.response.send_message(
            f"✅ **Tool calling settings updated for '{ai_name}':**\n" + "\n".join(changes),
            ephemeral=True
        )
    
    @app_commands.command(name="view_tool_config", description="View current tool calling configuration for an AI")
    @app_commands.describe(ai_name="Name of the AI to view configuration for")
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def view_tool_config(
        self,
        interaction: discord.Interaction,
        ai_name: str
    ):
        """View tool calling configuration for an AI."""
        server_id = str(interaction.guild.id)
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        if session is None:
            await interaction.response.send_message(f"❌ AI '{ai_name}' session data is invalid.", ephemeral=True)
            return
        
        config = session.get("config", {})
        tool_config = config.get("tool_calling", {})
        
        enabled = tool_config.get("enabled", False)
        allowed_tools = tool_config.get("allowed_tools", ["all"])
        
        # Get available tools
        from AI.tools import get_tool_names
        available_tools = get_tool_names()
        
        # Build response
        status_emoji = "✅" if enabled else "❌"
        status_text = "Enabled" if enabled else "Disabled"
        
        tools_text = "All tools" if "all" in allowed_tools else ", ".join(allowed_tools)
        
        response = f"**Tool Calling Configuration for '{ai_name}':**\n\n"
        response += f"{status_emoji} **Status:** {status_text}\n"
        response += f"📋 **Allowed Tools:** {tools_text}\n\n"
        response += f"**Available Tools:**\n"
        for tool in available_tools:
            response += f"  • `{tool}`\n"
        
        await interaction.response.send_message(response, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ConfigCommands(bot))
