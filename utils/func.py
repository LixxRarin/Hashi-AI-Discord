import asyncio
import datetime
import logging
import os
import socket
import time
from typing import Any, Dict, Optional, Callable, Awaitable, TypeVar

import yaml
from colorama import Fore, Style, init

from utils.persistence import read_json, write_json

from utils.func_character_cards import (
    register_character_card,
    unregister_character_card,
    list_character_cards,
    get_character_card,
    get_ais_using_card
)

# Type definitions
T = TypeVar('T')
SessionData = Dict[str, Any]
CacheData = Dict[str, Dict[str, Dict[str, str]]]


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log messages based on severity level."""

    def format(self, record):
        # Color scheme for different log levels
        LEVEL_COLORS = {
            "DEBUG": Fore.CYAN,
            "INFO": Fore.GREEN,
            "WARNING": Fore.YELLOW,
            "ERROR": Fore.RED,
            "CRITICAL": Fore.RED,
        }
        level_color = LEVEL_COLORS.get(record.levelname, Fore.WHITE)

        # Format timestamp with full date and time
        timestamp = datetime.datetime.fromtimestamp(
            record.created).strftime('%Y-%m-%d %H:%M:%S')
        message = record.getMessage()

        # Build colorized log line with different colors for each component:
        # - Timestamp: Green
        # - Level: Bold + level-specific color
        # - Module path: Blue
        # - Message: Bold white
        colored_timestamp = f"{Fore.GREEN}{timestamp}{Fore.RESET}"
        colored_level = f"{Style.BRIGHT}{level_color}{record.levelname:<8}{Style.RESET_ALL}"
        colored_module = f"{Fore.BLUE}{record.name}:{record.funcName}:{record.lineno}{Fore.RESET}"
        colored_message = f"{Style.BRIGHT}{Fore.WHITE}{message}{Style.RESET_ALL}"

        return f"{colored_timestamp} | {colored_level} | {colored_module} - {colored_message}"


def load_config() -> Dict[str, Any]:
    """
    Loads configuration from the YAML file without using logging.

    Returns:
        Dict[str, Any]: Configuration data from config.yml
    """
    try:
        with open("config.yml", "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except Exception:
        data = {}  # Return an empty dictionary on error
    return data


def setup_logging(debug_mode=False) -> logging.Logger:
    """
    Configures logging: sets up a file handler and a console handler with colors.

    Args:
        debug_mode (bool): Whether to enable debug logging to console

    Returns:
        logging.Logger: Configured root logger
    """
    # Initialize colorama with autoreset enabled
    init(autoreset=True)

    # Get root logger and remove any existing handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Set root level to DEBUG
    
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create file handler with structured format
    file_handler = logging.FileHandler("app.log", mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Create console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    console_handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(console_handler)

    # Silence noisy third-party libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("anthropic._base_client").setLevel(logging.WARNING)
    logging.getLogger("ollama").setLevel(logging.WARNING)
    logging.getLogger("discord").setLevel(logging.WARNING)  # Reduced Discord noise
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)  # Silence gateway messages

    return root_logger


# First, load the configuration without logging to avoid premature logger creation
config_yaml = load_config()
debug_mode = config_yaml.get("Options", {}).get("debug_mode", False)

# Next, configure logging
log = setup_logging(debug_mode)

# Session management
session_cache: Dict[str, Any] = {}

# Add this configuration to your config.yml file
config_yaml = load_config()





def get_default_ai_config(provider: str = "openai") -> dict:
    """
    Returns the default configuration for an AI session.
    This is the SINGLE source of truth for default configurations.
    
