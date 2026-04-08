"""
Setup UI Components - Interactive Setup Wizard

Provides step-by-step interactive UI for AI setup.
Similar to api_ui_components.py and config_ui_components.py.
"""

import discord
from discord import ui
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import traceback
import asyncio

import utils.func as func
from AI.core.registry import get_registry


@dataclass
class SetupWizardData:
    """Armazena o estado do wizard de setup."""
    
    # User info
    user_id: int
    guild_id: int
    guild_name: str
    
    # Step 1: Channel
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    
    # Step 2: Mode
    mode: Optional[str] = None  # "bot" or "webhook"
    
    # Step 3: API Connection
    api_connection_name: Optional[str] = None
    api_connection_data: Optional[dict] = None
    
    # Step 4: Character Card
    card_source: Optional[str] = None  # "registered", "url", "default"
    card_name: Optional[str] = None
    card_url: Optional[str] = None
    card_data: Optional[dict] = None
    card_cache_path: Optional[str] = None
    
    # Step 5: Greeting (opcional)
    greeting_index: int = 0
    total_greetings: int = 1
    
    # Step 6: Preset (opcional)
    preset_name: Optional[str] = None
    
    # Current step
    current_step: int = 1
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "guild_name": self.guild_name,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "mode": self.mode,
            "api_connection_name": self.api_connection_name,
            "card_source": self.card_source,
            "card_name": self.card_name,
            "card_url": self.card_url,
            "greeting_index": self.greeting_index,
            "preset_name": self.preset_name,
            "current_step": self.current_step
        }


def create_step_embed(
    step: int,
    title: str,
    description: str,
    wizard_data: SetupWizardData,
    color: discord.Color = discord.Color.blue()
) -> discord.Embed:
    """Cria embed padronizado para cada step."""
    embed = discord.Embed(
        title=f"🔧 AI Setup - Step {step}/7",
        description=f"**{title}**\n\n{description}",
        color=color
    )
    
    # Add progress info
    progress_text = []
    if wizard_data.channel_name:
        progress_text.append(f"📍 Channel: #{wizard_data.channel_name}")
    if wizard_data.mode:
        mode_emoji = "🤖" if wizard_data.mode == "bot" else "🔗"
        progress_text.append(f"{mode_emoji} Mode: {wizard_data.mode.title()}")
    if wizard_data.api_connection_name:
        progress_text.append(f"🔌 Connection: {wizard_data.api_connection_name}")
    if wizard_data.card_name or wizard_data.card_source:
        card_info = wizard_data.card_name or wizard_data.card_source
        progress_text.append(f"🎭 Card: {card_info}")
    
    if progress_text:
        embed.add_field(
            name="📊 Progress",
            value="\n".join(progress_text),
            inline=False
        )
    
    embed.set_footer(text=f"Server: {wizard_data.guild_name}")
    
    return embed


