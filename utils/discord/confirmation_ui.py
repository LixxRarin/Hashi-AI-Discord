"""
Confirmation UI Components

Provides reusable Discord UI components for confirmation dialogs.
Replaces emoji-based reactions with modern button-based interactions.

Features:
- Single and double confirmation flows
- Conditional confirmation logic
- Standardized embed templates
- No timeout (users can take their time)
- User validation (only requester can interact)
"""

from datetime import datetime
from typing import Callable, Optional, List, Dict, Any
import discord

def create_confirmation_embed(
    title: str,
    description: str,
    fields: Optional[List[Dict[str, Any]]] = None,
    color: discord.Color = discord.Color.orange(),
    thumbnail_url: Optional[str] = None,
    footer_text: Optional[str] = None,
    footer_icon_url: Optional[str] = None
) -> discord.Embed:
    """
    Create a standardized confirmation embed.
    
    Args:
        title: Embed title
        description: Main description text
        fields: List of field dictionaries with 'name', 'value', and optional 'inline'
        color: Embed color (default: orange for warnings)
        thumbnail_url: Optional thumbnail URL (e.g., character card)
        footer_text: Optional footer text
        footer_icon_url: Optional footer icon URL
        
    Returns:
        Configured Discord embed
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now()
    )
    
    # Add fields
    if fields:
        for field in fields:
            embed.add_field(
                name=field.get("name", ""),
                value=field.get("value", ""),
                inline=field.get("inline", False)
            )
    
    # Add thumbnail
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    
    # Add footer
    if footer_text:
        embed.set_footer(text=footer_text, icon_url=footer_icon_url)
    
    return embed


def create_success_embed(
    title: str,
    description: str,
    fields: Optional[List[Dict[str, Any]]] = None,
    thumbnail_url: Optional[str] = None
) -> discord.Embed:
    """
    Create a standardized success embed.
    
    Args:
        title: Embed title (should start with ✅)
        description: Success message
        fields: Optional additional fields
        thumbnail_url: Optional thumbnail URL
        
    Returns:
        Green success embed
    """
    return create_confirmation_embed(
        title=title,
        description=description,
        fields=fields,
        color=discord.Color.green(),
        thumbnail_url=thumbnail_url
    )


def create_cancellation_embed(
    title: str = "❌ Cancelled",
    description: str = "Operation cancelled. No changes were made.",
    fields: Optional[List[Dict[str, Any]]] = None
) -> discord.Embed:
    """
    Create a standardized cancellation embed.
    
    Args:
        title: Embed title
        description: Cancellation message
        fields: Optional additional fields
        
    Returns:
        Grey cancellation embed
    """
    return create_confirmation_embed(
        title=title,
        description=description,
        fields=fields,
        color=discord.Color.greyple()
    )


def create_error_embed(
    title: str,
    description: str,
    fields: Optional[List[Dict[str, Any]]] = None
) -> discord.Embed:
    """
    Create a standardized error embed.
    
    Args:
        title: Error title (should start with ❌)
        description: Error message
        fields: Optional additional fields
        
    Returns:
        Red error embed
    """
    return create_confirmation_embed(
        title=title,
        description=description,
        fields=fields,
        color=discord.Color.red()
    )

class ConfirmationView(discord.ui.View):
    """
    Single-step confirmation dialog with Confirm/Cancel buttons.
    
    Use for: Non-critical operations that still need user confirmation.
    
    Example:
        ```python
        async def on_confirm(interaction):
            await interaction.response.edit_message(
                embed=create_success_embed("✅ Done", "Action completed"),
                view=None
            )
        
        async def on_cancel(interaction):
            await interaction.response.edit_message(
                embed=create_cancellation_embed(),
                view=None
            )
        
        view = ConfirmationView(
            user_id=interaction.user.id,
            on_confirm=on_confirm,
            on_cancel=on_cancel
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        ```
    """
    
    def __init__(
        self,
        user_id: int,
        on_confirm: Callable[[discord.Interaction], Any],
        on_cancel: Callable[[discord.Interaction], Any],
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        confirm_style: discord.ButtonStyle = discord.ButtonStyle.success,
        cancel_style: discord.ButtonStyle = discord.ButtonStyle.danger
    ):
        """
        Initialize confirmation view.
        
        Args:
            user_id: Discord user ID who can interact with this view
            on_confirm: Async callback when confirmed
            on_cancel: Async callback when cancelled
            confirm_label: Label for confirm button
            cancel_label: Label for cancel button
            confirm_style: Style for confirm button
            cancel_style: Style for cancel button
        """
        super().__init__(timeout=None)  # No timeout!
        self.user_id = user_id
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        
        # Create buttons dynamically
        self.confirm_button = discord.ui.Button(
            label=confirm_label,
            style=confirm_style,
            emoji="✅"
        )
        self.confirm_button.callback = self._confirm_callback
        
        self.cancel_button = discord.ui.Button(
            label=cancel_label,
            style=cancel_style,
            emoji="❌"
        )
        self.cancel_button.callback = self._cancel_callback
        
        self.add_item(self.confirm_button)
        self.add_item(self.cancel_button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Validate that only the command requester can interact.
        
        Args:
            interaction: Discord interaction
            
        Returns:
            True if user is authorized, False otherwise
        """
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ You cannot interact with this confirmation.",
                ephemeral=True
            )
            return False
        return True
    
    async def _confirm_callback(self, interaction: discord.Interaction):
        """Handle confirm button click."""
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        # Call user's confirm handler
        await self.on_confirm(interaction)
        self.stop()
    
    async def _cancel_callback(self, interaction: discord.Interaction):
        """Handle cancel button click."""
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        # Call user's cancel handler
        await self.on_cancel(interaction)
        self.stop()


