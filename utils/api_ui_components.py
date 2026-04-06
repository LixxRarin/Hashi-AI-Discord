"""
API UI Components - Interactive UI for API Connection Management

Provides interactive Discord UI components for managing API connections.
Similar structure to config_ui_components.py.
"""

import discord
from discord import ui
from typing import Any, Dict, List, Optional
import traceback

import utils.func as func
from utils.api_metadata import (
    get_api_metadata,
    get_all_categories,
    get_category_params,
    get_category_emoji
)
from utils.pagination import PaginatedView
from AI.provider_registry import get_registry

def create_connection_list_embed(
    server_id: str,
    guild_name: str,
    page: int = 0,
    per_page: int = 5
) -> discord.Embed:
    """
    Create embed showing list of API connections.
    
    Args:
        server_id: Server ID
        guild_name: Guild name for title
        page: Current page number
        per_page: Connections per page
    
    Returns:
        Discord embed with connection list
    """
    connections = func.list_api_connections(server_id)
    
    if not connections:
        embed = discord.Embed(
            title=f"🔌 API Connections - {guild_name}",
            description="No API connections configured in this server.\n\n"
                       "💡 Click **Create New** to create your first connection!",
            color=discord.Color.blue()
        )
        return embed
    
    # Calculate pagination
    total = len(connections)
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, total)
    
    # Get registry for provider metadata
    registry = get_registry()
    
    # Create embed
    embed = discord.Embed(
        title=f"🔌 API Connections - {guild_name}",
        description=f"📊 Total: {total} connection(s)\n\n"
                   f"Select an action below to manage your connections.",
        color=discord.Color.blue()
    )
    
    # Add connections
    for idx, (conn_name, conn_data) in enumerate(sorted(connections.items())[start_idx:end_idx], start=start_idx + 1):
        provider = conn_data.get("provider", "unknown").lower()
        model = conn_data.get("model", "Unknown")
        
        # Get provider metadata
        try:
            provider_meta = registry.get_metadata(provider)
            provider_display = provider_meta.display_name
            provider_icon = provider_meta.icon
        except ValueError:
            provider_display = provider.upper()
            provider_icon = "🔵"
        
        # Get AIs using this connection
        ais_using = func.get_ais_using_connection(server_id, conn_name)
        usage_count = len(ais_using)
        
        # Build field value with usage info
        if usage_count > 0:
            status = f"⚡ {usage_count} AI{'s' if usage_count != 1 else ''} using"
        else:
            status = "💤 Not in use"
        
        field_value = f"{provider_icon} **{provider_display}** • `{model}`\n{status}"
        
        embed.add_field(
            name=f"{idx}. {conn_name}",
            value=field_value,
            inline=False
        )
    
    # Add footer with pagination info
    total_pages = (total + per_page - 1) // per_page
    embed.set_footer(text=f"Page {page + 1}/{total_pages} • Use buttons below to manage connections")
    
    return embed


def create_connection_details_embed(
    server_id: str,
    connection_name: str,
    connection_data: Dict[str, Any]
) -> discord.Embed:
    """
    Create detailed embed for a specific connection.
    
    Args:
        server_id: Server ID
        connection_name: Connection name
        connection_data: Connection data dictionary
    
    Returns:
        Discord embed with connection details
    """
    metadata = get_api_metadata()
    registry = get_registry()
    
    # Get provider info
    provider = connection_data.get("provider", "unknown").lower()
    try:
        provider_meta = registry.get_metadata(provider)
        provider_display = provider_meta.display_name
        provider_icon = provider_meta.icon
        color = getattr(discord.Color, provider_meta.color, discord.Color.blue)()
    except ValueError:
        provider_display = provider.upper()
        provider_icon = "🔵"
        color = discord.Color.blue()
    
    # Create embed
    embed = discord.Embed(
        title=f"🔌 {connection_name}",
        description=f"{provider_icon} **{provider_display}**",
        color=color
    )
    
    # Credentials section
    cred_text = f"• **Provider:** {provider_display}\n"
    cred_text += f"• **API Key:** `{metadata.format_value_for_display(connection_data.get('api_key'), 'api_key')}`\n"
    cred_text += f"• **Model:** `{connection_data.get('model', 'Unknown')}`"
    
    base_url = connection_data.get("base_url")
    if base_url:
        cred_text += f"\n• **Base URL:** `{base_url}`"
    
    embed.add_field(name="🔑 Credentials", value=cred_text, inline=False)
    
    # Generation parameters
    gen_text = f"• **Max Tokens:** `{connection_data.get('max_tokens', 1000)}`\n"
    gen_text += f"• **Temperature:** `{connection_data.get('temperature', 0.7)}`\n"
    gen_text += f"• **Top P:** `{connection_data.get('top_p', 1.0)}`\n"
    gen_text += f"• **Frequency Penalty:** `{connection_data.get('frequency_penalty', 0.0)}`\n"
    gen_text += f"• **Presence Penalty:** `{connection_data.get('presence_penalty', 0.0)}`\n"
    gen_text += f"• **Context Size:** `{connection_data.get('context_size', 16000)}` tokens"
    
    embed.add_field(name="⚙️ Generation", value=gen_text, inline=False)
    
    # Thinking parameters
    think_switch = connection_data.get('think_switch', True)
    think_depth = connection_data.get('think_depth', 3)
    hide_thinking = connection_data.get('hide_thinking_tags', True)
    save_thinking = connection_data.get('save_thinking_in_history', True)
    thinking_patterns = connection_data.get('thinking_tag_patterns', [])
    
    think_text = f"• **Enabled:** `{'✅' if think_switch else '❌'}`"
    if think_switch:
        think_text += f" (Depth: {think_depth})"
    think_text += f"\n• **Hide Tags:** `{'✅' if hide_thinking else '❌'}`"
    think_text += f"\n• **Save in History:** `{'✅' if save_thinking else '❌'}`"
    if thinking_patterns:
        think_text += f"\n• **Tag Patterns:** {len(thinking_patterns)} pattern(s)"
    
    embed.add_field(name="🧠 Thinking", value=think_text, inline=False)
    
    # Tools
    max_tool_rounds = connection_data.get('max_tool_rounds', 5)
    tools_text = f"• **Max Tool Rounds:** `{max_tool_rounds}`"
    
    embed.add_field(name="🔧 Tools", value=tools_text, inline=False)
    
    # Vision
    vision_enabled = connection_data.get('vision_enabled', False)
    vision_detail = connection_data.get('vision_detail', 'auto')
    max_image_size = connection_data.get('max_image_size', 20)
    
    vision_text = f"• **Enabled:** `{'✅' if vision_enabled else '❌'}`"
    if vision_enabled:
        vision_text += f"\n• **Detail Level:** `{vision_detail}`"
        vision_text += f"\n• **Max Image Size:** `{max_image_size} MB`"
    
    embed.add_field(name="🖼️ Vision", value=vision_text, inline=False)
    
    # Advanced
    custom_extra_body = connection_data.get('custom_extra_body')
    if custom_extra_body:
        import json
        extra_body_str = json.dumps(custom_extra_body, indent=2)
        if len(extra_body_str) > 200:
            extra_body_preview = extra_body_str[:200] + "..."
        else:
            extra_body_preview = extra_body_str
        
        adv_text = f"**Custom Extra Body:**\n```json\n{extra_body_preview}\n```"
        embed.add_field(name="🔬 Advanced", value=adv_text, inline=False)

    # Usage
    ais_using = func.get_ais_using_connection(server_id, connection_name)
    
    if ais_using:
        usage_text = f"**Used by {len(ais_using)} AI(s):**\n"
        for channel_id, ai_name in ais_using[:5]:
            usage_text += f"• `{ai_name}` in <#{channel_id}>\n"
        if len(ais_using) > 5:
            usage_text += f"• ... and {len(ais_using) - 5} more"
    else:
        usage_text = "Not currently used by any AI"
    
    embed.add_field(name="📊 Usage", value=usage_text, inline=False)
    
    # Metadata
    created_at = connection_data.get("created_at", "Unknown")
    created_by = connection_data.get("created_by")
    if created_by:
        embed.set_footer(text=f"Created by user ID {created_by} • {created_at}")
    else:
        embed.set_footer(text=f"Created at {created_at}")
    
    return embed

