"""
AI Configuration Manager

This module manages AI behavior configuration with a hierarchical system:
- Global defaults (defined in this file)
- AI-level overrides (session.json)

The configuration system auto-generates files on first run and handles
version updates similar to config_updater.py.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from ruamel.yaml import YAML
from packaging import version

import utils.func as func
from utils.config_updater import merge_ordered

# Set up ruamel.yaml in round-trip mode (preserves order and comments)
yaml = YAML(typ='rt')
yaml.preserve_quotes = True
yaml.encoding = "utf-8"

DEFAULT_AI_CONFIG_CONTENT = r"""version: "1.0.3"
# DEFAULT AI CONFIGURATION
# This file contains all default configuration values for AI behavior.
# Edit these values to change the default behavior for all new AIs.

# Display Settings - How the AI appears and sends messages
use_card_ai_display_name: true
send_the_greeting_message: true
send_message_line_by_line: false

# Timing Settings - When and how fast the AI responds
delay_for_generation: 4.0
cache_count_threshold: 5
engaged_delay: 2.5
engaged_message_threshold: 3

new_chat_on_reset: false
auto_add_generation_reactions: false # Automatically adds navigation reactions to the bot's most recent message. (◀️, ▶️, 🔄)

# Error Handling, how LLM errors are processed and displayed
error_handling_mode: "friendly"  # Options: friendly (user-friendly messages), detailed (show exception details), silent (don't send errors)
save_errors_in_history: false    # Save error messages in conversation history (allows LLM to see past errors)
send_errors_to_chat: true        # Send error messages to Discord channel (if false, errors are silent to users)

# Text Processing - How messages are formatted
remove_ai_text_from:
  - '\*[^*]*\*'      # Remove *asterisks*
  - '\[[^\]]*\]'     # Remove [brackets]
remove_ai_emoji: false

# Optimized message format - clear, concise, and LLM-friendly
# Shows display name with username and short ID: [11:09] Rarin (@lixxrarin) #1: message
# {attachments} and {stickers} are automatically appended if present
user_format_syntax: "[{time}] {name} (@{username}) #{short_id}: {message}{attachments}{stickers}"

# Optimized reply format, includes quote of original message for LLM context
# Format: > Author: original message
#         [11:09] User (@user) #2 → #1: message
user_reply_format_syntax: "{quote}[{time}] {name} (@{username}) #{short_id} → #{reply_short_id}: {message}{attachments}{stickers}"

# Attachment and Sticker Format Templates
# These control how attachments and stickers are displayed in the message context
# Note: When vision is enabled, images are sent as actual image data to the API
# These templates only affect the TEXT representation in the context
attachment_format: "[Attachment: {filename}]"  # Format for each attachment
sticker_format: "[Sticker: {name}]"  # Format for each sticker

# Available variables for customization:
# - {time}: Message time (HH:MM format)
# - {username}: Discord username (use for mentions)
# - {name}: Display name
# - {message}: User message content
# - {message_id}: Full Discord message ID (17-20 digits)
# - {short_id}: Short message ID (1-16 digits), use for replies (save tokens)
# - {attachments}: Formatted list of attachments (uses attachment_format template)
# - {stickers}: Formatted list of stickers (uses sticker_format template)
# - {quote}: Quote of original message in replies (format: "> Author Name: content\n")
# - {reply_username}: Reply target username
# - {reply_name}: Reply target display name
# - {reply_message}: Original message being replied to
# - {reply_message_id}: Original message ID (17-20 digits)
# - {reply_short_id}: Reply target short ID (1-16 digits)

# Attachment format variables:
# - {filename}: Name of the file
# - {url}: Direct URL to the file
# - {content_type}: MIME type (e.g., "image/png")
# - {size}: File size in bytes
#
# Sticker format variables:
# - {name}: Sticker name
# - {url}: Sticker URL
# - {id}: Sticker ID
# - {format}: Sticker format (e.g., "PNG", "APNG", "LOTTIE")

# Character Card Settings
greeting_index: 0
user_syntax_replacement: "none"  # Replace the syntax {{user}} with one of the following options: none, username, display_name, mention, id
use_lorebook: false # Not tested!!!
lorebook_scan_depth: 10

# Response Filter - Intelligent filtering
use_response_filter: false
response_filter_api_connection: null
response_filter_fallback: "respond"  # Options: respond, ignore
response_filter_timeout: 5.0

