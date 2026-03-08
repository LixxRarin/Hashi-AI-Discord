import re
import discord
from discord import app_commands
from discord.ext import commands
from typing import Dict, List

import utils.func as func
from utils.pagination import PaginatedView

# Import AI module to trigger provider registration
import AI
from AI.provider_registry import get_registry


class APIConnections(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def provider_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete function for provider selection."""
        try:
            registry = get_registry()
            choices = []
            
            for name, metadata in registry.get_all_metadata().items():
                if current.lower() in name.lower() or current.lower() in metadata.display_name.lower():
                    choices.append(
                        app_commands.Choice(
                            name=f"{metadata.icon} {metadata.display_name}",
                            value=name
                        )
                    )
            
            return choices[:25]
        except Exception as e:
            func.log.error(f"Error in provider_autocomplete: {e}")
            return []
    
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

    def _validate_connection_name(self, name: str) -> tuple[bool, str]:
        """
        Validate connection name format.
        
        Returns:
            tuple[bool, str]: (is_valid, error_message)
        """
        if not name:
            return False, "Connection name cannot be empty."
        
        if len(name) > 50:
            return False, "Connection name must be 50 characters or less."
        
        return True, ""

    def _mask_api_key(self, api_key: str) -> str:
        """Mask API key for display, showing only first and last 4 characters."""
        if len(api_key) <= 8:
            return "*" * len(api_key)
        return f"{api_key[:4]}...{api_key[-4:]}"

    @app_commands.command(name="new_api", description="Create a new API connection with LLM parameters")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(provider=provider_autocomplete)
    @app_commands.describe(
        connection_name="Unique name for this connection (e.g., 'my-openai')",
        provider="API Provider",
        api_key="API Key for this connection - REQUIRED",
        model="Model name (e.g., gpt-4, gpt-3.5-turbo) - REQUIRED",
        base_url="Custom API endpoint URL (optional)",
        max_tokens="Maximum tokens in response (default: 1000)",
        temperature="Temperature 0.0-2.0 (default: 0.7)",
        top_p="Top P 0.0-1.0 (default: 1.0)",
        frequency_penalty="Frequency penalty -2.0 to 2.0 (default: 0.0)",
        presence_penalty="Presence penalty -2.0 to 2.0 (default: 0.0)",
        context_size="Context size in tokens (default: 4096)",
        think_switch="Enable thinking feature (default: true)",
        think_depth="Thinking depth 1-5 (default: 3)",
        hide_thinking_tags="Hide thinking tags from AI responses (default: true)",
        thinking_tag_patterns="Comma-separated regex patterns for thinking tags (optional)",
        max_tool_rounds="Maximum tool calling rounds 1-10 (default: 5)",
        custom_extra_body="Custom extra parameters as JSON string (e.g., '{\"num_ctx\": 8192}')",
        save_thinking_in_history="Save thinking/reasoning in conversation history (default: true)",
        vision_enabled="Enable vision/image analysis (default: false)",
        vision_detail="Vision detail level: low, high, auto (default: auto)",
        max_image_size="Maximum image size in MB (default: 20)"
    )
    async def new_api(
        self,
        interaction: discord.Interaction,
        connection_name: str,
        provider: str,
        api_key: str,
        model: str,
        base_url: str = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        context_size: int = 4096,
        think_switch: bool = True,
        think_depth: int = 3,
        hide_thinking_tags: bool = True,
        thinking_tag_patterns: str = None,
        max_tool_rounds: int = 5,
        custom_extra_body: str = None,
        save_thinking_in_history: bool = True,
        vision_enabled: bool = False,
        vision_detail: str = "auto",
        max_image_size: int = 20
    ):
        """Create a new API connection with all LLM parameters."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        
        # Validate provider exists in registry
        registry = get_registry()
        if not registry.is_registered(provider):
            available = ', '.join(registry.list_providers())
            await interaction.followup.send(
                f"❌ **Error:** Provider '{provider}' is not registered.\n\n"
                f"Available providers: {available}",
                ephemeral=True
            )
            return
        
        # Validate connection name
        is_valid, error_msg = self._validate_connection_name(connection_name)
        if not is_valid:
            await interaction.followup.send(f"❌ **Error:** {error_msg}", ephemeral=True)
            return
        
        # Validate parameters
        if temperature < 0.0 or temperature > 2.0:
            await interaction.followup.send(
                "❌ **Error:** Temperature must be between 0.0 and 2.0.",
                ephemeral=True
            )
            return
        
        if top_p < 0.0 or top_p > 1.0:
            await interaction.followup.send(
                "❌ **Error:** Top P must be between 0.0 and 1.0.",
                ephemeral=True
            )
            return
        
        if frequency_penalty < -2.0 or frequency_penalty > 2.0:
            await interaction.followup.send(
                "❌ **Error:** Frequency penalty must be between -2.0 and 2.0.",
                ephemeral=True
            )
            return
        
        if presence_penalty < -2.0 or presence_penalty > 2.0:
            await interaction.followup.send(
                "❌ **Error:** Presence penalty must be between -2.0 and 2.0.",
                ephemeral=True
            )
            return
        
        if think_depth < 1 or think_depth > 5:
            await interaction.followup.send(
                "❌ **Error:** Think depth must be between 1 and 5.",
                ephemeral=True
            )
            return
        
        if max_tool_rounds < 1 or max_tool_rounds > 10:
            await interaction.followup.send(
                "❌ **Error:** Max tool rounds must be between 1 and 10.",
                ephemeral=True
            )
            return
        
        if max_tokens < 1:
            await interaction.followup.send(
                "❌ **Error:** Max tokens must be at least 1.",
                ephemeral=True
            )
            return
        
        if context_size < 1:
            await interaction.followup.send(
                "❌ **Error:** Context size must be at least 1.",
                ephemeral=True
            )
            return
        
        # Validate multimodal parameters
        if vision_detail not in ["low", "high", "auto"]:
            await interaction.followup.send(
                "❌ **Error:** Vision detail must be 'low', 'high', or 'auto'.",
                ephemeral=True
            )
            return
        
        if max_image_size < 1 or max_image_size > 100:
            await interaction.followup.send(
                "❌ **Error:** Max image size must be between 1 and 100 MB.",
                ephemeral=True
            )
            return
        
        # Process thinking_tag_patterns
        patterns_list = None
        if thinking_tag_patterns is not None:
            if thinking_tag_patterns.lower() == "none":
                patterns_list = []
            else:
                patterns_list = [p.strip() for p in thinking_tag_patterns.split(",")]
        
        # Create the connection
        try:
            success = await func.create_api_connection(
                server_id=server_id,
                connection_name=connection_name,
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                context_size=context_size,
                think_switch=think_switch,
                think_depth=think_depth,
                hide_thinking_tags=hide_thinking_tags,
                thinking_tag_patterns=patterns_list,
                max_tool_rounds=max_tool_rounds,
                custom_extra_body=custom_extra_body,
                save_thinking_in_history=save_thinking_in_history,
                vision_enabled=vision_enabled,
                vision_detail=vision_detail,
                max_image_size=max_image_size,
                created_by=str(interaction.user.id)
            )
        except ValueError as e:
            await interaction.followup.send(f"❌ **Error:** {e}", ephemeral=True)
            return
        
        if not success:
            await interaction.followup.send(
                f"❌ **Error:** Connection '{connection_name}' already exists in this server.",
                ephemeral=True
            )
            return
        
        # Get provider display name (already validated above)
        provider_metadata = registry.get_metadata(provider)
        provider_display = provider_metadata.display_name
        
        # Success message
        masked_key = self._mask_api_key(api_key)
        success_msg = f"✅ **API Connection Created Successfully!**\n\n"
        success_msg += f"**Connection Name:** `{connection_name}`\n"
        success_msg += f"**Provider:** {provider_display}\n"
        success_msg += f"**API Key:** `{masked_key}`\n"
        success_msg += f"**Model:** `{model}`\n"
        if base_url:
            success_msg += f"**Custom Endpoint:** `{base_url}`\n"
        success_msg += f"\n**LLM Parameters:**\n"
        success_msg += f"• Max Tokens: `{max_tokens}`\n"
        success_msg += f"• Temperature: `{temperature}`\n"
        success_msg += f"• Top P: `{top_p}`\n"
        success_msg += f"• Frequency Penalty: `{frequency_penalty}`\n"
        success_msg += f"• Presence Penalty: `{presence_penalty}`\n"
        success_msg += f"• Context Size: `{context_size}`\n"
        success_msg += f"• Max Tool Rounds: `{max_tool_rounds}`\n"
        success_msg += f"• Thinking: `{'Enabled' if think_switch else 'Disabled'}`"
        if think_switch:
            success_msg += f" (Depth: {think_depth})"
        success_msg += f"\n• Hide Thinking Tags: `{'Yes' if hide_thinking_tags else 'No'}`"
        if patterns_list is not None and patterns_list:
            success_msg += f"\n• Thinking Tag Patterns: `{len(patterns_list)} pattern(s)`"
        if custom_extra_body:
            success_msg += f"\n• Custom Extra Body: `{len(custom_extra_body)} chars`"
        success_msg += f"\n• Save Thinking in History: `{'Yes' if save_thinking_in_history else 'No'}`"
        
        # Multimodal parameters
        success_msg += f"\n\n**Multimodal Features:**\n"
        success_msg += f"• Vision: `{'Enabled' if vision_enabled else 'Disabled'}`"
        if vision_enabled:
            success_msg += f" (Detail: {vision_detail}, Max: {max_image_size}MB)"
        
        success_msg += f"\n\n💡 **Next Step:** Use `/setup` to create an AI with this connection!"
        
        await interaction.followup.send(success_msg, ephemeral=True)


    @app_commands.command(name="api_config", description="Update LLM parameters of an API connection")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        connection_name="Name of the connection to configure",
        new_connection_name="New name for the connection (to rename it)",
        api_key="API Key (leave empty to keep current)",
        model="Model name",
        base_url="Custom API endpoint URL",
        max_tokens="Maximum tokens in response",
        temperature="Temperature 0.0-2.0",
        top_p="Top P 0.0-1.0",
        frequency_penalty="Frequency penalty -2.0 to 2.0",
        presence_penalty="Presence penalty -2.0 to 2.0",
        context_size="Context size in tokens",
        think_switch="Enable thinking feature",
        think_depth="Thinking depth 1-5",
        hide_thinking_tags="Hide thinking tags from AI responses",
        thinking_tag_patterns="Comma-separated regex patterns for thinking tags (write 'none' to clear)",
        max_tool_rounds="Maximum tool calling rounds 1-10",
        custom_extra_body="Custom extra parameters as JSON string (write 'none' to clear)",
        save_thinking_in_history="Save thinking/reasoning in conversation history",
        vision_enabled="Enable vision/image analysis",
        vision_detail="Vision detail level: low, high, auto",
        max_image_size="Maximum image size in MB"
    )
    @app_commands.autocomplete(connection_name=connection_name_autocomplete)
    async def api_config(
        self,
        interaction: discord.Interaction,
        connection_name: str,
        new_connection_name: str = None,
        api_key: str = None,
        model: str = None,
        base_url: str = None,
        max_tokens: int = None,
        temperature: float = None,
        top_p: float = None,
        frequency_penalty: float = None,
        presence_penalty: float = None,
        context_size: int = None,
        think_switch: bool = None,
        think_depth: int = None,
        hide_thinking_tags: bool = None,
        thinking_tag_patterns: str = None,
        max_tool_rounds: int = None,
        custom_extra_body: str = None,
        save_thinking_in_history: bool = None,
        vision_enabled: bool = None,
        vision_detail: str = None,
        max_image_size: int = None
    ):
        """Update LLM parameters of an existing API connection."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        
        # Check if connection exists
        connection = func.get_api_connection(server_id, connection_name)
        if not connection:
            await interaction.followup.send(
                f"❌ **Error:** Connection '{connection_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        # Handle connection renaming if new_connection_name is provided
        renamed = False
        old_name = connection_name
        if new_connection_name is not None:
            # Validate new connection name
            is_valid, error_msg = self._validate_connection_name(new_connection_name)
            if not is_valid:
                await interaction.followup.send(f"❌ **Error:** {error_msg}", ephemeral=True)
                return
            
            # Perform the rename
            success, error_msg = await func.rename_api_connection(server_id, connection_name, new_connection_name)
            if not success:
                await interaction.followup.send(f"❌ **Error:** {error_msg}", ephemeral=True)
                return
            
            # Update connection_name for subsequent operations
            connection_name = new_connection_name
            renamed = True
            func.log.info(f"Renamed connection '{old_name}' to '{new_connection_name}' in server {server_id}")
        
        # Validate parameters if provided
        if temperature is not None and (temperature < 0.0 or temperature > 2.0):
            await interaction.followup.send(
                "❌ **Error:** Temperature must be between 0.0 and 2.0.",
                ephemeral=True
            )
            return
        
        if top_p is not None and (top_p < 0.0 or top_p > 1.0):
            await interaction.followup.send(
                "❌ **Error:** Top P must be between 0.0 and 1.0.",
                ephemeral=True
            )
            return
        
        if frequency_penalty is not None and (frequency_penalty < -2.0 or frequency_penalty > 2.0):
            await interaction.followup.send(
                "❌ **Error:** Frequency penalty must be between -2.0 and 2.0.",
                ephemeral=True
            )
            return
        
        if presence_penalty is not None and (presence_penalty < -2.0 or presence_penalty > 2.0):
            await interaction.followup.send(
                "❌ **Error:** Presence penalty must be between -2.0 and 2.0.",
                ephemeral=True
            )
            return
        
        if think_depth is not None and (think_depth < 1 or think_depth > 5):
            await interaction.followup.send(
                "❌ **Error:** Think depth must be between 1 and 5.",
                ephemeral=True
            )
            return
        
        if max_tool_rounds is not None and (max_tool_rounds < 1 or max_tool_rounds > 10):
            await interaction.followup.send(
                "❌ **Error:** Max tool rounds must be between 1 and 10.",
                ephemeral=True
            )
            return
        
        if max_tokens is not None and max_tokens < 1:
            await interaction.followup.send(
                "❌ **Error:** Max tokens must be at least 1.",
                ephemeral=True
            )
            return
        
        if context_size is not None and context_size < 1:
            await interaction.followup.send(
                "❌ **Error:** Context size must be at least 1.",
                ephemeral=True
            )
            return
        
        # Validate multimodal parameters
        if vision_detail is not None and vision_detail not in ["low", "high", "auto"]:
            await interaction.followup.send(
                "❌ **Error:** Vision detail must be 'low', 'high', or 'auto'.",
                ephemeral=True
            )
            return
        
        if max_image_size is not None and (max_image_size < 1 or max_image_size > 100):
            await interaction.followup.send(
                "❌ **Error:** Max image size must be between 1 and 100 MB.",
                ephemeral=True
            )
            return
        
        # Build updates dictionary
        updates = {}
        if api_key is not None:
            updates["api_key"] = api_key
        if model is not None:
            updates["model"] = model
        if base_url is not None:
            updates["base_url"] = None if base_url.lower() == "none" else base_url
        if max_tokens is not None:
            updates["max_tokens"] = max_tokens
        if temperature is not None:
            updates["temperature"] = temperature
        if top_p is not None:
            updates["top_p"] = top_p
        if frequency_penalty is not None:
            updates["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            updates["presence_penalty"] = presence_penalty
        if context_size is not None:
            updates["context_size"] = context_size
        if think_switch is not None:
            updates["think_switch"] = think_switch
        if think_depth is not None:
            updates["think_depth"] = think_depth
        if hide_thinking_tags is not None:
            updates["hide_thinking_tags"] = hide_thinking_tags
        if thinking_tag_patterns is not None:
            if thinking_tag_patterns.lower() == "none":
                updates["thinking_tag_patterns"] = []
            else:
                updates["thinking_tag_patterns"] = [p.strip() for p in thinking_tag_patterns.split(",")]
        if max_tool_rounds is not None:
            updates["max_tool_rounds"] = max_tool_rounds
        if custom_extra_body is not None:
            if custom_extra_body.lower() == "none":
                updates["custom_extra_body"] = None
            else:
                try:
                    import json
                    extra_body_dict = json.loads(custom_extra_body)
                    if not isinstance(extra_body_dict, dict):
                        raise ValueError("custom_extra_body must be a JSON object")
                    updates["custom_extra_body"] = extra_body_dict
                except json.JSONDecodeError as e:
                    await interaction.followup.send(
                        f"❌ Invalid JSON in custom_extra_body: {e}",
                        ephemeral=True
                    )
                    return
        if save_thinking_in_history is not None:
            updates["save_thinking_in_history"] = save_thinking_in_history
        if vision_enabled is not None:
            updates["vision_enabled"] = vision_enabled
        if vision_detail is not None:
            updates["vision_detail"] = vision_detail
        if max_image_size is not None:
            updates["max_image_size"] = max_image_size
        
        # Check if any changes were made (rename or parameter updates)
        if not updates and not renamed:
            await interaction.followup.send(
                "❌ **Error:** No parameters provided to update.",
                ephemeral=True
            )
            return
        
        # Update the connection parameters if there are any updates
        if updates:
            success = await func.update_api_connection(server_id, connection_name, **updates)
            
            if not success:
                await interaction.followup.send(
                    f"❌ **Error:** Failed to update connection '{connection_name}'.",
                    ephemeral=True
                )
                return
        
        # Check which AIs use this connection
        ais_using = func.get_ais_using_connection(server_id, connection_name)
        
        # Success message
        success_msg = f"✅ **API Connection Updated Successfully!**\n\n"
        
        # Show rename information if applicable
        if renamed:
            success_msg += f"**Old Name:** `{old_name}`\n"
            success_msg += f"**New Name:** `{connection_name}`\n"
        else:
            success_msg += f"**Connection Name:** `{connection_name}`\n"
        
        # Show updated parameters if any
        if updates or renamed:
            success_msg += f"**Updated Parameters:**\n"
            
            if renamed:
                success_msg += f"• Connection Name: `{old_name}` → `{connection_name}`\n"
            
            for key, value in updates.items():
                if key == "api_key":
                    success_msg += f"• API Key: `{self._mask_api_key(value)}`\n"
                elif key == "base_url":
                    success_msg += f"• Base URL: `{value if value else 'None'}`\n"
                elif key == "thinking_tag_patterns":
                    if isinstance(value, list):
                        success_msg += f"• Thinking Tag Patterns: `{len(value)} pattern(s)`\n"
                    else:
                        success_msg += f"• Thinking Tag Patterns: `{value}`\n"
                elif key == "hide_thinking_tags":
                    success_msg += f"• Hide Thinking Tags: `{'Yes' if value else 'No'}`\n"
                elif key == "custom_extra_body":
                    if value is None:
                        success_msg += f"• Custom Extra Body: `Cleared`\n"
                    else:
                        import json
                        success_msg += f"• Custom Extra Body: `{len(json.dumps(value))} chars`\n"
                elif key == "save_thinking_in_history":
                    success_msg += f"• Save Thinking in History: `{'Yes' if value else 'No'}`\n"
                else:
                    success_msg += f"• {key.replace('_', ' ').title()}: `{value}`\n"
        
        if ais_using:
            success_msg += f"\n⚠️ **Info:** This connection is used by {len(ais_using)} AI(s):\n"
            for channel_id, ai_name in ais_using[:5]:  # Show max 5
                channel = interaction.guild.get_channel(int(channel_id))
                channel_mention = channel.mention if channel else f"<#{channel_id}>"
                success_msg += f"• `{ai_name}` in {channel_mention}\n"
            if len(ais_using) > 5:
                success_msg += f"• ... and {len(ais_using) - 5} more\n"
            if renamed:
                success_msg += f"\n✅ All these AIs have been automatically updated to use the new connection name!"
            else:
                success_msg += "\nAll these AIs will use the updated parameters!"
        
        await interaction.followup.send(success_msg, ephemeral=True)

    @app_commands.command(name="list_apis", description="List all API connections in this server")
    @app_commands.default_permissions(administrator=True)
    async def list_apis(self, interaction: discord.Interaction):
        """List all API connections configured in the server, grouped by provider with pagination."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        connections = func.list_api_connections(server_id)
        
        if not connections:
            await interaction.followup.send(
                "❌ No API connections configured in this server.\n\n"
                "💡 Use `/new_api` to create your first connection!",
                ephemeral=True
            )
            return
        
        # Get registry for provider metadata
        registry = get_registry()
        
        # Create embeds - one per connection
        embeds = []
        total_connections = len(connections)
        
        for idx, (conn_name, conn_data) in enumerate(sorted(connections.items())):
            provider = conn_data.get("provider", "unknown").lower()
            model = conn_data.get("model", "Unknown")
            
            # Get provider metadata
            try:
                provider_meta = registry.get_metadata(provider)
                provider_display = provider_meta.display_name
                provider_icon = provider_meta.icon
                provider_color = getattr(discord.Color, provider_meta.color, discord.Color.blue)()
            except ValueError:
                provider_display = provider.upper()
                provider_icon = "🔵"
                provider_color = discord.Color.blue()
            
            # Get AIs using this connection
            ais_using = func.get_ais_using_connection(server_id, conn_name)
            usage_count = len(ais_using)
            
            # Build description
            if usage_count > 0:
                description = f"{provider_icon} {provider_display} • `{model}` • {usage_count} AI{'s' if usage_count != 1 else ''} using"
            else:
                description = f"{provider_icon} {provider_display} • `{model}` • Available"
            
            # Create embed with connection name as title
            embed = discord.Embed(
                title=conn_name,
                description=description,
                color=provider_color
            )
            
            # Credentials field
            api_key = conn_data.get("api_key", "")
            masked_key = self._mask_api_key(api_key)
            base_url = conn_data.get("base_url")
            
            cred_value = f"• **API Key:** `{masked_key}`"
            if base_url:
                cred_value += f"\n• **Endpoint:** Custom ✅"
            
            embed.add_field(
                name="🔑 Credentials",
                value=cred_value,
                inline=False
            )
            
            # Parameters field
            params_value = f"• **Temp:** `{conn_data.get('temperature', 0.7)}` • **Tokens:** `{conn_data.get('max_tokens', 1000)}`\n"
            params_value += f"• **Context:** `{conn_data.get('context_size', 4096)}` • **Thinking:** `{'✅' if conn_data.get('think_switch', True) else '❌'}`"
            
            embed.add_field(
                name="⚙️ Parameters",
                value=params_value,
                inline=False
            )
            
            # Usage field (if in use)
            if usage_count > 0:
                usage_value = f"• **AIs:** {', '.join([f'`{ai}`' for _, ai in ais_using[:3]])}"
                if usage_count > 3:
                    usage_value += f" +{usage_count - 3} more"
                
                embed.add_field(
                    name="🤖 Current Usage",
                    value=usage_value,
                    inline=False
                )
            
            # Footer with position and helpful tip
            embed.set_footer(text=f"Connection {idx + 1}/{total_connections} • Use /show_api for full details")
            
            embeds.append(embed)
        
        # Send with pagination if multiple embeds
        if len(embeds) == 0:
            await interaction.followup.send(
                "❌ No API connections configured in this server.",
                ephemeral=True
            )
        elif len(embeds) == 1:
            # Single embed, send directly
            await interaction.followup.send(embed=embeds[0], ephemeral=True)
        else:
            # Multiple embeds, use pagination
            view = PaginatedView(embeds, user_id=interaction.user.id)
            message = await interaction.followup.send(
                embed=view.get_current_embed(),
                view=view,
                ephemeral=True
            )
            view.message = message

    @app_commands.command(name="remove_api", description="Remove an API connection")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        connection_name="Name of the connection to remove",
        force="Force removal even if AIs are using it (default: false)"
    )
    @app_commands.autocomplete(connection_name=connection_name_autocomplete)
    async def remove_api(
        self,
        interaction: discord.Interaction,
        connection_name: str,
        force: bool = False
    ):
        """Remove an API connection from the server."""
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        
        # Check if connection exists
        connection = func.get_api_connection(server_id, connection_name)
        if not connection:
            await interaction.followup.send(
                f"❌ **Error:** Connection '{connection_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        # Check if any AIs are using this connection
        ais_using = func.get_ais_using_connection(server_id, connection_name)
        
        if ais_using and not force:
            warning_msg = f"⚠️ **Warning:** Cannot remove connection '{connection_name}'.\n\n"
            warning_msg += f"This connection is currently used by {len(ais_using)} AI(s):\n"
            for channel_id, ai_name in ais_using[:10]:  # Show max 10
                channel = interaction.guild.get_channel(int(channel_id))
                channel_mention = channel.mention if channel else f"<#{channel_id}>"
                warning_msg += f"• `{ai_name}` in {channel_mention}\n"
            if len(ais_using) > 10:
                warning_msg += f"• ... and {len(ais_using) - 10} more\n"
            warning_msg += "\n**Options:**\n"
            warning_msg += "1. Remove or reconfigure these AIs first\n"
            warning_msg += "2. Use `force:True` to force removal (AIs will break!)"
            
            await interaction.followup.send(warning_msg, ephemeral=True)
            return
        
        # Remove the connection
        success = await func.delete_api_connection(server_id, connection_name)
        
        if not success:
            await interaction.followup.send(
                f"❌ **Error:** Failed to remove connection '{connection_name}'.",
                ephemeral=True
            )
            return
        
        # Success message
        success_msg = f"✅ **API Connection Removed Successfully!**\n\n"
        success_msg += f"**Connection Name:** `{connection_name}`\n"
        
        if ais_using:
            success_msg += f"\n⚠️ **Warning:** {len(ais_using)} AI(s) were using this connection and may no longer work:\n"
            for channel_id, ai_name in ais_using[:5]:
                channel = interaction.guild.get_channel(int(channel_id))
                channel_mention = channel.mention if channel else f"<#{channel_id}>"
                success_msg += f"• `{ai_name}` in {channel_mention}\n"
            if len(ais_using) > 5:
                success_msg += f"• ... and {len(ais_using) - 5} more\n"
            success_msg += "\n💡 Reconfigure these AIs with `/setup` using a different connection."
        
        await interaction.followup.send(success_msg, ephemeral=True)

    @app_commands.command(name="show_api", description="Display detailed configuration of a specific API connection")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(connection_name="Name of the API connection to show")
    @app_commands.autocomplete(connection_name=connection_name_autocomplete)
    async def show_api(self, interaction: discord.Interaction, connection_name: str):
        """
        Retrieves and displays detailed configuration settings for a specific API connection.
        """
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        
        # Get the connection
        connection = func.get_api_connection(server_id, connection_name)
        if not connection:
            await interaction.followup.send(
                f"❌ **Error:** Connection '{connection_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        # Get provider info
        provider = connection.get("provider", "unknown").upper()
        color = discord.Color.green() if provider in ["OPENAI", "DEEPSEEK"] else discord.Color.red()
        
        # Create embed
        embed = discord.Embed(
            title=f"🔌 API Connection: {connection_name}",
            description=f"**Provider:** {provider}",
            color=color
        )
        
        # Basic connection info
        model = connection.get("model", "Unknown")
        api_key = connection.get("api_key", "")
        masked_key = self._mask_api_key(api_key)
        base_url = connection.get("base_url")
        
        embed.add_field(name="📦 Model", value=f"`{model}`", inline=True)
        embed.add_field(name="🔑 API Key", value=f"`{masked_key}`", inline=True)
        if base_url:
            embed.add_field(name="🔗 Custom Endpoint", value=f"`{base_url}`", inline=False)
        
        # LLM Parameters section
        llm_params = "**Generation Parameters:**\n"
        llm_params += f"• Max Tokens: `{connection.get('max_tokens', 1000)}`\n"
        llm_params += f"• Temperature: `{connection.get('temperature', 0.7)}`\n"
        llm_params += f"• Top P: `{connection.get('top_p', 1.0)}`\n"
        llm_params += f"• Frequency Penalty: `{connection.get('frequency_penalty', 0.0)}`\n"
        llm_params += f"• Presence Penalty: `{connection.get('presence_penalty', 0.0)}`\n"
        llm_params += f"• Context Size: `{connection.get('context_size', 4096)}` tokens"
        
        embed.add_field(name="⚙️ LLM Parameters", value=llm_params, inline=False)
        
        # Thinking parameters section
        think_switch = connection.get('think_switch', True)
        think_depth = connection.get('think_depth', 3)
        hide_thinking = connection.get('hide_thinking_tags', True)
        save_thinking = connection.get('save_thinking_in_history', True)
        thinking_patterns = connection.get('thinking_tag_patterns', [])
        
        thinking_params = f"• Thinking: `{'Enabled' if think_switch else 'Disabled'}`"
        if think_switch:
            thinking_params += f" (Depth: {think_depth})"
        thinking_params += f"\n• Hide Thinking Tags: `{'Yes' if hide_thinking else 'No'}`"
        thinking_params += f"\n• Save in History: `{'Yes' if save_thinking else 'No'}`"
        if thinking_patterns:
            thinking_params += f"\n• Tag Patterns: `{len(thinking_patterns)} pattern(s)`"
            # Show first 2 patterns as examples
            for i, pattern in enumerate(thinking_patterns[:2]):
                thinking_params += f"\n  └ `{pattern}`"
            if len(thinking_patterns) > 2:
                thinking_params += f"\n  └ ... and {len(thinking_patterns) - 2} more"
        
        embed.add_field(name="🧠 Thinking Configuration", value=thinking_params, inline=False)
        
        # Tool Calling section
        max_tool_rounds = connection.get('max_tool_rounds', 5)
        tool_calling_info = f"• Max Tool Rounds: `{max_tool_rounds}`\n"
        tool_calling_info += f"• Allows AI to call functions up to {max_tool_rounds} times per response"
        
        embed.add_field(name="🔧 Tool Calling", value=tool_calling_info, inline=False)
        
        # Multimodal (Vision) section
        vision_enabled = connection.get('vision_enabled', False)
        vision_detail = connection.get('vision_detail', 'auto')
        max_image_size = connection.get('max_image_size', 20)
        
        vision_info = f"• Vision: `{'Enabled' if vision_enabled else 'Disabled'}`"
        if vision_enabled:
            vision_info += f"\n• Detail Level: `{vision_detail}`"
            vision_info += f"\n• Max Image Size: `{max_image_size} MB`"
        else:
            vision_info += f"\n• Enable vision to analyze images in conversations"
        
        embed.add_field(name="🖼️ Multimodal (Vision)", value=vision_info, inline=False)
        
        # Advanced Settings section (only if custom_extra_body exists)
        custom_extra_body = connection.get('custom_extra_body')
        if custom_extra_body:
            import json
            extra_body_str = json.dumps(custom_extra_body, indent=2)
            
            # Limitar tamanho para não estourar o embed
            if len(extra_body_str) > 200:
                extra_body_preview = extra_body_str[:200] + "..."
            else:
                extra_body_preview = extra_body_str
            
            advanced_info = f"**Custom Extra Body:**\n```json\n{extra_body_preview}\n```"
            
            embed.add_field(name="🔬 Advanced Settings", value=advanced_info, inline=False)
        
        # Get AIs using this connection
        ais_using = func.get_ais_using_connection(server_id, connection_name)
        
        if ais_using:
            usage_info = f"**Used by {len(ais_using)} AI(s):**\n"
            for channel_id, ai_name in ais_using[:5]:  # Show max 5
                channel = interaction.guild.get_channel(int(channel_id))
                channel_mention = channel.mention if channel else f"<#{channel_id}>"
                usage_info += f"• `{ai_name}` in {channel_mention}\n"
            if len(ais_using) > 5:
                usage_info += f"• ... and {len(ais_using) - 5} more"
            embed.add_field(name="📊 Usage", value=usage_info, inline=False)
        else:
            embed.add_field(name="📊 Usage", value="Not currently used by any AI", inline=False)
        
        # Metadata
        created_at = connection.get("created_at", "Unknown")
        created_by = connection.get("created_by")
        if created_by:
            embed.set_footer(text=f"Created by <@{created_by}> • {created_at}")
        else:
            embed.set_footer(text=f"Created at {created_at}")
        
        await interaction.followup.send(embed=embed, ephemeral=False)


async def setup(bot):
    await bot.add_cog(APIConnections(bot))
