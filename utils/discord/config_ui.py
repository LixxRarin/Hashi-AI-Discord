"""
Config UI Components - Simplified Interactive UI

Simplified UI with fixed categories.
No complex hierarchical navigation - just category → config → edit.
"""

import discord
from discord import ui
from typing import Any, Dict, List, Optional
import traceback

import utils.func as func
from utils.config.parser import get_config_parser
from utils.config.metadata import (
    get_config_metadata,
    get_all_categories,
    get_category_configs,
    get_category_emoji,
    CONFIG_CATEGORIES
)
from utils.discord.embed_builder import EmbedBuilder
from utils.discord.embed_constants import EmbedStyle, EmbedEmojis


def create_category_selection_embed(ai_name: str) -> discord.Embed:
    """
    Create standardized category selection embed.
    
    This ensures consistency between initial command display and back button.
    """
    categories = get_all_categories()
    
    builder = (
        EmbedBuilder(EmbedStyle.INFO)
        .set_title(f"Configure: {ai_name}", emoji=EmbedEmojis.SETTINGS)
        .set_description("Choose a category to configure:")
    )
    
    # Add category info
    category_info = []
    for category in categories[:10]:  # Show first 10
        config_count = len(get_category_configs(category))
        emoji = get_category_emoji(category)
        category_info.append(f"{emoji} **{category}** - {config_count} configs")
    
    if len(categories) > 10:
        category_info.append(f"... and {len(categories) - 10} more categories")
    
    builder.add_field(
        name="Available Categories",
        value="\n".join(category_info),
        inline=False
    )
    
    builder.set_footer("Select a category from the menu below")
    
    return builder.build()