class APIConnectionListView(ui.View):
    """Main view for API connection management."""
    
    def __init__(self, server_id: str, guild_name: str, user_id: int, page: int = 0):
        super().__init__(timeout=300)
        self.server_id = server_id
        self.guild_name = guild_name
        self.user_id = user_id
        self.current_page = page
        self.per_page = 5
        
        # Calculate total pages
        connections = func.list_api_connections(server_id)
        total_connections = len(connections)
        self.total_pages = max(1, (total_connections + self.per_page - 1) // self.per_page)
        
        # Add action buttons (row 1)
        self.add_item(CreateConnectionButton())
        self.add_item(EditConnectionButton())
        self.add_item(RemoveConnectionButton())
        self.add_item(ViewDetailsButton())
        
        # Add pagination buttons (row 2) only if more than 1 page
        if self.total_pages > 1:
            self.first_btn = FirstPageButton()
            self.prev_btn = PreviousPageButton()
            self.counter_btn = PageCounterButton()
            self.next_btn = NextPageButton()
            self.last_btn = LastPageButton()
            
            self.add_item(self.first_btn)
            self.add_item(self.prev_btn)
            self.add_item(self.counter_btn)
            self.add_item(self.next_btn)
            self.add_item(self.last_btn)
            self._update_buttons()
    
    def _update_buttons(self):
        """Update pagination button states based on current page."""
        if self.total_pages <= 1:
            return
        
        # Update button states
        self.first_btn.disabled = (self.current_page == 0)
        self.prev_btn.disabled = (self.current_page == 0)
        self.next_btn.disabled = (self.current_page >= self.total_pages - 1)
        self.last_btn.disabled = (self.current_page >= self.total_pages - 1)
        self.counter_btn.label = f"Page {self.current_page + 1}/{self.total_pages}"
    
    async def _update_message(self, interaction: discord.Interaction):
        """Update the message with current page."""
        try:
            self._update_buttons()
            
            embed = create_connection_list_embed(
                server_id=self.server_id,
                guild_name=self.guild_name,
                page=self.current_page,
                per_page=self.per_page
            )
            
            await interaction.response.edit_message(
                embed=embed,
                view=self
            )
        except Exception as e:
            func.log.error(f"Error updating pagination: {e}")
            await interaction.response.send_message(
                f"❌ Error updating page: {str(e)}",
                ephemeral=True
            )


class FirstPageButton(ui.Button):
    """Button to go to first page."""
    
    def __init__(self):
        super().__init__(
            label="⏮️",
            style=discord.ButtonStyle.secondary,
            custom_id="api_first",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Go to first page."""
        self.view.current_page = 0
        await self.view._update_message(interaction)


class PreviousPageButton(ui.Button):
    """Button to go to previous page."""
    
    def __init__(self):
        super().__init__(
            label="◀️",
            style=discord.ButtonStyle.primary,
            custom_id="api_previous",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Go to previous page."""
        if self.view.current_page > 0:
            self.view.current_page -= 1
        await self.view._update_message(interaction)


class PageCounterButton(ui.Button):
    """Page counter display (non-interactive)."""
    
    def __init__(self):
        super().__init__(
            label="Page 1/1",
            style=discord.ButtonStyle.secondary,
            custom_id="api_counter",
            disabled=True,
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Non-interactive button."""
        pass


class NextPageButton(ui.Button):
    """Button to go to next page."""
    
    def __init__(self):
        super().__init__(
            label="▶️",
            style=discord.ButtonStyle.primary,
            custom_id="api_next",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Go to next page."""
        if self.view.current_page < self.view.total_pages - 1:
            self.view.current_page += 1
        await self.view._update_message(interaction)


class LastPageButton(ui.Button):
    """Button to go to last page."""
    
    def __init__(self):
        super().__init__(
            label="⏭️",
            style=discord.ButtonStyle.secondary,
            custom_id="api_last",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Go to last page."""
        self.view.current_page = self.view.total_pages - 1
        await self.view._update_message(interaction)


class CreateConnectionButton(ui.Button):
    """Button to create new API connection."""
    
    def __init__(self):
        super().__init__(
            label="Create New",
            style=discord.ButtonStyle.success,
            emoji="➕"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle create button click - show provider selection first."""
        server_id = str(interaction.guild.id)
        user_id = interaction.user.id
        
        # Show provider selection first (makes more sense)
        view = CreateConnectionProviderSelectView(
            server_id=server_id,
            user_id=user_id,
            create_data={}
        )
        
        embed = discord.Embed(
            title="➕ New Connection - Select Provider",
            description="First, select the API provider you want to use:",
            color=discord.Color.green()
        )
        
        await interaction.response.edit_message(
            embed=embed,
            view=view
        )


class CreateConnectionDetailsModal(ui.Modal):
    """Modal for connection details after provider selection."""
    
    def __init__(self, server_id: str, user_id: int, provider: str, provider_display: str):
        super().__init__(title=f"New {provider_display} Connection")
        
        self.server_id = server_id
        self.user_id = user_id
        self.provider = provider
        self.provider_display = provider_display
        
        # Connection name
        self.connection_name = ui.TextInput(
            label="Connection Name",
            placeholder="Unique name (e.g., my-openai-gpt4)",
            required=True,
            max_length=50,
            style=discord.TextStyle.short
        )
        self.add_item(self.connection_name)
        
        # Model
        self.model = ui.TextInput(
            label="Model",
            placeholder="e.g., gpt-4, deepseek-chat, claude-3-opus",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.model)
        
        # API Key
        self.api_key = ui.TextInput(
            label="API Key",
            placeholder="Your API key",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.api_key)
        
        # Base URL (optional)
        self.base_url = ui.TextInput(
            label="Base URL (Optional)",
            placeholder="Custom endpoint (leave empty for default)",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.base_url)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission - create connection with defaults."""
        try:
            # Validate inputs
            conn_name = self.connection_name.value.strip()
            model = self.model.value.strip()
            api_key = self.api_key.value.strip()
            
            if not conn_name:
                await interaction.response.send_message(
                    "❌ Connection name cannot be empty.",
                    ephemeral=True
                )
                return
            
            if not model:
                await interaction.response.send_message(
                    "❌ Model name is required.",
                    ephemeral=True
                )
                return
            
            # Check if connection already exists
            existing = func.get_api_connection(self.server_id, conn_name)
            if existing:
                await interaction.response.send_message(
                    f"❌ Connection '{conn_name}' already exists in this server.",
                    ephemeral=True
                )
                return
            
            # Create connection with sensible defaults
            success = await func.create_api_connection(
                server_id=self.server_id,
                connection_name=conn_name,
                provider=self.provider,
                api_key=api_key,
                model=model,
                base_url=self.base_url.value.strip() if self.base_url.value else None,
                max_tokens=1000,
                temperature=0.7,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                context_size=16000,
                think_switch=True,
                think_depth=3,
                hide_thinking_tags=True,
                thinking_tag_patterns=None,
                max_tool_rounds=5,
                custom_extra_body=None,
                save_thinking_in_history=True,
                vision_enabled=False,
                vision_detail="auto",
                max_image_size=20,
                created_by=str(interaction.user.id)
            )
            
            if not success:
                await interaction.response.send_message(
                    f"❌ Failed to create connection '{conn_name}'.",
                    ephemeral=True
                )
                return
            
            # Success - return to main view
            view = APIConnectionListView(
                server_id=self.server_id,
                guild_name=interaction.guild.name,
                user_id=self.user_id,
                page=0
            )
            
            embed = create_connection_list_embed(
                self.server_id,
                interaction.guild.name,
                page=0,
                per_page=5
            )
            
            # Send success message first
            await interaction.response.send_message(
                f"✅ **Connection Created!**\n"
                f"**Name:** `{conn_name}`\n"
                f"**Provider:** {self.provider_display}\n"
                f"**Model:** `{model}`\n\n"
                f"💡 Use `/setup` to create an AI with this connection!",
                ephemeral=True
            )
            
            func.log.info(f"Created API connection '{conn_name}' for provider '{self.provider}'")
        
        except Exception as e:
            func.log.error(f"Error creating connection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class CreateConnectionProviderSelectView(ui.View):
    """View for selecting provider."""
    
    def __init__(self, server_id: str, user_id: int, create_data: Dict[str, Any]):
        super().__init__(timeout=300)
        self.server_id = server_id
        self.user_id = user_id
        self.create_data = create_data
        
        # Add provider select
        self.add_item(ProviderSelect())
        
        # Add back button
        self.add_item(BackToMainButton(server_id, user_id))
    
    async def on_provider_selected(self, interaction: discord.Interaction, provider: str):
        """Handle provider selection - show connection details modal."""
        try:
            # Get provider display name
            registry = get_registry()
            provider_meta = registry.get_metadata(provider)
            
            # Show connection details modal
            modal = CreateConnectionDetailsModal(
                server_id=self.server_id,
                user_id=self.user_id,
                provider=provider,
                provider_display=provider_meta.display_name
            )
            
            await interaction.response.send_modal(modal)
        
        except Exception as e:
            func.log.error(f"Error in provider selection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class ProviderSelect(ui.Select):
    """Select menu for choosing provider."""
    
    def __init__(self):
        registry = get_registry()
        options = []
        
        for name, metadata in registry.get_all_metadata().items():
            # Don't use emoji parameter - some emojis are invalid in Discord SelectOption
            options.append(discord.SelectOption(
                label=f"{metadata.icon} {metadata.display_name}",
                value=name,
                description=f"{metadata.display_name} API"[:100]
            ))
        
        super().__init__(
            placeholder="Choose a provider...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle provider selection."""
        await self.view.on_provider_selected(interaction, self.values[0])


class CreateConnectionStep2Modal(ui.Modal):
    """Step 2: Model & Basic Parameters."""
    
    def __init__(self, server_id: str, user_id: int, create_data: Dict[str, Any]):
        super().__init__(title="New Connection - Step 2/3")
        
        self.server_id = server_id
        self.user_id = user_id
        self.create_data = create_data
        
        # Model
        self.model = ui.TextInput(
            label="Model",
            placeholder="e.g., gpt-4, deepseek-chat, claude-3-opus",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.model)
        
        # Max Tokens
        self.max_tokens = ui.TextInput(
            label="Max Tokens",
            placeholder="Default: 1000",
            default="1000",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.max_tokens)
        
        # Temperature
        self.temperature = ui.TextInput(
            label="Temperature (0.0-2.0)",
            placeholder="Default: 0.7",
            default="0.7",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.temperature)
        
        # Context Size
        self.context_size = ui.TextInput(
            label="Context Size",
            placeholder="Default: 16000",
            default="16000",
            required=False,
            style=discord.TextStyle.short
        )
        self.add_item(self.context_size)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle Step 2 submission - show Step 3 options."""
        try:
            # Validate and parse values
            model = self.model.value.strip()
            if not model:
                await interaction.response.send_message(
                    "❌ Model name is required.",
                    ephemeral=True
                )
                return
            
            try:
                max_tokens = int(self.max_tokens.value) if self.max_tokens.value else 1000
                temperature = float(self.temperature.value) if self.temperature.value else 0.7
                context_size = int(self.context_size.value) if self.context_size.value else 16000
            except ValueError as e:
                await interaction.response.send_message(
                    f"❌ Invalid number format: {e}",
                    ephemeral=True
                )
                return
            
            # Validate ranges
            if temperature < 0.0 or temperature > 2.0:
                await interaction.response.send_message(
                    "❌ Temperature must be between 0.0 and 2.0.",
                    ephemeral=True
                )
                return
            
            if max_tokens < 1:
                await interaction.response.send_message(
                    "❌ Max tokens must be at least 1.",
                    ephemeral=True
                )
                return
            
            if context_size < 1:
                await interaction.response.send_message(
                    "❌ Context size must be at least 1.",
                    ephemeral=True
                )
                return
            
            # Store data
            self.create_data.update({
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "context_size": context_size
            })
            
            # Show Step 3: Advanced options
            view = CreateConnectionStep3View(
                server_id=self.server_id,
                user_id=self.user_id,
                create_data=self.create_data
            )
            
            registry = get_registry()
            provider_meta = registry.get_metadata(self.create_data["provider"])
            
            embed = discord.Embed(
                title="➕ New Connection - Step 3/3 (Optional)",
                description=f"**Connection:** `{self.create_data['connection_name']}`\n"
                           f"**Provider:** {provider_meta.display_name}\n"
                           f"**Model:** `{model}`\n\n"
                           "Configure advanced parameters (optional) or finish creation:",
                color=discord.Color.green()
            )
            
            await interaction.response.edit_message(
                embed=embed,
                view=view
            )
        
        except Exception as e:
            func.log.error(f"Error in create step 2: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class CreateConnectionStep3View(ui.View):
    """Step 3: Advanced Parameters (Optional)."""
    
    def __init__(self, server_id: str, user_id: int, create_data: Dict[str, Any]):
        super().__init__(timeout=300)
        self.server_id = server_id
        self.user_id = user_id
        self.create_data = create_data
        
        # Add finish button (primary action)
        self.add_item(FinishCreateButton(server_id, user_id, create_data))
        
        # Add cancel button
        self.add_item(CancelCreateButton(server_id, user_id))


class FinishCreateButton(ui.Button):
    """Button to finish creation with current settings."""
    
    def __init__(self, server_id: str, user_id: int, create_data: Dict[str, Any]):
        super().__init__(
            label="✅ Create Connection",
            style=discord.ButtonStyle.success
        )
        self.server_id = server_id
        self.user_id = user_id
        self.create_data = create_data
    
    async def callback(self, interaction: discord.Interaction):
        """Create the connection."""
        try:
            # Set defaults for optional parameters
            defaults = {
                "top_p": 1.0,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
                "think_switch": True,
                "think_depth": 3,
                "hide_thinking_tags": True,
                "thinking_tag_patterns": None,  # Will use defaults
                "max_tool_rounds": 5,
                "custom_extra_body": None,
                "save_thinking_in_history": True,
                "vision_enabled": False,
                "vision_detail": "auto",
                "max_image_size": 20,
                "created_by": str(interaction.user.id)
            }
            
            # Merge with provided data
            final_data = {**defaults, **self.create_data}
            
            # Create connection
            success = await func.create_api_connection(
                server_id=self.server_id,
                **final_data
            )
            
            if not success:
                await interaction.response.send_message(
                    f"❌ Failed to create connection '{final_data['connection_name']}'.",
                    ephemeral=True
                )
                return
            
            # Success message
            registry = get_registry()
            provider_meta = registry.get_metadata(final_data["provider"])
            
            success_msg = f"✅ **API Connection Created Successfully!**\n\n"
            success_msg += f"**Connection Name:** `{final_data['connection_name']}`\n"
            success_msg += f"**Provider:** {provider_meta.display_name}\n"
            success_msg += f"**Model:** `{final_data['model']}`\n"
            success_msg += f"**Max Tokens:** `{final_data['max_tokens']}`\n"
            success_msg += f"**Temperature:** `{final_data['temperature']}`\n"
            success_msg += f"**Context Size:** `{final_data['context_size']}`\n\n"
            success_msg += "💡 **Next Step:** Use `/setup` to create an AI with this connection!"
            
            await interaction.response.send_message(
                success_msg,
                ephemeral=True
            )
            
            # Return to main view
            view = APIConnectionListView(
                server_id=self.server_id,
                guild_name=interaction.guild.name,
                user_id=self.user_id,
                page=0
            )
            
            embed = create_connection_list_embed(
                self.server_id,
                interaction.guild.name,
                page=0,
                per_page=5
            )
            
            await interaction.message.edit(
                embed=embed,
                view=view
            )
        
        except Exception as e:
            func.log.error(f"Error creating connection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class CancelCreateButton(ui.Button):
    """Button to cancel creation."""
    
    def __init__(self, server_id: str, user_id: int):
        super().__init__(
            label="← Cancel",
            style=discord.ButtonStyle.secondary
        )
        self.server_id = server_id
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        """Cancel and return to main view."""
        view = APIConnectionListView(
            server_id=self.server_id,
            guild_name=interaction.guild.name,
            user_id=self.user_id,
            page=0
        )
        
        embed = create_connection_list_embed(
            self.server_id,
            interaction.guild.name,
            page=0,
            per_page=5
        )
        
        await interaction.response.edit_message(
            embed=embed,
            view=view
        )


class EditConnectionButton(ui.Button):
    """Button to edit existing connection."""
    
    def __init__(self):
        super().__init__(
            label="Edit",
            style=discord.ButtonStyle.primary,
            emoji="✏️"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle edit button click."""
        server_id = str(interaction.guild.id)
        connections = func.list_api_connections(server_id)
        
        if not connections:
            await interaction.response.send_message(
                "❌ No API connections found in this server.",
                ephemeral=True
            )
            return
        
        # Show connection selection
        view = EditConnectionSelectView(
            server_id=server_id,
            user_id=interaction.user.id
        )
        
        embed = discord.Embed(
            title="✏️ Edit API Connection",
            description="Select a connection to edit its parameters:",
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(
            embed=embed,
            view=view
        )


class EditConnectionSelectView(ui.View):
    """View for selecting connection to edit."""
    
    def __init__(self, server_id: str, user_id: int):
        super().__init__(timeout=180)
        self.server_id = server_id
        self.user_id = user_id
        
        # Add connection select
        self.add_item(ConnectionSelect(
            server_id=server_id,
            placeholder="Choose a connection to edit...",
            callback_name="edit"
        ))
        
        # Add back button
        self.add_item(BackToMainButton(server_id, user_id))
    
    async def on_connection_selected(self, interaction: discord.Interaction, connection_name: str):
        """Handle connection selection - show category selection."""
        try:
            connection = func.get_api_connection(self.server_id, connection_name)
            
            if not connection:
                await interaction.response.send_message(
                    f"❌ Connection '{connection_name}' not found.",
                    ephemeral=True
                )
                return
            
            # Show category selection
            view = EditCategorySelectView(
                server_id=self.server_id,
                connection_name=connection_name,
                connection_data=connection,
                user_id=self.user_id
            )
            
            embed = discord.Embed(
                title=f"✏️ Edit: {connection_name}",
                description="Select a category to edit:",
                color=discord.Color.blue()
            )
            
            # Add category info
            metadata = get_api_metadata()
            for category in get_all_categories():
                params = get_category_params(category)
                emoji = get_category_emoji(category)
                embed.add_field(
                    name=f"{emoji} {category}",
                    value=f"{len(params)} parameter(s)",
                    inline=True
                )
            
            await interaction.response.edit_message(
                embed=embed,
                view=view
            )
        
        except Exception as e:
            func.log.error(f"Error in edit connection selection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class EditCategorySelectView(ui.View):
    """View for selecting parameter category to edit."""
    
    def __init__(
        self,
        server_id: str,
        connection_name: str,
        connection_data: Dict[str, Any],
        user_id: int
    ):
        super().__init__(timeout=180)
        self.server_id = server_id
        self.connection_name = connection_name
        self.connection_data = connection_data
        self.user_id = user_id
        
        # Add category select
        self.add_item(CategorySelect())
        
        # Add back button
        self.add_item(BackToConnectionListButton(server_id, user_id))
    
    async def on_category_selected(self, interaction: discord.Interaction, category: str):
        """Handle category selection - show parameter selection."""
        try:
            params = get_category_params(category)
            
            if not params:
                await interaction.response.send_message(
                    f"❌ No parameters in category '{category}'",
                    ephemeral=True
                )
                return
            
            # Show parameter selection
            view = EditParameterSelectView(
                server_id=self.server_id,
                connection_name=self.connection_name,
                connection_data=self.connection_data,
                category=category,
                params=params,
                user_id=self.user_id
            )
            
            # Create embed showing current values
            metadata = get_api_metadata()
            emoji = get_category_emoji(category)
            
            embed = discord.Embed(
                title=f"{emoji} {self.connection_name} - {category}",
                description=f"Current values for {len(params)} parameter(s):",
                color=discord.Color.blue()
            )
            
            # Add each parameter as a field
            for param in params:
                current_value = self.connection_data.get(param)
                formatted_value = metadata.format_value_for_display(current_value, param)
                label = metadata.get_label(param)
                
                embed.add_field(
                    name=f"**{label}**",
                    value=f"`{formatted_value}`",
                    inline=True
                )
            
            embed.set_footer(text="Select a parameter below to edit")
            
            await interaction.response.edit_message(
                embed=embed,
                view=view
            )
        
        except Exception as e:
            func.log.error(f"Error in category selection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class CategorySelect(ui.Select):
    """Select menu for choosing parameter category."""
    
    def __init__(self):
        options = []
        
        for category in get_all_categories():
            params = get_category_params(category)
            emoji = get_category_emoji(category)
            
            options.append(discord.SelectOption(
                label=category[:100],
                description=f"{len(params)} parameter(s)"[:100],
                value=category,
                emoji=emoji
            ))
        
        super().__init__(
            placeholder="Choose a category...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle category selection."""
        await self.view.on_category_selected(interaction, self.values[0])


class EditParameterSelectView(ui.View):
    """View for selecting specific parameter to edit."""
    
    def __init__(
        self,
        server_id: str,
        connection_name: str,
        connection_data: Dict[str, Any],
        category: str,
        params: List[str],
        user_id: int
    ):
        super().__init__(timeout=180)
        self.server_id = server_id
        self.connection_name = connection_name
        self.connection_data = connection_data
        self.category = category
        self.params = params
        self.user_id = user_id
        
        # Add parameter select
        self.add_item(ParameterSelect(params, connection_data))
        
        # Add back button
        self.add_item(BackToCategoryButton(
            server_id, connection_name, connection_data, user_id
        ))
    
    async def on_parameter_selected(self, interaction: discord.Interaction, param: str):
        """Handle parameter selection - show edit modal or select."""
        try:
            metadata = get_api_metadata()
            current_value = self.connection_data.get(param)
            param_type = metadata.get_param_type(param, current_value)
            
            # Check if this is a choice parameter
            if metadata.is_choice_param(param):
                # Use Select menu for choice parameters
                choices = metadata.get_choices(param)
                
                # Check if choices are boolean
                is_boolean = all(isinstance(c, bool) for c in choices)
                
                # Format current value for display
                if is_boolean:
                    current_display = "✅ Enabled" if current_value else "❌ Disabled"
                else:
                    current_display = str(current_value)
                
                # Create embed
                emoji = get_category_emoji(self.category)
                label = metadata.get_label(param)
                description = metadata.get_description(param)
                
                embed = discord.Embed(
                    title=f"{emoji} {self.connection_name} - {label}",
                    description=f"**Current value:** `{current_display}`\n\n{description}\n\nSelect a new value:",
                    color=discord.Color.blue()
                )
                
                # Create view with choice select
                view = EditParameterChoiceView(
                    server_id=self.server_id,
                    connection_name=self.connection_name,
                    connection_data=self.connection_data,
                    category=self.category,
                    param=param,
                    params=self.params,
                    choices=choices,
                    current_value=current_value,
                    user_id=self.user_id
                )
                
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                # Use Modal for other parameters
                modal = EditParameterModal(
                    server_id=self.server_id,
                    connection_name=self.connection_name,
                    connection_data=self.connection_data,
                    category=self.category,
                    param=param,
                    params=self.params,
                    current_value=current_value,
                    param_type=param_type,
                    user_id=self.user_id
                )
                
                await interaction.response.send_modal(modal)
        
        except Exception as e:
            func.log.error(f"Error opening parameter editor: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class ParameterSelect(ui.Select):
    """Select menu for choosing specific parameter."""
    
    def __init__(self, params: List[str], connection_data: Dict[str, Any]):
        metadata = get_api_metadata()
        options = []
        
        for param in params[:25]:  # Discord limit
            current_value = connection_data.get(param)
            formatted_value = metadata.format_value_for_display(current_value, param)
            label = metadata.get_label(param)
            
            options.append(discord.SelectOption(
                label=label[:100],
                description=f"Current: {formatted_value}"[:100],
                value=param
            ))
        
        super().__init__(
            placeholder="Choose a parameter to edit...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle parameter selection."""
        await self.view.on_parameter_selected(interaction, self.values[0])


class BackToConnectionListButton(ui.Button):
    """Button to go back to connection list for editing."""
    
    def __init__(self, server_id: str, user_id: int):
        super().__init__(
            label="← Back",
            style=discord.ButtonStyle.secondary
        )
        self.server_id = server_id
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        """Go back to connection selection."""
        view = EditConnectionSelectView(
            server_id=self.server_id,
            user_id=self.user_id
        )
        
        embed = discord.Embed(
            title="✏️ Edit API Connection",
            description="Select a connection to edit its parameters:",
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(
            embed=embed,
            view=view
        )


class BackToCategoryButton(ui.Button):
    """Button to go back to category selection."""
    
    def __init__(
        self,
        server_id: str,
        connection_name: str,
        connection_data: Dict[str, Any],
        user_id: int
    ):
        super().__init__(
            label="← Back",
            style=discord.ButtonStyle.secondary
        )
        self.server_id = server_id
        self.connection_name = connection_name
        self.connection_data = connection_data
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        """Go back to category selection."""
        view = EditCategorySelectView(
            server_id=self.server_id,
            connection_name=self.connection_name,
            connection_data=self.connection_data,
            user_id=self.user_id
        )
        
        embed = discord.Embed(
            title=f"✏️ Edit: {self.connection_name}",
            description="Select a category to edit:",
            color=discord.Color.blue()
        )
        
        # Add category info
        for category in get_all_categories():
            params = get_category_params(category)
            emoji = get_category_emoji(category)
            embed.add_field(
                name=f"{emoji} {category}",
                value=f"{len(params)} parameter(s)",
                inline=True
            )
        
        await interaction.response.edit_message(
            embed=embed,
            view=view
        )


class RemoveConnectionButton(ui.Button):
    """Button to remove connection."""
    
    def __init__(self):
        super().__init__(
            label="Remove",
            style=discord.ButtonStyle.danger,
            emoji="🗑️"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle remove button click."""
        server_id = str(interaction.guild.id)
        connections = func.list_api_connections(server_id)
        
        if not connections:
            await interaction.response.send_message(
                "❌ No API connections found in this server.",
                ephemeral=True
            )
            return
        
        # Show connection selection
        view = RemoveConnectionSelectView(
            server_id=server_id,
            user_id=interaction.user.id
        )
        
        embed = discord.Embed(
            title="🗑️ Remove API Connection",
            description="⚠️ **Warning:** Removing a connection may break AIs that use it.\n\n"
                       "Select a connection to remove:",
            color=discord.Color.red()
        )
        
        await interaction.response.edit_message(
            embed=embed,
            view=view
        )


class RemoveConnectionSelectView(ui.View):
    """View for selecting connection to remove."""
    
    def __init__(self, server_id: str, user_id: int):
        super().__init__(timeout=180)
        self.server_id = server_id
        self.user_id = user_id
        
        # Add connection select
        self.add_item(ConnectionSelect(
            server_id=server_id,
            placeholder="Choose a connection to remove...",
            callback_name="remove"
        ))
        
        # Add back button
        self.add_item(BackToMainButton(server_id, user_id))
    
    async def on_connection_selected(self, interaction: discord.Interaction, connection_name: str):
        """Handle connection selection - show confirmation."""
        try:
            connection = func.get_api_connection(self.server_id, connection_name)
            
            if not connection:
                await interaction.response.send_message(
                    f"❌ Connection '{connection_name}' not found.",
                    ephemeral=True
                )
                return
            
            # Check if any AIs are using this connection
            ais_using = func.get_ais_using_connection(self.server_id, connection_name)
            
            # Create confirmation embed
            embed = discord.Embed(
                title="⚠️ Confirm Removal",
                description=f"**Connection:** `{connection_name}`\n"
                           f"**Provider:** {connection.get('provider', 'Unknown').upper()}\n"
                           f"**Model:** `{connection.get('model', 'Unknown')}`",
                color=discord.Color.red()
            )
            
            if ais_using:
                warning_text = f"❌ **This connection is being used by {len(ais_using)} AI(s):**\n"
                for channel_id, ai_name in ais_using[:10]:
                    warning_text += f"• `{ai_name}` in <#{channel_id}>\n"
                if len(ais_using) > 10:
                    warning_text += f"• ... and {len(ais_using) - 10} more\n"
                warning_text += "\n⚠️ **Removing this connection will break these AIs!**"
                
                embed.add_field(
                    name="⚠️ Warning",
                    value=warning_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="✅ Safe to Remove",
                    value="This connection is not currently used by any AI.",
                    inline=False
                )
            
            embed.add_field(
                name="❓ Are you sure?",
                value="This action cannot be undone.",
                inline=False
            )
            
            # Create confirmation view
            view = RemoveConfirmView(
                server_id=self.server_id,
                connection_name=connection_name,
                user_id=self.user_id
            )
            
            await interaction.response.edit_message(
                embed=embed,
                view=view
            )
        
        except Exception as e:
            func.log.error(f"Error in remove selection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class RemoveConfirmView(ui.View):
    """View for confirming connection removal."""
    
    def __init__(self, server_id: str, connection_name: str, user_id: int):
        super().__init__(timeout=180)
        self.server_id = server_id
        self.connection_name = connection_name
        self.user_id = user_id
        
        # Add confirm and cancel buttons
        self.add_item(ConfirmRemoveButton(server_id, connection_name, user_id))
        self.add_item(CancelRemoveButton(server_id, user_id))


class ConfirmRemoveButton(ui.Button):
    """Button to confirm removal."""
    
    def __init__(self, server_id: str, connection_name: str, user_id: int):
        super().__init__(
            label="🗑️ Remove Anyway",
            style=discord.ButtonStyle.danger
        )
        self.server_id = server_id
        self.connection_name = connection_name
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        """Execute removal."""
        try:
            # Get AIs using this connection before removal
            ais_using = func.get_ais_using_connection(self.server_id, self.connection_name)
            
            # Remove the connection
            success = await func.delete_api_connection(self.server_id, self.connection_name)
            
            if not success:
                await interaction.response.send_message(
                    f"❌ Failed to remove connection '{self.connection_name}'.",
                    ephemeral=True
                )
                return
            
            # Return to main view first
            view = APIConnectionListView(
                server_id=self.server_id,
                guild_name=interaction.guild.name,
                user_id=self.user_id,
                page=0
            )
            
            embed = create_connection_list_embed(
                self.server_id,
                interaction.guild.name,
                page=0,
                per_page=5
            )
            
            await interaction.response.edit_message(
                embed=embed,
                view=view
            )
            
            # Then send success message as followup
            success_msg = f"✅ **Connection Removed Successfully!**\n\n"
            success_msg += f"**Connection Name:** `{self.connection_name}`\n"
            
            if ais_using:
                success_msg += f"\n⚠️ **Warning:** {len(ais_using)} AI(s) were using this connection:\n"
                for channel_id, ai_name in ais_using[:5]:
                    success_msg += f"• `{ai_name}` in <#{channel_id}>\n"
                if len(ais_using) > 5:
                    success_msg += f"• ... and {len(ais_using) - 5} more\n"
                success_msg += "\n💡 Reconfigure these AIs with `/setup` using a different connection."
            
            await interaction.followup.send(
                success_msg,
                ephemeral=True
            )
        
        except Exception as e:
            func.log.error(f"Error removing connection: {e}\n{traceback.format_exc()}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ Error: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Error: {str(e)}",
                    ephemeral=True
                )


class CancelRemoveButton(ui.Button):
    """Button to cancel removal."""
    
    def __init__(self, server_id: str, user_id: int):
        super().__init__(
            label="← Cancel",
            style=discord.ButtonStyle.secondary
        )
        self.server_id = server_id
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        """Cancel and return to main view."""
        view = APIConnectionListView(
            server_id=self.server_id,
            guild_name=interaction.guild.name,
            user_id=self.user_id,
            page=0
        )
        
        embed = create_connection_list_embed(
            self.server_id,
            interaction.guild.name,
            page=0,
            per_page=5
        )
        
        await interaction.response.edit_message(
            embed=embed,
            view=view
        )


class ViewDetailsButton(ui.Button):
    """Button to view connection details."""
    
    def __init__(self):
        super().__init__(
            label="View Details",
            style=discord.ButtonStyle.secondary,
            emoji="👁️"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle view details button click."""
        server_id = str(interaction.guild.id)
        connections = func.list_api_connections(server_id)
        
        if not connections:
            await interaction.response.send_message(
                "❌ No API connections found in this server.",
                ephemeral=True
            )
            return
        
        # Show connection selection
        view = ViewDetailsSelectView(
            server_id=server_id,
            user_id=interaction.user.id
        )
        
        embed = discord.Embed(
            title="👁️ View Connection Details",
            description="Select a connection to view its detailed configuration:",
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(
            embed=embed,
            view=view
        )


class ViewDetailsSelectView(ui.View):
    """View for selecting connection to view details."""
    
    def __init__(self, server_id: str, user_id: int):
        super().__init__(timeout=180)
        self.server_id = server_id
        self.user_id = user_id
        
        # Add connection select
        self.add_item(ConnectionSelect(
            server_id=server_id,
            placeholder="Choose a connection to view...",
            callback_name="view_details"
        ))
        
        # Add back button
        self.add_item(BackToMainButton(server_id, user_id))
    
    async def on_connection_selected(self, interaction: discord.Interaction, connection_name: str):
        """Handle connection selection."""
        try:
            connection = func.get_api_connection(self.server_id, connection_name)
            
            if not connection:
                await interaction.response.send_message(
                    f"❌ Connection '{connection_name}' not found.",
                    ephemeral=True
                )
                return
            
            # Create details embed
            embed = create_connection_details_embed(
                self.server_id,
                connection_name,
                connection
            )
            
            # Create view with action buttons
            view = ConnectionDetailsView(
                server_id=self.server_id,
                connection_name=connection_name,
                user_id=self.user_id
            )
            
            await interaction.response.edit_message(
                embed=embed,
                view=view
            )
        
        except Exception as e:
            func.log.error(f"Error viewing connection details: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class ConnectionDetailsView(ui.View):
    """View shown when displaying connection details."""
    
    def __init__(self, server_id: str, connection_name: str, user_id: int):
        super().__init__(timeout=180)
        self.server_id = server_id
        self.connection_name = connection_name
        self.user_id = user_id
        
        # Add action buttons
        self.add_item(BackToMainButton(server_id, user_id))


class ConnectionSelect(ui.Select):
    """Reusable select menu for choosing a connection."""
    
    def __init__(
        self,
        server_id: str,
        placeholder: str = "Choose a connection...",
        callback_name: str = "generic"
    ):
        self.server_id = server_id
        self.callback_name = callback_name
        
        # Get connections
        connections = func.list_api_connections(server_id)
        registry = get_registry()
        
        options = []
        for conn_name, conn_data in sorted(connections.items())[:25]:  # Discord limit
            provider = conn_data.get("provider", "unknown").lower()
            model = conn_data.get("model", "Unknown")
            
            # Get provider metadata
            try:
                provider_meta = registry.get_metadata(provider)
                provider_display = provider_meta.display_name
                provider_icon = provider_meta.icon
            except ValueError:
                provider_display = provider.upper()
                provider_icon = "🔵"
            
            # Get usage info
            ais_using = func.get_ais_using_connection(server_id, conn_name)
            usage_count = len(ais_using)
            
            if usage_count > 0:
                description = f"{provider_icon} {provider_display} • {model} • {usage_count} AI(s) using"
            else:
                description = f"{provider_icon} {provider_display} • {model} • Available"
            
            options.append(discord.SelectOption(
                label=conn_name[:100],
                value=conn_name,
                description=description[:100]
            ))
        
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle connection selection."""
        connection_name = self.values[0]
        
        # Route to appropriate handler based on callback_name
        if self.callback_name == "view_details":
            await self.view.on_connection_selected(interaction, connection_name)
        elif self.callback_name == "edit":
            await self.view.on_connection_selected(interaction, connection_name)
        elif self.callback_name == "remove":
            await self.view.on_connection_selected(interaction, connection_name)


class BackToMainButton(ui.Button):
    """Button to go back to main connection list."""
    
    def __init__(self, server_id: str, user_id: int):
        super().__init__(
            label="← Back",
            style=discord.ButtonStyle.secondary
        )
        self.server_id = server_id
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        """Go back to main list."""
        # Recreate main view
        view = APIConnectionListView(
            server_id=self.server_id,
            guild_name=interaction.guild.name,
            user_id=self.user_id,
            page=0
        )
        
        embed = create_connection_list_embed(
            self.server_id,
            interaction.guild.name,
            page=0,
            per_page=5
        )
        
        await interaction.response.edit_message(
            embed=embed,
            view=view
        )


class EditParameterModal(ui.Modal):
    """Modal for editing a parameter value."""
    
    def __init__(
        self,
        server_id: str,
        connection_name: str,
        connection_data: Dict[str, Any],
        category: str,
        param: str,
        params: List[str],
        current_value: Any,
        param_type: str,
        user_id: int
    ):
        # Use short name for title
        metadata = get_api_metadata()
        label = metadata.get_label(param)
        super().__init__(title=f"Edit: {label}"[:45])  # Discord limit
        
        self.server_id = server_id
        self.connection_name = connection_name
        self.connection_data = connection_data
        self.category = category
        self.param = param
        self.params = params
        self.param_type = param_type
        self.user_id = user_id
        self.metadata = metadata
        
        # Add text input
        self.value_input = metadata.get_modal_component(
            param,
            current_value,
            param_type
        )
        self.add_item(self.value_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            # Get input value
            input_value = self.value_input.value
            
            # Parse value
            parsed_value = self.metadata.parse_value_from_input(input_value, self.param_type)
            
            # Validate
            is_valid, error_msg = self.metadata.validate_value(
                self.param,
                parsed_value,
                self.param_type
            )
            
            if not is_valid:
                await interaction.response.send_message(
                    f"❌ Validation error: {error_msg}",
                    ephemeral=True
                )
                return
            
            # Update connection
            success = await func.update_api_connection(
                self.server_id,
                self.connection_name,
                **{self.param: parsed_value}
            )
            
            if not success:
                await interaction.response.send_message(
                    f"❌ Failed to update connection '{self.connection_name}'.",
                    ephemeral=True
                )
                return
            
            # Update local data
            self.connection_data[self.param] = parsed_value
            
            # Send confirmation message
            label = self.metadata.get_label(self.param)
            formatted_value = self.metadata.format_value_for_display(parsed_value, self.param)
            await interaction.response.send_message(
                f"✅ **Updated {label}**\nNew value: `{formatted_value}`",
                ephemeral=True
            )
            
            func.log.info(f"Updated connection '{self.connection_name}' parameter '{self.param}' = {parsed_value}")
        
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Invalid value: {str(e)}",
                ephemeral=True
            )
        except Exception as e:
            func.log.error(f"Error saving parameter: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error saving: {str(e)}",
                ephemeral=True
            )


class EditParameterChoiceView(ui.View):
    """View for editing parameter with predefined choices."""
    
    def __init__(
        self,
        server_id: str,
        connection_name: str,
        connection_data: Dict[str, Any],
        category: str,
        param: str,
        params: List[str],
        choices: List[Any],
        current_value: Any,
        user_id: int
    ):
        super().__init__(timeout=180)
        self.server_id = server_id
        self.connection_name = connection_name
        self.connection_data = connection_data
        self.category = category
        self.param = param
        self.params = params
        self.user_id = user_id
        self.metadata = get_api_metadata()
        
        # Add choice select
        self.add_item(ParameterChoiceSelect(param, choices, current_value))
        
        # Add back button
        self.add_item(BackToParameterListButton(
            server_id, connection_name, connection_data, category, params, user_id
        ))
    
    async def on_choice_selected(self, interaction: discord.Interaction, choice: str):
        """Handle choice selection and save."""
        try:
            # Get the actual choices to determine type
            choices = self.metadata.get_choices(self.param)
            is_boolean = all(isinstance(c, bool) for c in choices)
            
            # Convert value to correct type
            if is_boolean:
                # Convert string back to boolean
                value = choice.lower() == "true"
                display_value = "✅ Enabled" if value else "❌ Disabled"
            else:
                # Keep as string
                value = choice
                display_value = choice
            
            # Update connection
            success = await func.update_api_connection(
                self.server_id,
                self.connection_name,
                **{self.param: value}
            )
            
            if not success:
                await interaction.response.send_message(
                    f"❌ Failed to update connection '{self.connection_name}'.",
                    ephemeral=True
                )
                return
            
            # Update local data
            self.connection_data[self.param] = value
            
            # Send confirmation message
            label = self.metadata.get_label(self.param)
            await interaction.response.send_message(
                f"✅ **Updated {label}**\nNew value: `{display_value}`",
                ephemeral=True
            )
            
            func.log.info(f"Updated connection '{self.connection_name}' parameter '{self.param}' = {value}")
        
        except Exception as e:
            func.log.error(f"Error saving choice: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error saving: {str(e)}",
                ephemeral=True
            )


class ParameterChoiceSelect(ui.Select):
    """Select menu for choosing from predefined parameter values."""
    
    def __init__(self, param: str, choices: List[Any], current_value: Any):
        """Initialize choice select menu."""
        options = []
        
        # Check if choices are boolean
        is_boolean = all(isinstance(c, bool) for c in choices)
        
        for choice in choices:
            # Special handling for provider parameter
            if param == "provider":
                from AI.provider_registry import get_registry
                registry = get_registry()
                try:
                    provider_meta = registry.get_metadata(str(choice))
                    label = f"{provider_meta.icon} {provider_meta.display_name}"
                    value = str(choice)
                    # Use the provider's own description if available
                    description = provider_meta.description if provider_meta.description else f"{provider_meta.display_name} API"
                    is_default = (choice == current_value)
                except ValueError:
                    # Fallback if provider not found in registry
                    label = str(choice).upper()
                    value = str(choice)
                    description = f"Provider: {choice}"
                    is_default = (choice == current_value)
            elif is_boolean:
                # Display booleans as Enabled/Disabled
                label = "✅ Enabled" if choice else "❌ Disabled"
                value = "true" if choice else "false"  # Discord requires string values
                description = "Enable this feature" if choice else "Disable this feature"
                is_default = (choice == current_value)
            else:
                # Display string choices normally
                label = str(choice).replace('_', ' ').title()
                value = str(choice)
                description = f"Set to: {choice}"
                is_default = (choice == current_value)
            
            options.append(discord.SelectOption(
                label=label[:100],  # Discord limit
                value=value,
                default=is_default,
                description=description[:100]
            ))
        
        super().__init__(
            placeholder="Choose a value...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle choice selection."""
        await self.view.on_choice_selected(interaction, self.values[0])


class BackToParameterListButton(ui.Button):
    """Button to go back to parameter list."""
    
    def __init__(
        self,
        server_id: str,
        connection_name: str,
        connection_data: Dict[str, Any],
        category: str,
        params: List[str],
        user_id: int
    ):
        super().__init__(
            label="← Back",
            style=discord.ButtonStyle.secondary
        )
        self.server_id = server_id
        self.connection_name = connection_name
        self.connection_data = connection_data
        self.category = category
        self.params = params
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        """Go back to parameter list."""
        try:
            # Refresh connection data
            connection = func.get_api_connection(self.server_id, self.connection_name)
            if connection:
                self.connection_data = connection
            
            # Show parameter selection
            view = EditParameterSelectView(
                server_id=self.server_id,
                connection_name=self.connection_name,
                connection_data=self.connection_data,
                category=self.category,
                params=self.params,
                user_id=self.user_id
            )
            
            # Create embed showing current values
            metadata = get_api_metadata()
            emoji = get_category_emoji(self.category)
            
            embed = discord.Embed(
                title=f"{emoji} {self.connection_name} - {self.category}",
                description=f"Current values for {len(self.params)} parameter(s):",
                color=discord.Color.blue()
            )
            
            # Add each parameter as a field
            for param in self.params:
                current_value = self.connection_data.get(param)
                formatted_value = metadata.format_value_for_display(current_value, param)
                label = metadata.get_label(param)
                
                embed.add_field(
                    name=f"**{label}**",
                    value=f"`{formatted_value}`",
                    inline=True
                )
            
            embed.set_footer(text="Select a parameter below to edit")
            
            await interaction.response.edit_message(
                embed=embed,
                view=view
            )
        
        except Exception as e:
            func.log.error(f"Error going back to parameter list: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