This function returns only Discord behavioral configurations.
    LLM parameters (max_tokens, temperature, etc.) are now in api_connections.json.
    
    Now uses the new AI Config Manager system which loads defaults from
    config/defaults.yml. This allows users to customize default values without
    editing code.
    
    Args:
        provider: AI provider ("openai")
    
    Returns:
        dict: Default configuration dictionary (behavioral only)
    """
    
    try:
        from utils.ai_config_manager import get_ai_config_manager
        manager = get_ai_config_manager()
        return manager.get_defaults()
    except Exception as e:
        log.error(f"Error loading config from AI Config Manager: {e}")
        log.warning("Falling back to embedded defaults")
        
        # Fallback: Parse the same DEFAULT_AI_CONFIG_CONTENT used by the manager
        # This ensures a single source of truth for default values
        try:
            from utils.ai_config_manager import DEFAULT_AI_CONFIG_CONTENT
            from ruamel.yaml import YAML
            
            yaml_parser = YAML(typ='rt')
            parsed_config = yaml_parser.load(DEFAULT_AI_CONFIG_CONTENT)
            
            # Extract flat config (same logic as AIConfigManager.get_defaults())
            flat_config = {}
            for category, settings in parsed_config.items():
                if category == "version":
                    continue
                if isinstance(settings, dict):
                    for key, value in settings.items():
                        # Preserve nested dicts (like tool_calling)
                        flat_config[key] = value
            
            return flat_config
        except Exception as fallback_error:
            log.critical(f"Critical: Fallback parsing also failed: {fallback_error}")
            # Last resort: return minimal config to prevent total failure
            return {
                "use_card_ai_display_name": True,
                "send_message_line_by_line": True,
                "delay_for_generation": 4.0,
                "cache_count_threshold": 5,
            }


def get_default_ai_session(provider: str = "openai", channel_name: str = "default_channel_name") -> dict:
    """
    Returns the complete default session structure for an AI.
    Uses get_default_ai_config() internally to ensure consistency.
    
    This structure is compatible with the new API connections system.
    - api_connection: Reference to connection in api_connections.json
    - model and base_url: REMOVED (now in the connection)
    - config: ONLY behavioral configurations (no LLM parameters)
    
    Args:
        provider: AI provider ("openai")
        channel_name: Channel name (placeholder)
    
    Returns:
        dict: Complete session structure with all necessary keys
    """
    return {
        "api_connection": None,           # NEW - Reference to API connection
        "provider": provider,              # KEPT
        "channel_name": channel_name,
        "webhook_url": None,
        "chat_id": None,
        "character_card": None,           # Character card data structure
        "character_card_name": None,      # Name/ID of the registered card
        "setup_has_already": False,
        "last_message_time": lambda: time.time(),
        "awaiting_response": False,
        "muted_users": [],
        "mode": None,
        "config": get_default_ai_config(provider)  # Only behavioral configs
        # REMOVED: "model": None
        # REMOVED: "base_url": None
    }


async def timeout_async(func: Callable[[], Awaitable[T]], timeout: float,
                        on_timeout: Callable[[], Awaitable[None]]) -> None:
    """
    Awaits the execution of 'func' with a specified timeout.
    If a timeout occurs, the 'on_timeout' function is called.

    Args:
        func: Async function to execute
        timeout: Timeout in seconds
        on_timeout: Async function to call if timeout occurs
    """
    try:
        await asyncio.wait_for(func(), timeout=timeout)
    except asyncio.TimeoutError:
        log.warning(
            "Operation timed out after %s seconds. Executing on_timeout handler.", timeout)
        try:
            await on_timeout()
        except Exception as e:
            log.error("Error in on_timeout handler: %s", e)


def test_internet() -> bool:
    """
    Tests internet connectivity by attempting to connect to www.google.com.

    Returns:
        bool: True if successful, otherwise False
    """
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        log.debug("Internet connection test succeeded.")
        return True
    except OSError as e:
        log.error("Internet connection test failed: %s", e)
        return False


def is_channel_active(server_id: str, channel_id: str) -> bool:
    """
    Check if a channel is still active in the session data.

    Args:
        server_id: Server ID
        channel_id: Channel ID

    Returns:
        bool: True if the channel is active, False otherwise
    """
    return channel_id in session_cache.get(server_id, {}).get("channels", {})




async def load_session_cache() -> None:
    """Loads session data from hierarchical structure into memory cache"""
    global session_cache
    session_cache = {}

    from utils.data_paths import DataPaths
    data_paths = DataPaths()

    # Scan all server directories
    for server_id in data_paths.list_servers():
        session_cache[server_id] = {"channels": {}}

        # Scan all channel directories in this server
        for channel_id in data_paths.list_channels(server_id):
            # Load session file for this channel
            session_file = data_paths.get_session_file(server_id, channel_id)
            if os.path.exists(session_file):
                channel_data = await asyncio.to_thread(read_json, session_file)
                if channel_data:
                    session_cache[server_id]["channels"][channel_id] = channel_data

    log.info(f"Loaded session cache with {len(session_cache)} servers")


async def update_session_data(server_id: str, channel_id: str, new_data: Dict[str, Any]) -> None:
    """
    Updates the session data for a specific server and channel.

    Args:
        server_id: Server ID
        channel_id: Channel ID
        new_data: New session data (None to delete)
    """
    from utils.data_paths import DataPaths
    data_paths = DataPaths()

    # Update in-memory cache
    if server_id not in session_cache:
        session_cache[server_id] = {"channels": {}}
    if "channels" not in session_cache[server_id]:
        session_cache[server_id]["channels"] = {}

    # Handle None (deletion) vs update
    if new_data is None:
        # Remove from cache
        if channel_id in session_cache[server_id]["channels"]:
            del session_cache[server_id]["channels"][channel_id]

        # Delete file
        session_file = data_paths.get_session_file(server_id, channel_id)
        if os.path.exists(session_file):
            await asyncio.to_thread(os.remove, session_file)
            log.debug(f"Deleted session file for channel {channel_id}")
    else:
        # Update cache
        session_cache[server_id]["channels"][channel_id] = new_data

        # Write to per-channel file
        session_file = data_paths.get_session_file(server_id, channel_id)
        data_paths.ensure_directory(session_file)
        await asyncio.to_thread(write_json, session_file, new_data)
        log.debug(f"Updated session data for channel {channel_id}")


def get_session_data(server_id: str, channel_id: str) -> Optional[Dict[str, Any]]:
    """
    Gets session data for a specific server and channel from the in-memory cache.

    Args:
        server_id: Server ID
        channel_id: Channel ID

    Returns:
        Optional[Dict[str, Any]]: Session data or None if not found
    """
    return session_cache.get(server_id, {}).get("channels", {}).get(channel_id)


def get_ai_session_data_from_all_channels(server_id: str, ai_name: str) -> Optional[tuple[str, Dict[str, Any]]]:
    """
    Searches for a specific AI's session data across all channels in a given server.

    Args:
        server_id: The ID of the server.
        ai_name: The name of the AI to find.

    Returns:
        Optional[tuple[str, Dict[str, Any]]]: A tuple containing the channel ID and the session data for the AI if found, otherwise None.
    """
    server_data = session_cache.get(server_id, {})
    channels_data = server_data.get("channels", {})

    for channel_id, channel_ais in channels_data.items():
        # Skip if channel_ais is None (defensive check)
        if channel_ais is None:
            continue
        if ai_name in channel_ais:
            return channel_id, channel_ais[ai_name]
    return None


async def remove_session_data(server_id: str, channel_id: str) -> None:
    """
    Remove session data for a specific channel.

    Args:
        server_id: Server ID
        channel_id: Channel ID
    """
    global session_cache
    if server_id in session_cache and channel_id in session_cache[server_id].get("channels", {}):
        # Remove from in-memory cache
        del session_cache[server_id]["channels"][channel_id]
        log.info(f"Removed session data for channel {channel_id} from cache")

        # Update persistent storage directly
        await update_session_data(server_id, channel_id, None)

async def load_api_connections() -> Dict[str, Dict[str, Any]]:
    """
    Load API connections from all servers.

    Returns:
        Dict[str, Dict[str, Any]]: Dictionary of connections by server
    """
    from utils.data_paths import DataPaths

    data_paths = DataPaths()
    all_connections = {}

    for server_id in data_paths.list_servers():
        connections_file = data_paths.get_api_connections_file(server_id)
        if os.path.exists(connections_file):
            server_connections = await asyncio.to_thread(read_json, connections_file)
            if server_connections:
                all_connections[server_id] = server_connections

    return all_connections


async def save_api_connections(data: Dict[str, Dict[str, Any]]) -> None:
    """
    Save API connections per server.

    Args:
        data: Dictionary of connections by server to save
    """
    from utils.data_paths import DataPaths

    data_paths = DataPaths()

    for server_id, server_connections in data.items():
        connections_file = data_paths.get_api_connections_file(server_id)
        data_paths.ensure_directory(connections_file)
        await asyncio.to_thread(write_json, connections_file, server_connections)


def get_api_connection(server_id: str, connection_name: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific API connection.

    Args:
        server_id: Server ID
        connection_name: Connection name

    Returns:
        Optional[Dict[str, Any]]: Connection data or None if not found
    """
    from utils.data_paths import DataPaths

    data_paths = DataPaths()
    connections_file = data_paths.get_api_connections_file(server_id)

    if not os.path.exists(connections_file):
        return None

    connections = read_json(connections_file) or {}
    return connections.get(connection_name)