# Reply System - AI can reply to specific messages
enable_reply_system: false
reply_prompt: |
  Reply Syntax: <REPLY:ID> [your response]
  
  WHEN TO USE REPLIES (Be proactive):
  
  ALWAYS use <REPLY:ID> when:
  • Multiple people are actively talking (group chat) for clarity
  • Responding to a message that's not the most recent one
  • Answering a specific question from someone
  • Continuing a conversation thread from earlier messages
  • Any ambiguity about who/what you're responding to
  
  ONLY skip replies when:
  • True 1:1 conversation (just you and one person, back-and-forth)
  • Making a general statement to everyone
  • Starting a new topic
  
  MENTIONS: Use @username when:
  • You want to get someone's attention
  • Replying to them (combine with <REPLY:ID>)
  • Referring to someone in your message
  
  Example: '<REPLY:5> @user This is the user who was asking about XXXX.'
  
  CONTEXT: You'll see quoted content showing what users replied to:
  > Author: original message (ID #1)
  [time] User (@user) #2 → #1: their reply
  
  Rules:
  1. Never use the same <REPLY:id> twice in one response
  2. Line breaks (\n) send separate messages
  3. When in doubt, USE the reply - it's better to over-use than under-use
  
  EXAMPLES:
  • Group chat: '<REPLY:3> Hello, user.' (ALWAYS reply in groups)
  • Older message: '@John about your question earlier, yes!'
  • General: 'Hey everyone! How's it going?' (no reply needed)

# Ignore System, LLM decides during generation to skip responding
enable_ignore_system: false
ignore_sleep_threshold: 3
ignore_prompt: |
  Ignore Syntax:
  
  You can use <IGNORE> when you detect conversations not directed at you.
  
  When to use <IGNORE>:
  - Users are talking among themselves
  - Conversation is not directed at you
  - You have nothing useful to contribute
  - A complement to the user's previous sentence that does not need to be responded to (e.g., emoji)
  - Context makes it clear you shouldn't respond
  
  When you decide not to respond, output ONLY: <IGNORE>
  Do not add any other text or explanation.

# Sleep Mode, AI stops responding after too many refusals
sleep_mode_enabled: false
sleep_mode_threshold: 5

# Tool Calling, LLM function calling for enhanced capabilities
# Allows the AI to call tools like get_message_info, get_emoji_info, get_user_info, and memory tools
# Memory system requires tool_calling.enabled: true to work
tool_calling:
  enabled: false
  allowed_tools: ["all"]

# Memory System. Persistent memory across conversations
# Allows the AI to save, read, update, and remove information using memory tools
# REQUIRES: tool_calling.enabled: true
# When enabled, saved memories are injected into the prompt and LLM can manage them
enable_memory_system: false
memory_max_tokens: 1500  # Maximum tokens allowed in memory

# Memory System Prompt Template
# Variables: {{memory}}, {{char}}, {{user}}, {{memory_count}}, {{ai_name}}
memory_prompt: |
  Your Persistent Memory:
  
  {{memory}}
  
  You can manage your memories using: list_memories, add_memory, update_memory, remove_memory, search_memories

# Tool Calling Instructions
# Helps the LLM understand when and how to use tools proactively
# Variables: {{char}}, {{user}}
tool_calling_prompt: |
  # Use Tools Proactively
  
  You MUST use tools automatically when you encounter these patterns - don't wait to be asked:
  
  - #N or message IDs → get_message_info (always check actual message content)
  - <@ID> or user names → get_user_info (get real user details, don't guess)
  - :emoji: or "sticker" → get_emoji_info
  - #channel or "this channel" → get_channel_info
  - "server", "members", "roles" → get_server_info
  - Questions about past → search_memories or list_memories (check before answering)
  
  CRITICAL - Memory Management (Save/Update IMMEDIATELY):
  
  ALWAYS save NEW information:
  • Preferences: "I prefer X", "I like Y" → add_memory
  • Personal facts: "I'm a developer", "My name is X" → add_memory
  • Important context: "I'm working on X", "We have 50 members" → add_memory

  ALWAYS update CHANGED information:
  • Status updates: "We reached 100 members" (if you had ~100 saved) → update_memory
  • Corrections: "Actually I prefer Y" (if you had X saved) → update_memory
  • Progress: "I finished project X" (if you had "working on X") → update_memory
  • Any information that supersedes what you have saved → update_memory
  
  Process: When user shares info, FIRST check memories (list_memories/search_memories), THEN:
  - If it's new → add_memory
  - If it updates existing info → update_memory
  - If it contradicts saved info → update_memory
  
  Examples:
  • "I prefer dark mode" → add_memory(content="User prefers dark mode")
  • "We reached 100 members" → search_memories("members") → update_memory(memory_id=X, content="Server has 100 members")
  • "I finished the Python project" → search_memories("Python project") → update_memory
  • "Actually I'm a JavaScript developer" → search_memories("developer") → update_memory
  
  Key rule: Information changes over time. Keep your memory current by updating it automatically.

# Context Injection Order
# Customize the order in which context components are sent to the LLM
# Components are only included if their respective systems are enabled
# Available components:
#   - character_description: Character card description/personality
#   - system_message: Main system message
#   - lorebook_entries: Lorebook/world info entries
#   - memory_prompt: Persistent memory content
#   - tool_calling_prompt: Tool usage instructions
#   - reply_prompt: Reply system instructions
#   - ignore_prompt: Ignore system instructions
#   - conversation_history: Past messages in the conversation
#   - user_message: Current user message
context_order:
  - character_description
  - lorebook_entries
  - memory_prompt
  - tool_calling_prompt
  - reply_prompt
  - ignore_prompt
  - conversation_history
  - user_message
  - system_message

# Advanced Settings
system_message: |
  You are in a Discord chat. Keep responses short and casual, match the conversation's vibe.
  Respond proportionally. Short question = short answer. Don't write essays.
  Discord style: casual, quick messages. Use @username to mention, :emoji_name: for custom emojis.
  Respond naturally as your character, only your response, without the user format syntax.
"""


# Roleplay Preset. Optimized for 1-on-1 roleplay scenarios
ROLEPLAY_PRESET_OVERRIDES = {
    "delay_for_generation": 0.0,
    "cache_count_threshold": 1,
    "engaged_delay": 0.0,
    "enable_reply_system": False,
    "send_message_line_by_line": False,
    "user_syntax_replacement": "display_name",
    "use_lorebook": True,
    "system_message": "Write {{char}}'s next reply in a fictional chat between {{char}} and {{user}}.",
    "user_format_syntax": "{message}",
    "user_reply_format_syntax": "{message}",
    "remove_ai_text_from": [],
    "auto_add_generation_reactions": True,
    "error_handling_mode": "detailed",
    "save_errors_in_history": False,
    "send_errors_to_chat": True,
    "tool_calling": {
        "enabled": False,
        "allowed_tools": []
    }
}

# Discord Chat Preset. Natural casual behavior like a real server member
DISCORD_CHAT_PRESET_OVERRIDES = {
    "enable_reply_system": True,
    "enable_ignore_system": True,
    "sleep_mode_enabled": True,
    "send_message_line_by_line": True,
    "error_handling_mode": "friendly",
    "save_errors_in_history": True,
    "send_errors_to_chat": True,
    "enable_memory_system": True,
    "tool_calling": {
        "enabled": True,
        "allowed_tools": ["all"]
    }
}

# Builtin presets metadata
BUILTIN_PRESETS = {
    "default": {
        "name": "Default Preset",
        "description": "Default configuration. Original settings",
        "author": "LixxRarin",
        "version": "1.0.0",
        "overrides": {}  # No overrides. Pure default configuration!
    },
    "roleplay": {
        "name": "Roleplayer!",
        "description": "Optimized for 1-on-1 roleplay scenarios with immediate responses",
        "author": "LixxRarin",
        "version": "1.0.0",
        "overrides": ROLEPLAY_PRESET_OVERRIDES
    },
    "discord-chat": {
        "name": "Discord-Chat",
        "description": "Natural and casual Discord chat behavior, acts like a real server member (Works best with optimized character cards)",
        "author": "LixxRarin",
        "version": "1.0.0",
        "overrides": DISCORD_CHAT_PRESET_OVERRIDES
    }
}


class AIConfigManager:
    """
    Manages AI configuration with hierarchical overrides.
    
    Configuration hierarchy (lowest to highest priority):
    1. Global defaults (this file)
    2. AI-level config (session.json)
    """
    
    def __init__(self, config_dir: str = "config"):
        """
        Initialize the AI configuration manager.
        
        Args:
            config_dir: Directory to store configuration files
        """
        self.config_dir = Path(config_dir)
        self.defaults_file = self.config_dir / "defaults.yml"
        self.presets_dir = self.config_dir / "presets"
        
        # Load default configuration from constant
        self.default_config = yaml.load(DEFAULT_AI_CONFIG_CONTENT)
    
    def _ensure_directories(self):
        """Ensure all necessary directories exist."""
        self.config_dir.mkdir(exist_ok=True)
        self.presets_dir.mkdir(exist_ok=True)
    
    def _load_defaults_file(self):
        """
        Load the existing defaults.yml file.
        
        Returns:
            The parsed configuration if the file exists and is valid,
            otherwise returns None.
        """
        if not self.defaults_file.exists():
            return None
        try:
            with open(self.defaults_file, "r", encoding="utf-8") as f:
                return yaml.load(f)
        except Exception as e:
            func.log.error(f"Error loading defaults.yml: {e}")
            return None
    
    def _is_version_outdated(self, user_config):
        """
        Check if the user configuration is outdated compared to the default configuration.
        
        Args:
            user_config: The loaded user configuration
            
        Returns:
            True if the user's version is less than the default version, False otherwise.
        """
        if user_config is None:
            return False
        
        user_version = user_config.get("version")
        default_version = self.default_config.get("version")
        
        if user_version is None:
            func.log.warning("No version found in defaults.yml. Assuming outdated.")
            return True
        
        try:
            return version.parse(user_version) < version.parse(default_version)
        except Exception as e:
            func.log.error(f"Error comparing versions: {e}")
            return False
    
    def _merge_configs(self, user_config):
        """
        Merge the user configuration with the default configuration.
        
        This method:
          - Preserves the order of keys as defined in the default configuration.
          - Discards any extra keys that are not present in the default configuration.
          - Updates the root "version" key to match the default configuration.
          
        Args:
            user_config: The loaded user configuration
            
        Returns:
            Merged configuration
        """
        if user_config is None:
            return self.default_config
        
        merged = merge_ordered(user_config, self.default_config)
        # Ensure the "version" key is updated to the default version
        merged["version"] = self.default_config.get("version")
        return merged
    
    def _merge_config(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge default configuration with specific overrides.
        
        Args:
            overrides: Dictionary with values that differ from defaults
            
        Returns:
            Complete merged configuration
        """
        merged = dict(self.default_config)
        merged.pop("version", None)  # Remove version from config
        merged.update(overrides)
        return merged
    
    def _create_builtin_preset(self, preset_key: str) -> bool:
        """
        Create a builtin preset from its overrides.
        
        Args:
            preset_key: Key in BUILTIN_PRESETS dict
            
        Returns:
            True if created successfully
        """
        if preset_key not in BUILTIN_PRESETS:
            func.log.error(f"Unknown builtin preset: {preset_key}")
            return False
        
        preset_meta = BUILTIN_PRESETS[preset_key]
        preset_name = preset_meta["name"]
        
        # Check if preset already exists
        preset_file = self.presets_dir / f"{preset_name}.yml"
        if preset_file.exists():
            return True
        
        # Merge default config with overrides
        config = self._merge_config(preset_meta["overrides"])
        
        # Save the preset
        return self.save_preset(
            preset_name=preset_name,
            config=config,
            description=preset_meta["description"],
            author=preset_meta["author"]
        )
    
    async def initialize(self):
        """
        Initialize configuration system.
        Creates default files and builtin presets if they don't exist.
        Checks and updates defaults.yml if version is outdated.
        """
        self._ensure_directories()
        
        # Load existing defaults.yml if it exists
        user_config = self._load_defaults_file()
        
        # Create defaults.yml if it doesn't exist
        if user_config is None:
            func.log.warning(f"Configuration file '{self.defaults_file}' not found. Creating a new one...")
            try:
                with open(self.defaults_file, "w", encoding="utf-8") as f:
                    yaml.dump(self.default_config, f)
                func.log.info(f"Created {self.defaults_file}")
            except Exception as e:
                func.log.critical(f"Failed to create defaults file: {e}")
        # Update defaults.yml if version is outdated
        elif self._is_version_outdated(user_config):
            func.log.warning(
                f"Updating configuration '{self.defaults_file}' to version {self.default_config.get('version')}"
            )
            updated_config = self._merge_configs(user_config)
            try:
                with open(self.defaults_file, "w", encoding="utf-8") as f:
                    yaml.dump(updated_config, f)
                func.log.info(f"Configuration file '{self.defaults_file}' updated successfully!")
            except Exception as e:
                func.log.critical(f"Failed to update configuration file: {e}")
        else:
            func.log.info(f"Configuration file '{self.defaults_file}' is up-to-date.")
        
        # Create builtin presets
        for preset_key in BUILTIN_PRESETS.keys():
            try:
                if self._create_builtin_preset(preset_key):
                    pass
            except Exception as e:
                func.log.error(f"Error creating builtin preset '{preset_key}': {e}")
    
    def get_defaults(self) -> Dict[str, Any]:
        """
        Get default configuration values (excluding version).
        
        Returns:
            Dict with configuration keys and their default values
        """
        config = dict(self.default_config)
        config.pop("version", None)  # Remove version key
        return config
    
    def save_preset(self, preset_name: str, config: Dict[str, Any],
                   description: str = "", author: str = "user") -> bool:
        """
        Save a configuration preset.
        
        Args:
            preset_name: Name of the preset
            config: Configuration dictionary
            description: Optional description
            author: Author name
            
        Returns:
            True if saved successfully
        """
        self._ensure_directories()
        
        preset_data = {
            "name": preset_name,
            "description": description,
            "author": author,
            "version": "1.0.0",
            "config": config
        }
        
        preset_file = self.presets_dir / f"{preset_name}.yml"
        try:
            with open(preset_file, "w", encoding="utf-8") as f:
                yaml.dump(preset_data, f)
            func.log.info(f"Saved preset '{preset_name}' to {preset_file}")
            return True
        except Exception as e:
            func.log.error(f"Error saving preset '{preset_name}': {e}")
            return False
    
    def load_preset(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """
        Load a configuration preset.
        
        Args:
            preset_name: Name of the preset
            
        Returns:
            Preset configuration dict or None if not found
        """
        preset_file = self.presets_dir / f"{preset_name}.yml"
        if not preset_file.exists():
            func.log.warning(f"Preset '{preset_name}' not found")
            return None
        
        try:
            with open(preset_file, "r", encoding="utf-8") as f:
                preset_data = yaml.load(f)
                return preset_data.get("config", {})
        except Exception as e:
            func.log.error(f"Error loading preset '{preset_name}': {e}")
            return None
    
    def list_presets(self) -> list[Dict[str, str]]:
        """
        List all available presets.
        
        Returns:
            List of dicts with preset info (name, description, author)
        """
        if not self.presets_dir.exists():
            return []
        
        presets = []
        for preset_file in self.presets_dir.glob("*.yml"):
            try:
                with open(preset_file, "r", encoding="utf-8") as f:
                    preset_data = yaml.load(f)
                    presets.append({
                        "name": preset_data.get("name", preset_file.stem),
                        "description": preset_data.get("description", ""),
                        "author": preset_data.get("author", "unknown")
                    })
            except Exception as e:
                func.log.error(f"Error reading preset {preset_file}: {e}")
        
        return presets
    
    def delete_preset(self, preset_name: str) -> bool:
        """
        Delete a configuration preset.
        
        Args:
            preset_name: Name of the preset
            
        Returns:
            True if deleted successfully
        """
        preset_file = self.presets_dir / f"{preset_name}.yml"
        if not preset_file.exists():
            return False
        
        try:
            preset_file.unlink()
            func.log.info(f"Deleted preset '{preset_name}'")
            return True
        except Exception as e:
            func.log.error(f"Error deleting preset '{preset_name}': {e}")
            return False


def get_vision_config(
    session: Dict[str, Any],
    server_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Resolve vision configuration from API connection or session config.
    
    This centralizes vision config resolution to avoid duplication and inconsistency.
    
    Priority:
    1. API connection settings (if available)
    2. Session config settings
    3. Default values
    
    Args:
        session: AI session data
        server_id: Server ID for API connection resolution
        
    Returns:
        Dict with vision_enabled, vision_detail, max_image_size
    """
    # Default values
    vision_config = {
        'vision_enabled': False,
        'vision_detail': 'auto',
        'max_image_size': 20
    }
    
    # Try API connection first (highest priority)
    if server_id:
        connection_name = session.get("api_connection")
        if connection_name:
            connection = func.get_api_connection(server_id, connection_name)
            if connection:
                vision_config.update({
                    'vision_enabled': connection.get('vision_enabled', False),
                    'vision_detail': connection.get('vision_detail', 'auto'),
                    'max_image_size': connection.get('max_image_size', 20)
                })
                return vision_config
    
    # Fallback to session config
    config = session.get("config", {})
    vision_config.update({
        'vision_enabled': config.get('vision_enabled', False),
        'vision_detail': config.get('vision_detail', 'auto'),
        'max_image_size': config.get('max_image_size', 20)
    })
    
    return vision_config


# Global instance
_ai_config_manager: Optional[AIConfigManager] = None


def get_ai_config_manager() -> AIConfigManager:
    """Get the global AI configuration manager instance."""
    global _ai_config_manager
    if _ai_config_manager is None:
        _ai_config_manager = AIConfigManager()
    return _ai_config_manager


async def initialize_ai_config():
    """Initialize the AI configuration system."""
    manager = get_ai_config_manager()
    await manager.initialize()

