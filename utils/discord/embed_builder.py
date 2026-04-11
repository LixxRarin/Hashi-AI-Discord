"""
Centralized embed builder for creating standardized Discord embeds.

This module provides a fluent builder pattern for creating consistent, 
visually appealing embeds across the bot.
"""

from typing import Optional, List, Dict, Any, Callable, Union
from datetime import datetime
import discord

from .embed_constants import (
    EmbedStyle,
    EmbedColors,
    EmbedEmojis,
    FooterType,
    EMBED_LIMITS,
    FIELD_BULLET,
    FIELD_SEPARATOR,
)


class EmbedBuilder:
    """
    Fluent builder for creating standardized Discord embeds.
    
    Example:
        embed = EmbedBuilder(EmbedStyle.SUCCESS)
            .set_title("Operation Complete")
            .set_description("Your card has been activated")
            .add_field("Character", "Hashi", inline=True)
            .set_footer_hint("Use /cards to view all cards")
            .build()
    """
    
    def __init__(self, style: EmbedStyle = EmbedStyle.INFO):
        """
        Initialize the embed builder with a style.
        
        Args:
            style: The embed style (determines color and default emoji)
        """
        self.style = style
        self.embed = discord.Embed(color=EmbedColors.get(style))
        self._title_emoji: Optional[str] = None
        self._auto_timestamp = True
        self._footer_icon: Optional[str] = None
        
    def set_title(self, title: str, emoji: Optional[str] = None, auto_emoji: bool = True) -> "EmbedBuilder":
        """
        Set the embed title.
        
        Args:
            title: The title text
            emoji: Custom emoji to use (overrides auto_emoji)
            auto_emoji: If True, automatically adds style-appropriate emoji
            
        Returns:
            Self for chaining
        """
        if emoji:
            self._title_emoji = emoji
        elif auto_emoji:
            self._title_emoji = EmbedEmojis.get_style_emoji(self.style)
        
        full_title = f"{self._title_emoji} {title}" if self._title_emoji else title
        
        # Validate length
        if len(full_title) > EMBED_LIMITS["title"]:
            full_title = full_title[:EMBED_LIMITS["title"] - 3] + "..."
            
        self.embed.title = full_title
        return self
    
    def set_description(self, description: str) -> "EmbedBuilder":
        """
        Set the embed description.
        
        Args:
            description: The description text
            
        Returns:
            Self for chaining
        """
        # Validate length
        if len(description) > EMBED_LIMITS["description"]:
            description = description[:EMBED_LIMITS["description"] - 3] + "..."
            
        self.embed.description = description
        return self
    
    def add_field(
        self,
        name: str,
        value: str,
        inline: bool = False,
        emoji: Optional[str] = None
    ) -> "EmbedBuilder":
        """
        Add a field to the embed.
        
        Args:
            name: Field name
            value: Field value
            inline: Whether the field should be inline
            emoji: Optional emoji prefix for the field name
            
        Returns:
            Self for chaining
        """
        # Add emoji to name if provided
        if emoji:
            name = f"{emoji} {name}"
        
        # Validate lengths
        if len(name) > EMBED_LIMITS["field_name"]:
            name = name[:EMBED_LIMITS["field_name"] - 3] + "..."
        if len(value) > EMBED_LIMITS["field_value"]:
            value = value[:EMBED_LIMITS["field_value"] - 3] + "..."
        
        # Check field count limit
        if len(self.embed.fields) >= EMBED_LIMITS["fields"]:
            return self
            
        self.embed.add_field(name=name, value=value, inline=inline)
        return self
    
    def add_fields(
        self,
        fields: List[Dict[str, Any]],
        inline: bool = False
    ) -> "EmbedBuilder":
        """
        Add multiple fields at once.
        
        Args:
            fields: List of dicts with 'name', 'value', and optionally 'inline' and 'emoji'
            inline: Default inline value if not specified in field dict
            
        Returns:
            Self for chaining
        """
        for field in fields:
            self.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", inline),
                emoji=field.get("emoji")
            )
        return self
    
    def add_separator(self) -> "EmbedBuilder":
        """
        Add a visual separator field.
        
        Returns:
            Self for chaining
        """
        self.add_field(name=FIELD_SEPARATOR, value="", inline=False)
        return self
    
    def set_footer(
        self,
        text: str,
        icon_url: Optional[str] = None
    ) -> "EmbedBuilder":
        """
        Set custom footer text.
        
        Args:
            text: Footer text
            icon_url: Optional icon URL for footer
            
        Returns:
            Self for chaining
        """
        if len(text) > EMBED_LIMITS["footer"]:
            text = text[:EMBED_LIMITS["footer"] - 3] + "..."
            
        self.embed.set_footer(text=text, icon_url=icon_url)
        self._footer_icon = icon_url
        return self
    
    def set_footer_hint(self, hint: str, icon_url: Optional[str] = None) -> "EmbedBuilder":
        """
        Set footer with a usage hint.
        
        Args:
            hint: Hint text (e.g., "Use /command to...")
            icon_url: Optional icon URL
            
        Returns:
            Self for chaining
        """
        return self.set_footer(f"💡 {hint}", icon_url)
    
    def set_footer_navigation(
        self,
        current_page: int,
        total_pages: int,
        icon_url: Optional[str] = None
    ) -> "EmbedBuilder":
        """
        Set footer with page navigation info.
        
        Args:
            current_page: Current page number (1-indexed)
            total_pages: Total number of pages
            icon_url: Optional icon URL
            
        Returns:
            Self for chaining
        """
        return self.set_footer(f"Page {current_page}/{total_pages}", icon_url)
    
    def set_footer_info(
        self,
        info: str,
        icon_url: Optional[str] = None
    ) -> "EmbedBuilder":
        """
        Set footer with general info.
        
        Args:
            info: Info text
            icon_url: Optional icon URL
            
        Returns:
            Self for chaining
        """
        return self.set_footer(info, icon_url)
    
    def set_thumbnail(self, url: Optional[str]) -> "EmbedBuilder":
        """
        Set the embed thumbnail (small image in top-right corner).
        
        Args:
            url: Image URL
            
        Returns:
            Self for chaining
        """
        if url:
            self.embed.set_thumbnail(url=url)
        return self
    
    def set_image(self, url: Optional[str]) -> "EmbedBuilder":
        """
        Set the embed image (large image at bottom).
        
        Args:
            url: Image URL
            
        Returns:
            Self for chaining
        """
        if url:
            self.embed.set_image(url=url)
        return self
    
    def set_author(
        self,
        name: str,
        icon_url: Optional[str] = None,
        url: Optional[str] = None
    ) -> "EmbedBuilder":
        """
        Set the embed author.
        
        Args:
            name: Author name
            icon_url: Optional author icon URL
            url: Optional author URL
            
        Returns:
            Self for chaining
        """
        if len(name) > EMBED_LIMITS["author"]:
            name = name[:EMBED_LIMITS["author"] - 3] + "..."
            
        self.embed.set_author(name=name, icon_url=icon_url, url=url)
        return self
    
    def set_url(self, url: str) -> "EmbedBuilder":
        """
        Set the embed URL (makes title clickable).
        
        Args:
            url: URL to link to
            
        Returns:
            Self for chaining
        """
        self.embed.url = url
        return self
    
    def set_timestamp(self, timestamp: Optional[datetime] = None) -> "EmbedBuilder":
        """
        Set the embed timestamp.
        
        Args:
            timestamp: Datetime object (defaults to now)
            
        Returns:
            Self for chaining
        """
        self.embed.timestamp = timestamp or datetime.utcnow()
        return self
    
    def disable_timestamp(self) -> "EmbedBuilder":
        """
        Disable automatic timestamp.
        
        Returns:
            Self for chaining
        """
        self._auto_timestamp = False
        return self
    
    def build(self) -> discord.Embed:
        """
        Build and return the final embed.
        
        Returns:
            The constructed Discord embed
        """
        # Add timestamp if enabled and not already set
        if self._auto_timestamp and self.embed.timestamp is None:
            self.embed.timestamp = datetime.utcnow()
            
        return self.embed
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> discord.Embed:
        """
        Create an embed from a dictionary (for LLM-generated embeds).
        
        Args:
            data: Dictionary with embed data
            
        Returns:
            Discord embed
        """
        embed = discord.Embed()
        
        if "title" in data:
            embed.title = data["title"][:EMBED_LIMITS["title"]]
        if "description" in data:
            embed.description = data["description"][:EMBED_LIMITS["description"]]
        if "color" in data:
            embed.color = discord.Color(data["color"])
        if "url" in data:
            embed.url = data["url"]
        if "timestamp" in data:
            embed.timestamp = datetime.fromisoformat(data["timestamp"])
            
        if "footer" in data:
            footer = data["footer"]
            embed.set_footer(
                text=footer.get("text", "")[:EMBED_LIMITS["footer"]],
                icon_url=footer.get("icon_url")
            )
            
        if "author" in data:
            author = data["author"]
            embed.set_author(
                name=author.get("name", "")[:EMBED_LIMITS["author"]],
                icon_url=author.get("icon_url"),
                url=author.get("url")
            )
            
        if "thumbnail" in data:
            embed.set_thumbnail(url=data["thumbnail"].get("url"))
            
        if "image" in data:
            embed.set_image(url=data["image"].get("url"))
            
        if "fields" in data:
            for field in data["fields"][:EMBED_LIMITS["fields"]]:
                embed.add_field(
                    name=field.get("name", "")[:EMBED_LIMITS["field_name"]],
                    value=field.get("value", "")[:EMBED_LIMITS["field_value"]],
                    inline=field.get("inline", False)
                )
                
        return embed


