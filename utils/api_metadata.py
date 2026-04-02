"""
API Connection Metadata - Categories, Validation, and UI Helpers

Dynamic metadata system for API connections.
Similar to config_metadata.py, facilitates maintenance and extension.

To add a new parameter:
1. Add to appropriate category in API_PARAMETER_CATEGORIES
2. Add validation in VALIDATORS (if needed)
3. Add label/description in LABELS/DESCRIPTIONS (optional)
4. Done! System automatically detects type and generates UI
"""

import discord
from discord import ui
from typing import Any, Dict, Optional, Tuple, List
import re

import utils.func as func


# Parameter categories (easy to extend)
API_PARAMETER_CATEGORIES: Dict[str, List[str]] = {
    "Credentials": [
        "provider",
        "api_key",
        "base_url",
        "model"
    ],
    "Generation": [
        "max_tokens",
        "temperature",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
        "context_size"
    ],
    "Thinking": [
        "think_switch",
        "think_depth",
        "hide_thinking_tags",
        "thinking_tag_patterns",
        "save_thinking_in_history"
    ],
    "Tools": [
        "max_tool_rounds"
    ],
    "Vision": [
        "vision_enabled",
        "vision_detail",
        "max_image_size"
    ],
    "Advanced": [
        "custom_extra_body"
    ]
}


# Category emojis
CATEGORY_EMOJIS: Dict[str, str] = {
    "Credentials": "🔑",
    "Generation": "⚙️",
    "Thinking": "🧠",
    "Tools": "🔧",
    "Vision": "🖼️",
    "Advanced": "🔬"
}


def get_all_categories() -> List[str]:
    """Get list of all category names."""
    return list(API_PARAMETER_CATEGORIES.keys())


def get_category_params(category: str) -> List[str]:
    """Get list of parameter keys for a category."""
    return API_PARAMETER_CATEGORIES.get(category, [])


def get_category_emoji(category: str) -> str:
    """Get emoji for a category."""
    return CATEGORY_EMOJIS.get(category, "⚙️")


def find_param_category(param: str) -> str:
    """Find which category a parameter belongs to."""
    for category, params in API_PARAMETER_CATEGORIES.items():
        if param in params:
            return category
    return "Uncategorized"


