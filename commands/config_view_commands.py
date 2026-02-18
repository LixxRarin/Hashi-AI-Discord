"""
Enhanced Configuration Visualization

Improved commands for viewing AI configurations in an organized way.
"""

import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from utils.ai_config_manager import get_ai_config_manager
from commands.shared.autocomplete import AutocompleteHelpers
from AI.provider_registry import get_registry


class ConfigViewCommands(commands.Cog):
    """Commands for viewing AI configurations."""
    
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
    
    @app_commands.command(name="show_config", description="Display AI configuration settings organized by category")
    @app_commands.describe(
        ai_name="Name of the AI to show config for",
        category="Specific category to show (leave empty for all)"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    @app_commands.choices(category=[
        app_commands.Choice(name="All Categories", value="all"),
        app_commands.Choice(name="Display Settings", value="display"),
        app_commands.Choice(name="Timing Settings", value="timing"),
        app_commands.Choice(name="Text Processing", value="text"),
        app_commands.Choice(name="Character Card", value="card"),
        app_commands.Choice(name="Response Filter", value="filter"),
        app_commands.Choice(name="Reply System", value="reply"),
        app_commands.Choice(name="Tool Calling", value="tools"),
        app_commands.Choice(name="Memory System", value="memory"),
        app_commands.Choice(name="Sleep Mode", value="sleep"),
        app_commands.Choice(name="Advanced", value="advanced")
    ])
    async def show_config(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        category: app_commands.Choice[str] = None
    ):
        """Display AI configuration settings organized by category."""
        server_id = str(interaction.guild.id)
        
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
        
        provider = session.get("provider", "openai")
        ai_config = session.get("config", {})
        
        # Choose color based on provider
        registry = get_registry()
        try:
            metadata = registry.get_metadata(provider)
            color = getattr(discord.Color, metadata.color)()
            provider_label = f"{metadata.icon} {metadata.display_name}"
        except (ValueError, AttributeError) as e:
            func.log.error(f"Error getting provider metadata for '{provider}': {e}")
            color = discord.Color.red()
            provider_label = "❌ Unsupported"
        
        # Determine which category to show
        show_category = category.value if category else "all"
        
        if show_category == "all":
            # Show summary of all categories
            embed = self._build_summary_embed(ai_name, session, ai_config, provider_label, color)
        else:
            # Show detailed view of specific category
            embed = self._build_category_embed(ai_name, session, ai_config, show_category, provider_label, color)
        
        await interaction.response.send_message(embed=embed, ephemeral=False)
    
    def _build_summary_embed(self, ai_name: str, session: dict, config: dict, provider_label: str, color) -> discord.Embed:
        """Build summary embed showing all categories."""
        embed = discord.Embed(
            title=f"⚙️ Configuration: {ai_name}",
            description=f"**Provider:** {provider_label}",
            color=color
        )
        
        # API Connection
        api_connection_name = session.get("api_connection", "Not set")
        embed.add_field(name="🔌 API Connection", value=f"`{api_connection_name}`", inline=False)
        
        # Display Settings
        display_settings = []
        display_settings.append(f"• Display Name: `{config.get('use_card_ai_display_name', 'N/A')}`")
        display_settings.append(f"• Send Greeting: `{config.get('send_the_greeting_message', 'N/A')}`")
        display_settings.append(f"• Line by Line: `{config.get('send_message_line_by_line', 'N/A')}`")
        embed.add_field(name="🖥️ Display", value="\n".join(display_settings), inline=True)
        
        # Timing Settings
        timing_settings = []
        timing_settings.append(f"• Delay: `{config.get('delay_for_generation', 'N/A')}s`")
        timing_settings.append(f"• Cache: `{config.get('cache_count_threshold', 'N/A')}`")
        timing_settings.append(f"• Engaged: `{config.get('engaged_delay', 'N/A')}s`")
        embed.add_field(name="⏱️ Timing", value="\n".join(timing_settings), inline=True)
        
        # Character Card
        card_settings = []
        card_settings.append(f"• Greeting: `#{config.get('greeting_index', 0)}`")
        card_settings.append(f"• {{{{user}}}}: `{config.get('user_syntax_replacement', 'none')}`")
        card_settings.append(f"• Lorebook: `{config.get('use_lorebook', False)}`")
        embed.add_field(name="🎭 Character Card", value="\n".join(card_settings), inline=True)
        
        # Response Filter
        filter_enabled = config.get('use_response_filter', False)
        filter_status = "✅ Enabled" if filter_enabled else "❌ Disabled"
        embed.add_field(name="🔍 Response Filter", value=filter_status, inline=True)
        
        # Reply System
        reply_enabled = config.get('enable_reply_system', False)
        reply_status = "✅ Enabled" if reply_enabled else "❌ Disabled"
        embed.add_field(name="💬 Reply System", value=reply_status, inline=True)
        
        # Ignore System
        ignore_enabled = config.get('enable_ignore_system', False)
        ignore_status = "✅ Enabled" if ignore_enabled else "❌ Disabled"
        embed.add_field(name="🚫 Ignore System", value=ignore_status, inline=True)
        
        # Tool Calling
        tool_config = config.get('tool_calling', {})
        tool_enabled = tool_config.get('enabled', False)
        tool_status = "✅ Enabled" if tool_enabled else "❌ Disabled"
        embed.add_field(name="🔧 Tool Calling", value=tool_status, inline=True)
        
        # Memory System
        memory_enabled = config.get('enable_memory_system', False)
        memory_status = "✅ Enabled" if memory_enabled else "❌ Disabled"
        embed.add_field(name="🧠 Memory System", value=memory_status, inline=True)
        
        # Sleep Mode
        sleep_enabled = config.get('sleep_mode_enabled', False)
        sleep_status = "✅ Enabled" if sleep_enabled else "❌ Disabled"
        embed.add_field(name="😴 Sleep Mode", value=sleep_status, inline=True)
        
        embed.set_footer(text="Use /show_config with category parameter for detailed view")
        
        return embed
    
    def _build_category_embed(self, ai_name: str, session: dict, config: dict, category: str, provider_label: str, color) -> discord.Embed:
        """Build detailed embed for specific category."""
        embed = discord.Embed(
            title=f"⚙️ {ai_name} - {self._get_category_name(category)}",
            description=f"**Provider:** {provider_label}",
            color=color
        )
        
        if category == "display":
            embed.add_field(
                name="Use Display Name",
                value=f"`{config.get('use_card_ai_display_name', True)}`\nUse character card display name for webhooks",
                inline=False
            )
            embed.add_field(
                name="Send Greeting Message",
                value=f"`{config.get('send_the_greeting_message', False)}`\nAutomatically send greeting when starting chat",
                inline=False
            )
            embed.add_field(
                name="Send Line by Line",
                value=f"`{config.get('send_message_line_by_line', True)}`\nSend messages one line at a time",
                inline=False
            )
            embed.set_footer(text="Use /config_display to modify these settings")
        
        elif category == "timing":
            embed.add_field(
                name="Base Delay",
                value=f"`{config.get('delay_for_generation', 4.0)}` seconds\nDelay before generating response",
                inline=False
            )
            embed.add_field(
                name="Cache Threshold",
                value=f"`{config.get('cache_count_threshold', 5)}` messages\nMessages needed to trigger response",
                inline=False
            )
            embed.add_field(
                name="Engaged Delay",
                value=f"`{config.get('engaged_delay', 2.5)}` seconds\nReduced delay when conversation is active",
                inline=False
            )
            embed.add_field(
                name="Engaged Threshold",
                value=f"`{config.get('engaged_message_threshold', 2)}` messages\nMessages to activate engaged mode",
                inline=False
            )
            embed.set_footer(text="Use /config_timing to modify these settings")
        
        elif category == "text":
            patterns = config.get('remove_ai_text_from', [])
            pattern_str = ", ".join(f"`{p}`" for p in patterns[:3]) if patterns else "None"
            if len(patterns) > 3:
                pattern_str += f" (+{len(patterns)-3} more)"
            
            embed.add_field(
                name="Remove Patterns",
                value=f"{pattern_str}\nRegex patterns to remove from AI responses",
                inline=False
            )
            embed.add_field(
                name="Remove Emoji",
                value=f"`{config.get('remove_ai_emoji', False)}`\nRemove emojis from responses",
                inline=False
            )
            
            error_mode = config.get('error_handling_mode', 'friendly')
            error_mode_display = {
                "friendly": "Friendly (user-friendly messages)",
                "detailed": "Detailed (show exception details)",
                "silent": "Silent (don't send errors)"
            }.get(error_mode, error_mode)
            
            embed.add_field(
                name="Error Handling Mode",
                value=f"`{error_mode_display}`\nHow LLM errors are formatted",
                inline=False
            )
            embed.add_field(
                name="Save Errors in History",
                value=f"`{config.get('save_errors_in_history', False)}`\nSave error messages in conversation history (LLM can see past errors)",
                inline=False
            )
            embed.add_field(
                name="Send Errors to Chat",
                value=f"`{config.get('send_errors_to_chat', True)}`\nSend error messages to Discord channel (visible to users)",
                inline=False
            )
            embed.set_footer(text="Use /config_text to modify these settings")
        
        elif category == "card":
            embed.add_field(
                name="Greeting Index",
                value=f"`{config.get('greeting_index', 0)}`\nWhich greeting to use (0=first, 1+=alternates)",
                inline=False
            )
            embed.add_field(
                name="{{user}} Replacement",
                value=f"`{config.get('user_syntax_replacement', 'none')}`\nHow to replace {{user}} placeholder",
                inline=False
            )
            embed.add_field(
                name="Use Lorebook",
                value=f"`{config.get('use_lorebook', False)}`\nEnable lorebook entries",
                inline=False
            )
            embed.add_field(
                name="Lorebook Scan Depth",
                value=f"`{config.get('lorebook_scan_depth', 10)}` messages\nMessages to scan for lorebook triggers",
                inline=False
            )
            embed.set_footer(text="Use /config_card to modify these settings")
        
        elif category == "filter":
            embed.add_field(
                name="Filter Enabled",
                value=f"`{config.get('use_response_filter', False)}`\nIntelligent response filtering",
                inline=False
            )
            embed.add_field(
                name="API Connection",
                value=f"`{config.get('response_filter_api_connection', 'Not set')}`\nConnection for filter (must support Tool Calling)",
                inline=False
            )
            embed.add_field(
                name="Fallback Behavior",
                value=f"`{config.get('response_filter_fallback', 'respond')}`\nWhat to do if filter fails",
                inline=False
            )
            embed.add_field(
                name="Timeout",
                value=f"`{config.get('response_filter_timeout', 5.0)}` seconds\nMaximum wait time for filter",
                inline=False
            )
            embed.set_footer(text="Use /config_filter to modify these settings")
        
        elif category == "reply":
            embed.add_field(
                name="Reply System Enabled",
                value=f"`{config.get('enable_reply_system', False)}`\nAllow AI to reply to specific messages",
                inline=False
            )
            prompt = config.get('reply_prompt', '')
            prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
            embed.add_field(
                name="Reply Prompt",
                value=f"```\n{prompt_preview}\n```",
                inline=False
            )
            embed.set_footer(text="Use /config_reply to modify these settings")
        
        elif category == "tools":
            tool_config = config.get('tool_calling', {})
            embed.add_field(
                name="Tool Calling Enabled",
                value=f"`{tool_config.get('enabled', False)}`\nAllow AI to call functions to query information",
                inline=False
            )
            
            allowed_tools = tool_config.get('allowed_tools', [])
            if "all" in allowed_tools:
                tools_str = "All tools enabled"
            elif allowed_tools:
                tools_str = ", ".join(f"`{t}`" for t in allowed_tools[:5])
                if len(allowed_tools) > 5:
                    tools_str += f" (+{len(allowed_tools)-5} more)"
            else:
                tools_str = "No tools allowed"
            
            embed.add_field(
                name="Allowed Tools",
                value=tools_str,
                inline=False
            )
            
            # Get all available tools dynamically
            from AI.tools import TOOL_DEFINITIONS
            tools_list = []
            for tool_def in TOOL_DEFINITIONS:
                tool_name = tool_def["function"]["name"]
                tool_desc = tool_def["function"]["description"].split('.')[0]  # First sentence only
                tools_list.append(f"• `{tool_name}` - {tool_desc[:60]}{'...' if len(tool_desc) > 60 else ''}")
            
            # Split into multiple fields if too many tools
            tools_per_field = 6
            for i in range(0, len(tools_list), tools_per_field):
                chunk = tools_list[i:i+tools_per_field]
                field_name = "ℹ️ Available Tools" if i == 0 else f"ℹ️ Available Tools (cont.)"
                embed.add_field(
                    name=field_name,
                    value="\n".join(chunk),
                    inline=False
                )
            
            embed.add_field(
                name="⚠️ Note",
                value="Tool calling requires an API connection that supports function calling (OpenAI, DeepSeek, etc.)",
                inline=False
            )
            
            embed.set_footer(text=f"Tool calling allows AI to query information dynamically • {len(TOOL_DEFINITIONS)} tools available")
        
        elif category == "memory":
            memory_enabled = config.get('enable_memory_system', False)
            max_tokens = config.get('memory_max_tokens', 1000)
            
            embed.add_field(
                name="Memory System Enabled",
                value=f"`{memory_enabled}`\nPersistent memory across conversations",
                inline=False
            )
            embed.add_field(
                name="Maximum Tokens",
                value=f"`{max_tokens}` tokens\nMaximum tokens allowed in memory (counted with tiktoken)",
                inline=False
            )
            
            # Check if tool calling is enabled
            tool_config = config.get('tool_calling', {})
            tool_calling_enabled = tool_config.get('enabled', False)
            
            if memory_enabled and not tool_calling_enabled:
                embed.add_field(
                    name="⚠️ Warning",
                    value="Memory system is enabled but tool calling is disabled!\nMemory tools won't work without tool calling.",
                    inline=False
                )
            
            embed.add_field(
                name="📋 Memory Tools",
                value=(
                    "• `list_memories` - View saved memories\n"
                    "• `add_memory` - Save new information\n"
                    "• `update_memory` - Modify existing memory\n"
                    "• `remove_memory` - Delete specific memory\n"
                    "• `search_memories` - Search by keyword"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💡 How It Works",
                value=(
                    "1. LLM can save important information using memory tools\n"
                    "2. Saved memories are injected into the prompt automatically\n"
                    "3. Each chat has its own independent memory\n"
                    "4. Memory files: `data/memory/{ai_name}_{chat_id}.json`"
                ),
                inline=False
            )
            
            embed.set_footer(text="Use /config_memory to modify these settings • Requires tool_calling.enabled: true")
        
        elif category == "sleep":
            embed.add_field(
                name="Sleep Mode Enabled",
                value=f"`{config.get('sleep_mode_enabled', False)}`\nAI stops responding after refusals",
                inline=False
            )
            embed.add_field(
                name="Threshold",
                value=f"`{config.get('sleep_mode_threshold', 5)}` refusals\nConsecutive refusals before sleep",
                inline=False
            )
            
            # Wake-up patterns
            wakeup_patterns = config.get('sleep_wakeup_patterns', ['{ai_mention}', '{reply}'])
            if wakeup_patterns:
                patterns_display = []
                for pattern in wakeup_patterns[:5]:  # Show first 5
                    if pattern == "{ai_mention}":
                        patterns_display.append("• `{ai_mention}` - Wake on direct mention")
                    elif pattern == "{reply}":
                        patterns_display.append("• `{reply}` - Wake on reply to AI")
                    elif pattern == "{ai_name}":
                        patterns_display.append("• `{ai_name}` - Wake when AI name appears")
                    else:
                        # Regex pattern
                        patterns_display.append(f"• `{pattern}` - Custom regex")
                
                if len(wakeup_patterns) > 5:
                    patterns_display.append(f"... and {len(wakeup_patterns) - 5} more")
                
                embed.add_field(
                    name="Wake-up Patterns",
                    value="\n".join(patterns_display) if patterns_display else "None configured",
                    inline=False
                )
            
            embed.add_field(
                name="💡 Pattern Types",
                value=(
                    "**Placeholders:**\n"
                    "• `{ai_mention}` - Direct @mention\n"
                    "• `{reply}` - Reply to AI message\n"
                    "• `{ai_name}` - AI name in text\n\n"
                    "**Regex:** Custom patterns like `\\b(?i:bot)\\b`"
                ),
                inline=False
            )
            
            embed.set_footer(text="Use /config_sleep to modify these settings • Edit config/defaults.yml for wake-up patterns")
        
        elif category == "ignore":
            embed.add_field(
                name="Ignore System Enabled",
                value=f"`{config.get('enable_ignore_system', False)}`\nLLM decides during generation to skip responding",
                inline=False
            )
            embed.add_field(
                name="Sleep Threshold",
                value=f"`{config.get('ignore_sleep_threshold', 3)}` ignores\nConsecutive ignores before sleep mode",
                inline=False
            )
            
            # Show mutual exclusivity warning if both are enabled
            if config.get('enable_ignore_system', False) and config.get('use_response_filter', False):
                embed.add_field(
                    name="⚠️ Warning",
                    value="Both ignore system and response filter are enabled! Only one should be active.",
                    inline=False
                )
            
            embed.set_footer(text="Use /config_ignore to modify these settings")
        
        elif category == "advanced":
            api_connection = session.get("api_connection", "Not set")
            embed.add_field(
                name="API Connection",
                value=f"`{api_connection}`\nConnection used for this AI",
                inline=False
            )
            
            sys_msg = config.get('system_message', '')
            sys_msg_preview = sys_msg[:200] + "..." if len(sys_msg) > 200 else sys_msg
            embed.add_field(
                name="System Message",
                value=f"```\n{sys_msg_preview}\n```",
                inline=False
            )
            
            embed.add_field(
                name="New Chat on Reset",
                value=f"`{config.get('new_chat_on_reset', False)}`\nCreate new chat when resetting",
                inline=False
            )
            embed.add_field(
                name="Auto Reactions",
                value=f"`{config.get('auto_add_generation_reactions', False)}`\nAdd ◀️▶️🔄 reactions automatically",
                inline=False
            )
            
            # Context Order
            context_order = config.get('context_order', [])
            if context_order and isinstance(context_order, list):
                order_display = "\n".join([f"{i+1}. `{component}`" for i, component in enumerate(context_order)])
                embed.add_field(
                    name="📋 Context Injection Order",
                    value=order_display,
                    inline=False
                )
            
            embed.set_footer(text="Use /config_advanced to modify these settings")
        
        return embed
    
    def _get_category_name(self, category: str) -> str:
        """Get display name for category."""
        names = {
            "display": "Display Settings",
            "timing": "Timing Settings",
            "text": "Text Processing",
            "card": "Character Card",
            "filter": "Response Filter",
            "reply": "Reply System",
            "tools": "Tool Calling",
            "memory": "Memory System",
            "ignore": "Ignore System",
            "sleep": "Sleep Mode",
            "advanced": "Advanced Settings"
        }
        return names.get(category, category.title())
    
    @app_commands.command(name="config_help", description="Show help for configuration commands")
    async def config_help(self, interaction: discord.Interaction):
        """Show help for all configuration commands."""
        embed = discord.Embed(
            title="⚙️ Configuration Commands Help",
            description="Organized commands for managing AI behavior",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📋 Viewing Configurations",
            value=(
                "`/show_config` - View AI configuration (organized by category)\n"
                "`/config_help` - Show this help message"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Configuration Commands",
            value=(
                "`/config_display` - Display & messaging settings\n"
                "`/config_timing` - Response timing settings\n"
                "`/config_text` - Text processing settings\n"
                "`/config_card` - Character Card V3 settings\n"
                "`/config_filter` - Response filter settings\n"
                "`/config_reply` - Reply system settings\n"
                "`/config_ignore` - Ignore system settings\n"
                "`/config_sleep` - Sleep mode settings\n"
                "`/config_tool_calling` - Tool calling (function calling) settings\n"
                "`/config_memory` - Persistent memory system settings\n"
                "`/config_advanced` - Advanced settings"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📦 Preset Commands",
            value=(
                "`/preset_save` - Save current config as preset\n"
                "`/preset_apply` - Apply preset to an AI\n"
                "`/preset_list` - List available presets\n"
                "`/preset_info` - View preset details\n"
                "`/preset_delete` - Delete a preset"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔧 Other Commands",
            value=(
                "`/copy_config` - Copy settings from one AI to another\n"
                "`/character_info` - View Character Card details"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💡 Tips",
            value=(
                "• Edit `config/defaults.yml` to change global defaults\n"
                "• Use presets to save and reuse favorite configurations\n"
                "• View specific categories with `/show_config category:<name>`"
            ),
            inline=False
        )
        
        embed.set_footer(text="Configuration System")
        
        await interaction.response.send_message(embed=embed, ephemeral=False)


async def setup(bot):
    await bot.add_cog(ConfigViewCommands(bot))