def create_success_embed(
    title: str,
    description: str,
    fields: Optional[List[Dict[str, Any]]] = None,
    footer: Optional[str] = None,
    thumbnail_url: Optional[str] = None
) -> discord.Embed:
    """
    Quick helper to create a success embed.
    
    Args:
        title: Embed title
        description: Embed description
        fields: Optional list of fields
        footer: Optional footer text
        thumbnail_url: Optional thumbnail URL
        
    Returns:
        Success embed
    """
    builder = EmbedBuilder(EmbedStyle.SUCCESS).set_title(title).set_description(description)
    
    if fields:
        builder.add_fields(fields)
    if footer:
        builder.set_footer_hint(footer)
    if thumbnail_url:
        builder.set_thumbnail(thumbnail_url)
        
    return builder.build()


def create_error_embed(
    title: str,
    description: str,
    fields: Optional[List[Dict[str, Any]]] = None,
    footer: Optional[str] = None
) -> discord.Embed:
    """
    Quick helper to create an error embed.
    
    Args:
        title: Embed title
        description: Embed description
        fields: Optional list of fields
        footer: Optional footer text
        
    Returns:
        Error embed
    """
    builder = EmbedBuilder(EmbedStyle.ERROR).set_title(title).set_description(description)
    
    if fields:
        builder.add_fields(fields)
    if footer:
        builder.set_footer_hint(footer)
        
    return builder.build()