async def create_api_connection(
    server_id: str,
    connection_name: str,
    provider: str,
    api_key: str,
    model: str,
    base_url: Optional[str] = None,
    max_tokens: int = 1000,
    temperature: float = 0.5,
    top_p: float = 1.0,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    context_size: int = 16000,
    think_switch: bool = True,
    think_depth: int = 3,
    hide_thinking_tags: bool = True,
    thinking_tag_patterns: Optional[list[str]] = None,
    max_tool_rounds: int = 10,
    custom_extra_body: Optional[str] = None,
    save_thinking_in_history: bool = True,
    vision_enabled: bool = False,
    vision_detail: str = "auto",
    max_image_size: int = 20,
    created_by: Optional[str] = None
) -> bool:
    """
    Create a new API connection.
    
    Args:
        server_id: Server ID
        connection_name: Unique name for the connection
        provider: API provider (e.g., "openai")
        api_key: API key
        model: Model name
        base_url: Custom URL (optional)
        max_tokens: Maximum tokens in response
        temperature: Temperature (0.0-2.0)
        top_p: Top P (0.0-1.0)
        frequency_penalty: Frequency penalty (-2.0 to 2.0)
        presence_penalty: Presence penalty (-2.0 to 2.0)
        context_size: Context size in tokens
        think_switch: Enable thinking
        think_depth: Thinking depth (1-5)
        hide_thinking_tags: Hide thinking tags from AI responses
        thinking_tag_patterns: Regex patterns for thinking tags
        max_tool_rounds: Maximum tool calling rounds (1-10)
        custom_extra_body: Custom extra parameters as JSON string
        save_thinking_in_history: Save thinking/reasoning in conversation history
        vision_enabled: Enable vision/image analysis (default: False)
        vision_detail: Vision detail level - "low", "high", "auto" (default: "auto")
        max_image_size: Maximum image size in MB (default: 20)
        created_by: User ID who created it
        
    Returns:
        bool: True if created successfully, False if already exists
    """
    import datetime
    import json
    
    # Parse custom_extra_body if provided
    extra_body_dict = None
    if custom_extra_body:
        try:
            extra_body_dict = json.loads(custom_extra_body)
            if not isinstance(extra_body_dict, dict):
                raise ValueError("custom_extra_body must be a JSON object")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in custom_extra_body: {e}")
    
    # Set default thinking tag patterns if not provided
    if thinking_tag_patterns is None:
        thinking_tag_patterns = [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
            r'<thought>.*?</thought>',
            r'<reasoning>.*?</reasoning>'
        ]
    
    connections = await load_api_connections()
    
    if server_id not in connections:
        connections[server_id] = {}
    
    if connection_name in connections[server_id]:
        log.warning(f"Connection '{connection_name}' already exists")
        return False
    
    connections[server_id][connection_name] = {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
        "context_size": context_size,
        "think_switch": think_switch,
        "think_depth": think_depth,
        "hide_thinking_tags": hide_thinking_tags,
        "thinking_tag_patterns": thinking_tag_patterns,
        "max_tool_rounds": max_tool_rounds,
        "custom_extra_body": extra_body_dict,
        "save_thinking_in_history": save_thinking_in_history,
        "vision_enabled": vision_enabled,
        "vision_detail": vision_detail,
        "max_image_size": max_image_size,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "created_by": created_by
    }
    
    await save_api_connections(connections)
    log.info(f"Created API connection '{connection_name}'")
    return True


