"""
Config Metadata - Categories, Validation, and UI Helpers

Provides:
- Fixed category definitions (easy to extend)
- Validation rules
- User-friendly labels
- UI component generation

To add a new config:
1. Add to defaults.yml
2. Add to appropriate category in CONFIG_CATEGORIES
3. Done! Type/validation auto-detected
"""

import discord
from discord import ui
from typing import Any, Dict, Optional, Tuple, List
import re

import utils.func as func


# Category emojis for visual distinction
CATEGORY_EMOJIS: Dict[str, str] = {
    "Display & Messaging": "💬",
    "Timing & Delays": "⏱️",
    "Text Processing": "✂️",
    "Message Action Buttons": "🔘",
    "Character Card": "🎭",
    "Response Filter": "🔍",
    "Reply System": "💬",
    "Reaction System": "😊",
    "Ignore System": "🚫",
    "Poll System": "🗳️",
    "Block System": "📦",
    "Embed System": "💎",
    "Tool Calling": "🔧",
    "Memory System": "🧠",
    "Moderation Tools": "🛡️",
    "Sleep Mode": "😴",
    "Advanced Settings": "⚙️",
}


CONFIG_CATEGORIES: Dict[str, List[str]] = {
    "Display & Messaging": [
        "use_card_ai_display_name",
        "send_the_greeting_message",
        "send_message_line_by_line",
        "new_chat_on_reset",
    ],
    
    "Timing & Delays": [
        "delay_for_generation",
        "cache_count_threshold",
        "engaged_delay",
        "engaged_message_threshold",
        "typing_detection_enabled",
        "typing_grace_period",
    ],
    
    "Text Processing": [
        "remove_ai_text_from",
        "remove_ai_emoji",
        "error_handling_mode",
        "save_errors_in_history",
        "send_errors_to_chat",
        "user_format_syntax",
        "user_reply_format_syntax",
        "attachment_format",
        "sticker_format",
        "edit_marker_text",
        "delete_marker_text",
        "show_original_on_edit",
        "edit_format",
        "enable_delete_tracking",
        "show_content_on_delete",
    ],
  
    "Message Action Buttons": [
        "message_action_buttons.enabled",
        "message_action_buttons.buttons",
    ],
    
    "Character Card": [
        "greeting_index",
        "user_syntax_replacement",
        "use_lorebook",
        "lorebook_scan_depth",
    ],
    
    "Response Filter": [
        "use_response_filter",
        "response_filter_api_connection",
        "response_filter_fallback",
        "response_filter_timeout",
    ],
    
    "Reply System": [
        "advanced_expressions.reply.enabled",
        "advanced_expressions.reply.prompt",
    ],
    
    "Reaction System": [
        "advanced_expressions.reaction.enabled",
        "advanced_expressions.reaction.prompt",
    ],
    
    "Ignore System": [
        "advanced_expressions.ignore.enabled",
        "advanced_expressions.ignore.prompt",
        "advanced_expressions.ignore.sleep_threshold",
    ],
    
    "Poll System": [
        "advanced_expressions.poll.enabled",
        "advanced_expressions.poll.prompt",
    ],
    
    "Block System": [
        "advanced_expressions.block.enabled",
        "advanced_expressions.block.prompt",
    ],
    
    "Embed System": [
        "advanced_expressions.embed.enabled",
        "advanced_expressions.embed.prompt",
    ],
    
    "Tool Calling": [
        "tool_calling.enabled",
        "tool_calling.allowed_tools",
        "tool_calling.tool_result_max_percentage",
        "tool_calling.tool_result_min_chars",
        "tool_calling.tool_result_max_chars",
    ],
    
    "Memory System": [
        "enable_memory_system",
        "memory_max_tokens",
        "memory_prompt",
    ],
    
    "Moderation Tools": [
        "enable_moderation_tools",
    ],
    
    "Sleep Mode": [
        "sleep_mode_enabled",
        "sleep_mode_threshold",
        "sleep_wakeup_patterns",
    ],
    
    "Advanced Settings": [
        "system_message",
        "context_order",
        "tool_calling_prompt",
    ],
}


def get_all_categories() -> List[str]:
    """Get list of all category names."""
    return list(CONFIG_CATEGORIES.keys())


def get_category_configs(category: str) -> List[str]:
    """Get list of config keys for a category."""
    return CONFIG_CATEGORIES.get(category, [])


