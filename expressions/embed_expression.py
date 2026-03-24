"""
Embed Expression - Discord Rich Embed Creation System

This module provides the Embed expression, which allows the LLM to create
rich Discord embeds using raw JSON for full control.

Syntax: <EMBED>{"title": "...", "description": "...", ...}</EMBED>

The LLM has complete control over embed structure via JSON.

Example:
    <EMBED>
    {
      "title": "Welcome!",
      "description": "Thanks for joining",
      "color": 3066993
    }
    </EMBED>
    
    <EMBED>
    {
      "title": "Server Stats",
      "color": 3447003,
      "fields": [
        {"name": "Members", "value": "150", "inline": true},
        {"name": "Online", "value": "45", "inline": true}
      ]
    }
    </EMBED>
"""

import re
import json
from typing import Dict, Any, List, Tuple, Optional
import logging

from .base import BaseExpression, ExpressionResult

log = logging.getLogger(__name__)


class EmbedExpression(BaseExpression):
    """
    Embed System - Allows AI to create rich Discord embeds with JSON.
    
    This expression enables the LLM to create embeds with full control
    over structure, colors, fields, and formatting.
    """
    
    # Regex pattern to capture <EMBED>json</EMBED>
    # DOTALL flag makes . match newlines
    EMBED_PATTERN = r'<EMBED>(.*?)</EMBED>'
    
    # Discord embed limits
    MAX_TITLE_LENGTH = 256
    MAX_DESCRIPTION_LENGTH = 4096
    MAX_FIELDS = 25
    MAX_FIELD_NAME_LENGTH = 256
    MAX_FIELD_VALUE_LENGTH = 1024
    MAX_FOOTER_LENGTH = 2048
    MAX_AUTHOR_NAME_LENGTH = 256
    MAX_EMBEDS_PER_MESSAGE = 10
    MAX_TOTAL_CHARACTERS = 6000
    
    @property
    def name(self) -> str:
        return "embed"
    
    @property
    def display_name(self) -> str:
        return "Embed System"
    
    @property
    def description(self) -> str:
        return "Allows AI to create rich Discord embeds using JSON"
    
    @property
    def syntax_pattern(self) -> str:
        return self.EMBED_PATTERN
    
    @property
    def icon(self) -> str:
        return "💎"
    
    def has_syntax(self, text: str) -> bool:
        """Check if text contains embed syntax."""
        if not text:
            return False
        return bool(re.search(self.EMBED_PATTERN, text, re.DOTALL))
    
    def parse(self, text: str, config: Dict[str, Any]) -> ExpressionResult:
        """
        Parse embed syntax and extract embed data.
        
        Args:
            text: Text containing embed syntax
            config: AI configuration
            
        Returns:
            ExpressionResult with metadata about embeds
        """
        embeds = self.extract_embeds(text)
        
        return ExpressionResult(
            metadata={
                "expression": "embed",
                "embeds": embeds,
                "embed_count": len(embeds)
            }
        )
    
    def remove_syntax(self, text: str) -> str:
        """
        Remove embed tags from text.
        
        Args:
            text: Text containing embed syntax
            
        Returns:
            Text with embed tags removed
        """
        if not text:
            return text
        
        return re.sub(self.EMBED_PATTERN, '', text, flags=re.DOTALL).strip()
    
    def get_default_prompt(self) -> str:
        """Get the default prompt for the embed system."""
        return """Embed Syntax: <EMBED>{json}</EMBED>

Create rich Discord embeds with full JSON control.

STRUCTURE:
{
  "title": "Title text",
  "description": "Main content",
  "color": 3447003,  // Decimal color code
  "fields": [
    {"name": "Field", "value": "Value", "inline": true}
  ],
  "footer": {"text": "Footer text"},
  "thumbnail": {"url": "image_url"}
}

COMMON COLORS (decimal):
- Blue: 3447003
- Green: 3066993
- Red: 15158332
- Yellow: 16776960
- Purple: 10181046

EXAMPLES:
Simple:
<EMBED>
{"title": "Welcome!", "description": "Thanks for joining", "color": 3066993}
</EMBED>

With fields:
<EMBED>
{
  "title": "Server Stats",
  "color": 3447003,
  "fields": [
    {"name": "Members", "value": "150", "inline": true},
    {"name": "Online", "value": "45", "inline": true}
  ]
}
</EMBED>"""
    
    def extract_embeds(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract all embeds from text with validation.
        
        Args:
            text: Text containing embed syntax
            
        Returns:
            List of dicts with embed information:
            [
                {
                    "json_data": {...},
                    "valid": True,
                    "error": None,
                    "position": 0
                }
            ]
        """
        if not text:
            return []
        
        embeds = []
        
        for i, match in enumerate(re.finditer(self.EMBED_PATTERN, text, re.DOTALL)):
            try:
                # Extract JSON content
                json_str = match.group(1).strip()
                
                # Parse JSON
                try:
                    json_data = json.loads(json_str)
                except json.JSONDecodeError as e:
                    log.warning(f"Invalid JSON in embed: {e}")
                    embeds.append({
                        "valid": False,
                        "error": f"Invalid JSON: {str(e)}",
                        "position": i,
                        "raw_match": match.group(0)
                    })
                    continue
                
                # Validate embed structure
                is_valid, error = self.validate_embed_data(json_data)
                
                embed_info = {
                    "json_data": json_data,
                    "valid": is_valid,
                    "error": error,
                    "position": i,
                    "raw_match": match.group(0)
                }
                
                embeds.append(embed_info)
                
                if is_valid:
                    title = json_data.get('title', 'Untitled')
                    log.info(f"Parsed valid embed: '{title}'")
                else:
                    log.warning(f"Invalid embed: {error}")
                
            except Exception as e:
                log.error(f"Error parsing embed: {e}", exc_info=True)
                embeds.append({
                    "valid": False,
                    "error": f"Parse error: {str(e)}",
                    "position": i,
                    "raw_match": match.group(0)
                })
        
        return embeds
    
    def validate_embed_data(self, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate embed data against Discord limits.
        
        Args:
            data: Embed JSON data
            
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        if not isinstance(data, dict):
            return False, "Embed data must be a JSON object"
        
        # Calculate total character count
        total_chars = 0
        
        # Validate title
        if 'title' in data:
            title = str(data['title'])
            if len(title) > self.MAX_TITLE_LENGTH:
                return False, f"Title too long ({len(title)} chars, max {self.MAX_TITLE_LENGTH})"
            total_chars += len(title)
        
        # Validate description
        if 'description' in data:
            description = str(data['description'])
            if len(description) > self.MAX_DESCRIPTION_LENGTH:
                return False, f"Description too long ({len(description)} chars, max {self.MAX_DESCRIPTION_LENGTH})"
            total_chars += len(description)
        
        # Validate color
        if 'color' in data:
            color = data['color']
            if not isinstance(color, int):
                return False, "Color must be an integer (decimal color code)"
            if color < 0 or color > 16777215:  # 0xFFFFFF
                return False, f"Color out of range (0-16777215): {color}"
        
        # Validate fields
        if 'fields' in data:
            fields = data['fields']
            if not isinstance(fields, list):
                return False, "Fields must be an array"
            
            if len(fields) > self.MAX_FIELDS:
                return False, f"Too many fields ({len(fields)}, max {self.MAX_FIELDS})"
            
            for i, field in enumerate(fields):
                if not isinstance(field, dict):
                    return False, f"Field {i+1} must be an object"
                
                if 'name' not in field or 'value' not in field:
                    return False, f"Field {i+1} missing 'name' or 'value'"
                
                name = str(field['name'])
                value = str(field['value'])
                
                if len(name) > self.MAX_FIELD_NAME_LENGTH:
                    return False, f"Field {i+1} name too long ({len(name)} chars, max {self.MAX_FIELD_NAME_LENGTH})"
                
                if len(value) > self.MAX_FIELD_VALUE_LENGTH:
                    return False, f"Field {i+1} value too long ({len(value)} chars, max {self.MAX_FIELD_VALUE_LENGTH})"
                
                total_chars += len(name) + len(value)
        
        # Validate footer
        if 'footer' in data:
            footer = data['footer']
            if not isinstance(footer, dict):
                return False, "Footer must be an object"
            
            if 'text' in footer:
                footer_text = str(footer['text'])
                if len(footer_text) > self.MAX_FOOTER_LENGTH:
                    return False, f"Footer text too long ({len(footer_text)} chars, max {self.MAX_FOOTER_LENGTH})"
                total_chars += len(footer_text)
        
        # Validate author
        if 'author' in data:
            author = data['author']
            if not isinstance(author, dict):
                return False, "Author must be an object"
            
            if 'name' in author:
                author_name = str(author['name'])
                if len(author_name) > self.MAX_AUTHOR_NAME_LENGTH:
                    return False, f"Author name too long ({len(author_name)} chars, max {self.MAX_AUTHOR_NAME_LENGTH})"
                total_chars += len(author_name)
        
        # Check total character limit
        if total_chars > self.MAX_TOTAL_CHARACTERS:
            return False, f"Total embed characters exceed limit ({total_chars}, max {self.MAX_TOTAL_CHARACTERS})"
        
        # Validate URLs if present
        url_fields = ['url', 'thumbnail', 'image', 'footer', 'author']
        for field_name in url_fields:
            if field_name in data:
                field_data = data[field_name]
                if isinstance(field_data, dict) and 'url' in field_data:
                    url = field_data['url']
                    if not isinstance(url, str):
                        return False, f"{field_name}.url must be a string"
                    if not url.startswith(('http://', 'https://')):
                        return False, f"{field_name}.url must start with http:// or https://"
        
        return True, None
    
    def validate_syntax(self, text: str) -> Tuple[bool, str]:
        """
        Validate embed syntax in text.
        
        Args:
            text: Text to validate
            
        Returns:
            Tuple of (is_valid: bool, reason: str)
        """
        if not text:
            return False, "Empty text"
        
        if not self.has_syntax(text):
            return True, "No embed syntax (valid)"
        
        embeds = self.extract_embeds(text)
        
        if not embeds:
            return False, "Failed to parse embeds"
        
        # Check if all embeds are valid
        invalid_embeds = [e for e in embeds if not e.get('valid', False)]
        
        if invalid_embeds:
            errors = [e.get('error', 'Unknown error') for e in invalid_embeds]
            return False, f"Invalid embed(s): {'; '.join(errors)}"
        
        # Check total embed count
        if len(embeds) > self.MAX_EMBEDS_PER_MESSAGE:
            return False, f"Too many embeds ({len(embeds)}, max {self.MAX_EMBEDS_PER_MESSAGE} per message)"
        
        return True, f"Valid embed syntax ({len(embeds)} embed(s))"
