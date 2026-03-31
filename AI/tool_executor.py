"""
Tool Executor - Executes tool calls from LLM

This module handles the execution of tool calls requested by the LLM,
including validation, context preparation, and result formatting.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Callable
import tiktoken

log = logging.getLogger(__name__)

class ToolExecutor:
    """
    Executes tool calls from LLM function calling.
    
    This class:
    1. Registers available tools
    2. Validates tool calls
    3. Executes tools with proper context
    4. Handles errors gracefully
    5. Formats results for the LLM
    """
    
    def __init__(self):
        """Initialize the tool executor."""
        self.tools: Dict[str, Callable] = {}
        self._register_tools()
        log.debug("ToolExecutor initialized with %d tools", len(self.tools))
    
    def _register_tools(self):
        """Register all available tools."""
        from AI.tools import discord_tools, memory_tools, bash_tool
        
        # Register unified Discord query tool
        self.tools["discord_query"] = discord_tools.discord_query
        
        # Register unified memory tool
        self.tools["memory"] = memory_tools.memory
        
        # Register bash tool
        self.tools["bash_tool"] = bash_tool.bash_tool
        
        log.info(f"Registered {len(self.tools)} tools: {list(self.tools.keys())}")
    
    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single tool call.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments for the tool
            context: Context information (server_id, channel_id, guild, etc.)
            
        Returns:
            Dict with tool execution result
        """
        log.info(f"Executing tool: {tool_name}")
        log.debug(f"Tool arguments: {arguments}")
        
        # Validate tool exists
        if tool_name not in self.tools:
            error_msg = f"Unknown tool: {tool_name}"
            log.error(f"{error_msg}")
            return {
                "error": error_msg,
                "available_tools": list(self.tools.keys())
            }
        
        # Check if tool is allowed
        allowed_tools = context.get("allowed_tools", ["all"])
        if "all" not in allowed_tools and tool_name not in allowed_tools:
            error_msg = f"Tool '{tool_name}' is not allowed in current configuration"
            log.warning(error_msg)
            return {
                "error": error_msg,
                "allowed_tools": allowed_tools
            }
        
        try:
            # Get the tool function
            tool_func = self.tools[tool_name]
            
            # Add context to arguments
            arguments["context"] = context
            
            # Execute the tool
            result = await tool_func(**arguments)
            
            log.info(f"Tool '{tool_name}' executed successfully")
            return result
            
        except TypeError as e:
            # Invalid arguments
            error_msg = f"Invalid arguments for tool '{tool_name}': {str(e)}"
            log.error(error_msg, exc_info=True)
            return {
                "error": error_msg
            }
        
        except Exception as e:
            # General error
            error_msg = f"Error executing tool '{tool_name}': {str(e)}"
            log.error(error_msg, exc_info=True)
            return {
                "error": error_msg
            }
    
    async def execute_tool_calls(
        self,
        tool_calls: List[Any],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple tool calls from LLM response.
        
        Args:
            tool_calls: List of tool call objects from OpenAI API
            context: Context information
            
        Returns:
            List of tool results in OpenAI format
        """
        # Calculate dynamic truncation limit based on context_size
        truncation_limit = self._calculate_truncation_limit(context)
        
        results = []
        
        for tool_call in tool_calls:
            try:
                # Extract tool information
                tool_id = tool_call.id
                tool_name = tool_call.function.name
                
                # Parse arguments (they come as JSON string from some providers, dict from others)
                if isinstance(tool_call.function.arguments, str):
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as e:
                        log.error(f"Failed to parse tool arguments: {e}")
                        arguments = {}
                elif isinstance(tool_call.function.arguments, dict):
                    # Already a dict (e.g., from Ollama)
                    arguments = tool_call.function.arguments
                else:
                    log.error(f"Unexpected arguments type: {type(tool_call.function.arguments)}")
                    arguments = {}
                
                log.info(f"Processing tool call: {tool_name} (id: {tool_id})")
                
                # Execute the tool
                result = await self.execute_tool(tool_name, arguments, context)
                
                # Format result for OpenAI API
                # Convert result to JSON string
                result_str = json.dumps(result, ensure_ascii=False)
                
                # Truncate if too long (dynamic limit based on context_size)
                if len(result_str) > truncation_limit:
                    # Count actual tokens using tiktoken
                    try:
                        # Get model from context
                        model = "gpt-4"
                        session = context.get("session", {})
                        connection_name = session.get("api_connection")
                        if connection_name:
                            server_id = context.get("server_id")
                            if server_id:
                                from utils import func
                                connection = func.get_api_connection(server_id, connection_name)
                                if connection:
                                    model = connection.get("model", "gpt-4")
                        
                        # Count tokens
                        actual_tokens = self._count_tokens(result_str, model)
                    except Exception as e:
                        log.warning(f"Failed to count tokens: {e}")
                        actual_tokens = len(result_str) // 4  # Fallback estimate
                    
                    log.warning(
                        f"Tool result too long ({len(result_str)} chars / {actual_tokens} tokens), "
                        f"truncating to {truncation_limit} chars"
                    )
                    
                    # Truncate with buffer for truncation message
                    truncate_at = truncation_limit - 100
                    result_str = result_str[:truncate_at] + f"\n\n... [truncated: {len(result_str) - truncate_at} chars / ~{actual_tokens} tokens removed]"
                
                results.append({
                    "tool_call_id": tool_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": result_str
                })
                
            except Exception as e:
                log.error(f"Error processing tool call: {e}", exc_info=True)
                # Return error result
                results.append({
                    "tool_call_id": tool_call.id if hasattr(tool_call, 'id') else "unknown",
                    "role": "tool",
                    "name": tool_call.function.name if hasattr(tool_call, 'function') else "unknown",
                    "content": json.dumps({"error": f"Failed to execute tool: {str(e)}"})
                })
        
        return results
    
    def _count_tokens(self, text: str, model: str = "gpt-4") -> int:
        """
        Count tokens in text using tiktoken.
        
        Args:
            text: Text to count tokens for
            model: Model name for encoding (default: gpt-4)
            
        Returns:
            int: Number of tokens
        """
        try:
            # Get encoding for model
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except Exception as e:
            log.warning(f"Failed to count tokens with tiktoken for model '{model}': {e}")
            # Fallback to character estimation (4 chars per token)
            return len(text) // 4
    
    def _calculate_truncation_limit(self, context: Dict[str, Any]) -> int:
        """
        Calculate dynamic truncation limit for tool results based on context_size.
        Uses tiktoken for accurate token-to-character conversion.
        
        Args:
            context: Context information containing session data
            
        Returns:
            int: Maximum characters allowed for tool results
        """
        # Extract session and config
        session = context.get("session", {})
        config = session.get("config", {})
        tool_config = config.get("tool_calling", {})
        
        # Get context_size and model - try API connection first
        context_size = 4096  # Default fallback
        model = "gpt-4"  # Default model for tiktoken
        connection_name = session.get("api_connection")
        
        if connection_name:
            # Try to get from API connection
            try:
                from utils import func
                server_id = context.get("server_id")
                if server_id:
                    connection = func.get_api_connection(server_id, connection_name)
                    if connection:
                        context_size = connection.get("context_size", 4096)
                        model = connection.get("model", "gpt-4")
                    else:
                        context_size = config.get("context_size", 4096)
                else:
                    context_size = config.get("context_size", 4096)
            except Exception as e:
                log.warning(f"Failed to get context_size from API connection: {e}")
                context_size = config.get("context_size", 4096)
        else:
            # Fallback to config
            context_size = config.get("context_size", 4096)
        
        # Get configuration parameters with defaults
        percentage = tool_config.get("tool_result_max_percentage", 35)
        min_chars = tool_config.get("tool_result_min_chars", 500)
        max_chars = tool_config.get("tool_result_max_chars", 50000)
        
        # Calculate token limit: context_size * percentage / 100
        token_limit = int(context_size * percentage / 100)
        
        # Convert token limit to character limit using tiktoken
        # Sample text to estimate chars per token for this model
        try:
            encoding = tiktoken.encoding_for_model(model)
            # Use a representative sample to estimate chars/token ratio
            sample = "The quick brown fox jumps over the lazy dog. " * 10
            sample_tokens = len(encoding.encode(sample))
            chars_per_token = len(sample) / sample_tokens if sample_tokens > 0 else 4
        except Exception as e:
            log.warning(f"Failed to estimate chars_per_token with tiktoken for model '{model}': {e}")
            chars_per_token = 4  # Fallback
        
        # Calculate character limit
        calculated_limit = int(token_limit * chars_per_token)
        
        # Apply safety bounds
        truncation_limit = max(min_chars, min(calculated_limit, max_chars))
        
        log.debug(
            f"Tool result truncation limit: {truncation_limit} chars "
            f"(context: {context_size} tokens, {percentage}% = {token_limit} tokens, "
            f"~{chars_per_token:.2f} chars/token, model: {model}, "
            f"bounds: {min_chars}-{max_chars})"
        )
        
        return truncation_limit
    
    def prepare_context(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: str,
        guild: Any,
        session: Dict[str, Any],
        bot_client: Any = None,
        message: Any = None
    ) -> Dict[str, Any]:
        """
        Prepare context for tool execution.
        
        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID
            ai_name: AI name
            chat_id: Chat session ID
            guild: Discord guild object (may be fake)
            session: Session configuration
            bot_client: Discord bot client (for getting real guild)
            message: Discord message object (for author info)
            
        Returns:
            Context dictionary
        """
        config = session.get("config", {})
        tool_config = config.get("tool_calling", {})
        memory_max_tokens = config.get("memory_max_tokens", 1000)
        
        # Validate and fix guild if needed
        # If guild is None or doesn't have members attribute (fake guild),
        # try to get real guild from bot_client
        if bot_client and (guild is None or not hasattr(guild, 'members')):
            try:
                guild = bot_client.get_guild(int(server_id))
                if guild:
                    log.debug("Retrieved real guild from bot_client")
            except Exception as e:
                log.warning(f"Failed to get guild from bot_client: {e}")
        
        return {
            "server_id": server_id,
            "channel_id": channel_id,
            "ai_name": ai_name,
            "chat_id": chat_id,
            "guild": guild,
            "bot_client": bot_client,
            "message": message,
            "allowed_tools": tool_config.get("allowed_tools", ["all"]),
            "memory_max_tokens": memory_max_tokens,
            "session": session
        }


# Global executor instance
_executor = ToolExecutor()


def get_executor() -> ToolExecutor:
    """Get the global tool executor instance."""
    return _executor
