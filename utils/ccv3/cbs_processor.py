"""
Curly Braced Syntaxes (CBS) Processor

Processes macros/syntaxes like {{char}}, {{user}}, {{random:}}, etc.
according to the Character Card V3 specification.
"""

import logging
import random
import re
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


class CBSProcessor:
    """
    Processes Curly Braced Syntaxes in character card text.
    """
    
    def __init__(self):
        """Initialize the CBS processor."""
        self.pick_cache = {}  # Cache for {{pick:}} to ensure consistency
        self.extracted_hidden_keys = []  # Extracted hidden keys for lorebook scanning
    
    def process(
        self,
        text: str,
        char_name: str,
        user_name: str,
        session: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Process all CBS in the text.
        
        Args:
            text: Text to process
            char_name: Character name
            user_name: User name
            session: Optional session data for context
            
        Returns:
            Processed text with CBS replaced
        """
        if not text:
            return text
        
        try:
            # Process in order (some CBS may contain others)
            
            # 1. Comments (remove completely)
            text = self._process_comments(text)
            
            # 2. Hidden keys (remove but keep for lorebook scanning)
            text = self._process_hidden_keys(text)
            
            # Store extracted hidden keys in session for lorebook scanning
            if self.extracted_hidden_keys and session is not None:
                if '_hidden_keys' not in session:
                    session['_hidden_keys'] = []
                session['_hidden_keys'].extend(self.extracted_hidden_keys)
                log.debug(f"Extracted {len(self.extracted_hidden_keys)} hidden keys for lorebook scanning")
            
            # 3. Character and user names
            text = self._process_char_syntax(text, char_name)
            text = self._process_user_syntax(text, user_name)
            
            # 4. Random selections
            text = self._process_random(text)
            text = self._process_pick(text)
            
            # 5. Dice rolls
            text = self._process_roll(text)
            
            # 6. Text transformations
            text = self._process_reverse(text)
            
            return text
            
        except Exception as e:
            log.error(f"Error processing CBS: {e}")
            return text
    
    def _process_char_syntax(self, text: str, char_name: str) -> str:
        """
        Replace {{char}}, <char>, and <bot> with character name.
        
        Args:
            text: Text to process
            char_name: Character name
            
        Returns:
            Processed text
        """
        # {{char}} - case insensitive
        text = re.sub(r'\{\{char\}\}', char_name, text, flags=re.IGNORECASE)
        
        # <char> and <bot> - case insensitive
        text = re.sub(r'<char>', char_name, text, flags=re.IGNORECASE)
        text = re.sub(r'<bot>', char_name, text, flags=re.IGNORECASE)
        
        return text
    
    def _process_user_syntax(self, text: str, user_name: str) -> str:
        """
        Replace {{user}} with user name.
        
        Args:
            text: Text to process
            user_name: User name
            
        Returns:
            Processed text
        """
        # {{user}} - case insensitive
        text = re.sub(r'\{\{user\}\}', user_name, text, flags=re.IGNORECASE)
        
        return text
    
    def _process_random(self, text: str) -> str:
        """
        Replace {{random:A,B,C}} with random choice.
        
        Args:
            text: Text to process
            
        Returns:
            Processed text
        """
        def random_replace(match):
            options_str = match.group(1)
            # Handle escaped commas
            options = self._split_with_escape(options_str, ',')
            return random.choice(options).strip()
        
        text = re.sub(
            r'\{\{random:([^}]+)\}\}',
            random_replace,
            text,
            flags=re.IGNORECASE
        )
        
        return text
    
    def _process_pick(self, text: str) -> str:
        """
        Replace {{pick:A,B,C}} with deterministic choice (cached).
        
        Args:
            text: Text to process
            
        Returns:
            Processed text
        """
        def pick_replace(match):
            full_match = match.group(0)
            options_str = match.group(1)
            
            # Use cache to ensure same value for same prompt
            if full_match not in self.pick_cache:
                options = self._split_with_escape(options_str, ',')
                self.pick_cache[full_match] = random.choice(options).strip()
            
            return self.pick_cache[full_match]
        
        text = re.sub(
            r'\{\{pick:([^}]+)\}\}',
            pick_replace,
            text,
            flags=re.IGNORECASE
        )
        
        return text
    
    def _process_roll(self, text: str) -> str:
        """
        Replace {{roll:N}} or {{roll:dN}} with random number 1-N.
        
        Args:
            text: Text to process
            
        Returns:
            Processed text
        """
        def roll_replace(match):
            dice_str = match.group(1)
            # Remove 'd' prefix if present
            dice_str = dice_str.lstrip('dD')
            try:
                max_value = int(dice_str)
                return str(random.randint(1, max_value))
            except ValueError:
                log.warning(f"Invalid dice value: {dice_str}")
                return match.group(0)
        
        text = re.sub(
            r'\{\{roll:([dD]?\d+)\}\}',
            roll_replace,
            text,
            flags=re.IGNORECASE
        )
        
        return text
    
    def _process_comments(self, text: str) -> str:
        """
        Remove {{// comment}} completely.
        
        Args:
            text: Text to process
            
        Returns:
            Processed text
        """
        # {{// anything}} - remove completely
        text = re.sub(
            r'\{\{//[^}]*\}\}',
            '',
            text,
            flags=re.IGNORECASE
        )
        
        return text
    
    def _process_hidden_keys(self, text: str) -> str:
        """
        Extract and remove {{hidden_key:X}} for lorebook scanning.
        
        Extracted keys are stored in self.extracted_hidden_keys
        for use in recursive lorebook scanning.
        
        Args:
            text: Text to process
            
        Returns:
            Processed text with hidden keys removed
        """
        # Clear previous extractions
        self.extracted_hidden_keys = []
        
        def extract_and_remove(match):
            """Extract key content and remove from text."""
            key_content = match.group(1)
            self.extracted_hidden_keys.append(key_content)
            return ''  # Remove from text
        
        text = re.sub(
            r'\{\{hidden_key:([^}]+)\}\}',
            extract_and_remove,
            text,
            flags=re.IGNORECASE
        )
        
        return text
    
    def _process_reverse(self, text: str) -> str:
        """
        Replace {{reverse:X}} with reversed text.
        
        Args:
            text: Text to process
            
        Returns:
            Processed text
        """
        def reverse_replace(match):
            content = match.group(1)
            return content[::-1]
        
        text = re.sub(
            r'\{\{reverse:([^}]+)\}\}',
            reverse_replace,
            text,
            flags=re.IGNORECASE
        )
        
        return text
    
    def _split_with_escape(self, text: str, delimiter: str) -> list:
        """
        Split text by delimiter, respecting escaped delimiters.
        
        Args:
            text: Text to split
            delimiter: Delimiter character
            
        Returns:
            List of split parts
        """
        # Replace escaped delimiters with placeholder
        placeholder = '\x00'
        escaped = f'\\{delimiter}'
        text = text.replace(escaped, placeholder)
        
        # Split by delimiter
        parts = text.split(delimiter)
        
        # Restore escaped delimiters
        parts = [p.replace(placeholder, delimiter) for p in parts]
        
        return parts
    
    def clear_pick_cache(self):
        """Clear the pick cache (call between prompts)."""
        self.pick_cache.clear()


# Global processor instance
_processor = CBSProcessor()


def process_cbs(
    text: str,
    char_name: str,
    user_name: str,
    session: Optional[Dict[str, Any]] = None
) -> str:
    """
    Process all CBS in text.
    
    Args:
        text: Text to process
        char_name: Character name
        user_name: User name
        session: Optional session data
        
    Returns:
        Processed text
    """
    return _processor.process(text, char_name, user_name, session)


def replace_char_syntax(text: str, char_name: str) -> str:
    """
    Replace only character name syntaxes.
    
    Args:
        text: Text to process
        char_name: Character name
        
    Returns:
        Processed text
    """
    return _processor._process_char_syntax(text, char_name)


def replace_user_syntax(text: str, user_name: str) -> str:
    """
    Replace only user name syntaxes.
    
    Args:
        text: Text to process
        user_name: User name
        
    Returns:
        Processed text
    """
    return _processor._process_user_syntax(text, user_name)


def clear_pick_cache():
    """Clear the pick cache."""
    _processor.clear_pick_cache()