class DoubleConfirmationView(discord.ui.View):
    """
    Two-step confirmation dialog for dangerous operations.
    
    Step 1: "I Understand" + "Cancel"
    Step 2: "Confirm [Action]" + "Go Back"
    
    Use for: Destructive operations like deleting data, clearing history, etc.
    
    Example:
        ```python
        async def on_confirm(interaction):
            # Execute dangerous operation
            await delete_data()
            await interaction.response.edit_message(
                embed=create_success_embed("✅ Deleted", "Data deleted successfully"),
                view=None
            )
        
        async def on_cancel(interaction):
            await interaction.response.edit_message(
                embed=create_cancellation_embed(),
                view=None
            )
        
        view = DoubleConfirmationView(
            user_id=interaction.user.id,
            on_confirm=on_confirm,
            on_cancel=on_cancel,
            action_name="Delete Data",
            step1_embed=step1_embed,
            step2_embed=step2_embed
        )
        await interaction.followup.send(embed=step1_embed, view=view, ephemeral=True)
        ```
    """
    
    def __init__(
        self,
        user_id: int,
        on_confirm: Callable[[discord.Interaction], Any],
        on_cancel: Callable[[discord.Interaction], Any],
        action_name: str,
        step1_embed: discord.Embed,
        step2_embed: discord.Embed,
        confirm_style: discord.ButtonStyle = discord.ButtonStyle.danger
    ):
        """
        Initialize double confirmation view.
        
        Args:
            user_id: Discord user ID who can interact with this view
            on_confirm: Async callback when confirmed (after step 2)
            on_cancel: Async callback when cancelled
            action_name: Name of the action (e.g., "Delete History")
            step1_embed: Embed to show in step 1
            step2_embed: Embed to show in step 2
            confirm_style: Style for final confirm button (default: danger/red)
        """
        super().__init__(timeout=None)  # No timeout!
        self.user_id = user_id
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.action_name = action_name
        self.step1_embed = step1_embed
        self.step2_embed = step2_embed
        self.confirm_style = confirm_style
        self.step = 1
        
        # Initialize with step 1 buttons
        self._setup_step1_buttons()
    
    def _setup_step1_buttons(self):
        """Setup buttons for step 1."""
        self.clear_items()
        
        understand_button = discord.ui.Button(
            label="I Understand",
            style=discord.ButtonStyle.primary,
            emoji="⚠️"
        )
        understand_button.callback = self._understand_callback
        
        cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            emoji="❌"
        )
        cancel_button.callback = self._cancel_callback
        
        self.add_item(understand_button)
        self.add_item(cancel_button)
    
    def _setup_step2_buttons(self):
        """Setup buttons for step 2."""
        self.clear_items()
        
        confirm_button = discord.ui.Button(
            label=f"Confirm {self.action_name}",
            style=self.confirm_style,
            emoji="🗑️"
        )
        confirm_button.callback = self._confirm_callback
        
        back_button = discord.ui.Button(
            label="Go Back",
            style=discord.ButtonStyle.secondary,
            emoji="◀️"
        )
        back_button.callback = self._back_callback
        
        self.add_item(confirm_button)
        self.add_item(back_button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Validate that only the command requester can interact.
        
        Args:
            interaction: Discord interaction
            
        Returns:
            True if user is authorized, False otherwise
        """
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ You cannot interact with this confirmation.",
                ephemeral=True
            )
            return False
        return True
    
    async def _understand_callback(self, interaction: discord.Interaction):
        """Handle 'I Understand' button click (step 1 → step 2)."""
        self.step = 2
        self._setup_step2_buttons()
        await interaction.response.edit_message(
            embed=self.step2_embed,
            view=self
        )
    
    async def _back_callback(self, interaction: discord.Interaction):
        """Handle 'Go Back' button click (step 2 → step 1)."""
        self.step = 1
        self._setup_step1_buttons()
        await interaction.response.edit_message(
            embed=self.step1_embed,
            view=self
        )
    
    async def _confirm_callback(self, interaction: discord.Interaction):
        """Handle final confirm button click (step 2)."""
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        # Call user's confirm handler
        await self.on_confirm(interaction)
        self.stop()
    
    async def _cancel_callback(self, interaction: discord.Interaction):
        """Handle cancel button click."""
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        # Call user's cancel handler
        await self.on_cancel(interaction)
        self.stop()


async def confirm_dangerous_action(
    interaction: discord.Interaction,
    action_name: str,
    warning_message: str,
    details_fields: List[Dict[str, Any]],
    on_confirm: Callable[[discord.Interaction], Any],
    thumbnail_url: Optional[str] = None
) -> None:
    """
    Show a double confirmation dialog for a dangerous action.
    
    This is a convenience function that creates the embeds and view automatically.
    
    Args:
        interaction: Discord interaction (should be deferred)
        action_name: Name of the action (e.g., "Clear History")
        warning_message: Warning message to display
        details_fields: List of detail fields to show
        on_confirm: Async callback when confirmed
        thumbnail_url: Optional thumbnail URL
        
    Example:
        ```python
        await confirm_dangerous_action(
            interaction=interaction,
            action_name="Clear History",
            warning_message="This will permanently delete all conversation history!",
            details_fields=[
                {"name": "📊 Details", "value": f"• **AI:** {ai_name}\\n• **Messages:** {count}"}
            ],
            on_confirm=clear_history_callback,
            thumbnail_url=thumbnail_url
        )
        ```
    """
    # Create step 1 embed
    step1_embed = create_confirmation_embed(
        title=f"⚠️ {action_name} Confirmation (Step 1/2)",
        description=f"{warning_message}\n\n**Please review the details below carefully.**",
        fields=details_fields,
        color=discord.Color.orange(),
        thumbnail_url=thumbnail_url,
        footer_text=f"Requested by {interaction.user.name}",
        footer_icon_url=interaction.user.display_avatar.url
    )
    
    # Create step 2 embed
    step2_embed = create_confirmation_embed(
        title=f"⚠️ {action_name} Confirmation (Step 2/2)",
        description=f"**Final confirmation required.**\n\n{warning_message}\n\n"
                   f"⚠️ **This action cannot be undone!**",
        fields=details_fields,
        color=discord.Color.red(),
        thumbnail_url=thumbnail_url,
        footer_text=f"Requested by {interaction.user.name}",
        footer_icon_url=interaction.user.display_avatar.url
    )
    
    # Create cancel callback
    async def on_cancel(cancel_interaction: discord.Interaction):
        cancel_embed = create_cancellation_embed(
            title=f"❌ {action_name} Cancelled",
            description="No changes were made."
        )
        await cancel_interaction.response.edit_message(
            embed=cancel_embed,
            view=None
        )
    
    # Create view
    view = DoubleConfirmationView(
        user_id=interaction.user.id,
        on_confirm=on_confirm,
        on_cancel=on_cancel,
        action_name=action_name,
        step1_embed=step1_embed,
        step2_embed=step2_embed
    )
    
    # Send confirmation dialog
    await interaction.followup.send(
        embed=step1_embed,
        view=view,
        ephemeral=True
    )


async def confirm_simple_action(
    interaction: discord.Interaction,
    title: str,
    description: str,
    details_fields: List[Dict[str, Any]],
    on_confirm: Callable[[discord.Interaction], Any],
    thumbnail_url: Optional[str] = None,
    confirm_label: str = "Confirm",
    cancel_label: str = "Cancel"
) -> None:
    """
    Show a simple single-step confirmation dialog.
    
    This is a convenience function for non-critical confirmations.
    
    Args:
        interaction: Discord interaction (should be deferred)
        title: Confirmation title
        description: Confirmation description
        details_fields: List of detail fields to show
        on_confirm: Async callback when confirmed
        thumbnail_url: Optional thumbnail URL
        confirm_label: Label for confirm button
        cancel_label: Label for cancel button
        
    Example:
        ```python
        await confirm_simple_action(
            interaction=interaction,
            title="Apply Character Card",
            description="Apply this character card to the AI?",
            details_fields=[
                {"name": "📊 Details", "value": f"• **Card:** {card_name}"}
            ],
            on_confirm=apply_card_callback,
            thumbnail_url=thumbnail_url
        )
        ```
    """
    # Create confirmation embed
    embed = create_confirmation_embed(
        title=title,
        description=description,
        fields=details_fields,
        color=discord.Color.blue(),
        thumbnail_url=thumbnail_url,
        footer_text=f"Requested by {interaction.user.name}",
        footer_icon_url=interaction.user.display_avatar.url
    )
    
    # Create cancel callback
    async def on_cancel(cancel_interaction: discord.Interaction):
        cancel_embed = create_cancellation_embed()
        await cancel_interaction.response.edit_message(
            embed=cancel_embed,
            view=None
        )
    
    # Create view
    view = ConfirmationView(
        user_id=interaction.user.id,
        on_confirm=on_confirm,
        on_cancel=on_cancel,
        confirm_label=confirm_label,
        cancel_label=cancel_label
    )
    
    # Send confirmation dialog
    await interaction.followup.send(
        embed=embed,
        view=view,
        ephemeral=True
    )
