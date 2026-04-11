"""
Debug Embed System - Guild-Scoped Debug Information

Modular, data-driven debug embed system. Events are defined declaratively
via schemas — no per-event builder methods needed.

Usage:
    await DebugEmbed.send(guild, event="setup", data={...})
    await DebugEmbed.send(guild, event="llm_response", data={...})
    await DebugEmbed.send(guild, event="error", data={...})
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable

import discord

import utils.func as func

log = logging.getLogger(__name__)


# ─── Formatting Helpers ──────────────────────────────────────────────────────

def fmt_number(num: int) -> str:
    """Format number with k/M suffix."""
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return str(num)


def progress_bar(current: int, maximum: int, length: int = 10) -> str:
    """Create a visual progress bar (e.g. ▓▓▓░░░░░░░)."""
    if maximum <= 0:
        return "░" * length
    pct = min(current / maximum, 1.0)
    filled = int(pct * length)
    return "▓" * filled + "░" * (length - filled)


def truncate(text: str, limit: int = 1000) -> str:
    """Truncate text with ellipsis."""
    return text[:limit] + "..." if len(text) > limit else text


def _get_version() -> str:
    """Read bot version from version.txt."""
    try:
        with open("version.txt", "r") as f:
            return f.read().strip()
    except Exception:
        return "Unknown"


# ─── Field Extractors ────────────────────────────────────────────────────────
# Each extractor receives (data: dict) and returns a list of
# (name: str, value: str, inline: bool) tuples to add as embed fields.
# This keeps logic composable and reusable across events.

def _fields_command(data: Dict[str, Any]) -> List[tuple]:
    """Extract fields for generic command events."""
    fields = []
    
    executor = data.get("executor")
    channel = data.get("channel")
    if executor:
        fields.append(("Executed By", str(executor), True))
    if channel:
        fields.append(("Channel", str(channel), True))
    
    # Render arbitrary key-value changes
    for key, value in data.get("changes", {}).items():
        fields.append((key.replace("_", " ").title(), str(value), False))
    
    # API connection specifics
    for key in ("connection_name", "provider", "endpoint", "model"):
        if key in data:
            fields.append((key.replace("_", " ").title(), str(data[key]), True))
    
    # Config change specifics
    if "setting" in data:
        fields.append(("Setting", data["setting"], True))
    if "category" in data:
        fields.append(("Category", data["category"], True))
    if "old_value" in data and "new_value" in data:
        fields.append(("Change", f"`{data['old_value']}` → `{data['new_value']}`", False))
    
    return fields


def _fields_llm_response(data: Dict[str, Any]) -> List[tuple]:
    """Extract fields for LLM response events."""
    fields = []
    
    provider_raw = data.get("provider", "unknown")
    model = data.get("model", "unknown")
    
    # Resolve display name
    try:
        from AI.core.registry import get_registry
        registry = get_registry()
        provider_display = registry.get_metadata(provider_raw.lower()).display_name
    except Exception:
        provider_display = provider_raw
    
    fields.append(("Provider & Model", f"{provider_display} • `{model}`", False))
    
    channel_mention = data.get("channel")
    if channel_mention:
        fields.append(("Channel", str(channel_mention), True))
    
    # Token breakdown
    tokens = data.get("tokens", {})
    if tokens:
        sys_t = tokens.get("system", 0)
        ctx_t = tokens.get("context", 0)
        comp_t = tokens.get("completion", 0)
        total_t = tokens.get("total", 0)
        window = tokens.get("context_window", 0)
        
        lines = [
            f"**System:** {fmt_number(sys_t)} · **Context:** {fmt_number(ctx_t)}",
            f"**Completion:** {fmt_number(comp_t)} · **Total:** {fmt_number(total_t)}"
        ]
        
        if window > 0:
            pct = (total_t / window) * 100
            bar = progress_bar(total_t, window)
            lines.append(f"{bar} {fmt_number(total_t)}/{fmt_number(window)} ({pct:.1f}%)")
        
        fields.append(("Token Usage", "\n".join(lines), False))
    
    # Memory
    memory = data.get("memory", {})
    if memory:
        msg_count = memory.get("messages_count", 0)
        est = memory.get("estimated_tokens", 0)
        fields.append(("Memory", f"{msg_count} messages · ~{fmt_number(est)} tokens", True))
    
    # Tool calls
    tool_calls = data.get("tool_calls", [])
    if tool_calls:
        tool_lines = [f"• **{c.get('name', '?')}**: {c.get('result', 'N/A')}" for c in tool_calls[:5]]
        if len(tool_calls) > 5:
            tool_lines.append(f"… and {len(tool_calls) - 5} more")
        fields.append(("Tool Calls", "\n".join(tool_lines), False))
    
    # Performance
    latency = data.get("latency_ms")
    tps = data.get("tps")
    if latency is not None or tps is not None:
        parts = []
        if latency is not None:
            parts.append(f"**Latency:** {latency}ms")
        if tps is not None:
            parts.append(f"**Speed:** {tps:.1f} tok/s")
        fields.append(("Performance", " · ".join(parts), True))
    
    # Raw response
    raw = data.get("raw_response", "")
    if raw:
        fields.append(("Raw Response", f"```\n{truncate(raw, 900)}\n```", False))
    
    return fields


def _fields_ignore(data: Dict[str, Any]) -> List[tuple]:
    """Extract fields for ignore detection events."""
    fields = []
    
    ignore_type = data.get("ignore_type", "unknown")
    is_pure = ignore_type == "pure"
    
    fields.append(("Ignore Type", ignore_type.title(), True))
    
    channel = data.get("channel")
    if channel:
        fields.append(("Channel", str(channel), True))
    
    raw = data.get("raw_response", "")
    if raw:
        fields.append(("Raw Response", f"```\n{truncate(raw, 500)}\n```", False))
    
    # Sleep mode (only for pure ignores)
    if data.get("sleep_mode_enabled") and is_pure:
        active = data.get("sleep_mode_active", False)
        consecutive = data.get("consecutive_ignores", 0)
        threshold = data.get("ignore_threshold", 3)
        
        fields.append(("Sleep Mode", "🟢 Active" if active else "⚪ Inactive", True))
        fields.append(("Ignores", f"{consecutive} / {threshold}", True))
        
        if data.get("just_entered_sleep"):
            fields.append(("⚡ Sleep Triggered", f"Entered after {consecutive} consecutive ignores", False))
    
    # Impure guidance
    if not is_pure:
        fields.append(("⚠️ Issue", "<IGNORE> tag found with additional content. Use ONLY `<IGNORE>` without extra text.", False))
    
    return fields


def _fields_system(data: Dict[str, Any]) -> List[tuple]:
    """Extract fields for system lifecycle events (startup, shutdown, sleep, status)."""
    fields = []
    
    # Generic fields
    for key in ("version", "reason"):
        if key in data:
            fields.append((key.title(), str(data[key]), True))
    
    for key in ("servers", "total_ais"):
        if key in data:
            fields.append((key.replace("_", " ").title(), str(data[key]), True))
    
    # Status change
    if "old_status" in data and "new_status" in data:
        fields.append(("Status", f"{data['old_status']} → {data['new_status']}", False))
    
    # Sleep mode specifics
    if "status" in data:
        fields.append(("Status", data["status"].title(), True))
    
    channel = data.get("channel")
    if channel:
        fields.append(("Channel", str(channel), True))
    
    # Uptime
    uptime = data.get("uptime")
    if uptime is not None:
        h, m = int(uptime // 3600), int((uptime % 3600) // 60)
        fields.append(("Uptime", f"{h}h {m}m", True))
    
    # AIs in sleep
    ais = data.get("ais_in_sleep", [])
    if ais:
        text = "\n".join(f"• {a}" for a in ais[:10])
        if len(ais) > 10:
            text += f"\n… and {len(ais) - 10} more"
        fields.append(("AIs in Sleep", text, False))
    
    return fields


def _fields_error(data: Dict[str, Any]) -> List[tuple]:
    """Extract fields for error/warning/critical events."""
    fields = []
    
    if "error_type" in data:
        fields.append(("Error Type", data["error_type"], True))
    
    msg = data.get("message")
    if msg:
        fields.append(("Message", truncate(msg, 1000), False))
    
    ctx = data.get("context", {})
    if ctx:
        text = "\n".join(f"**{k.replace('_', ' ').title()}:** {v}" for k, v in ctx.items())
        fields.append(("Context", text, False))
    
    if "suggestion" in data:
        fields.append(("Suggestion", data["suggestion"], False))
    
    return fields


def _fields_card_parsed(data: Dict[str, Any]) -> List[tuple]:
    """Extract fields for character card parsing debug."""
    fields = []
    
    card = data.get("character_card")
    if not card:
        return fields
    
    raw = getattr(card, 'raw_data', card) if not isinstance(card, dict) else card
    
    fields.append(("Spec", f"`{raw.get('spec', 'chara_card_v1')}`", True))
    fields.append(("Version", f"`{raw.get('spec_version', '1.0')}`", True))
    
    if not isinstance(card, dict):
        components = {
            "System Prompt": bool(getattr(card, 'system_prompt', None)),
            "Post-History": bool(getattr(card, 'post_history_instructions', None)),
            "Depth Prompt": bool(getattr(card, 'depth_prompt', None)),
        }
        status_text = "\n".join(f"{'✅' if v else '❌'} {k}" for k, v in components.items())
        fields.append(("V2/V3 Components", status_text, False))
        
        alt = getattr(card, 'alternate_greetings', None)
        if alt:
            fields.append(("Alt Greetings", str(len(alt)), True))
        
        book = getattr(card, 'character_book', None)
        if book:
            entries = len(book.get('entries', [])) if isinstance(book, dict) else 0
            fields.append(("Lorebook", f"{entries} entries", True))
    
    return fields


# ─── Event Schema Registry ───────────────────────────────────────────────────
# Each event is declared as a schema dict. The builder reads these to produce
# embeds generically. To add a new event type, just add a dict here.
#
# Schema keys:
#   emoji: str          — Prefix emoji for the title
#   title: str          — Title template (supports {ai_name}, {title} placeholders)
#   color: str          — Key into COLORS palette
#   description: str|fn — Static text or callable(data) -> str
#   fields: callable    — Function(data) -> list of (name, value, inline) tuples
#   thumbnail: bool     — If True, attempt to set character card thumbnail
#   author: bool        — If True, set bot user as embed author

EVENT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    # ── Command Events ─────────────────────────────────────
    "setup":                    {"emoji": "✅", "title": "Setup Complete",              "color": "success", "fields": _fields_command},
    "character":                {"emoji": "🎭", "title": "Character Applied",           "color": "success", "fields": _fields_command},
    "provider":                 {"emoji": "🔄", "title": "Provider Changed",            "color": "success", "fields": _fields_command},
    "reset":                    {"emoji": "🔄", "title": "History Reset",               "color": "success", "fields": _fields_command},
    "config_change":            {"emoji": "⚙️", "title": "Config Changed",              "color": "info",    "fields": _fields_command},
    "api_connection_created":   {"emoji": "🔌", "title": "API Connection Created",      "color": "success", "fields": _fields_command},
    "api_connection_edited":    {"emoji": "✏️", "title": "API Connection Edited",        "color": "info",    "fields": _fields_command},
    "api_connection_removed":   {"emoji": "🗑️", "title": "API Connection Removed",      "color": "warning", "fields": _fields_command},
    "remove_ai":                {"emoji": "❌", "title": "AI Removed",                  "color": "warning", "fields": _fields_command},
    
    # ── LLM Events ─────────────────────────────────────────
    "llm_response": {
        "emoji": "🤖", "title": "Debug Mode: {ai_name}",
        "color": "llm",
        "fields": _fields_llm_response,
        "thumbnail": True, "author": True,
    },
    "ignore_detected": {
        "emoji": "🚫", "title": "Ignore Detected: {ai_name}",
        "color": "warning",
        "description": lambda d: "AI sent <IGNORE> with extra content (impure)" if d.get("ignore_type") != "pure" else "AI decided not to respond",
        "fields": _fields_ignore,
        "thumbnail": True, "author": True,
    },
    "card_parsed": {
        "emoji": "🔍", "title": "Card Debug: {ai_name}",
        "color": "info",
        "description": lambda d: f"Parsed as **{d.get('character_card', {}).__class__.__name__}**" if not isinstance(d.get('character_card'), dict) else "Raw card data",
        "fields": _fields_card_parsed,
    },
    
    # ── System Events ──────────────────────────────────────
    "sleep_mode_change":  {"emoji": "😴", "title": "Sleep Mode: {ai_name}",   "color": "info",    "fields": _fields_system},
    "bot_status_change":  {"emoji": "🤖", "title": "Bot Status Changed",      "color": "info",    "fields": _fields_system},
    "bot_startup":        {"emoji": "🚀", "title": "Bot Started",             "color": "success", "fields": _fields_system},
    "bot_shutdown":       {"emoji": "🛑", "title": "Bot Shutdown",            "color": "warning", "fields": _fields_system},
    
    # ── Error Events ───────────────────────────────────────
    "error":    {"emoji": "🔴", "title": "{title}", "color": "error",    "fields": _fields_error},
    "warning":  {"emoji": "🟡", "title": "{title}", "color": "warning",  "fields": _fields_error},
    "critical": {"emoji": "🔴", "title": "{title}", "color": "critical", "fields": _fields_error},
}


# ─── Color Palette ────────────────────────────────────────────────────────────

COLORS = {
    "success":  discord.Color.green(),
    "info":     discord.Color.blue(),
    "llm":      discord.Color.dark_embed(),
    "warning":  discord.Color.gold(),
    "error":    discord.Color.red(),
    "critical": discord.Color.dark_red(),
}


# ─── Main Class ───────────────────────────────────────────────────────────────

class DebugEmbed:
    """
    Guild-scoped debug embed system.
    
    Events are defined declaratively in EVENT_SCHEMAS. The build pipeline:
      1. Look up schema for the event
      2. Resolve title template with data placeholders
      3. Call field extractor to get embed fields
      4. Apply enrichments (thumbnail, author icon)
      5. Add standard footer
    
    To add a new event, add a dict to EVENT_SCHEMAS — no new methods needed.
    """
    
    @classmethod
    async def send(
        cls,
        guild: discord.Guild,
        event: str,
        data: Dict[str, Any],
        force: bool = False
    ) -> bool:
        """
        Send a debug embed to the configured debug channel.
        
        Args:
            guild: Discord guild where the event occurred
            event: Event type key (must exist in EVENT_SCHEMAS)
            data: Event-specific data dictionary
            force: If True, send even if debug is disabled
            
        Returns:
            True if embed was sent successfully
        """
        if not guild:
            log.debug("No guild provided, skipping debug embed")
            return False
        
        server_id = str(guild.id)
        
        try:
            if not force and not cls._is_enabled(server_id):
                return False
            
            channel = cls._get_debug_channel(guild)
            if not channel:
                log.debug(f"No debug channel configured for guild {server_id}")
                return False
            
            embed = await cls.build_embed(guild, channel, event, data, server_id)
            if not embed:
                return False
            
            return await cls._send_embed(channel, embed)
            
        except Exception as e:
            log.error(f"Error sending debug embed for event '{event}': {e}")
            return False
    
    @classmethod
    async def send_to_all_guilds(cls, bot, event: str, data: Dict[str, Any]) -> int:
        """Send debug embed to all guilds with debug enabled."""
        if not bot or not bot.guilds:
            return 0
        
        count = 0
        for guild in bot.guilds:
            try:
                if await cls.send(guild, event, data):
                    count += 1
            except Exception as e:
                log.error(f"Error sending debug embed to guild {guild.id}: {e}")
        
        if count > 0:
            log.info(f"Sent '{event}' debug embed to {count}/{len(bot.guilds)} guild(s)")
        return count
    
    # ── Public Builder ────────────────────────────────────────────────────
    
    @classmethod
    async def build_embed(
        cls,
        guild: Optional[discord.Guild],
        channel: Optional[discord.TextChannel],
        event: str,
        data: Dict[str, Any],
        server_id: str
    ) -> Optional[discord.Embed]:
        """
        Build a discord.Embed from an event schema.
        
        This is the single generic builder — no per-event methods needed.
        Can be called directly to get an embed without sending it.
        """
        schema = EVENT_SCHEMAS.get(event)
        if not schema:
            log.warning(f"Unknown debug event: {event}")
            return None
        
        try:
            return await cls._build_from_schema(guild, channel, event, schema, data, server_id)
        except Exception as e:
            log.error(f"Error building embed for '{event}': {e}")
            return None
    
    # ── Internal ──────────────────────────────────────────────────────────
    
    @classmethod
    async def _build_from_schema(
        cls,
        guild: Optional[discord.Guild],
        channel: Optional[discord.TextChannel],
        event: str,
        schema: Dict[str, Any],
        data: Dict[str, Any],
        server_id: str
    ) -> discord.Embed:
        """Generic embed builder driven by a schema dict."""
        
        # Resolve title
        emoji = schema.get("emoji", "ℹ️")
        title_template = schema.get("title", event.replace("_", " ").title())
        title_vars = {
            "ai_name": data.get("ai_name", ""),
            "title": data.get("title", "Event"),
        }
        title_text = title_template.format_map({k: v for k, v in title_vars.items() if f"{{{k}}}" in title_template})
        
        # Resolve description
        desc = schema.get("description")
        if callable(desc):
            try:
                desc = desc(data)
            except Exception:
                desc = None
        
        # Resolve color
        color = COLORS.get(schema.get("color", "info"), discord.Color.blue())
        
        # Create embed
        embed = discord.Embed(
            title=f"{emoji} {title_text}",
            description=desc,
            color=color,
            timestamp=datetime.now()
        )
        
        # Add fields from extractor
        field_extractor = schema.get("fields")
        if field_extractor:
            for name, value, inline in field_extractor(data):
                if value:  # Skip empty fields
                    embed.add_field(name=name, value=str(value), inline=inline)
        
        # Enrichment: bot author
        if schema.get("author") and guild:
            try:
                bot = guild.me
                if bot:
                    embed.set_author(name=f"@{bot.name}", icon_url=bot.display_avatar.url)
            except Exception:
                pass
        
        # Enrichment: character card thumbnail
        if schema.get("thumbnail") and channel:
            try:
                session = data.get("session")
                if session:
                    from utils.media.thumbnails import get_thumbnail_url
                    url = await get_thumbnail_url(channel, session, server_id=server_id)
                    if url:
                        embed.set_thumbnail(url=url)
            except Exception:
                pass
        
        # Standard footer
        version = _get_version()
        embed.set_footer(text=f"Project Hashi v{version} • Server: {server_id}")
        
        return embed
    
    @classmethod
    def _is_enabled(cls, server_id: str) -> bool:
        """Check if debug embeds are enabled for a server."""
        try:
            from utils.core.paths import DataPaths
            import os
            
            data_paths = DataPaths()
            debug_config_file = data_paths.get_debug_config_file(server_id)
            
            if not os.path.exists(debug_config_file):
                return False
            
            config = func.read_json(debug_config_file) or {}
            return config.get("enabled", False)
            
        except Exception as e:
            log.error(f"Error checking debug status: {e}")
            return False
    
    @classmethod
    def _get_debug_channel(cls, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get the configured debug channel for a guild."""
        try:
            from utils.core.paths import DataPaths
            import os
            
            server_id = str(guild.id)
            data_paths = DataPaths()
            debug_config_file = data_paths.get_debug_config_file(server_id)
            
            if not os.path.exists(debug_config_file):
                return None
            
            config = func.read_json(debug_config_file) or {}
            channel_id = config.get("debug_channel_id")
            
            if not channel_id:
                return None
            
            channel = guild.get_channel(int(channel_id))
            return channel if isinstance(channel, discord.TextChannel) else None
            
        except Exception as e:
            log.error(f"Error getting debug channel: {e}")
            return None
    
    @classmethod
    async def _send_embed(cls, channel: discord.TextChannel, embed: discord.Embed) -> bool:
        """Send an embed to a channel with error handling."""
        try:
            await channel.send(embed=embed)
            return True
        except discord.Forbidden:
            log.warning(f"No permission to send to debug channel {channel.id}")
            return False
        except discord.HTTPException as e:
            log.error(f"HTTP error sending debug embed: {e}")
            return False
        except Exception as e:
            log.error(f"Error sending debug embed: {e}")
            return False
