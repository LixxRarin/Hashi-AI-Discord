"""
Pagination utility for Discord embeds with button navigation.

Provides a reusable View class for paginating through multiple embeds
using Discord UI buttons instead of reactions.
"""
import discord
from discord import ui
from typing import List, Optional
import logging

log = logging.getLogger(__name__)


class PaginatedView(ui.View):
    """
    Discord UI View for paginating through embeds with buttons.
    
    Features:
    - Four navigation buttons: First, Previous, Next, Last
    - Automatic button state management (disable when not applicable)
    - Page counter display
    - Configurable timeout
    - Support for file attachments (thumbnails)
    
    Example:
        >>> embeds = [embed1, embed2, embed3]
        >>> view = PaginatedView(embeds, timeout=180)
        >>> await interaction.followup.send(
        ...     embed=view.get_current_embed(),
        ...     view=view,
        ...     ephemeral=True
        ... )
    """
    
    def __init__(
        self,
        embeds: List[discord.Embed],
        files: Optional[List[Optional[discord.File]]] = None,
        timeout: float = 180.0,
        user_id: Optional[int] = None
    ):
        """
        Initialize the paginated view.
        
        Args:
            embeds: List of embeds to paginate through
            files: Optional list of files (one per embed, can be None)
            timeout: Timeout in seconds (default: 180)
            user_id: Optional user ID to restrict interaction (default: None = anyone)
        """
        super().__init__(timeout=timeout)
        
        if not embeds:
            raise ValueError("embeds list cannot be empty")
        
        self.embeds = embeds
        self.files = files or [None] * len(embeds)
        self.current_page = 0
        self.total_pages = len(embeds)
        self.user_id = user_id
        self.message: Optional[discord.Message] = None
        
        # Update button states
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current page."""
        # Disable first/previous on first page
        self.first_button.disabled = (self.current_page == 0)
        self.previous_button.disabled = (self.current_page == 0)
        
        # Disable next/last on last page
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
        self.last_button.disabled = (self.current_page >= self.total_pages - 1)
        
        # Update page counter label
        self.page_counter.label = f"Page {self.current_page + 1}/{self.total_pages}"
    
    def get_current_embed(self) -> discord.Embed:
        """Get the current embed with updated footer."""
        embed = self.embeds[self.current_page]
        
        # Add page info to footer if not already present
        footer_text = embed.footer.text if embed.footer else ""
        if not footer_text or "Page" not in footer_text:
            if footer_text:
                footer_text = f"{footer_text} • Page {self.current_page + 1}/{self.total_pages}"
            else:
                footer_text = f"Page {self.current_page + 1}/{self.total_pages}"
            embed.set_footer(text=footer_text)
        
        return embed
    
    def get_current_file(self) -> Optional[discord.File]:
        """Get the current file attachment if available."""
        return self.files[self.current_page] if self.files else None
    
    async def _update_message(self, interaction: discord.Interaction):
        """Update the message with current page."""
        try:
            self._update_buttons()
            
            current_file = self.get_current_file()
            
            # If there's a file, we need to edit with the file
            # Note: Discord doesn't allow editing attachments, so we keep the original
            await interaction.response.edit_message(
                embed=self.get_current_embed(),
                view=self
            )
            
        except discord.NotFound:
            log.warning("Message not found when trying to update pagination")
        except discord.HTTPException as e:
            log.error(f"HTTP error updating pagination: {e}")
        except Exception as e:
            log.error(f"Error updating pagination message: {e}", exc_info=True)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the user is allowed to interact with this view."""
        # If user_id is set, only that user can interact
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ You cannot interact with this pagination.",
                ephemeral=True
            )
            return False
        return True
    
    async def on_timeout(self):
        """Called when the view times out."""
        try:
            # Disable all buttons
            for item in self.children:
                if isinstance(item, ui.Button):
                    item.disabled = True
            
            # Update the message if we have a reference
            if self.message:
                await self.message.edit(view=self)
        except discord.NotFound:
            pass  # Message was deleted
        except Exception as e:
            log.error(f"Error handling pagination timeout: {e}")
    
    @ui.button(label="⏮️", style=discord.ButtonStyle.secondary, custom_id="first")
    async def first_button(self, interaction: discord.Interaction, button: ui.Button):
        """Go to first page."""
        self.current_page = 0
        await self._update_message(interaction)
    
    @ui.button(label="◀️", style=discord.ButtonStyle.primary, custom_id="previous")
    async def previous_button(self, interaction: discord.Interaction, button: ui.Button):
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
        await self._update_message(interaction)
    
    @ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, custom_id="counter", disabled=True)
    async def page_counter(self, interaction: discord.Interaction, button: ui.Button):
        """Page counter (non-interactive)."""
        pass  # This button is just for display
    
    @ui.button(label="▶️", style=discord.ButtonStyle.primary, custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        """Go to next page."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        await self._update_message(interaction)
    
    @ui.button(label="⏭️", style=discord.ButtonStyle.secondary, custom_id="last")
    async def last_button(self, interaction: discord.Interaction, button: ui.Button):
        """Go to last page."""
        self.current_page = self.total_pages - 1
        await self._update_message(interaction)


def create_paginated_embeds(
    items: List[dict],
    items_per_page: int,
    title_template: str,
    color: discord.Color,
    format_item_func,
    description: Optional[str] = None
) -> List[discord.Embed]:
    """
    Helper function to create paginated embeds from a list of items.
    
    Args:
        items: List of items to paginate
        items_per_page: Number of items per page
        title_template: Title template (can include {page} and {total_pages})
        color: Embed color
        format_item_func: Function to format each item (returns tuple of name, value, inline)
        description: Optional description for all embeds
    
    Returns:
        List of embeds
    
    Example:
        >>> def format_ai(ai):
        ...     return (f"🤖 {ai['name']}", f"Provider: {ai['provider']}", True)
        >>> 
        >>> embeds = create_paginated_embeds(
        ...     items=ai_list,
        ...     items_per_page=5,
        ...     title_template="🤖 AIs - Page {page}/{total_pages}",
        ...     color=discord.Color.blue(),
        ...     format_item_func=format_ai
        ... )
    """
    if not items:
        # Return single embed with "no items" message
        embed = discord.Embed(
            title=title_template.format(page=1, total_pages=1),
            description=description or "No items found.",
            color=color
        )
        return [embed]
    
    embeds = []
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    
    for page in range(total_pages):
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(items))
        page_items = items[start_idx:end_idx]
        
        # Create embed for this page
        title = title_template.format(page=page + 1, total_pages=total_pages)
        embed = discord.Embed(title=title, color=color)
        
        if description:
            embed.description = description
        
        # Add items as fields
        for item in page_items:
            name, value, inline = format_item_func(item)
            embed.add_field(name=name, value=value, inline=inline)
        
        embeds.append(embed)
    
    return embeds
