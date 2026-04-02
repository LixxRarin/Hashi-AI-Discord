"""
Config Parser - Simplified Type Detection

Simplified parser that only detects types and defaults from YAML.
Categories are now defined in config_metadata.py.
"""

from typing import Any, Dict, Optional
from ruamel.yaml import YAML

import utils.func as func


class ConfigParser:
    """
    Simplified parser for config type detection.
    
    Only extracts:
    - Config types (bool, int, float, str, dict, list)
    - Default values
    
    Categories are defined separately in config_metadata.py.
    """
    
    def __init__(self):
        self.yaml = YAML(typ='rt')
        self.yaml.preserve_quotes = True
        self._cache = None
        self._cache_version = None
    
    def parse_yaml_structure(self, yaml_content: str) -> Dict[str, Any]:
        """
        Parse YAML and extract types and defaults.
        
        Args:
            yaml_content: Raw YAML string
        
        Returns:
            {
                "config_types": {
                    "delay_for_generation": "float",
                    "advanced_expressions.reply.enabled": "bool",
                    ...
                },
                "defaults": {
                    "delay_for_generation": 4.0,
                    "advanced_expressions": {...},
                    ...
                }
            }
        """
        # Check cache
        parsed_yaml = self.yaml.load(yaml_content)
        version = parsed_yaml.get("version")
        
        if self._cache and self._cache_version == version:
            return self._cache
        
        # Parse structure
        config_types = {}
        defaults = {}
        
        # Remove version key
        config_data = {k: v for k, v in parsed_yaml.items() if k != "version"}
        
        # Recursively extract types and defaults
        self._extract_types_recursive(config_data, config_types, defaults, path=[])
        
        result = {
            "config_types": config_types,
            "defaults": defaults
        }
        
        # Cache result
        self._cache = result
        self._cache_version = version
        
        return result
    
    def _extract_types_recursive(
        self,
        data: Dict[str, Any],
        config_types: Dict[str, str],
        defaults: Dict[str, Any],
        path: list
    ):
        """
        Recursively extract types and defaults.
        
        Args:
            data: Current dict level
            config_types: Types dict to populate
            defaults: Defaults dict to populate
            path: Current path in nested structure
        """
        for key, value in data.items():
            full_path = ".".join(path + [key])
            
            # Infer type
            value_type = self._infer_type(value)
            config_types[full_path] = value_type
            
            # Store default (top-level only for non-nested)
            if not path:
                defaults[key] = value
            
            # Recurse into dicts
            if isinstance(value, dict):
                self._extract_types_recursive(
                    value,
                    config_types,
                    defaults,
                    path + [key]
                )
    
    def _infer_type(self, value: Any) -> str:
        """
        Infer config type from value.
        
        Args:
            value: Config value
        
        Returns:
            Type string: "bool", "int", "float", "str", "list", "dict"
        """
        if isinstance(value, bool):
            return "bool"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "str"
        elif isinstance(value, list):
            return "list"
        elif isinstance(value, dict):
            return "dict"
        else:
            return "str"  # Default fallback
    
    def get_nested_value(self, config: dict, path: str) -> Any:
        """
        Get value from nested config using dot notation.
        
        Args:
            config: Config dict
            path: Dot-separated path (e.g., "advanced_expressions.reply.enabled")
        
        Returns:
            Value at path or None
        """
        keys = path.split('.')
        value = config
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return None
            else:
                return None
        
        return value
    
    def set_nested_value(self, config: dict, path: str, value: Any):
        """
        Set value in nested config using dot notation.
        
        Args:
            config: Config dict to modify
            path: Dot-separated path
            value: Value to set
        """
        keys = path.split('.')
        current = config
        
        # Navigate to parent
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set final value
        current[keys[-1]] = value


# Global instance
_config_parser: Optional[ConfigParser] = None


def get_config_parser() -> ConfigParser:
    """Get the global config parser instance."""
    global _config_parser
    if _config_parser is None:
        _config_parser = ConfigParser()
    return _config_parser