async def update_api_connection(
    server_id: str,
    connection_name: str,
    **updates
) -> bool:
    """
    Update an existing API connection.
    
    Args:
        server_id: Server ID
        connection_name: Connection name
        **updates: Fields to update
        
    Returns:
        bool: True if updated successfully, False if not found
    """
    connections = await load_api_connections()
    
    if server_id not in connections or connection_name not in connections[server_id]:
        log.warning(f"Connection '{connection_name}' not found")
        return False
    
    # Remove None values from updates
    updates = {k: v for k, v in updates.items() if v is not None}
    
    connections[server_id][connection_name].update(updates)
    await save_api_connections(connections)
    log.info(f"Updated API connection '{connection_name}'")
    return True


async def rename_api_connection(
    server_id: str,
    old_connection_name: str,
    new_connection_name: str
) -> tuple[bool, str]:
    """
    Rename an API connection and update all AIs using it.
    
    Args:
        server_id: Server ID
        old_connection_name: Current connection name
        new_connection_name: New connection name
        
    Returns:
        tuple[bool, str]: (success, error_message)
    """
    connections = await load_api_connections()
    
    # Check if old connection exists
    if server_id not in connections or old_connection_name not in connections[server_id]:
        return False, f"Connection '{old_connection_name}' not found in this server."
    
    # Check if new name already exists
    if new_connection_name in connections[server_id]:
        return False, f"Connection '{new_connection_name}' already exists in this server."
    
    # Rename the connection in api_connections.json
    connections[server_id][new_connection_name] = connections[server_id].pop(old_connection_name)
    await save_api_connections(connections)
    log.info(f"Renamed API connection '{old_connection_name}' to '{new_connection_name}'")
    
    # Update all AI sessions that use this connection
    updated_ais = []
    server_data = session_cache.get(server_id, {})
    channels_data = server_data.get("channels", {})
    
    for channel_id, channel_ais in channels_data.items():
        for ai_name, ai_session in channel_ais.items():
            if ai_session.get("api_connection") == old_connection_name:
                ai_session["api_connection"] = new_connection_name
                updated_ais.append((channel_id, ai_name))
                # Queue update to persistent storage
                await update_session_data(server_id, channel_id, channel_ais)
    
    if updated_ais:
        log.info(f"Updated {len(updated_ais)} AI(s) to use new connection name '{new_connection_name}'")
    
    return True, ""