class Step1_ChannelSelectView(ui.View):
    """Seleção de canal."""
    
    def __init__(self, wizard_data: SetupWizardData):
        super().__init__(timeout=300)
        self.wizard_data = wizard_data
        
        # Add channel select
        self.add_item(ChannelSelectMenu())
        
        # Add cancel button
        self.add_item(CancelButton())
    
    async def on_channel_selected(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Handle channel selection with validation."""
        try:
            # Validate: Check if channel already has any AI configured
            server_id = str(self.wizard_data.guild_id)
            channel_id = str(channel.id)
            channel_data = func.get_session_data(server_id, channel_id) or {}
            
            if channel_data:
                # Channel already has AI(s) configured
                existing_ais = list(channel_data.keys())
                existing_modes = [ai_data.get("mode", "unknown") for ai_data in channel_data.values()]
                
                await interaction.response.send_message(
                    f"❌ **Channel already has AI configured**\n\n"
                    f"**Channel:** #{channel.name}\n"
                    f"**Existing AI(s):** {', '.join(existing_ais)}\n"
                    f"**Mode(s):** {', '.join(existing_modes)}\n\n"
                    f"💡 **Only 1 AI per channel is allowed.**\n"
                    f"To configure a new AI, remove the existing one first using `/remove_ai`.",
                    ephemeral=True
                )
                return
            
            # Channel is empty, proceed
            self.wizard_data.channel_id = channel_id
            self.wizard_data.channel_name = channel.name
            self.wizard_data.current_step = 2
            
            # Move to step 2 with improved descriptions
            view = Step2_ModeSelectView(self.wizard_data)
            embed = create_step_embed(
                step=2,
                title="Select Mode",
                description=(
                    "Choose how the AI will appear in the channel:\n\n"
                    
                    "🤖 **Bot Mode**\n"
                    "The AI uses the bot's Discord account.\n"
                    "**Advantages:**\n"
                    "• More complete and realistic profile\n"
                    "• Full support for replys\n"
                    "• Advanced expressions work 100%\n"
                    "• Server-specific avatar and nickname\n"
                    "• More stable and reliable\n\n"
                    
                    "🔗 **Webhook Mode**\n"
                    "The AI uses a custom webhook.\n"
                    "**Advantages:**\n"
                    "• Ideal for roleplay and characters\n"
                    "• Doesn't interfere with bot profile\n"
                    "• Fully customizable avatar and name\n"
                    "• More flexible for multiple characters\n\n"
                    
                    "⚠️ **Important:** Only 1 AI per channel is allowed."
                ),
                wizard_data=self.wizard_data
            )
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            func.log.error(f"Error in channel selection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class ChannelSelectMenu(ui.ChannelSelect):
    """Select menu for channel selection."""
    
    def __init__(self):
        super().__init__(
            placeholder="Choose a channel...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle channel selection."""
        channel = self.values[0]
        await self.view.on_channel_selected(interaction, channel)

class Step2_ModeSelectView(ui.View):
    """Seleção de modo (bot ou webhook)."""
    
    def __init__(self, wizard_data: SetupWizardData):
        super().__init__(timeout=300)
        self.wizard_data = wizard_data
        
        # Add mode buttons
        self.add_item(BotModeButton())
        self.add_item(WebhookModeButton())
        
        # Add navigation
        self.add_item(BackButton(target_step=1))
        self.add_item(CancelButton())


class BotModeButton(ui.Button):
    """Botão para selecionar modo bot."""
    
    def __init__(self):
        super().__init__(
            label="Bot Mode",
            style=discord.ButtonStyle.primary,
            emoji="🤖"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle bot mode selection."""
        try:
            self.view.wizard_data.mode = "bot"
            self.view.wizard_data.current_step = 3
            
            # Validation already done in Step 1, proceed directly to Step 3
            view = Step3_APIConnectionView(self.view.wizard_data)
            embed = create_step_embed(
                step=3,
                title="Select API Connection",
                description="Choose an API connection for the AI to use.\n\n"
                           "If you don't have any connections yet, create one first.",
                wizard_data=self.view.wizard_data
            )
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            func.log.error(f"Error selecting bot mode: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class WebhookModeButton(ui.Button):
    """Botão para selecionar modo webhook."""
    
    def __init__(self):
        super().__init__(
            label="Webhook Mode",
            style=discord.ButtonStyle.secondary,
            emoji="🔗"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle webhook mode selection."""
        try:
            self.view.wizard_data.mode = "webhook"
            self.view.wizard_data.current_step = 3
            
            # Move to step 3
            view = Step3_APIConnectionView(self.view.wizard_data)
            embed = create_step_embed(
                step=3,
                title="Select API Connection",
                description="Choose an API connection for the AI to use.\n\n"
                           "If you don't have any connections yet, create one first.",
                wizard_data=self.view.wizard_data
            )
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            func.log.error(f"Error selecting webhook mode: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

class Step3_APIConnectionView(ui.View):
    """Seleção de API connection."""
    
    def __init__(self, wizard_data: SetupWizardData):
        super().__init__(timeout=300)
        self.wizard_data = wizard_data
        
        # Check if connections exist
        server_id = str(wizard_data.guild_id)
        connections = func.list_api_connections(server_id)
        
        if connections:
            # Add connection select
            self.add_item(APIConnectionSelectMenu(connections))
        
        # Always add "Create New" button
        self.add_item(CreateNewConnectionButton())
        
        # Add navigation
        self.add_item(BackButton(target_step=2))
        self.add_item(CancelButton())
    
    async def on_connection_selected(self, interaction: discord.Interaction, connection_name: str):
        """Handle connection selection."""
        try:
            server_id = str(self.wizard_data.guild_id)
            connection = func.get_api_connection(server_id, connection_name)
            
            if not connection:
                await interaction.response.send_message(
                    f"❌ Connection '{connection_name}' not found.",
                    ephemeral=True
                )
                return
            
            self.wizard_data.api_connection_name = connection_name
            self.wizard_data.api_connection_data = connection
            self.wizard_data.current_step = 4
            
            # Move to step 4
            view = Step4_CharacterCardView(self.wizard_data)
            embed = create_step_embed(
                step=4,
                title="Select Character Card",
                description="Choose a character card for the AI.\n\n"
                           "You can select a registered card, import from URL, or use the default.",
                wizard_data=self.wizard_data
            )
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            func.log.error(f"Error in connection selection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class APIConnectionSelectMenu(ui.Select):
    """Select menu for API connections."""
    
    def __init__(self, connections: Dict[str, Any]):
        registry = get_registry()
        options = []
        
        for conn_name, conn_data in sorted(connections.items())[:25]:
            provider = conn_data.get("provider", "unknown").lower()
            model = conn_data.get("model", "Unknown")
            
            try:
                provider_meta = registry.get_metadata(provider)
                provider_display = provider_meta.display_name
                provider_icon = provider_meta.icon
            except ValueError:
                provider_display = provider.upper()
                provider_icon = "🔵"
            
            description = f"{provider_icon} {provider_display} • {model}"
            
            options.append(discord.SelectOption(
                label=conn_name[:100],
                value=conn_name,
                description=description[:100]
            ))
        
        super().__init__(
            placeholder="Choose an API connection...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle connection selection."""
        await self.view.on_connection_selected(interaction, self.values[0])


class CreateNewConnectionButton(ui.Button):
    """Botão para criar nova connection."""
    
    def __init__(self):
        super().__init__(
            label="Create New Connection",
            style=discord.ButtonStyle.success,
            emoji="➕"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Redirect to /api_connections."""
        await interaction.response.send_message(
            "💡 **Create API Connection**\n\n"
            "To create a new API connection, use the `/api_connections` command.\n\n"
            "After creating the connection, run `/setup` again to continue.",
            ephemeral=True
        )


# ============================================================================
# NAVIGATION BUTTONS
# ============================================================================

class BackButton(ui.Button):
    """Botão para voltar ao step anterior."""
    
    def __init__(self, target_step: int):
        super().__init__(
            label="← Back",
            style=discord.ButtonStyle.secondary
        )
        self.target_step = target_step
    
    async def callback(self, interaction: discord.Interaction):
        """Go back to previous step."""
        try:
            self.view.wizard_data.current_step = self.target_step
            
            # Create appropriate view for target step
            if self.target_step == 1:
                view = Step1_ChannelSelectView(self.view.wizard_data)
                embed = create_step_embed(
                    step=1,
                    title="Select Channel",
                    description="Choose the channel where the AI will be active:",
                    wizard_data=self.view.wizard_data
                )
            elif self.target_step == 2:
                view = Step2_ModeSelectView(self.view.wizard_data)
                embed = create_step_embed(
                    step=2,
                    title="Select Mode",
                    description="Choose how the AI will appear in the channel:",
                    wizard_data=self.view.wizard_data
                )
            elif self.target_step == 3:
                view = Step3_APIConnectionView(self.view.wizard_data)
                embed = create_step_embed(
                    step=3,
                    title="Select API Connection",
                    description="Choose an API connection for the AI to use:",
                    wizard_data=self.view.wizard_data
                )
            elif self.target_step == 4:
                view = Step4_CharacterCardView(self.view.wizard_data)
                embed = create_step_embed(
                    step=4,
                    title="Select Character Card",
                    description="Choose a character card for the AI:",
                    wizard_data=self.view.wizard_data
                )
            elif self.target_step == 5:
                view = Step5_GreetingSelectView(self.view.wizard_data)
                embed = create_step_embed(
                    step=5,
                    title="Select Greeting",
                    description="Choose which greeting to use:",
                    wizard_data=self.view.wizard_data
                )
            elif self.target_step == 6:
                view = Step6_PresetSelectView(self.view.wizard_data)
                embed = create_step_embed(
                    step=6,
                    title="Select Preset",
                    description="Choose a configuration preset:",
                    wizard_data=self.view.wizard_data
                )
            else:
                await interaction.response.send_message(
                    "❌ Invalid step",
                    ephemeral=True
                )
                return
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            func.log.error(f"Error going back: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class CancelButton(ui.Button):
    """Botão para cancelar o wizard."""
    
    def __init__(self):
        super().__init__(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Cancel the wizard."""
        embed = discord.Embed(
            title="❌ Setup Cancelled",
            description="AI setup has been cancelled.\n\nRun `/setup` again when you're ready.",
            color=discord.Color.red()
        )
        
        await interaction.response.edit_message(embed=embed, view=None)


class Step4_CharacterCardView(ui.View):
    """Seleção de character card."""
    
    def __init__(self, wizard_data: SetupWizardData):
        super().__init__(timeout=300)
        self.wizard_data = wizard_data
        
        # Get registered cards
        server_id = str(wizard_data.guild_id)
        cards = func.list_character_cards(server_id)
        
        # Row 1: Card selection (if cards exist)
        if cards:
            self.add_item(RegisteredCardSelectMenu(cards))
        
        # Row 2: Import options
        self.add_item(ImportFromURLButton())
        self.add_item(ImportFileInstructionsButton())
        self.add_item(UseDefaultButton())
        
        # Row 3: Navigation
        self.add_item(BackButton(target_step=3))
        self.add_item(CancelButton())
    
    async def on_card_selected(self, interaction: discord.Interaction, card_name: str):
        """Handle registered card selection."""
        try:
            server_id = str(self.wizard_data.guild_id)
            card_info = func.get_character_card(server_id, card_name)
            
            if not card_info:
                await interaction.response.send_message(
                    f"❌ Card '{card_name}' not found.",
                    ephemeral=True
                )
                return
            
            self.wizard_data.card_source = "registered"
            self.wizard_data.card_name = card_name
            self.wizard_data.card_data = card_info
            self.wizard_data.card_cache_path = card_info.get("cache_path")
            self.wizard_data.current_step = 5
            
            # Load card to get greeting count
            from pathlib import Path
            from utils.ccv3.parser import parse_character_card
            
            card_file = Path(card_info.get("cache_path"))
            if card_file.exists():
                with open(card_file, 'rb') as f:
                    raw_data = f.read()
                character_card = parse_character_card(raw_data)
                if character_card:
                    alt_greetings = character_card.alternate_greetings or []
                    self.wizard_data.total_greetings = 1 + len(alt_greetings)
            
            # Move to step 5
            await self._move_to_step5(interaction)
        
        except Exception as e:
            func.log.error(f"Error in card selection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    async def _move_to_step5(self, interaction: discord.Interaction):
        """Move to greeting selection."""
        view = Step5_GreetingSelectView(self.wizard_data)
        embed = create_step_embed(
            step=5,
            title="Select Greeting (Optional)",
            description=f"This character has {self.wizard_data.total_greetings} greeting(s).\n\n"
                       "Choose which greeting to use, or skip to use the default (first greeting).",
            wizard_data=self.wizard_data
        )
        
        await interaction.response.edit_message(embed=embed, view=view)


class RegisteredCardSelectMenu(ui.Select):
    """Select menu for registered cards."""
    
    def __init__(self, cards: Dict[str, Any]):
        options = []
        
        for card_name, card_data in sorted(cards.items())[:25]:
            creator = card_data.get("creator", "Unknown")
            description = f"By {creator}"
            
            options.append(discord.SelectOption(
                label=card_name[:100],
                value=card_name,
                description=description[:100],
                emoji="🎭"
            ))
        
        super().__init__(
            placeholder="Choose a registered card...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle card selection."""
        await self.view.on_card_selected(interaction, self.values[0])


class ImportFromURLButton(ui.Button):
    """Botão para importar card via URL."""
    
    def __init__(self):
        super().__init__(
            label="Import from URL",
            style=discord.ButtonStyle.primary,
            emoji="🔗",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Show modal to enter URL."""
        modal = ImportCardURLModal(self.view.wizard_data)
        await interaction.response.send_modal(modal)


class ImportFileInstructionsButton(ui.Button):
    """Botão com instruções para importar arquivo."""
    
    def __init__(self):
        super().__init__(
            label="Import File",
            style=discord.ButtonStyle.secondary,
            emoji="📁",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Show instructions."""
        embed = discord.Embed(
            title="📁 Import Character Card File",
            description=(
                "Discord doesn't allow file uploads during interactions.\n\n"
                "**To import a card file:**\n"
                "1. Use `/import_card` command\n"
                "2. Upload your PNG/JSON/CHARX file\n"
                "3. Return here and select it from the list\n\n"
                "**Or use a URL instead:**\n"
                "Click the 'Import from URL' button"
            ),
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


class UseDefaultButton(ui.Button):
    """Botão para usar card padrão."""
    
    def __init__(self):
        super().__init__(
            label="Use Default",
            style=discord.ButtonStyle.secondary,
            emoji="⭐",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Use default card."""
        try:
            from utils.ccv3 import load_local_card
            
            default_card_path = "character_cards/hashi.png"
            result = await load_local_card(default_card_path)
            
            if not result:
                await interaction.response.send_message(
                    "❌ Default card 'hashi.png' not found.\n\n"
                    "Please use another option.",
                    ephemeral=True
                )
                return
            
            character_card, card_cache_path = result
            
            self.view.wizard_data.card_source = "default"
            self.view.wizard_data.card_name = "hashi"
            self.view.wizard_data.card_cache_path = card_cache_path
            self.view.wizard_data.current_step = 5
            
            # Get greeting count
            alt_greetings = character_card.alternate_greetings or []
            self.view.wizard_data.total_greetings = 1 + len(alt_greetings)
            
            # Move to step 5
            view = Step5_GreetingSelectView(self.view.wizard_data)
            embed = create_step_embed(
                step=5,
                title="Select Greeting (Optional)",
                description=f"This character has {self.view.wizard_data.total_greetings} greeting(s).\n\n"
                           "Choose which greeting to use, or skip to use the default.",
                wizard_data=self.view.wizard_data
            )
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            func.log.error(f"Error using default card: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class ImportCardURLModal(ui.Modal):
    """Modal para importar card via URL."""
    
    def __init__(self, wizard_data: SetupWizardData):
        super().__init__(title="Import Card from URL")
        self.wizard_data = wizard_data
        
        self.url_input = ui.TextInput(
            label="Card URL",
            placeholder="https://example.com/card.png",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.url_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle URL submission."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            card_url = self.url_input.value.strip()
            
            # Download and parse card
            from utils.ccv3 import download_card
            
            result = await download_card(card_url)
            
            if not result:
                await interaction.followup.send(
                    "❌ Failed to download or parse card from URL.\n\n"
                    "Please check the URL and try again.",
                    ephemeral=True
                )
                return
            
            character_card, card_cache_path = result
            
            self.wizard_data.card_source = "url"
            self.wizard_data.card_url = card_url
            self.wizard_data.card_name = character_card.name
            self.wizard_data.card_cache_path = card_cache_path
            self.wizard_data.current_step = 5
            
            # Get greeting count
            alt_greetings = character_card.alternate_greetings or []
            self.wizard_data.total_greetings = 1 + len(alt_greetings)
            
            await interaction.followup.send(
                f"✅ Card '{character_card.name}' imported successfully!",
                ephemeral=True
            )
        
        except Exception as e:
            func.log.error(f"Error importing card from URL: {e}\n{traceback.format_exc()}")
            await interaction.followup.send(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

class Step5_GreetingSelectView(ui.View):
    """Seleção de greeting (opcional)."""
    
    def __init__(self, wizard_data: SetupWizardData):
        super().__init__(timeout=300)
        self.wizard_data = wizard_data
        
        # Add greeting select if multiple greetings
        if wizard_data.total_greetings > 1:
            self.add_item(GreetingSelectMenu(wizard_data.total_greetings))
            # Skip button with clear text for multiple greetings
            self.add_item(SkipButton(next_step=6, label="Use Default Greeting"))
        else:
            # Only 1 greeting, so just continue
            self.add_item(SkipButton(next_step=6, label="Continue"))
        
        # Add navigation
        self.add_item(BackButton(target_step=4))
        self.add_item(CancelButton())
    
    async def on_greeting_selected(self, interaction: discord.Interaction, greeting_index: int):
        """Handle greeting selection."""
        try:
            self.wizard_data.greeting_index = greeting_index
            self.wizard_data.current_step = 6
            
            # Move to step 6
            view = Step6_PresetSelectView(self.wizard_data)
            embed = create_step_embed(
                step=6,
                title="Select Preset (Optional)",
                description="Choose a configuration preset to apply, or skip to use default settings.",
                wizard_data=self.wizard_data
            )
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            func.log.error(f"Error in greeting selection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class GreetingSelectMenu(ui.Select):
    """Select menu for greeting selection."""
    
    def __init__(self, total_greetings: int):
        options = []
        
        for i in range(min(total_greetings, 25)):
            if i == 0:
                label = "Greeting 1 (Default)"
                description = "First greeting (first_mes)"
            else:
                label = f"Greeting {i + 1}"
                description = f"Alternate greeting #{i}"
            
            options.append(discord.SelectOption(
                label=label,
                value=str(i),
                description=description,
                default=(i == 0)
            ))
        
        super().__init__(
            placeholder="Choose a greeting...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle greeting selection."""
        greeting_index = int(self.values[0])
        await self.view.on_greeting_selected(interaction, greeting_index)


class SkipButton(ui.Button):
    """Botão para pular step opcional."""
    
    def __init__(self, next_step: int, label: str = "Skip"):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            emoji="⏭️"
        )
        self.next_step = next_step
    
    async def callback(self, interaction: discord.Interaction):
        """Skip to next step."""
        try:
            self.view.wizard_data.current_step = self.next_step
            
            if self.next_step == 6:
                view = Step6_PresetSelectView(self.view.wizard_data)
                embed = create_step_embed(
                    step=6,
                    title="Select Preset (Optional)",
                    description="Choose a configuration preset to apply, or skip to use default settings.",
                    wizard_data=self.view.wizard_data
                )
            elif self.next_step == 7:
                view = Step7_ConfirmationView(self.view.wizard_data)
                embed = create_confirmation_embed(self.view.wizard_data)
            else:
                await interaction.response.send_message(
                    "❌ Invalid step",
                    ephemeral=True
                )
                return
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            func.log.error(f"Error skipping step: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class Step6_PresetSelectView(ui.View):
    """Seleção de preset (opcional)."""
    
    def __init__(self, wizard_data: SetupWizardData):
        super().__init__(timeout=300)
        self.wizard_data = wizard_data
        
        # Get available presets
        from utils.config.ai_manager import get_ai_config_manager
        config_manager = get_ai_config_manager()
        presets = config_manager.list_presets()
        
        # Add preset select if presets exist
        if presets:
            self.add_item(PresetSelectMenu(presets))
        
        # Add skip button
        self.add_item(SkipButton(next_step=7, label="Skip (Use Default)"))
        
        # Add navigation
        self.add_item(BackButton(target_step=5))
        self.add_item(CancelButton())
    
    async def on_preset_selected(self, interaction: discord.Interaction, preset_name: str):
        """Handle preset selection."""
        try:
            self.wizard_data.preset_name = preset_name
            self.wizard_data.current_step = 7
            
            # Move to step 7
            view = Step7_ConfirmationView(self.wizard_data)
            embed = create_confirmation_embed(self.wizard_data)
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            func.log.error(f"Error in preset selection: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )


class PresetSelectMenu(ui.Select):
    """Select menu for preset selection."""
    
    def __init__(self, presets):
        options = []
        
        # presets is a list of dicts with 'name', 'description', 'author'
        for preset in presets[:25]:  # Limit to 25 options
            if isinstance(preset, dict):
                preset_name = preset.get("name", "")
                preset_desc = preset.get("description", "")
                
                if preset_name and preset_name.strip():
                    # Use description as label if available, otherwise use name
                    label = preset_name[:100]
                    description = preset_desc[:100] if preset_desc else None
                    
                    options.append(discord.SelectOption(
                        label=label,
                        value=preset_name[:100],  # Value is the preset name
                        description=description,
                        emoji="⚙️"
                    ))
        
        # Fallback if no valid options
        if not options:
            options.append(discord.SelectOption(
                label="No presets available",
                value="none",
                emoji="❌"
            ))
        
        super().__init__(
            placeholder="Choose a preset...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle preset selection."""
        preset_name = self.values[0]
        if preset_name != "none":
            await self.view.on_preset_selected(interaction, preset_name)


def create_confirmation_embed(wizard_data: SetupWizardData) -> discord.Embed:
    """Cria embed de confirmação com todos os dados."""
    embed = discord.Embed(
        title="✅ Confirm AI Setup",
        description="Please review your configuration before creating the AI:",
        color=discord.Color.green()
    )
    
    # Channel & Mode
    mode_emoji = "🤖" if wizard_data.mode == "bot" else "🔗"
    embed.add_field(
        name="📍 Channel & Mode",
        value=f"**Channel:** #{wizard_data.channel_name}\n"
              f"**Mode:** {mode_emoji} {wizard_data.mode.title()}",
        inline=False
    )
    
    # API Connection
    if wizard_data.api_connection_data:
        provider = wizard_data.api_connection_data.get("provider", "unknown").upper()
        model = wizard_data.api_connection_data.get("model", "Unknown")
        embed.add_field(
            name="🔌 API Connection",
            value=f"**Name:** {wizard_data.api_connection_name}\n"
                  f"**Provider:** {provider}\n"
                  f"**Model:** {model}",
            inline=False
        )
    
    # Character Card
    card_info = f"**Source:** {wizard_data.card_source.title()}\n"
    if wizard_data.card_name:
        card_info += f"**Name:** {wizard_data.card_name}\n"
    if wizard_data.card_url:
        card_info += f"**URL:** {wizard_data.card_url[:50]}...\n"
    
    embed.add_field(
        name="🎭 Character Card",
        value=card_info,
        inline=False
    )
    
    # Greeting
    embed.add_field(
        name="💬 Greeting",
        value=f"Greeting {wizard_data.greeting_index + 1} of {wizard_data.total_greetings}",
        inline=True
    )
    
    # Preset
    preset_text = wizard_data.preset_name if wizard_data.preset_name else "Default settings"
    embed.add_field(
        name="⚙️ Configuration",
        value=preset_text,
        inline=True
    )
    
    embed.set_footer(text="Click 'Confirm & Create' to proceed")
    
    return embed


class Step7_ConfirmationView(ui.View):
    """Tela de confirmação final."""
    
    def __init__(self, wizard_data: SetupWizardData):
        super().__init__(timeout=300)
        self.wizard_data = wizard_data
        
        # Add confirm button
        self.add_item(ConfirmSetupButton())
        
        # Add navigation
        self.add_item(BackButton(target_step=6))
        self.add_item(CancelButton())


class ConfirmSetupButton(ui.Button):
    """Botão para confirmar e executar setup."""
    
    def __init__(self):
        super().__init__(
            label="✅ Confirm & Create AI",
            style=discord.ButtonStyle.success
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Execute the setup."""
        try:
            # Defer without ephemeral to allow editing the original message
            await interaction.response.defer()
            
            # Execute setup
            from commands.ai.lifecycle import execute_setup_from_wizard
            
            success, message = await execute_setup_from_wizard(
                bot=interaction.client,
                wizard_data=self.view.wizard_data,
                interaction=interaction
            )
            
            if success:
                embed = discord.Embed(
                    title="✅ Setup Complete!",
                    description=message,
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Setup Failed",
                    description=message,
                    color=discord.Color.red()
                )
            
            # Edit the original setup message instead of creating a new one
            await interaction.edit_original_response(embed=embed, view=None)
        
        except Exception as e:
            func.log.error(f"Error executing setup: {e}\n{traceback.format_exc()}")
            try:
                await interaction.edit_original_response(
                    embed=discord.Embed(
                        title="❌ Error",
                        description=f"Error executing setup: {str(e)}",
                        color=discord.Color.red()
                    ),
                    view=None
                )
            except:
                # Fallback if edit fails
                await interaction.followup.send(
                    f"❌ Error executing setup: {str(e)}",
                    ephemeral=True
                )