def get_category_emoji(category: str) -> str:
    """Get emoji for a category."""
    return CATEGORY_EMOJIS.get(category, "⚙️")


def find_config_category(config_key: str) -> str:
    """Find which category a config belongs to."""
    for category, configs in CONFIG_CATEGORIES.items():
        if config_key in configs:
            return category
    return "Uncategorized"


class ConfigMetadata:
    """
    Metadata system for config validation and UI generation.
    
    Provides:
    - Validation rules (min/max, choices, regex)
    - User-friendly labels
    - UI component generation
    """
    
    # Validation rules by type
    VALIDATORS = {
        "float": {
            "delay_for_generation": {"min": 0.0},
            "engaged_delay": {"min": 0.0},
            "typing_grace_period": {"min": 0.0},
            "response_filter_timeout": {"min": 1.0},
        },
        "int": {
            "cache_count_threshold",
            "engaged_message_threshold",
            "greeting_index", 
            "lorebook_scan_depth", 
            "sleep_mode_threshold",
            "memory_max_tokens", 
        },
        "choice": {
            # String choices
            "error_handling_mode": ["friendly", "detailed", "silent"],
            "user_syntax_replacement": ["none", "username", "display_name", "mention", "id"],
            "response_filter_fallback": ["respond", "ignore"],
            
            # Boolean choices - Display & Messaging
            "use_card_ai_display_name": [True, False],
            "send_the_greeting_message": [True, False],
            "send_message_line_by_line": [True, False],
            "new_chat_on_reset": [True, False],
            
            # Boolean choices - Timing & Delays
            "typing_detection_enabled": [True, False],
            
            # Boolean choices - Text Processing
            "remove_ai_emoji": [True, False],
            "save_errors_in_history": [True, False],
            "send_errors_to_chat": [True, False],
            "show_original_on_edit": [True, False],
            "enable_delete_tracking": [True, False],
            "show_content_on_delete": [True, False],
            
            # Boolean choices - Message Action Buttons
            "message_action_buttons.enabled": [True, False],
            
            # Boolean choices - Character Card
            "use_lorebook": [True, False],
            
            # Boolean choices - Response Filter
            "use_response_filter": [True, False],
            
            # Boolean choices - Expression Systems
            "advanced_expressions.reply.enabled": [True, False],
            "advanced_expressions.reaction.enabled": [True, False],
            "advanced_expressions.ignore.enabled": [True, False],
            "advanced_expressions.poll.enabled": [True, False],
            "advanced_expressions.block.enabled": [True, False],
            "advanced_expressions.embed.enabled": [True, False],
            
            # Boolean choices - Tool Calling
            "tool_calling.enabled": [True, False],
            
            # Boolean choices - Memory System
            "enable_memory_system": [True, False],
            
            # Boolean choices - Moderation Tools
            "enable_moderation_tools": [True, False],
            
            # Boolean choices - Sleep Mode
            "sleep_mode_enabled": [True, False],
        }
    }
    
    # User-friendly labels (auto-generated from name if not specified)
    LABELS = {
        "delay_for_generation": "Generation Delay",
        "use_card_ai_display_name": "Use Card Display Name",
        "cache_count_threshold": "Cache Threshold",
        "send_the_greeting_message": "Send Greeting Message",
        "send_message_line_by_line": "Send Line by Line",
        "engaged_delay": "Engaged Delay",
        "engaged_message_threshold": "Engaged Threshold",
        "typing_detection_enabled": "Typing Detection",
        "typing_grace_period": "Typing Grace Period",
        "new_chat_on_reset": "New Chat on Reset",
        "error_handling_mode": "Error Handling Mode",
        "save_errors_in_history": "Save Errors in History",
        "send_errors_to_chat": "Send Errors to Chat",
        "remove_ai_emoji": "Remove AI Emoji",
        "greeting_index": "Greeting Index",
        "user_syntax_replacement": "{{user}} Replacement",
        "use_lorebook": "Use Lorebook",
        "lorebook_scan_depth": "Lorebook Scan Depth",
        "use_response_filter": "Use Response Filter",
        "response_filter_api_connection": "Filter API Connection",
        "response_filter_fallback": "Filter Fallback",
        "response_filter_timeout": "Filter Timeout",
        "sleep_mode_enabled": "Sleep Mode Enabled",
        "sleep_mode_threshold": "Sleep Mode Threshold",
        "enable_memory_system": "Memory System",
        "memory_max_tokens": "Memory Max Tokens",
        "enable_moderation_tools": "Moderation Tools",
        "message_action_buttons.enabled": "Enable Action Buttons",
        "message_action_buttons.buttons": "Button Configuration",
    }
    
    # Descriptions (extracted from YAML comments or provided here)
    DESCRIPTIONS = {
        "delay_for_generation": "Seconds to wait before responding",
        "use_card_ai_display_name": "Use character card display name for webhook",
        "cache_count_threshold": "Number of messages before responding",
        "send_the_greeting_message": "Send greeting when starting chat",
        "send_message_line_by_line": "Send messages one line at a time",
        "engaged_delay": "Reduced delay when conversation is active",
        "engaged_message_threshold": "Messages to activate engaged mode",
        "typing_detection_enabled": "Wait for user to stop typing",
        "typing_grace_period": "Seconds after user stops typing",
        "error_handling_mode": "How to format LLM errors",
        "save_errors_in_history": "Save errors in history (LLM can see)",
        "send_errors_to_chat": "Send errors to Discord channel",
        "remove_ai_emoji": "Remove emojis from responses",
        "greeting_index": "Which greeting to use (0=first)",
        "user_syntax_replacement": "How to replace {{user}}",
        "use_lorebook": "Enable lorebook entries",
        "lorebook_scan_depth": "Messages to scan for triggers",
        "use_response_filter": "Intelligent response filtering",
        "response_filter_api_connection": "Connection for filter (requires Tool Calling)",
        "response_filter_fallback": "What to do if filter fails",
        "response_filter_timeout": "Maximum wait time for filter",
        "sleep_mode_enabled": "AI stops responding after refusals",
        "sleep_mode_threshold": "Consecutive refusals before sleep",
        "enable_memory_system": "Persistent memory across conversations",
        "memory_max_tokens": "Maximum tokens allowed in memory",
        "enable_moderation_tools": "Allow AI to moderate users (DANGEROUS!)",
        "message_action_buttons.enabled": "Show Discord UI buttons on AI messages (previous/next/regenerate/delete/edit)",
        "message_action_buttons.buttons": "List of buttons to display (type, emoji, label, style, enabled for each button)",
    }
    
    def is_choice_config(self, config_key: str) -> bool:
        """
        Check if config has predefined choices.
        
        Args:
            config_key: Config key to check
        
        Returns:
            True if config has predefined choices
        """
        return config_key in self.VALIDATORS.get("choice", {})
    
    def get_choices(self, config_key: str) -> List[str]:
        """
        Get available choices for a choice config.
        
        Args:
            config_key: Config key
        
        Returns:
            List of available choices, or empty list if not a choice config
        """
        return self.VALIDATORS.get("choice", {}).get(config_key, [])
    
    def get_label(self, config_name: str) -> str:
        """
        Get user-friendly label for config.
        
        Args:
            config_name: Config name
        
        Returns:
            User-friendly label
        """
        # Check if we have a custom label
        if config_name in self.LABELS:
            return self.LABELS[config_name]
        
        # Auto-generate from name
        # Convert snake_case to Title Case
        return config_name.replace('_', ' ').title()
    
    def get_description(self, config_name: str) -> str:
        """
        Get description for config.
        
        Args:
            config_name: Config name
        
        Returns:
            Description or empty string
        """
        return self.DESCRIPTIONS.get(config_name, "")
    
    def validate_value(
        self,
        config_name: str,
        value: Any,
        config_type: str
    ) -> Tuple[bool, str]:
        """
        Validate config value.
        
        Args:
            config_name: Config name
            value: Value to validate
            config_type: Expected type
        
        Returns:
            (is_valid, error_message)
        """
        # Type conversion
        try:
            if config_type == "bool":
                if isinstance(value, str):
                    value = value.lower() in ["true", "1", "yes"]
                else:
                    value = bool(value)
            elif config_type == "int":
                value = int(value)
            elif config_type == "float":
                value = float(value)
            elif config_type == "str":
                value = str(value)
            elif config_type == "list":
                if isinstance(value, str):
                    # Parse comma-separated
                    value = [item.strip() for item in value.split(",") if item.strip()]
        except (ValueError, TypeError) as e:
            return False, f"Invalid value for type {config_type}: {e}"
        
        # Range validation for numbers
        if config_type in ["int", "float"]:
            validators = self.VALIDATORS.get(config_type, {})
            if config_name in validators:
                rules = validators[config_name]
                min_val = rules.get("min")
                max_val = rules.get("max")
                
                if min_val is not None and value < min_val:
                    return False, f"Value must be >= {min_val}"
                if max_val is not None and value > max_val:
                    return False, f"Value must be <= {max_val}"
        
        # Choice validation
        if config_type == "choice" or config_name in self.VALIDATORS.get("choice", {}):
            choices = self.VALIDATORS["choice"].get(config_name, [])
            if choices and value not in choices:
                return False, f"Value must be one of: {', '.join(choices)}"
        
        return True, ""
    
    def get_modal_component(
        self,
        config_name: str,
        current_value: Any,
        config_type: str
    ) -> ui.TextInput:
        """
        Generate appropriate Modal TextInput for config.
        
        Args:
            config_name: Config name
            current_value: Current value
            config_type: Config type
        
        Returns:
            discord.ui.TextInput component
        """
        label = self.get_label(config_name)
        description = self.get_description(config_name)
        
        # Determine placeholder based on type
        placeholder = description
        
        if config_type == "bool":
            placeholder = "true or false"
            current_value = str(current_value).lower()
        elif config_type == "int":
            validators = self.VALIDATORS.get("int", {})
            if config_name in validators:
                rules = validators[config_name]
                min_val = rules.get("min", "")
                max_val = rules.get("max", "")
                if max_val:
                    placeholder = f"Integer ({min_val} - {max_val})"
                else:
                    placeholder = f"Integer (min: {min_val})"
        elif config_type == "float":
            validators = self.VALIDATORS.get("float", {})
            if config_name in validators:
                rules = validators[config_name]
                min_val = rules.get("min", "")
                max_val = rules.get("max", "")
                placeholder = f"Decimal ({min_val} - {max_val})"
        elif config_type == "list":
            placeholder = "Comma-separated values"
            if isinstance(current_value, list):
                current_value = ", ".join(str(v) for v in current_value)
        elif config_type == "choice":
            choices = self.VALIDATORS["choice"].get(config_name, [])
            if choices:
                placeholder = f"Options: {', '.join(choices)}"
        
        # Determine style based on content length
        if isinstance(current_value, str) and len(current_value) > 100:
            style = discord.TextStyle.paragraph
            max_length = 4000
        else:
            style = discord.TextStyle.short
            max_length = 100 if config_type in ["bool", "int", "float"] else 1000
        
        return ui.TextInput(
            label=label[:45],  # Discord limit
            placeholder=placeholder[:100] if placeholder else None,  # Discord limit
            default=str(current_value) if current_value is not None else "",
            required=True,
            style=style,
            max_length=max_length
        )
    
    def format_value_for_display(self, value: Any) -> str:
        """
        Format value for display in embeds.
        
        Args:
            value: Value to format
        
        Returns:
            Formatted string
        """
        if isinstance(value, bool):
            return "✅" if value else "❌"
        elif isinstance(value, (list, dict)):
            if isinstance(value, list):
                return f"List ({len(value)} items)"
            else:
                return f"Dict ({len(value)} items)"
        elif isinstance(value, str) and len(value) > 50:
            return value[:47] + "..."
        elif value is None:
            return "Not set"
        else:
            return str(value)
    
    def parse_value_from_input(
        self,
        input_value: str,
        config_type: str
    ) -> Any:
        """
        Parse value from user input string.
        
        Args:
            input_value: User input string
            config_type: Expected type
        
        Returns:
            Parsed value
        
        Raises:
            ValueError: If parsing fails
        """
        if config_type == "bool":
            return input_value.lower() in ["true", "1", "yes"]
        elif config_type == "int":
            return int(input_value)
        elif config_type == "float":
            return float(input_value)
        elif config_type == "list":
            # Parse comma-separated
            return [item.strip() for item in input_value.split(",") if item.strip()]
        elif config_type == "dict":
            # For simple dicts, might need JSON parsing
            import json
            try:
                return json.loads(input_value)
            except json.JSONDecodeError:
                raise ValueError("Invalid dict. Use valid JSON format.")
        else:
            return input_value


# Global instance
_config_metadata: Optional[ConfigMetadata] = None


def get_config_metadata() -> ConfigMetadata:
    """Get the global config metadata instance."""
    global _config_metadata
    if _config_metadata is None:
        _config_metadata = ConfigMetadata()
    return _config_metadata