async def delete_api_connection(server_id: str, connection_name: str) -> bool:
    """
    Remove an API connection.
    
    Args:
        server_id: Server ID
        connection_name: Connection name
        
    Returns:
        bool: True if removed successfully, False if not found
    """
    connections = await load_api_connections()
    
    if server_id not in connections or connection_name not in connections[server_id]:
        log.warning(f"Connection '{connection_name}' not found")
        return False
    
    del connections[server_id][connection_name]
    
    # Clean up empty server entries
    if not connections[server_id]:
        del connections[server_id]
    
    await save_api_connections(connections)
    log.info(f"Deleted API connection '{connection_name}'")
    return True


def list_api_connections(server_id: str) -> Dict[str, Any]:
    """
    List all API connections for a server.

    Args:
        server_id: Server ID

    Returns:
        Dict[str, Any]: Dictionary of server connections
    """
    from utils.data_paths import DataPaths

    data_paths = DataPaths()
    connections_file = data_paths.get_api_connections_file(server_id)

    if not os.path.exists(connections_file):
        return {}

    connections = read_json(connections_file) or {}
    return connections


def get_ais_using_connection(server_id: str, connection_name: str) -> list[tuple[str, str]]:
    """
    Return list of AIs using a specific connection.
    
    Args:
        server_id: Server ID
        connection_name: Connection name
        
    Returns:
        list[tuple[str, str]]: List of tuples (channel_id, ai_name)
    """
    ais_using = []
    server_data = session_cache.get(server_id, {})
    channels_data = server_data.get("channels", {})
    
    for channel_id, channel_ais in channels_data.items():
        for ai_name, ai_session in channel_ais.items():
            if ai_session.get("api_connection") == connection_name:
                ais_using.append((channel_id, ai_name))
    
    return ais_using


def get_thinking_config(session: Dict[str, Any], server_id: str) -> tuple[bool, list[str]]:
    """
    Get thinking configuration (hide_thinking_tags and thinking_tag_patterns).
    Checks API connection first (new way), then falls back to session config (old way).
    
    Args:
        session: AI session data
        server_id: Server ID
        
    Returns:
        tuple[bool, list[str]]: (hide_thinking_tags, thinking_tag_patterns)
    """
    # Default values
    default_hide = True
    default_patterns = [
        r'<think>.*?</think>',
        r'<thinking>.*?</thinking>',
        r'<thought>.*?</thought>',
        r'<reasoning>.*?</reasoning>'
    ]
    
    # Try to get from API connection first (new way)
    api_connection_name = session.get("api_connection")
    if api_connection_name:
        connection = get_api_connection(server_id, api_connection_name)
        if connection:
            hide_tags = connection.get("hide_thinking_tags", default_hide)
            patterns = connection.get("thinking_tag_patterns", default_patterns)
            return hide_tags, patterns
    
    # Fall back to session config (old way, for backward compatibility)
    config = session.get("config", {})
    hide_tags = config.get("hide_thinking_tags", default_hide)
    patterns = config.get("thinking_tag_patterns", default_patterns)
    
    return hide_tags, patterns


