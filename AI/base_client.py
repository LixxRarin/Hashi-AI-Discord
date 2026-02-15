"""
Base AI Client

This module provides an abstract base class for AI provider clients.
It defines the interface that all AI providers must implement and provides
common functionality for configuration resolution.

This makes it easy to add new AI providers (Anthropic, Google, Cohere, etc.)
by simply implementing the abstract methods.

Classes:
    - BaseAIClient: Abstract base class for AI clients
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging

import utils.func as func


log = logging.getLogger(__name__)


class BaseAIClient(ABC):
    """
    Abstract base class for AI provider clients.
    
    This class defines the interface that all AI providers must implement
    and provides common functionality for resolving configuration from
    API connections or fallback sources.
    
    To add a new AI provider:
    1. Create a new class that inherits from BaseAIClient
    2. Set the provider_name class attribute
    3. Implement the abstract methods:
       - create_client()
       - generate_response()
       - count_tokens()
    4. Use the provided resolve_* methods for configuration
    
    Example:
        >>> class AnthropicClient(BaseAIClient):
        ...     provider_name = "Anthropic"
        ...     
        ...     def create_client(self, session, server_id):
        ...         api_key = self.resolve_api_key(session, server_id)
        ...         return anthropic.AsyncAnthropic(api_key=api_key)
        ...     
        ...     async def generate_response(self, messages, config):
        ...         # Implementation specific to Anthropic
        ...         pass
    """
    
    # Provider name (must be set by subclass)
    provider_name: str = None
    
    def __init__(self):
        """Initialize the base client."""
        if self.provider_name is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set provider_name class attribute"
            )
    
    @abstractmethod
    def create_client(self, session: Dict[str, Any], server_id: Optional[str] = None):
        """
        Create and return the provider-specific client instance.
        
        Args:
            session: Session data
            server_id: Server ID (required for connection resolution)
            
        Returns:
            Provider-specific client instance
        """
        pass
    
    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        session: Dict[str, Any],
        server_id: str,
        tools: Optional[List[Dict]] = None,
        tool_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Generate a response from the AI provider with optional tool calling support.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            session: Session data
            server_id: Server ID
            tools: Optional list of tool definitions for function calling
            tool_context: Optional context for tool execution
            **kwargs: Additional provider-specific parameters
            
        Returns:
            str: Generated response text
        """
        pass
    
    @abstractmethod
    def count_tokens(self, text: str, model: str) -> int:
        """
        Count the number of tokens in a text string.
        
        Args:
            text: Text to count tokens for
            model: Model name (token counting may be model-specific)
            
        Returns:
            int: Number of tokens
        """
        pass
    
    @abstractmethod
    async def get_bot_info(
        self,
        session: Dict[str, Any],
        server_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get bot/model information.
        
        Args:
            session: Session data
            server_id: Server ID (required for connection resolution)
            
        Returns:
            Optional[Dict[str, Any]]: Dictionary with keys:
                - name: Model/bot name
                - avatar_url: Avatar URL (optional)
                - title: Display title
                - description: Description text
                - visibility: Visibility status
                - num_interactions: Number of interactions (optional)
                - author_username: Author/owner username
        """
        pass
    
    
    def supports_structured_outputs(self) -> bool:
        """
        Check if this client supports Structured Outputs (JSON Schema).
        
        Subclasses should override this if they support structured outputs.
        
        Returns:
            bool: True if structured outputs are supported
        """
        return False
    
    async def generate_response_structured(
        self,
        messages: List[Dict[str, str]],
        json_schema: Dict[str, Any],
        session: Dict[str, Any],
        server_id: str,
        schema_name: str = "response",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a structured response following a JSON Schema.
        
        This method uses Structured Outputs to ensure the model returns
        JSON that strictly follows the provided schema.
        
        Args:
            messages: List of message dictionaries
            json_schema: JSON Schema that the response must follow
            session: Session data
            server_id: Server ID
            schema_name: Name for the schema
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Dict[str, Any]: Parsed JSON response matching the schema
            
        Raises:
            NotImplementedError: If provider doesn't support structured outputs
        """
        if not self.supports_structured_outputs():
            raise NotImplementedError(
                f"{self.provider_name} does not support Structured Outputs. "
                f"Please use a provider that supports this feature (e.g., OpenAI, DeepSeek)."
            )
        
        raise NotImplementedError(
            f"{self.__class__.__name__} claims to support structured outputs "
            f"but has not implemented generate_response_structured()"
        )
    
    def supports_vision(self) -> bool:
        """
        Check if this client supports vision/image analysis.
        
        Subclasses should override this if they support vision capabilities.
        
        Returns:
            bool: True if vision is supported
        """
        return False
    
    def prepare_multimodal_content(
        self,
        text: str,
        images: List[Dict[str, Any]]
    ) -> Any:
        """
        Prepare multimodal content in provider-specific format.
        
        This method formats text and images into the format expected by the provider's API.
        
        Args:
            text: Text content
            images: List of processed image dicts with url, base64, format, detail
            
        Returns:
            Any: Provider-specific content format (could be str, list, dict, etc.)
            
        Raises:
            NotImplementedError: If provider doesn't support multimodal content
        """
        if not self.supports_vision():
            # If no vision support, just return text
            return text
        
        raise NotImplementedError(
            f"{self.__class__.__name__} claims to support vision "
            f"but has not implemented prepare_multimodal_content()"
        )
    
    def _resolve_connection(
        self, 
        session: Dict[str, Any], 
        server_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve API connection from session.
        
        Args:
            session: Session data
            server_id: Server ID
            
        Returns:
            Connection data or None if not using connections
        """
        connection_name = session.get("api_connection")
        if not connection_name:
            return None
        
        connection = func.get_api_connection(server_id, connection_name)
        if not connection:
            log.error(
                f"API connection '{connection_name}' not found for server {server_id}"
            )
            return None
        
        return connection
    
    def resolve_api_key(
        self, 
        session: Dict[str, Any], 
        server_id: Optional[str] = None
    ) -> str:
        """
        Resolve API key from connection or fallback to config.
        
        Priority:
        1. API connection (if configured)
        2. config.yaml fallback
        
        Args:
            session: Session data
            server_id: Server ID (required for connection resolution)
            
        Returns:
            str: API key
        """
        # Try to get from connection first
        if server_id:
            connection_name = session.get("api_connection")
            if connection_name:
                connection = func.get_api_connection(server_id, connection_name)
                if connection:
                    api_key = connection.get("api_key", "")
                    if not api_key:
                        log.error(
                            f"API connection '{connection_name}' exists but has no API key. "
                            f"Please update it with /api_config"
                        )
                    return api_key
                else:
                    log.error(
                        f"API connection '{connection_name}' not found for server {server_id}. "
                        f"Please verify the connection exists with /list_apis"
                    )
                    return ""
            else:
                log.warning(
                    f"Session does not have 'api_connection' field. "
                    f"Please reconfigure this AI with /setup using an API connection."
                )
        
        # Fallback to config.yaml for backward compatibility
        fallback_key = func.config_yaml.get(self.provider_name, {}).get("api_key", "")
        if not fallback_key:
            log.error(
                f"No API key found for {self.provider_name}! Please either:\n"
                f"  1. Create an API connection: /new_api\n"
                f"  2. Configure your AI: /setup with api_connection parameter\n"
                f"  3. Or add api_key to config.yaml (legacy method)"
            )
        return fallback_key
    
    def resolve_base_url(
        self, 
        session: Dict[str, Any], 
        server_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolve custom base URL from connection or fallback.
        
        Priority:
        1. API connection (if configured)
        2. Session (backward compatibility)
        3. config.yaml fallback
        
        Args:
            session: Session data
            server_id: Server ID (required for connection resolution)
            
        Returns:
            Optional[str]: Base URL or None
        """
        # Try to get from connection first
        if server_id:
            connection = self._resolve_connection(session, server_id)
            if connection:
                return connection.get("base_url")
        
        # Fallback to session for backward compatibility
        if session.get("base_url"):
            return session["base_url"]
        
        # Fallback to config.yaml
        return func.config_yaml.get(self.provider_name, {}).get("base_url", None)
    
    def resolve_model(
        self, 
        session: Dict[str, Any], 
        server_id: Optional[str] = None,
        default_model: str = "gpt-3.5-turbo"
    ) -> str:
        """
        Resolve model name from connection or fallback.
        
        Priority:
        1. API connection (if configured)
        2. Session (backward compatibility)
        3. config.yaml fallback
        4. Default model
        
        Args:
            session: Session data
            server_id: Server ID (required for connection resolution)
            default_model: Default model if none found
            
        Returns:
            str: Model name
        """
        # Try to get from connection first
        if server_id:
            connection = self._resolve_connection(session, server_id)
            if connection:
                return connection.get("model", default_model)
        
        # Fallback to session for backward compatibility
        if session.get("model"):
            return session["model"]
        
        # Fallback to config.yaml
        return func.config_yaml.get(self.provider_name, {}).get("model", default_model)
    
    def get_llm_params(
        self, 
        session: Dict[str, Any], 
        server_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get LLM parameters from connection or session.
        
        Priority:
        1. API connection (if configured)
        2. Session config (backward compatibility)
        
        Args:
            session: Session data
            server_id: Server ID (required for connection resolution)
            
        Returns:
            Dict[str, Any]: Dictionary of LLM parameters including thinking configuration
        """
        # Default thinking patterns (fallback for old connections)
        default_patterns = [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
            r'<thought>.*?</thought>',
            r'<reasoning>.*?</reasoning>'
        ]
        
        # Try to get from connection first
        if server_id:
            connection = self._resolve_connection(session, server_id)
            if connection:
                return {
                    "max_tokens": connection.get("max_tokens", 1000),
                    "temperature": connection.get("temperature", 0.7),
                    "top_p": connection.get("top_p", 1.0),
                    "frequency_penalty": connection.get("frequency_penalty", 0.0),
                    "presence_penalty": connection.get("presence_penalty", 0.0),
                    "context_size": connection.get("context_size", 4096),
                    "think_switch": connection.get("think_switch", True),
                    "think_depth": connection.get("think_depth", 3),
                    "hide_thinking_tags": connection.get("hide_thinking_tags", True),
                    "thinking_tag_patterns": connection.get("thinking_tag_patterns", default_patterns),
                    "custom_extra_body": connection.get("custom_extra_body", None),
                    "save_thinking_in_history": connection.get("save_thinking_in_history", True),
                    "vision_enabled": connection.get("vision_enabled", False),
                    "vision_detail": connection.get("vision_detail", "auto"),
                    "max_image_size": connection.get("max_image_size", 20)
                }
        
        # Fallback to session config for backward compatibility
        config = session.get("config", {})
        return {
            "max_tokens": config.get("max_tokens", 1000),
            "temperature": config.get("temperature", 0.7),
            "top_p": config.get("top_p", 1.0),
            "frequency_penalty": config.get("frequency_penalty", 0.0),
            "presence_penalty": config.get("presence_penalty", 0.0),
            "context_size": config.get("context_size", 4096),
            "think_switch": config.get("think_switch", True),
            "think_depth": config.get("think_depth", 3),
            "hide_thinking_tags": config.get("hide_thinking_tags", True),
            "thinking_tag_patterns": config.get("thinking_tag_patterns", default_patterns),
            "custom_extra_body": config.get("custom_extra_body", None),
            "save_thinking_in_history": config.get("save_thinking_in_history", True)
        }
    
    # Token validation cache (class-level to share across all providers)
    _token_validation_cache = {}  # Key: (provider, token_hash, base_url), Value: (is_valid, timestamp)
    _token_cache_ttl = 3600  # 1 hour TTL
    
    async def validate_token(
        self,
        token: str,
        base_url: Optional[str] = None
    ) -> bool:
        """
        Validate an API token by making a simple API call.
        
        This method should be overridden by subclasses if they need
        provider-specific validation logic.
        
        Args:
            token: API token to validate
            base_url: Optional custom base URL
            
        Returns:
            bool: True if valid, False otherwise
        """
        import hashlib
        import time
        
        # Create cache key (hash token for security)
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        cache_key = (self.provider_name, token_hash, base_url or "")
        
        # Check cache
        if cache_key in BaseAIClient._token_validation_cache:
            is_valid, timestamp = BaseAIClient._token_validation_cache[cache_key]
            if time.time() - timestamp < BaseAIClient._token_cache_ttl:
                log.debug(f"Token validation from cache for {self.provider_name}: {is_valid}")
                return is_valid
        
        # If subclass doesn't implement validation, assume valid
        log.warning(
            f"{self.__class__.__name__} does not implement validate_token(). "
            f"Assuming token is valid."
        )
        # Cache the assumption
        BaseAIClient._token_validation_cache[cache_key] = (True, time.time())
        return True
    
    @staticmethod
    def create_error_response(
        exception: Exception,
        error_type: Optional[str] = None,
        friendly_message: Optional[str] = None
    ) -> str:
        """
        Create a structured error response from an exception.
        
        This helper method creates an LLMError object and returns its string
        representation for transport between components.
        
        Args:
            exception: The exception that occurred
            error_type: Optional custom error type (defaults to exception class name)
            friendly_message: Optional custom friendly message (defaults based on error type)
            
        Returns:
            String representation of the error for transport
        """
        from AI.error_types import LLMError
        
        # Determine error type
        if error_type is None:
            error_type = type(exception).__name__
        
        # Get detailed error message
        error_message = str(exception)
        
        # Determine friendly message based on error type if not provided
        if friendly_message is None:
            # Map common error types to friendly messages
            if "ConnectionError" in error_type or "TimeoutError" in error_type:
                friendly_message = "I'm having trouble connecting. Please try again later."
            elif "RateLimitError" in error_type:
                friendly_message = "I'm receiving too many requests. Please wait a moment and try again."
            elif "APIError" in error_type:
                friendly_message = "I'm having trouble connecting. Please try again later."
            elif "EmptyResponse" in error_type:
                friendly_message = "I'm sorry, but I couldn't generate a response. Please try again."
            else:
                friendly_message = "An error occurred while generating a response. Please try again later."
        
        # Create and return error
        error = LLMError(
            error_type=error_type,
            error_message=error_message,
            friendly_message=friendly_message
        )
        
        return error.to_string()
    
    @staticmethod
    def count_tokens_with_tiktoken(text: str, model: str) -> int:
        """
        Count tokens using tiktoken (for OpenAI-compatible models).
        
        This is a utility method that can be used by any provider that
        uses tiktoken for token counting (OpenAI, Azure OpenAI, etc.).
        
        Args:
            text: Text to count tokens for
            model: Model name
            
        Returns:
            int: Number of tokens
        """
        import tiktoken
        
        try:
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except Exception:
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
                return len(encoding.encode(text))
            except Exception:
                # Approximate: ~4 characters per token for English text
                return len(text) // 4
    
    @staticmethod
    def count_messages_tokens(
        messages: list,
        model: str,
        count_fn: callable
    ) -> int:
        """
        Count total tokens in a list of messages.
        
        This is a utility method that can be used by any provider.
        
        Args:
            messages: List of message dictionaries
            model: Model name
            count_fn: Function to count tokens in text (e.g., count_tokens method)
            
        Returns:
            int: Total number of tokens
        """
        total = 0
        for msg in messages:
            # Add overhead for message structure (~4 tokens per message)
            total += 4
            total += count_fn(msg.get("content", ""), model)
            total += count_fn(msg.get("role", ""), model)
        return total
    
    # Circuit breaker state (class-level to share across instances)
    _circuit_breaker_failures = {}
    _circuit_breaker_last_failure = {}
    _circuit_breaker_open_until = {}
    
    @staticmethod
    async def retry_with_backoff(
        func_to_retry,
        max_retries: int = 3,
        base_delay: float = 1,
        circuit_breaker_key: str = None
    ):
        """
        Retry an async function with exponential backoff and circuit breaker pattern.
        
        Circuit breaker prevents repeated API calls during outages.
        After 5 consecutive failures, the circuit opens for 60 seconds.
        
        Args:
            func_to_retry: Async function to retry
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds (doubles each retry)
            circuit_breaker_key: Optional key for circuit breaker (e.g., "openai_api")
            
        Returns:
            Result of the function call
            
        Raises:
            Last exception if all retries fail or circuit is open
        """
        import asyncio
        import time
        
        # Check circuit breaker
        if circuit_breaker_key:
            current_time = time.time()
            open_until = BaseAIClient._circuit_breaker_open_until.get(circuit_breaker_key, 0)
            
            if current_time < open_until:
                remaining = int(open_until - current_time)
                log.warning(
                    f"Circuit breaker OPEN for {circuit_breaker_key}. "
                    f"Skipping API call. Retry in {remaining}s."
                )
                raise Exception(f"Circuit breaker open for {circuit_breaker_key} ({remaining}s remaining)")
        
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                result = await func_to_retry()
                
                # Success - reset circuit breaker
                if circuit_breaker_key:
                    BaseAIClient._circuit_breaker_failures[circuit_breaker_key] = 0
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # Track failure for circuit breaker
                if circuit_breaker_key:
                    failures = BaseAIClient._circuit_breaker_failures.get(circuit_breaker_key, 0) + 1
                    BaseAIClient._circuit_breaker_failures[circuit_breaker_key] = failures
                    BaseAIClient._circuit_breaker_last_failure[circuit_breaker_key] = time.time()
                    
                    # Open circuit after 5 consecutive failures
                    if failures >= 5:
                        open_duration = 60  # 60 seconds
                        BaseAIClient._circuit_breaker_open_until[circuit_breaker_key] = time.time() + open_duration
                        log.error(
                            f"Circuit breaker OPENED for {circuit_breaker_key} after {failures} failures. "
                            f"Will retry in {open_duration}s."
                        )
                
                if attempt == max_retries - 1:
                    raise
                    
                delay = base_delay * (2 ** attempt)
                log.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed. Retrying in {delay}s. Error: {str(e)}"
                )
                await asyncio.sleep(delay)
        
        if last_exception:
            raise last_exception
    
    @staticmethod
    def truncate_history_by_tokens(
        history: list,
        system_message: str,
        context_size: int,
        model: str,
        reserve_tokens: int,
        count_fn: callable
    ) -> list:
        """
        Truncate conversation history to fit within context size.
        
        This is a generic utility that can be used by any provider.
        
        Args:
            history: List of message dictionaries
            system_message: System message (not included in history)
            context_size: Maximum context size in tokens
            model: Model name for token counting
            reserve_tokens: Tokens to reserve for response
            count_fn: Function to count tokens (e.g., count_tokens method)
            
        Returns:
            Truncated list of messages
        """
        max_tokens = context_size - reserve_tokens
        
        # Start with system message tokens
        current_tokens = 0
        if system_message:
            current_tokens = count_fn(system_message, model) + 4
        
        if not history:
            return []
        
        # Add messages from the end (most recent first)
        selected_messages = []
        for msg in reversed(history):
            # Count tokens for this message
            msg_tokens = 4  # Message overhead
            msg_tokens += count_fn(msg.get("content", ""), model)
            msg_tokens += count_fn(msg.get("role", ""), model)
            
            if current_tokens + msg_tokens <= max_tokens:
                selected_messages.insert(0, msg)
                current_tokens += msg_tokens
            else:
                break
        
        return selected_messages
    
    async def _handle_tool_calls_openai_format(
        self,
        response,
        messages: List[Dict],
        tools: List[Dict],
        tool_context: Optional[Dict[str, Any]],
        client,
        api_params: Dict[str, Any]
    ) -> Optional[str]:
        """
        Handle tool calls for OpenAI-compatible APIs with support for multiple rounds.
        
        This implementation supports iterative tool calling where the LLM can make
        multiple tool calls in sequence (e.g., list all users, then get details about one).
        
        Args:
            response: API response with tool calls
            messages: Original messages sent to API
            tools: Tool definitions
            tool_context: Context for tool execution
            client: API client instance (must have chat.completions.create method)
            api_params: Original API parameters
            
        Returns:
            Final response text after tool execution, or None if failed
        """
        try:
            from AI.tool_executor import get_executor
            
            executor = get_executor()
            current_messages = messages.copy()
            
            # Get max_tool_rounds from API connection (default: 5)
            max_rounds = 5
            if tool_context:
                session = tool_context.get("session", {})
                server_id = tool_context.get("server_id")
                if session and server_id:
                    connection = self._resolve_connection(session, server_id)
                    if connection:
                        max_rounds = connection.get("max_tool_rounds", 5)
                        # Validate and cap the value
                        max_rounds = max(1, min(max_rounds, 10))
            
            log.debug(f"Tool calling configured with max_rounds={max_rounds}")
            
            for round_num in range(max_rounds):
                # Check if current response has tool calls
                if not hasattr(response.choices[0].message, 'tool_calls') or not response.choices[0].message.tool_calls:
                    # No more tool calls - return the content
                    final_content = response.choices[0].message.content or ""
                    
                    if not final_content or final_content.isspace():
                        log.error(
                            f"LLM returned empty response after {round_num} tool round(s). "
                            f"Total messages: {len(current_messages)}"
                        )
                        return None
                    
                    log.info(f"Received final response after {round_num + 1} tool round(s) ({len(final_content)} chars)")
                    return final_content
                
                # Process tool calls for this round
                tool_calls = response.choices[0].message.tool_calls
                log.info(f"Tool round {round_num + 1}: Processing {len(tool_calls)} tool call(s)")
                
                # Execute all tool calls
                tool_results = await executor.execute_tool_calls(tool_calls, tool_context or {})
                
                # Add assistant message with tool calls
                assistant_message = {
                    "role": "assistant",
                    "content": response.choices[0].message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in tool_calls
                    ]
                }
                current_messages.append(assistant_message)
                
                # Add tool results
                for result in tool_results:
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "name": result["name"],
                        "content": result["content"]
                    })
                
                log.debug(f"Prepared {len(current_messages)} messages (including tool results from round {round_num + 1})")
                
                # Make next API call with tool results
                api_params_next = api_params.copy()
                api_params_next["messages"] = current_messages
                # Keep tools available for potential additional calls
                api_params_next["tools"] = tools
                api_params_next["tool_choice"] = "auto"
                
                async def make_request():
                    return await client.chat.completions.create(**api_params_next)
                
                log.info(f"Requesting response from LLM after tool round {round_num + 1}")
                
                try:
                    response = await self.retry_with_backoff(
                        make_request,
                        max_retries=2,
                        base_delay=2,
                        circuit_breaker_key=f"{self.provider_name.lower()}_api_tools"
                    )
                except Exception as e:
                    log.error(f"Failed to make API call after tool round {round_num + 1}: {e}", exc_info=True)
                    return None
                
                # Validate response
                if not response or not hasattr(response, 'choices') or not response.choices:
                    log.error(f"Invalid response after tool round {round_num + 1}: response is None or has no choices")
                    return None
                
                if not response.choices[0] or not hasattr(response.choices[0], 'message'):
                    log.error(f"Invalid response after tool round {round_num + 1}: first choice is None or has no message")
                    return None
                
                # Continue to next round (will check for more tool calls at top of loop)
            
            # If we hit max rounds, log warning and return what we have
            log.warning(f"Reached maximum tool rounds ({max_rounds}), returning current response")
            final_content = response.choices[0].message.content or ""
            return final_content if final_content else None
            
        except Exception as e:
            log.error(f"Error handling tool calls: {e}", exc_info=True)
            return None