class ConfigCategorySelect(ui.Select):
    """Select menu for choosing config category."""
    
    def __init__(self):
        """Initialize category select menu."""
        options = []
        
        for category in get_all_categories():
            config_count = len(get_category_configs(category))
            emoji = get_category_emoji(category)
            
            options.append(discord.SelectOption(
                label=category[:100],  # Discord limit
                description=f"{config_count} configuration(s)"[:100],
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


class ConfigCategorySelectView(ui.View):
    """View for selecting config category."""
    
    def __init__(
        self,
        ai_name: str,
        server_id: str,
        channel_id: str,
        session: Dict[str, Any]
    ):
        super().__init__(timeout=180)
        self.ai_name = ai_name
        self.server_id = server_id
        self.channel_id = channel_id
        self.session = session
        self.parser = get_config_parser()
        self.metadata = get_config_metadata()
        
        # Add category select
        self.add_item(ConfigCategorySelect())
    
    async def on_category_selected(self, interaction: discord.Interaction, category: str):
        """Handle category selection - show configs with values."""
        try:
            # Get configs in this category
            config_keys = get_category_configs(category)
            
            if not config_keys:
                await interaction.response.send_message(
                    f"❌ No configurations in category '{category}'",
                    ephemeral=True
                )
                return
            
            # Get current config
            current_config = self.session.get("config", {})
            
            # Create embed showing all configs with values
            emoji = get_category_emoji(category)
            builder = (
                EmbedBuilder(EmbedStyle.INFO)
                .set_title(f"{self.ai_name} - {category}", emoji=emoji, auto_emoji=False)
                .set_description(f"Current values for {len(config_keys)} configuration(s):")
            )
            
            # Add each config as a field
            for config_key in config_keys:
                # Get current value
                current_value = self.parser.get_nested_value(current_config, config_key)
                formatted_value = self.metadata.format_value_for_display(current_value)
                
                # Get label
                label = self.metadata.get_label(config_key.split('.')[-1])
                
                builder.add_field(
                    name=f"**{label}**",
                    value=f"`{formatted_value}`",
                    inline=True
                )
            
            builder.set_footer("Select a configuration below to edit")
            
            # Create view with config selection
            view = ConfigItemSelectView(
                ai_name=self.ai_name,
                server_id=self.server_id,
                channel_id=self.channel_id,
                session=self.session,
                category=category,
                config_keys=config_keys
            )
            
            await interaction.response.edit_message(embed=builder.build(), view=view)
        
        except Exception as e:
            func.log.error(f"Error in category selection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class ConfigItemSelect(ui.Select):
    """Select menu for choosing specific config."""
    
    def __init__(
        self,
        config_keys: List[str],
        current_config: Dict[str, Any],
        parser,
        metadata
    ):
        """Initialize config item select menu."""
        options = []
        
        for config_key in config_keys[:25]:  # Discord limit
            # Get current value
            current_value = parser.get_nested_value(current_config, config_key)
            formatted_value = metadata.format_value_for_display(current_value)
            
            # Get label
            label = metadata.get_label(config_key.split('.')[-1])  # Use last part for nested
            
            options.append(discord.SelectOption(
                label=label[:100],  # Discord limit
                description=f"Current: {formatted_value}"[:100],
                value=config_key
            ))
        
        super().__init__(
            placeholder="Choose a configuration to edit...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle config selection."""
        await self.view.on_config_selected(interaction, self.values[0])


class ConfigItemSelectView(ui.View):
    """View for selecting specific config to edit."""
    
    def __init__(
        self,
        ai_name: str,
        server_id: str,
        channel_id: str,
        session: Dict[str, Any],
        category: str,
        config_keys: List[str]
    ):
        super().__init__(timeout=180)
        self.ai_name = ai_name
        self.server_id = server_id
        self.channel_id = channel_id
        self.session = session
        self.category = category
        self.config_keys = config_keys
        self.parser = get_config_parser()
        self.metadata = get_config_metadata()
        
        # Get current config
        current_config = session.get("config", {})
        
        # Add config select
        self.add_item(ConfigItemSelect(
            config_keys,
            current_config,
            self.parser,
            self.metadata
        ))
        
        # Add back button
        self.add_item(BackButton())
    
    async def on_config_selected(self, interaction: discord.Interaction, config_key: str):
        """Handle config selection - route to choice menu or modal."""
        try:
            # Get current value
            config = self.session.get("config", {})
            current_value = self.parser.get_nested_value(config, config_key)
            
            # Check if this is a choice config
            if self.metadata.is_choice_config(config_key):
                # Use Select menu for choice configs
                choices = self.metadata.get_choices(config_key)
                
                # Check if choices are boolean
                is_boolean = all(isinstance(c, bool) for c in choices)
                
                # Format current value for display
                if is_boolean:
                    current_display = "✅ Enabled" if current_value else "❌ Disabled"
                else:
                    current_display = str(current_value)
                
                # Create embed
                emoji = get_category_emoji(self.category)
                label = self.metadata.get_label(config_key.split('.')[-1])
                description = self.metadata.get_description(config_key)
                
                builder = (
                    EmbedBuilder(EmbedStyle.INFO)
                    .set_title(f"{self.ai_name} - {label}", emoji=emoji, auto_emoji=False)
                    .set_description(f"**Current value:** `{current_display}`\n\n{description}\n\nSelect a new value from the options below:")
                )
                
                # Add available options as field
                if is_boolean:
                    options_text = "• **✅ Enabled**\n• **❌ Disabled**"
                else:
                    options_text = "\n".join([f"• **{str(choice).replace('_', ' ').title()}**" for choice in choices])
                
                builder.add_field(
                    name="Available Options",
                    value=options_text,
                    inline=False
                )
                
                # Create view with choice select
                view = ConfigChoiceSelectView(
                    ai_name=self.ai_name,
                    server_id=self.server_id,
                    channel_id=self.channel_id,
                    session=self.session,
                    category=self.category,
                    config_key=config_key,
                    config_keys=self.config_keys,
                    choices=choices,
                    current_value=current_value
                )
                
                await interaction.response.edit_message(embed=builder.build(), view=view)
            else:
                # Use Modal for other configs (existing behavior)
                # Get config type from parser
                from utils.config.ai_manager import DEFAULT_AI_CONFIG_CONTENT
                parsed_structure = self.parser.parse_yaml_structure(DEFAULT_AI_CONFIG_CONTENT)
                config_types = parsed_structure["config_types"]
                config_type = config_types.get(config_key, "str")
                
                # Create and show modal
                modal = ConfigEditModal(
                    ai_name=self.ai_name,
                    server_id=self.server_id,
                    channel_id=self.channel_id,
                    session=self.session,
                    config_key=config_key,
                    current_value=current_value,
                    config_type=config_type,
                    parser=self.parser,
                    metadata=self.metadata
                )
                
                await interaction.response.send_modal(modal)
        
        except Exception as e:
            func.log.error(f"Error opening config editor: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class BackButton(ui.Button):
    """Button to go back to category selection."""
    
    def __init__(self):
        super().__init__(
            label="← Back",
            style=discord.ButtonStyle.secondary
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle back button click."""
        # Go back to category selection
        view = ConfigCategorySelectView(
            ai_name=self.view.ai_name,
            server_id=self.view.server_id,
            channel_id=self.view.channel_id,
            session=self.view.session
        )
        
        # Use standardized embed creation
        embed = create_category_selection_embed(self.view.ai_name)
        
        await interaction.response.edit_message(embed=embed, view=view)


class BackToCategoryButton(ui.Button):
    """Button to go back to category config list."""
    
    def __init__(self, category: str, config_keys: List[str]):
        super().__init__(
            label="← Back",
            style=discord.ButtonStyle.secondary
        )
        self.category = category
        self.config_keys = config_keys
    
    async def callback(self, interaction: discord.Interaction):
        """Go back to category config list."""
        try:
            # Get current config
            current_config = self.view.session.get("config", {})
            
            # Create embed showing all configs with values
            emoji = get_category_emoji(self.category)
            builder = (
                EmbedBuilder(EmbedStyle.INFO)
                .set_title(f"{self.view.ai_name} - {self.category}", emoji=emoji, auto_emoji=False)
                .set_description(f"Current values for {len(self.config_keys)} configuration(s):")
            )
            
            # Add each config as a field
            parser = get_config_parser()
            metadata = get_config_metadata()
            
            for config_key in self.config_keys:
                # Get current value
                current_value = parser.get_nested_value(current_config, config_key)
                formatted_value = metadata.format_value_for_display(current_value)
                
                # Get label
                label = metadata.get_label(config_key.split('.')[-1])
                
                builder.add_field(
                    name=f"**{label}**",
                    value=f"`{formatted_value}`",
                    inline=True
                )
            
            builder.set_footer("Select a configuration below to edit")
            
            # Create view with config selection
            view = ConfigItemSelectView(
                ai_name=self.view.ai_name,
                server_id=self.view.server_id,
                channel_id=self.view.channel_id,
                session=self.view.session,
                category=self.category,
                config_keys=self.config_keys
            )
            
            await interaction.response.edit_message(embed=builder.build(), view=view)
        
        except Exception as e:
            func.log.error(f"Error going back to category: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class ConfigChoiceSelect(ui.Select):
    """Select menu for choosing from predefined config values."""
    
    def __init__(self, config_key: str, choices: List[Any], current_value: Any):
        """Initialize choice select menu."""
        options = []
        
        # Check if choices are boolean
        is_boolean = all(isinstance(c, bool) for c in choices)
        
        for choice in choices:
            if is_boolean:
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


class ConfigChoiceSelectView(ui.View):
    """View for selecting config value from predefined choices."""
    
    def __init__(
        self,
        ai_name: str,
        server_id: str,
        channel_id: str,
        session: Dict[str, Any],
        category: str,
        config_key: str,
        config_keys: List[str],
        choices: List[str],
        current_value: Any
    ):
        super().__init__(timeout=180)
        self.ai_name = ai_name
        self.server_id = server_id
        self.channel_id = channel_id
        self.session = session
        self.category = category
        self.config_key = config_key
        self.config_keys = config_keys
        self.parser = get_config_parser()
        self.metadata = get_config_metadata()
        
        # Add choice select
        self.add_item(ConfigChoiceSelect(config_key, choices, current_value))
        
        # Add back button
        self.add_item(BackToCategoryButton(category, config_keys))
    
    async def on_choice_selected(self, interaction: discord.Interaction, choice: str):
        """Handle choice selection and save."""
        try:
            # Get the actual choices to determine type
            choices = self.metadata.get_choices(self.config_key)
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
            
            # Capture old value before saving
            config = self.session.setdefault("config", {})
            old_value = self.parser.get_nested_value(config, self.config_key)
            
            # Save value
            self.parser.set_nested_value(config, self.config_key, value)
            
            # Save to session.json
            channel_data = func.get_session_data(self.server_id, self.channel_id)
            channel_data[self.ai_name] = self.session
            await func.update_session_data(self.server_id, self.channel_id, channel_data)
            
            # Send confirmation
            label = self.metadata.get_label(self.config_key.split('.')[-1])
            await interaction.response.send_message(
                f"✅ **Updated {label}**\nNew value: `{display_value}`",
                ephemeral=True
            )
            
            func.log.info(f"Updated config {self.config_key} = {value} for AI '{self.ai_name}'")
            
            # Send debug embed
            if interaction.guild:
                try:
                    from utils.core.debug_embed import DebugEmbed
                    
                    # Determine category from config_key
                    category = self.config_key.split('.')[0] if '.' in self.config_key else "General"
                    setting = self.config_key.split('.')[-1]
                    
                    await DebugEmbed.send(
                        guild=interaction.guild,
                        event="config_change",
                        data={
                            "ai_name": self.ai_name,
                            "category": category.replace('_', ' ').title(),
                            "setting": setting.replace('_', ' ').title(),
                            "old_value": str(old_value) if old_value is not None else "None",
                            "new_value": str(value),
                            "executor": f"<@{interaction.user.id}>",
                            "channel": f"<#{self.channel_id}>"
                        }
                    )
                except Exception as e:
                    func.log.debug(f"Failed to send debug embed: {e}")
        
        except Exception as e:
            func.log.error(f"Error saving choice: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error saving: {str(e)}",
                ephemeral=True
            )


class ConfigEditModal(ui.Modal):
    """Modal for editing a config value."""
    
    def __init__(
        self,
        ai_name: str,
        server_id: str,
        channel_id: str,
        session: Dict[str, Any],
        config_key: str,
        current_value: Any,
        config_type: str,
        parser,
        metadata
    ):
        # Use short name for title
        short_name = config_key.split('.')[-1]
        super().__init__(title=f"Edit: {short_name}"[:45])  # Discord limit
        
        self.ai_name = ai_name
        self.server_id = server_id
        self.channel_id = channel_id
        self.session = session
        self.config_key = config_key
        self.config_type = config_type
        self.parser = parser
        self.metadata = metadata
        
        # Add text input
        self.value_input = metadata.get_modal_component(
            short_name,
            current_value,
            config_type
        )
        self.add_item(self.value_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        try:
            # Get input value
            input_value = self.value_input.value
            
            # Parse value
            parsed_value = self.metadata.parse_value_from_input(input_value, self.config_type)
            
            # Validate
            is_valid, error_msg = self.metadata.validate_value(
                self.config_key,
                parsed_value,
                self.config_type
            )
            
            if not is_valid:
                await interaction.response.send_message(
                    f"❌ Validation error: {error_msg}",
                    ephemeral=True
                )
                return
            
            # Capture old value before saving
            config = self.session.get("config", {})
            old_value = self.parser.get_nested_value(config, self.config_key)
            
            # Save to session
            await self._save_value(parsed_value, interaction, old_value)
            
            # Send confirmation
            formatted_value = self.metadata.format_value_for_display(parsed_value)
            await interaction.response.send_message(
                f"✅ **Updated {self.config_key}**\n"
                f"New value: `{formatted_value}`",
                ephemeral=True
            )
        
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Invalid value: {str(e)}",
                ephemeral=True
            )
        except Exception as e:
            func.log.error(f"Error saving config: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error saving: {str(e)}",
                ephemeral=True
            )
    
    async def _save_value(self, value: Any, interaction=None, old_value=None):
        """Save value to session.json."""
        # Get config
        config = self.session.setdefault("config", {})
        
        # Set value using parser helper
        self.parser.set_nested_value(config, self.config_key, value)
        
        # Save to session.json
        channel_data = func.get_session_data(self.server_id, self.channel_id)
        channel_data[self.ai_name] = self.session
        await func.update_session_data(self.server_id, self.channel_id, channel_data)
        
        func.log.info(f"Updated config {self.config_key} = {value} for AI '{self.ai_name}'")
        
        # Send debug embed
        if interaction and interaction.guild:
            try:
                from utils.core.debug_embed import DebugEmbed
                
                # Determine category from config_key
                category = self.config_key.split('.')[0] if '.' in self.config_key else "General"
                setting = self.config_key.split('.')[-1]
                
                await DebugEmbed.send(
                    guild=interaction.guild,
                    event="config_change",
                    data={
                        "ai_name": self.ai_name,
                        "category": category.replace('_', ' ').title(),
                        "setting": setting.replace('_', ' ').title(),
                        "old_value": str(old_value) if old_value is not None else "None",
                        "new_value": str(value),
                        "executor": f"<@{interaction.user.id}>",
                        "channel": f"<#{self.channel_id}>"
                    }
                )
            except Exception as e:
                func.log.debug(f"Failed to send debug embed: {e}")