async def delete_server_session_data(server_id: str) -> bool:
    """
    Delete all session data for a server.
    
    Args:
        server_id: Discord server ID
        
    Returns:
        bool: True if deleted successfully, False otherwise
    """
    global session_cache

    try:
        # Remove from in-memory cache
        if server_id in session_cache:
            del session_cache[server_id]
            log.info("Removed server from session cache")

        # Delete all channel session files for this server
        from utils.data_paths import DataPaths
        data_paths = DataPaths()

        deleted_count = 0
        for channel_id in data_paths.list_channels(server_id):
            session_file = data_paths.get_session_file(server_id, channel_id)
            if os.path.exists(session_file):
                await asyncio.to_thread(os.remove, session_file)
                deleted_count += 1

        if deleted_count > 0:
            log.info(f"Deleted {deleted_count} session file(s) for server {server_id}")

        return True

    except Exception as e:
        log.error(f"Error deleting session data: {e}")
        return False


async def delete_server_api_connections(server_id: str) -> bool:
    """
    Delete all API connections for a server.
    
    Args:
        server_id: Discord server ID
        
    Returns:
        bool: True if deleted successfully, False otherwise
    """
    try:
        connections = await load_api_connections()
        
        if server_id in connections:
            connection_count = len(connections[server_id])
            del connections[server_id]
            await save_api_connections(connections)
            log.info(f"Deleted {connection_count} API connection(s)")
            return True
        else:
            log.debug("No API connections found")
            return True  # Not an error if data doesn't exist
            
    except Exception as e:
        log.error(f"Error deleting API connections: {e}")
        return False


async def cleanup_server_data(server_id: str, server_name: str = None) -> Dict[str, Any]:
    """
    Orchestrate complete cleanup of all server data.
    
    This function coordinates cleanup across all data storage systems:
    - Session configurations
    - API connections
    - Character cards (with smart file deletion)
    - Conversation histories
    - Short ID mappings
    - Memory files
    
    Args:
        server_id: Discord server ID
        server_name: Server name for logging (optional)
    
    Returns:
        Dict with cleanup results containing success status and details for each component
    """
    server_display = f"{server_name} (ID: {server_id})" if server_name else f"ID: {server_id}"
    log.info(f"Starting cleanup for server: {server_display}")
    
    results = {
        "success": True,
        "session_data": False,
        "api_connections": False,
        "character_cards": {},
        "conversations": False,
        "short_id_mappings": False,
        "memory_files": 0,
        "errors": []
    }
    
    # 1. Clean session data
    try:
        results["session_data"] = await delete_server_session_data(server_id)
    except Exception as e:
        error_msg = f"Session data cleanup failed: {e}"
        results["errors"].append(error_msg)
        log.error(error_msg)
        results["success"] = False
    
    # 2. Clean API connections
    try:
        results["api_connections"] = await delete_server_api_connections(server_id)
    except Exception as e:
        error_msg = f"API connections cleanup failed: {e}"
        results["errors"].append(error_msg)
        log.error(error_msg)
        results["success"] = False
    
    # 3. Clean character cards (with smart deletion)
    try:
        from utils.func_character_cards import delete_server_character_cards
        results["character_cards"] = await delete_server_character_cards(server_id)
        if not results["character_cards"].get("success", False):
            results["success"] = False
    except Exception as e:
        error_msg = f"Character cards cleanup failed: {e}"
        results["errors"].append(error_msg)
        log.error(error_msg)
        results["success"] = False
        results["character_cards"] = {"success": False, "error": str(e)}

    # 4. Clean conversation history
    try:
        from messaging.store import get_store
        from utils.data_paths import DataPaths

        data_paths = DataPaths()
        channels = data_paths.list_channels(server_id)

        total_deleted = 0
        for channel_id in channels:
            store = get_store(server_id, channel_id)
            deleted = await store.delete_server_conversations(server_id)
            total_deleted += deleted

        results["conversations"] = total_deleted
    except Exception as e:
        error_msg = f"Conversations cleanup failed: {e}"
        results["errors"].append(error_msg)
        log.error(error_msg)
        results["success"] = False
    
    # 5. Clean short ID mappings
    try:
        from messaging.short_id_manager import get_short_id_manager
        manager = get_short_id_manager()
        results["short_id_mappings"] = await manager.delete_server_mappings(server_id)
    except Exception as e:
        error_msg = f"Short ID mappings cleanup failed: {e}"
        results["errors"].append(error_msg)
        log.error(error_msg)
        results["success"] = False
    
    # 6. Clean memory files
    try:
        from AI.tools.memory_tools import delete_server_memory_files
        results["memory_files"] = delete_server_memory_files(server_id)
    except Exception as e:
        error_msg = f"Memory files cleanup failed: {e}"
        results["errors"].append(error_msg)
        log.error(error_msg)
        results["success"] = False
    
    # Log summary
    if results["success"]:
        log.info(
            f"Successfully cleaned up data for server {server_display}:\n"
            f"  - Session data: {'✓' if results['session_data'] else '✗'}\n"
            f"  - API connections: {'✓' if results['api_connections'] else '✗'}\n"
            f"  - Character cards: {results['character_cards'].get('cards_unregistered', 0)} unregistered, "
            f"{results['character_cards'].get('files_deleted', 0)} files deleted\n"
            f"  - Conversations: {'✓' if results['conversations'] else '✗'}\n"
            f"  - Short ID mappings: {'✓' if results['short_id_mappings'] else '✗'}\n"
            f"  - Memory files: {results['memory_files']} deleted"
        )
    else:
        log.error(
            f"Cleanup completed with errors for server {server_display}. "
            f"Errors: {', '.join(results['errors'])}"
        )
    return results


