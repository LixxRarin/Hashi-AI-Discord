"""
Reusable embed templates for common use cases.

This module provides high-level templates that combine the EmbedBuilder
with common patterns used throughout the bot.
"""

from typing import List, Dict, Any, Optional, Callable, Union
import discord

from .embed_builder import EmbedBuilder
from .embed_constants import EmbedStyle, EmbedEmojis, FIELD_BULLET


class EmbedTemplate:
    """Collection of reusable embed templates."""
    
    @staticmethod
    def list_items(
        title: str,
        items: List[Any],
        formatter: Callable[[Any], str],
        style: EmbedStyle = EmbedStyle.INFO,
        description: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        footer_hint: Optional[str] = None,
        current_page: Optional[int] = None,
        total_pages: Optional[int] = None,
        empty_message: str = "No items found.",
        max_items_per_page: int = 10
    ) -> discord.Embed:
        """
        Create a list embed with formatted items.
        
        Args:
            title: Embed title
            items: List of items to display
            formatter: Function to format each item as a string
            style: Embed style
            description: Optional description
            thumbnail_url: Optional thumbnail URL
            footer_hint: Optional footer hint
            current_page: Current page number (for pagination)
            total_pages: Total pages (for pagination)
            empty_message: Message to show when list is empty
            max_items_per_page: Maximum items to show
            
        Returns:
            List embed
        """
        builder = EmbedBuilder(style)
        
        # Add count to title
        count = len(items)
        full_title = f"{title} ({count})" if count > 0 else title
        builder.set_title(full_title)
        
        if description:
            builder.set_description(description)
        
        if thumbnail_url:
            builder.set_thumbnail(thumbnail_url)
        
        # Format items
        if items:
            items_text = "\n".join([
                f"{FIELD_BULLET} {formatter(item)}" 
                for item in items[:max_items_per_page]
            ])
            builder.set_description(items_text if not description else f"{description}\n\n{items_text}")
        else:
            builder.set_description(empty_message)
        
        # Footer
        if current_page and total_pages:
            builder.set_footer_navigation(current_page, total_pages)
        elif footer_hint:
            builder.set_footer_hint(footer_hint)
        
        return builder.build()
    
    @staticmethod
    def detail_view(
        title: str,
        sections: List[Dict[str, Any]],
        style: EmbedStyle = EmbedStyle.INFO,
        description: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        image_url: Optional[str] = None,
        footer_hint: Optional[str] = None,
        author_name: Optional[str] = None,
        author_icon_url: Optional[str] = None
    ) -> discord.Embed:
        """
        Create a detailed view embed with organized sections.
        
        Args:
            title: Embed title
            sections: List of sections, each with 'name', 'value', 'inline', and optional 'emoji'
            style: Embed style
            description: Optional description
            thumbnail_url: Optional thumbnail URL
            image_url: Optional image URL
            footer_hint: Optional footer hint
            author_name: Optional author name
            author_icon_url: Optional author icon URL
            
        Returns:
            Detail view embed
        """
        builder = EmbedBuilder(style).set_title(title)
        
        if description:
            builder.set_description(description)
        
        if author_name:
            builder.set_author(author_name, icon_url=author_icon_url)
        
        if thumbnail_url:
            builder.set_thumbnail(thumbnail_url)
        
        if image_url:
            builder.set_image(image_url)
        
        # Add sections as fields
        builder.add_fields(sections)
        
        if footer_hint:
            builder.set_footer_hint(footer_hint)
        
        return builder.build()
    
    @staticmethod
    def status_display(
        title: str,
        is_active: bool,
        status_fields: List[Dict[str, Any]],
        description: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        footer_hint: Optional[str] = None,
        last_updated: Optional[str] = None
    ) -> discord.Embed:
        """
        Create a status display embed.
        
        Args:
            title: Embed title
            is_active: Whether the item is active
            status_fields: List of status fields
            description: Optional description
            thumbnail_url: Optional thumbnail URL
            footer_hint: Optional footer hint
            last_updated: Optional last updated timestamp text
            
        Returns:
            Status embed
        """
        style = EmbedStyle.ACTIVE if is_active else EmbedStyle.INACTIVE
        builder = EmbedBuilder(style).set_title(title)
        
        # Add status indicator to description
        status_emoji = EmbedEmojis.ACTIVE if is_active else EmbedEmojis.INACTIVE
        status_text = "Active" if is_active else "Inactive"
        status_line = f"{status_emoji} **Status:** {status_text}"
        
        if description:
            full_description = f"{status_line}\n\n{description}"
        else:
            full_description = status_line
        
        builder.set_description(full_description)
        
        if thumbnail_url:
            builder.set_thumbnail(thumbnail_url)
        
        # Add status fields
        builder.add_fields(status_fields)
        
        # Footer
        if last_updated:
            footer_text = f"Last updated: {last_updated}"
            if footer_hint:
                footer_text += f" • {footer_hint}"
            builder.set_footer(footer_text)
        elif footer_hint:
            builder.set_footer_hint(footer_hint)
        
        return builder.build()
    
    @staticmethod
    def confirmation(
        action: str,
        details: str,
        warning: bool = False,
        fields: Optional[List[Dict[str, Any]]] = None,
        footer_hint: Optional[str] = None
    ) -> discord.Embed:
        """
        Create a confirmation dialog embed.
        
        Args:
            action: The action to confirm
            details: Details about the action
            warning: Whether this is a destructive action
            fields: Optional additional fields
            footer_hint: Optional footer hint
            
        Returns:
            Confirmation embed
        """
        style = EmbedStyle.WARNING if warning else EmbedStyle.INFO
        builder = EmbedBuilder(style).set_title(f"Confirm: {action}")
        
        builder.set_description(details)
        
        if fields:
            builder.add_fields(fields)
        
        if footer_hint:
            builder.set_footer_hint(footer_hint)
        else:
            builder.set_footer_hint("Click the buttons below to confirm or cancel")
        
        return builder.build()
    
    @staticmethod
    def wizard_step(
        step_number: int,
        total_steps: int,
        step_title: str,
        instructions: str,
        current_value: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None,
        thumbnail_url: Optional[str] = None
    ) -> discord.Embed:
        """
        Create a wizard step embed for multi-step processes.
        
        Args:
            step_number: Current step number (1-indexed)
            total_steps: Total number of steps
            step_title: Title for this step
            instructions: Instructions for this step
            current_value: Current value/selection
            fields: Optional additional fields
            thumbnail_url: Optional thumbnail URL
            
        Returns:
            Wizard step embed
        """
        builder = EmbedBuilder(EmbedStyle.INFO)
        
        # Title with progress
        title = f"Step {step_number}/{total_steps}: {step_title}"
        builder.set_title(title, auto_emoji=False)
        
        # Description with instructions
        description = instructions
        if current_value:
            description += f"\n\n**Current selection:** {current_value}"
        
        builder.set_description(description)
        
        if thumbnail_url:
            builder.set_thumbnail(thumbnail_url)
        
        if fields:
            builder.add_fields(fields)
        
        # Progress indicator in footer
        progress_bar = "█" * step_number + "░" * (total_steps - step_number)
        builder.set_footer(f"Progress: {progress_bar}")
        
        return builder.build()
    
    @staticmethod
    def success_action(
        action: str,
        details: str,
        fields: Optional[List[Dict[str, Any]]] = None,
        thumbnail_url: Optional[str] = None,
        footer_hint: Optional[str] = None
    ) -> discord.Embed:
        """
        Create a success message embed for completed actions.
        
        Args:
            action: The action that was completed
            details: Details about the result
            fields: Optional additional fields
            thumbnail_url: Optional thumbnail URL
            footer_hint: Optional footer hint
            
        Returns:
            Success embed
        """
        builder = EmbedBuilder(EmbedStyle.SUCCESS).set_title(action)
        builder.set_description(details)
        
        if thumbnail_url:
            builder.set_thumbnail(thumbnail_url)
        
        if fields:
            builder.add_fields(fields)
        
        if footer_hint:
            builder.set_footer_hint(footer_hint)
        
        return builder.build()
    
    @staticmethod
    def error_message(
        error_title: str,
        error_details: str,
        solution: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None,
        footer_hint: Optional[str] = None
    ) -> discord.Embed:
        """
        Create an error message embed.
        
        Args:
            error_title: Title describing the error
            error_details: Detailed error message
            solution: Optional suggested solution
            fields: Optional additional fields
            footer_hint: Optional footer hint
            
        Returns:
            Error embed
        """
        builder = EmbedBuilder(EmbedStyle.ERROR).set_title(error_title)
        
        description = error_details
        if solution:
            description += f"\n\n**Solution:** {solution}"
        
        builder.set_description(description)
        
        if fields:
            builder.add_fields(fields)
        
        if footer_hint:
            builder.set_footer_hint(footer_hint)
        
        return builder.build()
    
    @staticmethod
    def comparison(
        title: str,
        before: Dict[str, str],
        after: Dict[str, str],
        style: EmbedStyle = EmbedStyle.INFO,
        description: Optional[str] = None,
        footer_hint: Optional[str] = None
    ) -> discord.Embed:
        """
        Create a comparison embed showing before/after values.
        
        Args:
            title: Embed title
            before: Dict of field names to before values
            after: Dict of field names to after values
            style: Embed style
            description: Optional description
            footer_hint: Optional footer hint
            
        Returns:
            Comparison embed
        """
        builder = EmbedBuilder(style).set_title(title)
        
        if description:
            builder.set_description(description)
        
        # Add comparison fields
        for key in before.keys():
            before_val = before.get(key, "N/A")
            after_val = after.get(key, "N/A")
            
            builder.add_field(
                name=key,
                value=f"**Before:** {before_val}\n**After:** {after_val}",
                inline=False
            )
        
        if footer_hint:
            builder.set_footer_hint(footer_hint)
        
        return builder.build()
    
    @staticmethod
    def statistics(
        title: str,
        stats: Dict[str, str],
        style: EmbedStyle = EmbedStyle.INFO,
        description: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        footer_hint: Optional[str] = None,
        inline_fields: bool = True
    ) -> discord.Embed:
        """
        Create a statistics display embed.
        
        Args:
            title: Embed title
            stats: Dict of stat names to values
            style: Embed style
            description: Optional description
            thumbnail_url: Optional thumbnail URL
            footer_hint: Optional footer hint
            inline_fields: Whether to display stats inline
            
        Returns:
            Statistics embed
        """
        builder = EmbedBuilder(style).set_title(title)
        
        if description:
            builder.set_description(description)
        
        if thumbnail_url:
            builder.set_thumbnail(thumbnail_url)
        
        # Add stats as fields
        for name, value in stats.items():
            builder.add_field(
                name=name,
                value=str(value),
                inline=inline_fields,
                emoji=EmbedEmojis.STATS
            )
        
        if footer_hint:
            builder.set_footer_hint(footer_hint)
        
        return builder.build()