def create_warning_embed(
    title: str,
    description: str,
    fields: Optional[List[Dict[str, Any]]] = None,
    footer: Optional[str] = None
) -> discord.Embed:
    """
    Quick helper to create a warning embed.
    
    Args:
        title: Embed title
        description: Embed description
        fields: Optional list of fields
        footer: Optional footer text
        
    Returns:
        Warning embed
    """
    builder = EmbedBuilder(EmbedStyle.WARNING).set_title(title).set_description(description)
    
    if fields:
        builder.add_fields(fields)
    if footer:
        builder.set_footer_hint(footer)
        
    return builder.build()


def create_info_embed(
    title: str,
    description: str,
    fields: Optional[List[Dict[str, Any]]] = None,
    footer: Optional[str] = None,
    thumbnail_url: Optional[str] = None
) -> discord.Embed:
    """
    Quick helper to create an info embed.
    
    Args:
        title: Embed title
        description: Embed description
        fields: Optional list of fields
        footer: Optional footer text
        thumbnail_url: Optional thumbnail URL
        
    Returns:
        Info embed
    """
    builder = EmbedBuilder(EmbedStyle.INFO).set_title(title).set_description(description)
    
    if fields:
        builder.add_fields(fields)
    if footer:
        builder.set_footer_hint(footer)
    if thumbnail_url:
        builder.set_thumbnail(thumbnail_url)
        
    return builder.build()
