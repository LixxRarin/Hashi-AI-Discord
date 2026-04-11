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


def _escape_code_blocks(text: str) -> str:
    """
    Escape triple backticks in text to prevent markdown conflicts.
    Uses zero-width spaces to preserve visual appearance.
    
    When LLM responses contain code blocks (```), they break the outer
    code block formatting in embeds. This function inserts zero-width
    spaces between backticks to prevent the conflict.
    """
    # Replace ``` with `​`​` (backtick + zero-width space + backtick + zero-width space + backtick)
    return text.replace("```", "`\u200b`\u200b`")


def _format_duration(seconds: float) -> str:
    """
    Format duration in human-readable form.
    
    Examples:
        0.0005 -> "500µs"
        0.123 -> "123ms"
        1.234 -> "1.23s"
        65.5 -> "1m 5.5s"
    """
    if seconds < 0.001:
        return f"{seconds * 1000000:.0f}µs"
    elif seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.2f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"


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
    
    # Raw response (with markdown escape fix)
    raw = data.get("raw_response", "")
    if raw:
        # Escape triple backticks to prevent markdown conflicts
        raw_escaped = _escape_code_blocks(raw)
        fields.append(("Raw Response", f"```\n{truncate(raw_escaped, 900)}\n```", False))
    
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
    """Extract fields for system lifecycle events (startup, shutdown, sleep, status) - Enhanced."""
    fields = []
    
    # Version with emoji
    version = data.get("version")
    if version:
        fields.append(("Version", f"🏷️ `{version}`", True))
    
    # Servers count
    servers = data.get("servers")
    if servers is not None:
        fields.append(("Servers", f"🌐 {servers}", True))
    
    # Total AIs
    total_ais = data.get("total_ais")
    if total_ais is not None:
        fields.append(("Total AIs", f"🤖 {total_ais}", True))
    
    # Features (for startup)
    features = data.get("features", [])
    if features:
        feature_text = "\n".join(f"✅ {f}" for f in features)
        fields.append(("Features", feature_text, False))
    
    # Uptime (for shutdown)
    uptime = data.get("uptime")
    if uptime is not None:
        h, m = int(uptime // 3600), int((uptime % 3600) // 60)
        s = int(uptime % 60)
        uptime_str = f"⏱️ {h}h {m}m {s}s"
        fields.append(("Uptime", uptime_str, True))
    
    # Reason
    reason = data.get("reason")
    if reason:
        fields.append(("Reason", reason, False))
    
    # Status change with emoji indicators
    if "old_status" in data and "new_status" in data:
        old = data["old_status"].title()
        new = data["new_status"].title()
        
        # Add emoji indicators
        status_emoji = {
            "online": "🟢",
            "idle": "🌙",
            "dnd": "🔴",
            "offline": "⚫"
        }
        old_emoji = status_emoji.get(data["old_status"], "")
        new_emoji = status_emoji.get(data["new_status"], "")
        
        fields.append(("Status Change", f"{old_emoji} {old} → {new_emoji} {new}", False))
    
    # Sleep mode specifics
    if "status" in data and "old_status" not in data:
        fields.append(("Status", data["status"].title(), True))
    
    # AIs in sleep
    ais = data.get("ais_in_sleep", [])
    if ais:
        text = "\n".join(f"😴 {a}" for a in ais[:10])
        if len(ais) > 10:
            text += f"\n… and {len(ais) - 10} more"
        fields.append(("Sleeping AIs", text, False))
    
    # Channel
    channel = data.get("channel")
    if channel:
        fields.append(("Channel", str(channel), True))
    
    # Messages processed (for shutdown)
    messages = data.get("messages_processed")
    if messages is not None:
        fields.append(("Messages Processed", f"💬 {messages:,}", True))
    
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


def _fields_tool_call_bash(data: Dict[str, Any]) -> List[tuple]:
    """Extract fields for bash tool execution debug."""
    fields = []
    
    # Command (with syntax highlighting)
    command = data.get("command", "")
    if command:
        # Truncate very long commands
        display_cmd = command if len(command) <= 500 else command[:497] + "..."
        # Escape code blocks in command
        display_cmd = _escape_code_blocks(display_cmd)
        fields.append(("Command", f"```bash\n{display_cmd}\n```", False))
    
    # Mode and Container Info
    mode = data.get("mode", "unknown")
    container_id = data.get("container_id", "N/A")
    container_info = f"**Mode:** {mode.title()}\n**Container:** `{container_id}`"
    fields.append(("Execution Mode", container_info, True))
    
    # Working Directory
    working_dir = data.get("working_dir", "/workspace")
    fields.append(("Working Dir", f"`{working_dir}`", True))
    
    # Exit Code with visual indicator
    exit_code = data.get("exit_code", -1)
    success = data.get("success", False)
    if success:
        exit_status = f"✅ **Success** (exit code: {exit_code})"
    else:
        exit_status = f"❌ **Failed** (exit code: {exit_code})"
    fields.append(("Status", exit_status, True))
    
    # Execution Time
    exec_time = data.get("execution_time", 0)
    time_str = _format_duration(exec_time)
    fields.append(("Execution Time", f"⏱️ {time_str}", True))
    
    # Output (stdout)
    stdout = data.get("stdout", "")
    if stdout:
        # Truncate long output
        max_len = data.get("max_output_length", 1000)
        if len(stdout) > max_len:
            display_out = stdout[:max_len] + f"\n... (truncated {len(stdout) - max_len} chars)"
        else:
            display_out = stdout
        # Escape code blocks in output
        display_out = _escape_code_blocks(display_out)
        fields.append(("Output", f"```\n{display_out}\n```", False))
    else:
        fields.append(("Output", "*No output*", False))
    
    # Errors (stderr) - only if present
    stderr = data.get("stderr", "")
    if stderr:
        max_len = data.get("max_output_length", 1000)
        if len(stderr) > max_len:
            display_err = stderr[:max_len] + f"\n... (truncated {len(stderr) - max_len} chars)"
        else:
            display_err = stderr
        # Escape code blocks in errors
        display_err = _escape_code_blocks(display_err)
        fields.append(("Errors", f"```\n{display_err}\n```", False))
    
    # Container Statistics (if available)
    command_count = data.get("command_count")
    container_uptime = data.get("container_uptime")
    if command_count is not None or container_uptime is not None:
        stats = []
        if command_count is not None:
            stats.append(f"**Commands:** {command_count}")
        if container_uptime is not None:
            uptime_str = _format_duration(container_uptime)
            stats.append(f"**Uptime:** {uptime_str}")
        if stats:
            fields.append(("Container Stats", " · ".join(stats), False))
    
    return fields


def _fields_tool_call_memory(data: Dict[str, Any]) -> List[tuple]:
    """Extract fields for memory tool execution debug."""
    fields = []
    
    # Operation Type
    tool_name = data.get("tool_name", "unknown")
    operation = tool_name.replace("_memory", "").title()  # read/edit/write
    fields.append(("Operation", f"`{operation}`", True))
    
    # File Path
    file_path = data.get("file_path", "N/A")
    if file_path and file_path != "N/A":
        # Show only filename for brevity
        from pathlib import Path
        filename = Path(file_path).name
        fields.append(("File", f"`{filename}`", True))
    
    # Status with visual indicator
    success = data.get("success", False)
    error = data.get("error")
    if error:
        fields.append(("Status", f"❌ **Failed**", True))
        fields.append(("Error", str(error)[:500], False))
    else:
        fields.append(("Status", f"✅ **Success**", True))
    
    # Execution Time
    exec_time = data.get("execution_time", 0)
    time_str = _format_duration(exec_time)
    fields.append(("Duration", f"⏱️ {time_str}", True))
    
    # Token Usage (for edit/write operations)
    tokens_used = data.get("tokens_used")
    max_tokens = data.get("max_tokens")
    if tokens_used is not None and max_tokens is not None:
        percentage = (tokens_used / max_tokens * 100) if max_tokens > 0 else 0
        bar = progress_bar(tokens_used, max_tokens)
        token_info = f"{bar} {tokens_used}/{max_tokens} tokens ({percentage:.1f}%)"
        fields.append(("Memory Usage", token_info, False))
    
    # Content Preview (for read operations)
    if operation == "Read":
        content = data.get("content", "")
        if content:
            preview = content[:300] + "..." if len(content) > 300 else content
            preview = _escape_code_blocks(preview)
            fields.append(("Content Preview", f"```\n{preview}\n```", False))
        
        metadata = data.get("metadata", {})
        if metadata:
            last_updated = metadata.get("last_updated", "Unknown")
            fields.append(("Last Updated", last_updated, True))
    
    # Edit Details (for edit operations)
    if operation == "Edit":
        old_string = data.get("old_string", "")
        new_string = data.get("new_string", "")
        if old_string or new_string:
            old_preview = (old_string[:100] + "...") if len(old_string) > 100 else old_string
            new_preview = (new_string[:100] + "...") if len(new_string) > 100 else new_string
            old_preview = _escape_code_blocks(old_preview)
            new_preview = _escape_code_blocks(new_preview)
            fields.append(("Change", f"**Old:**\n```\n{old_preview}\n```\n**New:**\n```\n{new_preview}\n```", False))
    
    return fields


def _fields_tool_call_generic(data: Dict[str, Any]) -> List[tuple]:
    """Extract fields for generic tool call debug."""
    fields = []
    
    # Tool Name
    tool_name = data.get("tool_name", "unknown")
    fields.append(("Tool", f"`{tool_name}`", True))
    
    # Execution Time
    exec_time = data.get("execution_time")
    if exec_time is not None:
        time_str = _format_duration(exec_time)
        fields.append(("Duration", f"⏱️ {time_str}", True))
    
    # Status
    success = data.get("success", True)
    error = data.get("error")
    if error:
        fields.append(("Status", f"❌ **Error**", True))
        fields.append(("Error Message", str(error)[:500], False))
    else:
        fields.append(("Status", f"✅ **Success**", True))
    
    # Arguments (formatted JSON)
    arguments = data.get("arguments", {})
    if arguments:
        # Remove context from display
        display_args = {k: v for k, v in arguments.items() if k != "context"}
        if display_args:
            import json
            try:
                args_json = json.dumps(display_args, indent=2, ensure_ascii=False)
                # Truncate if too long
                if len(args_json) > 800:
                    args_json = args_json[:800] + "\n... (truncated)"
                fields.append(("Arguments", f"```json\n{args_json}\n```", False))
            except Exception:
                # If JSON serialization fails, show as string
                args_str = str(display_args)[:800]
                fields.append(("Arguments", f"```\n{args_str}\n```", False))
    
    # Result Summary
    result_summary = data.get("result_summary")
    if result_summary:
        fields.append(("Result", result_summary, False))
    
    # Full Result (truncated)
    result = data.get("result")
    if result and not error:
        import json
        try:
            result_json = json.dumps(result, indent=2, ensure_ascii=False)
            if len(result_json) > 1000:
                result_json = result_json[:1000] + "\n... (truncated)"
            fields.append(("Full Result", f"```json\n{result_json}\n```", False))
        except Exception:
            # If not JSON serializable, show as string
            result_str = str(result)[:1000]
            fields.append(("Full Result", f"```\n{result_str}\n```", False))
    
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
    
    # ── Tool Call Events ───────────────────────────────────
    "tool_call_bash": {
        "emoji": "🔧",
        "title": "Bash Tool: {ai_name}",
        "color": "tool_bash",
        "description": lambda d: f"Executed bash command in {d.get('mode', 'unknown')} container",
        "fields": _fields_tool_call_bash,
        "thumbnail": True,
        "author": True,
    },
    "tool_call_memory": {
        "emoji": "💾",
        "title": "Memory Tool: {ai_name}",
        "color": "tool_memory",
        "description": lambda d: f"Executed memory operation: {d.get('tool_name', 'unknown').replace('_memory', '').title()}",
        "fields": _fields_tool_call_memory,
        "thumbnail": True,
        "author": True,
    },
    "tool_call_generic": {
        "emoji": "🔧",
        "title": "Tool Call: {tool_name}",
        "color": "tool_generic",
        "description": lambda d: f"Executed tool: {d.get('tool_name', 'unknown')}",
        "fields": _fields_tool_call_generic,
        "thumbnail": True,
        "author": True,
    },
    
    # ── System Events ──────────────────────────────────────
    "sleep_mode_change":  {"emoji": "😴", "title": "Sleep Mode: {ai_name}",   "color": "info",    "fields": _fields_system},
    "bot_status_change":  {"emoji": "🤖", "title": "Bot Status Changed",      "color": "info",    "fields": _fields_system},
    "bot_startup":        {"emoji": "🥢", "title": "Hashi AI Started",        "color": "startup", "fields": _fields_system, "description": "Bot is now online and ready to serve!", "author": True},
    "bot_shutdown":       {"emoji": "🛑", "title": "Hashi AI Shutting Down",  "color": "shutdown", "fields": _fields_system, "description": "Bot is shutting down gracefully...", "author": True},
    
    # ── Error Events ───────────────────────────────────────
    "error":    {"emoji": "🔴", "title": "{title}", "color": "error",    "fields": _fields_error},
    "warning":  {"emoji": "🟡", "title": "{title}", "color": "warning",  "fields": _fields_error},
    "critical": {"emoji": "🔴", "title": "{title}", "color": "critical", "fields": _fields_error},
}


# ─── Color Palette ────────────────────────────────────────────────────────────

COLORS = {
    "success":      discord.Color.green(),
    "info":         discord.Color.blue(),
    "llm":          discord.Color.dark_embed(),
    "warning":      discord.Color.gold(),
    "error":        discord.Color.red(),
    "critical":     discord.Color.dark_red(),
    "tool_bash":    discord.Color.purple(),
    "tool_memory":  discord.Color.blue(),
    "tool_generic": discord.Color.teal(),
    "startup":      discord.Color.brand_green(),
    "shutdown":     discord.Color.orange(),
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
            "tool_name": data.get("tool_name", ""),
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
