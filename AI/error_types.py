"""
LLM Error Types - Structured Error Handling

Provides structured error representation for LLM API errors,
allowing flexible error handling based on configuration.
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class LLMError:
    """
    Represents an LLM error in a structured format.
    
    Attributes:
        error_type: Type of error (e.g., "APIConnectionError", "RateLimitError")
        error_message: Detailed error message
        friendly_message: User-friendly error message
    """
    error_type: str
    error_message: str
    friendly_message: str
    
    def to_detailed_string(self) -> str:
        """
        Returns detailed error string in format: 'ErrorType: message'
        
        Returns:
            Formatted error string with type and message
        """
        return f"{self.error_type}: {self.error_message}"
    
    def to_friendly_string(self) -> str:
        """
        Returns user-friendly error message.
        
        Returns:
            Friendly error message
        """
        return self.friendly_message
    
    @staticmethod
    def is_error_response(response: str) -> bool:
        """
        Checks if a response string is an error response.
        
        Args:
            response: Response string to check
            
        Returns:
            True if response is an error, False otherwise
        """
        return isinstance(response, str) and response.startswith("__LLM_ERROR__:")
    
    @staticmethod
    def from_string(error_str: str) -> Optional['LLMError']:
        """
        Converts error string back to LLMError object.
        
        Args:
            error_str: Error string in format "__LLM_ERROR__:type|message|friendly"
            
        Returns:
            LLMError object or None if parsing fails
        """
        if not error_str.startswith("__LLM_ERROR__:"):
            return None
        
        # Parse: __LLM_ERROR__:ErrorType|error_message|friendly_message
        try:
            parts = error_str[14:].split("|", 2)
            if len(parts) == 3:
                return LLMError(parts[0], parts[1], parts[2])
        except Exception:
            pass
        
        return None
    
    def to_string(self) -> str:
        """
        Converts LLMError to string for transport between components.
        
        Returns:
            String representation in format "__LLM_ERROR__:type|message|friendly"
        """
        # Escape pipe characters in messages to avoid parsing issues
        error_type = self.error_type.replace("|", "\\|")
        error_message = self.error_message.replace("|", "\\|")
        friendly_message = self.friendly_message.replace("|", "\\|")
        
        return f"__LLM_ERROR__:{error_type}|{error_message}|{friendly_message}"
