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

import utils.func as func

# Set up ruamel.yaml in round-trip mode (preserves order and comments)
yaml = YAML(typ='rt')
yaml.preserve_quotes = True
yaml.encoding = "utf-8"

DEFAULT_AI_CONFIG_CONTENT = r"""version: "1.0.1"
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
user_format_syntax: "[{time}] {name} (@{username}) #{short_id}: {message}"

# Optimized reply format, includes quote of original message for LLM context
# Format: > Author: original message
#         [11:09] User (@user) #2 → #1: message
user_reply_format_syntax: "{quote}[{time}] {name} (@{username}) #{short_id} → #{reply_short_id}: {message}"

# Available variables for customization:
# - {time}: Message time (HH:MM format)
# - {username}: Discord username (use for mentions)
# - {name}: Display name
# - {message}: Message content
# - {message_id}: Full Discord message ID (17-20 digits)
# - {short_id}: Short message ID (1-16 digits), use for replies (save tokens)
# - {quote}: Quote of original message in replies (format: "> Author Name: content\n")
# - {reply_username}: Reply target username
# - {reply_name}: Reply target display name
# - {reply_message}: Original message being replied to
# - {reply_message_id}: Original message ID (17-20 digits)
# - {reply_short_id}: Reply target short ID (1-16 digits)

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
  Reply Syntax:
  
  You CAN reply to specific messages using: <REPLY:ID> [your response]
  
  CONTEXT: When users reply to messages, you'll see quoted content like:
  > Author: original message (ID #1)
  [time] User (@user) #2 → #1: their reply
  
  This quote shows what they're replying to, giving you full context.
  
  You choose when it's useful:
  - Want to reference a specific message? Use it.
  - Multiple users and you want clarity? Use it.
  - Natural 1:1 conversation flow? Skip it.
  
  Rules:
  1. Never use the same <REPLY:id> more than once per response
  2. Line breaks (\n) send separate messages, keep single replies on one line
  3. Use REPLY tags only when necessary to avoid ambiguity.
  
  EXAMPLES:
  - '<REPLY:1> Hey!\n<REPLY:2> Hello to you too!'
  - '<REPLY:3> Cats are amazing! They sleep 16h a day and are very independent.'
  - Or just: '@everyone Hey everyone, what's up?' (no reply needed)
  - 'Message 1!\nMessage 2!'

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
# Allows the AI to call tools like get_message_info, get_emoji_info, get_user_info
tool_calling:
  enabled: false
  allowed_tools: ["all"]

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
        """
        self._ensure_directories()
        
        # Create defaults.yml if it doesn't exist
        if not self.defaults_file.exists():
            func.log.info("Creating default AI configuration file...")
            try:
                with open(self.defaults_file, "w", encoding="utf-8") as f:
                    yaml.dump(self.default_config, f)
                func.log.info(f"Created {self.defaults_file}")
            except Exception as e:
                func.log.error(f"Error creating defaults file: {e}")
        
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

