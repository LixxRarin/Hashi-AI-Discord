import asyncio
import datetime
import logging
import socket
import time
from typing import Any, Dict, Optional, Callable, Awaitable, TypeVar

import yaml
from colorama import Fore, init

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
        LOG_COLORS = {
            "DEBUG": Fore.CYAN,
            "INFO": Fore.GREEN,
            "WARNING": Fore.YELLOW,
            "ERROR": Fore.RED,
            "CRITICAL": Fore.RED + "\033[1m",
        }
        log_color = LOG_COLORS.get(record.levelname, Fore.WHITE)

        # Format timestamp using record time
        timestamp = datetime.datetime.fromtimestamp(
            record.created).strftime('%H:%M:%S')
        message = record.getMessage()

        # Display: [HH:MM:SS] LEVEL    [file:line] - message
        return f"{log_color}[{timestamp}] {record.levelname:<8} [{record.filename}:{record.lineno}] {Fore.RESET}- {message}"


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

    # Remove any existing handlers to ensure basicConfig applies correctly
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Configure file logging
    logging.basicConfig(
        level=logging.DEBUG,            # Global logging level
        filename="app.log",             # Log file name
        filemode="a",                   # Append mode
        format="[%(filename)s] %(levelname)s : %(message)s",
        encoding="utf-8",
    )

    # Create a console handler with colors
    console_handler = logging.StreamHandler()

    if debug_mode:
        console_handler.setLevel(logging.DEBUG)
    else:
        console_handler.setLevel(logging.INFO)

    console_handler.setFormatter(ColoredFormatter())

    # Add the console handler to the root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(console_handler)

    # Silence noisy third-party libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

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




def get_conversations_file() -> str:
    """
    Get the unified conversations file path.
    This is the NEW file that replaces conversation_history.json, message_tracking.json,
    and generation_cache.json.
    
    Returns:
        str: Path to the conversations file
    """
    return "data/conversations.json"




def get_session_file() -> str:
    """
    Get the session file path from configuration.
    
    Returns:
        str: Path to the session file
    """
    config = load_config()
    return config.get("Data", {}).get("session_file", "data/session.json")


def get_api_connections_file() -> str:
    """
    Get the API connections file path from configuration.
    
    Returns:
        str: Path to the API connections file
    """
    config = load_config()
    return config.get("Data", {}).get("api_connections_file", "data/api_connections.json")


def get_character_cards_file() -> str:
    """
    Get the character cards file path from configuration.
    
    Returns:
        str: Path to the character cards file
    """
    config = load_config()
    return config.get("Data", {}).get("character_cards_file", "data/character_cards.json")


def get_debug_config_file() -> str:
    """
    Get the debug config file path from configuration.
    
    Returns:
        str: Path to the debug config file
    """
    config = load_config()
    return config.get("Data", {}).get("debug_config_file", "data/debug_config.json")



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
    """Loads session data from session.json into memory cache"""
    global session_cache
    session_cache = await asyncio.to_thread(read_json, get_session_file()) or {}
    log.info(f"Loaded session cache with {len(session_cache)} servers")


async def update_session_data(server_id: str, channel_id: str, new_data: Dict[str, Any]) -> None:
    """
    Updates the session data for a specific server and channel.

    Args:
        server_id: Server ID
        channel_id: Channel ID
        new_data: New session data
    """
    # Update in-memory cache
    if server_id not in session_cache:
        session_cache[server_id] = {"channels": {}}
    if "channels" not in session_cache[server_id]:
        session_cache[server_id]["channels"] = {}
    session_cache[server_id]["channels"][channel_id] = new_data

    # Write directly to file
    session_data = await asyncio.to_thread(read_json, get_session_file()) or {}
    
    if server_id not in session_data:
        session_data[server_id] = {"channels": {}}
    if "channels" not in session_data[server_id]:
        session_data[server_id]["channels"] = {}
    
    if new_data is None:  # If new_data is None, it means we are removing the channel
        if channel_id in session_data[server_id]["channels"]:
            del session_data[server_id]["channels"][channel_id]
    else:
        session_data[server_id]["channels"][channel_id] = new_data
    
    await asyncio.to_thread(write_json, get_session_file(), session_data)
    log.debug(f"Updated session data for server {server_id}, channel {channel_id}")


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
        log.info(f"Removed session data for server {server_id}, channel {channel_id} from cache.")

        # Update persistent storage directly
        await update_session_data(server_id, channel_id, None)

async def load_api_connections() -> Dict[str, Dict[str, Any]]:
    """
    Load API connections from api_connections.json file.
    
    Returns:
        Dict[str, Dict[str, Any]]: Dictionary of connections by server
    """
    return await asyncio.to_thread(read_json, get_api_connections_file()) or {}


async def save_api_connections(data: Dict[str, Dict[str, Any]]) -> None:
    """
    Save API connections to api_connections.json file.
    
    Args:
        data: Dictionary of connections to save
    """
    await asyncio.to_thread(write_json, get_api_connections_file(), data)


def get_api_connection(server_id: str, connection_name: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific API connection.
    
    Args:
        server_id: Server ID
        connection_name: Connection name
        
    Returns:
        Optional[Dict[str, Any]]: Connection data or None if not found
    """
    connections = read_json(get_api_connections_file()) or {}
    return connections.get(server_id, {}).get(connection_name)


async def create_api_connection(
    server_id: str,
    connection_name: str,
    provider: str,
    api_key: str,
    model: str,
    base_url: Optional[str] = None,
    max_tokens: int = 1000,
    temperature: float = 0.7,
    top_p: float = 1.0,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    context_size: int = 64000,
    think_switch: bool = True,
    think_depth: int = 3,
    hide_thinking_tags: bool = True,
    thinking_tag_patterns: Optional[list[str]] = None,
    max_tool_rounds: int = 5,
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
        log.warning(f"Connection '{connection_name}' already exists in server {server_id}")
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
    log.info(f"Created API connection '{connection_name}' in server {server_id}")
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
        log.warning(f"Connection '{connection_name}' not found in server {server_id}")
        return False
    
    # Remove None values from updates
    updates = {k: v for k, v in updates.items() if v is not None}
    
    connections[server_id][connection_name].update(updates)
    await save_api_connections(connections)
    log.info(f"Updated API connection '{connection_name}' in server {server_id}")
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
    log.info(f"Renamed API connection '{old_connection_name}' to '{new_connection_name}' in server {server_id}")
    
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
        log.warning(f"Connection '{connection_name}' not found in server {server_id}")
        return False
    
    del connections[server_id][connection_name]
    
    # Clean up empty server entries
    if not connections[server_id]:
        del connections[server_id]
    
    await save_api_connections(connections)
    log.info(f"Deleted API connection '{connection_name}' from server {server_id}")
    return True


def list_api_connections(server_id: str) -> Dict[str, Any]:
    """
    List all API connections for a server.
    
    Args:
        server_id: Server ID
        
    Returns:
        Dict[str, Any]: Dictionary of server connections
    """
    connections = read_json(get_api_connections_file()) or {}
    return connections.get(server_id, {})


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