async def cleanup_channel_data(server_id: str, channel_id: str, channel_name: str = None) -> Dict[str, Any]:
    """
    Cleanup all data for a deleted channel.
    
    This function is called when a channel is deleted from a server.
    It removes channel-specific data while preserving server-level data.
    
    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        channel_name: Channel name for logging (optional)
    
    Returns:
        Dict with cleanup results
    """
    channel_display = f"#{channel_name} (ID: {channel_id})" if channel_name else f"ID: {channel_id}"
    log.info(f"Starting cleanup for deleted channel: {channel_display}")
    
    results = {
        "success": True,
        "session_data": False,
        "conversations": False,
        "short_id_mappings": False,
        "memory_files": 0,
        "errors": []
    }
    
    # 1. Clean session data for this channel
    try:
        results["session_data"] = await remove_session_data(server_id, channel_id)
    except Exception as e:
        error_msg = f"Session data cleanup failed: {e}"
        results["errors"].append(error_msg)
        log.error(error_msg)
        results["success"] = False

    # 2. Clean conversation history for this channel
    try:
        from messaging.store import get_store
        store = get_store(server_id, channel_id)
        results["conversations"] = await store.delete_channel_conversations(server_id, channel_id)
    except Exception as e:
        error_msg = f"Conversations cleanup failed: {e}"
        results["errors"].append(error_msg)
        log.error(error_msg)
        results["success"] = False
    
    # 3. Clean short ID mappings for this channel
    try:
        from messaging.short_id_manager import get_short_id_manager
        manager = get_short_id_manager()
        results["short_id_mappings"] = await manager.delete_channel_mappings(server_id, channel_id)
    except Exception as e:
        error_msg = f"Short ID mappings cleanup failed: {e}"
        results["errors"].append(error_msg)
        log.error(error_msg)
        results["success"] = False
    
    # 4. Clean memory files for this channel
    try:
        from AI.tools.memory_tools import delete_channel_memory_files
        results["memory_files"] = delete_channel_memory_files(server_id, channel_id)
    except Exception as e:
        error_msg = f"Memory files cleanup failed: {e}"
        results["errors"].append(error_msg)
        log.error(error_msg)
        results["success"] = False
    
    # Log summary
    if results["success"]:
        log.info(
            f"Successfully cleaned up data for channel {channel_display}:\n"
            f"  - Session data: {'✓' if results['session_data'] else '✗'}\n"
            f"  - Conversations: {'✓' if results['conversations'] else '✗'}\n"
            f"  - Short ID mappings: {'✓' if results['short_id_mappings'] else '✗'}\n"
            f"  - Memory files: {results['memory_files']} deleted"
        )
    else:
        log.error(
            f"Cleanup completed with errors for channel {channel_display}. "
            f"Errors: {', '.join(results['errors'])}"
        )
    
    return results


