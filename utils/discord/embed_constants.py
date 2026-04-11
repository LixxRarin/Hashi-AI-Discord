"""
Centralized constants for Discord embed styling and formatting.

This module provides a standardized color palette, emoji mappings, and style
definitions used across all embeds in the bot.
"""

from enum import Enum
from typing import Dict, Optional
import discord


class EmbedStyle(Enum):
    """Predefined embed styles with associated colors and emojis."""
    
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    CHARACTER = "character"
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEBUG = "debug"
    SYSTEM = "system"
    LLM = "llm"
    TOOL_BASH = "tool_bash"
    TOOL_MEMORY = "tool_memory"
    TOOL_GENERIC = "tool_generic"
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    CRITICAL = "critical"


class EmbedColors:
    """Standardized color palette for embeds."""
    
    SUCCESS = discord.Color.green()
    ERROR = discord.Color.red()
    WARNING = discord.Color.gold()
    INFO = discord.Color.blue()
    CHARACTER = discord.Color.purple()
    ACTIVE = discord.Color.green()
    INACTIVE = discord.Color.greyple()
    DEBUG = discord.Color.dark_embed()
    SYSTEM = discord.Color.blue()
    LLM = discord.Color.dark_embed()
    TOOL_BASH = discord.Color.purple()
    TOOL_MEMORY = discord.Color.blue()
    TOOL_GENERIC = discord.Color.teal()
    STARTUP = discord.Color.brand_green()
    SHUTDOWN = discord.Color.orange()
    CRITICAL = discord.Color.dark_red()
    
    @classmethod
    def get(cls, style: EmbedStyle) -> discord.Color:
        """Get color for a given style."""
        return getattr(cls, style.value.upper())


class EmbedEmojis:
    """Standardized emoji mappings for embed titles and fields."""
    
    # Status emojis
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    INFO = "ℹ️"
    ACTIVE = "🟢"
    INACTIVE = "⚪"
    
    # Category emojis
    CHARACTER = "🎭"
    DEBUG = "🔧"
    SYSTEM = "⚙️"
    LLM = "🤖"
    TOOL = "🔨"
    
    # Action emojis
    ADD = "➕"
    REMOVE = "➖"
    EDIT = "✏️"
    VIEW = "👁️"
    SEARCH = "🔍"
    SETTINGS = "⚙️"
    
    # Data emojis
    STATS = "📊"
    TIME = "⏰"
    USER = "👤"
    SERVER = "🏠"
    MESSAGE = "💬"
    FILE = "📄"
    LINK = "🔗"
    KEY = "🔑"
    
    # Navigation emojis
    FIRST = "⏮️"
    PREVIOUS = "◀️"
    NEXT = "▶️"
    LAST = "⏭️"
    
    @classmethod
    def get_style_emoji(cls, style: EmbedStyle) -> str:
        """Get emoji for a given style."""
        mapping = {
            EmbedStyle.SUCCESS: cls.SUCCESS,
            EmbedStyle.ERROR: cls.ERROR,
            EmbedStyle.WARNING: cls.WARNING,
            EmbedStyle.INFO: cls.INFO,
            EmbedStyle.CHARACTER: cls.CHARACTER,
            EmbedStyle.ACTIVE: cls.ACTIVE,
            EmbedStyle.INACTIVE: cls.INACTIVE,
            EmbedStyle.DEBUG: cls.DEBUG,
            EmbedStyle.SYSTEM: cls.SYSTEM,
            EmbedStyle.LLM: cls.LLM,
            EmbedStyle.TOOL_BASH: cls.TOOL,
            EmbedStyle.TOOL_MEMORY: cls.TOOL,
            EmbedStyle.TOOL_GENERIC: cls.TOOL,
            EmbedStyle.STARTUP: cls.SUCCESS,
            EmbedStyle.SHUTDOWN: cls.WARNING,
            EmbedStyle.CRITICAL: cls.ERROR,
        }
        return mapping.get(style, cls.INFO)


class FooterType(Enum):
    """Types of footer content."""
    
    HINT = "hint"  # Usage hints (e.g., "Use /command to...")
    NAVIGATION = "navigation"  # Page numbers (e.g., "Page 1/5")
    INFO = "info"  # Server/version info
    TIMESTAMP = "timestamp"  # Just timestamp, no text
    CUSTOM = "custom"  # Custom text


# Discord embed limits
EMBED_LIMITS = {
    "title": 256,
    "description": 4096,
    "fields": 25,
    "field_name": 256,
    "field_value": 1024,
    "footer": 2048,
    "author": 256,
    "total_characters": 6000,
}


# Default thumbnail URLs
DEFAULT_THUMBNAILS = {
    "success": None,  # Use bot avatar
    "error": None,
    "warning": None,
    "info": None,
}


# Field formatting
FIELD_BULLET = "•"
FIELD_SEPARATOR = "─" * 20