class APIMetadata:
    """
    Metadata system for API connections.
    
    Provides:
    - Validation rules (min/max, choices, regex)
    - User-friendly labels
    - UI component generation
    """
    
    # Validation rules by type
    VALIDATORS = {
        "float": {
            "temperature": {"min": 0.0, "max": 2.0},
            "top_p": {"min": 0.0, "max": 1.0},
            "frequency_penalty": {"min": -2.0, "max": 2.0},
            "presence_penalty": {"min": -2.0, "max": 2.0},
        },
        "int": {
            "max_tokens": {"min": 1},
            "context_size": {"min": 1},
            "think_depth": {"min": 1, "max": 5},
            "max_tool_rounds": {"min": 1, "max": 50},
            "max_image_size": {"min": 1, "max": 100},
        },
        "choice": {
            # String choices
            "vision_detail": ["low", "high", "auto"],
            
            # Boolean choices
            "think_switch": [True, False],
            "hide_thinking_tags": [True, False],
            "save_thinking_in_history": [True, False],
            "vision_enabled": [True, False],
        },
        "str": {
            "connection_name": {"max_length": 50, "required": True},
            "api_key": {"required": True, "sensitive": True},
            "model": {"required": True},
            "provider": {"required": True},
        }
    }
    
    # User-friendly labels (auto-generated from name if not specified)
    LABELS = {
        "connection_name": "Connection Name",
        "provider": "Provider",
        "api_key": "API Key",
        "base_url": "Base URL",
        "model": "Model",
        "max_tokens": "Max Tokens",
        "temperature": "Temperature",
        "top_p": "Top P",
        "frequency_penalty": "Frequency Penalty",
        "presence_penalty": "Presence Penalty",
        "context_size": "Context Size",
        "think_switch": "Enable Thinking",
        "think_depth": "Thinking Depth",
        "hide_thinking_tags": "Hide Thinking Tags",
        "thinking_tag_patterns": "Thinking Tag Patterns",
        "save_thinking_in_history": "Save Thinking in History",
        "max_tool_rounds": "Max Tool Rounds",
        "vision_enabled": "Enable Vision",
        "vision_detail": "Vision Detail Level",
        "max_image_size": "Max Image Size (MB)",
        "custom_extra_body": "Custom Extra Body (JSON)",
    }
    
    # Descriptions (tooltips/help text)
    DESCRIPTIONS = {
        "connection_name": "Unique name for this API connection",
        "provider": "API provider (OpenAI, DeepSeek, Claude, Ollama)",
        "api_key": "API key for authentication",
        "base_url": "Custom API endpoint (optional)",
        "model": "Model name (e.g., gpt-4, deepseek-chat)",
        "max_tokens": "Maximum tokens in response",
        "temperature": "Randomness (0.0 = deterministic, 2.0 = very random)",
        "top_p": "Nucleus sampling threshold",
        "frequency_penalty": "Reduce repetition of token sequences",
        "presence_penalty": "Reduce repetition of topics",
        "context_size": "Maximum context window in tokens",
        "think_switch": "Enable extended thinking/reasoning",
        "think_depth": "Depth of thinking process (1-5)",
        "hide_thinking_tags": "Remove thinking tags from responses",
        "thinking_tag_patterns": "Regex patterns to detect thinking tags",
        "save_thinking_in_history": "Include thinking in conversation history",
        "max_tool_rounds": "Maximum tool calling iterations",
        "vision_enabled": "Enable image analysis capabilities",
        "vision_detail": "Image analysis detail level",
        "max_image_size": "Maximum image size in megabytes",
        "custom_extra_body": "Additional provider-specific parameters (JSON)",
    }
    
    def is_choice_param(self, param: str) -> bool:
        """
        Check if parameter has predefined choices.
        
        Args:
            param: Parameter key to check
        
        Returns:
            True if parameter has predefined choices
        """
        return param in self.VALIDATORS.get("choice", {})
    
    def get_choices(self, param: str) -> List[Any]:
        """
        Get available choices for a choice parameter.
        
        Args:
            param: Parameter key
        
        Returns:
            List of available choices, or empty list if not a choice param
        """
        return self.VALIDATORS.get("choice", {}).get(param, [])
    
    def get_label(self, param: str) -> str:
        """
        Get user-friendly label for parameter.
        
        Args:
            param: Parameter name
        
        Returns:
            User-friendly label
        """
        # Check if we have a custom label
        if param in self.LABELS:
            return self.LABELS[param]
        
        # Auto-generate from name
        # Convert snake_case to Title Case
        return param.replace('_', ' ').title()
    
    def get_description(self, param: str) -> str:
        """
        Get description for parameter.
        
        Args:
            param: Parameter name
        
        Returns:
            Description or empty string
        """
        return self.DESCRIPTIONS.get(param, "")
    
    def validate_value(
        self,
        param: str,
        value: Any,
        param_type: str
    ) -> Tuple[bool, str]:
        """
        Validate parameter value.
        
        Args:
            param: Parameter name
            value: Value to validate
            param_type: Expected type
        
        Returns:
            (is_valid, error_message)
        """
        # Type conversion
        try:
            if param_type == "bool":
                if isinstance(value, str):
                    value = value.lower() in ["true", "1", "yes"]
                else:
                    value = bool(value)
            elif param_type == "int":
                value = int(value)
            elif param_type == "float":
                value = float(value)
            elif param_type == "str":
                value = str(value)
            elif param_type == "list":
                if isinstance(value, str):
                    # Parse comma-separated
                    value = [item.strip() for item in value.split(",") if item.strip()]
        except (ValueError, TypeError) as e:
            return False, f"Invalid value for type {param_type}: {e}"
        
        # String length validation
        if param_type == "str":
            validators = self.VALIDATORS.get("str", {})
            if param in validators:
                rules = validators[param]
                max_length = rules.get("max_length")
                required = rules.get("required", False)
                
                if required and not value:
                    return False, "This field is required"
                if max_length and len(value) > max_length:
                    return False, f"Value must be {max_length} characters or less"
        
        # Range validation for numbers
        if param_type in ["int", "float"]:
            validators = self.VALIDATORS.get(param_type, {})
            if param in validators:
                rules = validators[param]
                min_val = rules.get("min")
                max_val = rules.get("max")
                
                if min_val is not None and value < min_val:
                    return False, f"Value must be >= {min_val}"
                if max_val is not None and value > max_val:
                    return False, f"Value must be <= {max_val}"
        
        # Choice validation
        if param_type == "choice" or param in self.VALIDATORS.get("choice", {}):
            choices = self.VALIDATORS["choice"].get(param, [])
            if choices and value not in choices:
                return False, f"Value must be one of: {', '.join(str(c) for c in choices)}"
        
        return True, ""
    
    def get_modal_component(
        self,
        param: str,
        current_value: Any,
        param_type: str
    ) -> ui.TextInput:
        """
        Generate appropriate Modal TextInput for parameter.
        
        Args:
            param: Parameter name
            current_value: Current value
            param_type: Parameter type
        
        Returns:
            discord.ui.TextInput component
        """
        label = self.get_label(param)
        description = self.get_description(param)
        
        # Determine placeholder based on type
        placeholder = description
        
        if param_type == "bool":
            placeholder = "true or false"
            current_value = str(current_value).lower() if current_value is not None else "false"
        elif param_type == "int":
            validators = self.VALIDATORS.get("int", {})
            if param in validators:
                rules = validators[param]
                min_val = rules.get("min", "")
                max_val = rules.get("max", "")
                if max_val:
                    placeholder = f"Integer ({min_val} - {max_val})"
                else:
                    placeholder = f"Integer (min: {min_val})"
        elif param_type == "float":
            validators = self.VALIDATORS.get("float", {})
            if param in validators:
                rules = validators[param]
                min_val = rules.get("min", "")
                max_val = rules.get("max", "")
                placeholder = f"Decimal ({min_val} - {max_val})"
        elif param_type == "list":
            placeholder = "Comma-separated values"
            if isinstance(current_value, list):
                current_value = ", ".join(str(v) for v in current_value)
        elif param_type == "choice":
            choices = self.VALIDATORS["choice"].get(param, [])
            if choices:
                placeholder = f"Options: {', '.join(str(c) for c in choices)}"
        
        # Determine style based on content length
        if isinstance(current_value, str) and len(current_value) > 100:
            style = discord.TextStyle.paragraph
            max_length = 4000
        else:
            style = discord.TextStyle.short
            max_length = 100 if param_type in ["bool", "int", "float"] else 1000
        
        # Special handling for sensitive fields
        validators = self.VALIDATORS.get("str", {})
        if param in validators and validators[param].get("sensitive"):
            style = discord.TextStyle.short
        
        return ui.TextInput(
            label=label[:45],  # Discord limit
            placeholder=placeholder[:100] if placeholder else None,  # Discord limit
            default=str(current_value) if current_value is not None else "",
            required=validators.get(param, {}).get("required", False) if param in validators else False,
            style=style,
            max_length=max_length
        )
    
    def format_value_for_display(self, value: Any, param: str = None) -> str:
        """
        Format value for display in embeds.
        
        Args:
            value: Value to format
            param: Parameter name (for special formatting)
        
        Returns:
            Formatted string
        """
        # Special handling for sensitive data
        if param == "api_key":
            return self._mask_api_key(value)
        
        if isinstance(value, bool):
            return "✅ Enabled" if value else "❌ Disabled"
        elif isinstance(value, list):
            if not value:
                return "None"
            return f"{len(value)} item(s)"
        elif isinstance(value, dict):
            if not value:
                return "None"
            return f"{len(value)} key(s)"
        elif isinstance(value, str) and len(value) > 50:
            return value[:47] + "..."
        elif value is None:
            return "None"
        else:
            return str(value)
    
    def _mask_api_key(self, api_key: str) -> str:
        """Mask API key for display, showing only first and last 4 characters."""
        if not api_key:
            return "Not set"
        if len(api_key) <= 8:
            return "*" * len(api_key)
        return f"{api_key[:4]}...{api_key[-4:]}"
    
    def parse_value_from_input(
        self,
        input_value: str,
        param_type: str
    ) -> Any:
        """
        Parse value from user input string.
        
        Args:
            input_value: User input string
            param_type: Expected type
        
        Returns:
            Parsed value
        
        Raises:
            ValueError: If parsing fails
        """
        if param_type == "bool":
            return input_value.lower() in ["true", "1", "yes"]
        elif param_type == "int":
            return int(input_value)
        elif param_type == "float":
            return float(input_value)
        elif param_type == "list":
            # Parse comma-separated
            return [item.strip() for item in input_value.split(",") if item.strip()]
        elif param_type == "dict":
            # For simple dicts, might need JSON parsing
            import json
            try:
                return json.loads(input_value)
            except json.JSONDecodeError:
                raise ValueError("Invalid dict. Use valid JSON format.")
        else:
            return input_value
    
    def get_param_type(self, param: str, value: Any = None) -> str:
        """
        Determine parameter type.
        
        Args:
            param: Parameter name
            value: Current value (optional, for type inference)
        
        Returns:
            Type string: "str", "int", "float", "bool", "list", "dict", "choice"
        """
        # Check if it's a choice parameter
        if param in self.VALIDATORS.get("choice", {}):
            return "choice"
        
        # Check explicit type validators
        for type_name in ["str", "int", "float"]:
            if param in self.VALIDATORS.get(type_name, {}):
                return type_name
        
        # Infer from value if provided
        if value is not None:
            if isinstance(value, bool):
                return "bool"
            elif isinstance(value, int):
                return "int"
            elif isinstance(value, float):
                return "float"
            elif isinstance(value, list):
                return "list"
            elif isinstance(value, dict):
                return "dict"
        
        # Default to string
        return "str"


# Global instance
_api_metadata: Optional[APIMetadata] = None


def get_api_metadata() -> APIMetadata:
    """Get the global API metadata instance."""
    global _api_metadata
    if _api_metadata is None:
        _api_metadata = APIMetadata()
    return _api_metadata
