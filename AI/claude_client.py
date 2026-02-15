from typing import Dict, Any, List, Optional

from anthropic import AsyncAnthropic, APIError, APIConnectionError, RateLimitError, APITimeoutError

import utils.func as func
from AI.base_client import BaseAIClient


class ClaudeClient(BaseAIClient):
    """Anthropic Claude API client for chat completions and tool use."""
    
    provider_name = "Claude"
    
    def supports_structured_outputs(self) -> bool:
        """Claude supports structured outputs via tool use."""
        return True
    
    def supports_vision(self) -> bool:
        """Claude supports vision with claude-3-opus, claude-3-sonnet, claude-3-haiku, claude-3-5-sonnet."""
        return True
    
    def prepare_multimodal_content(
        self,
        text: str,
        images: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Prepare multimodal content in Anthropic Claude format.
        
        Claude format uses content as an array with text and image objects.
        Images must be base64-encoded.
        
        Args:
            text: Text content
            images: List of processed image dicts with base64, format
            
        Returns:
            List of content objects for Claude API
        """
        content = []
        
        # Add text first
        if text:
            content.append({
                "type": "text",
                "text": text
            })
        
        # Add images
        for image in images:
            base64_data = image.get('base64')
            image_format = image.get('format', 'image/jpeg')
            
            # Extract media type (e.g., "image/jpeg" -> "image/jpeg")
            media_type = image_format
            
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_data
                }
            })
        
        return content
    
    def create_client(self, session: Dict[str, Any], server_id: Optional[str] = None) -> AsyncAnthropic:
        """Creates an AsyncAnthropic client."""
        api_key = self.resolve_api_key(session, server_id)
        base_url = self.resolve_base_url(session, server_id)
        
        client_kwargs = {
            "api_key": api_key,
            "timeout": 60.0,
        }
        
        if base_url:
            client_kwargs["base_url"] = base_url
        
        return AsyncAnthropic(**client_kwargs)
    
    def count_tokens(self, text: str, model: str) -> int:
        """
        Count the number of tokens in a text string.
        
        Note: Anthropic uses a different tokenizer than OpenAI.
        We use character-based approximation since we can't easily access
        Anthropic's tokenizer synchronously.
        """
        # Anthropic's approximation: ~3.5 characters per token for English
        return len(text) // 4
    
    def _extract_system_message(self, messages: List[Dict[str, str]]) -> tuple[Optional[str], List[Dict[str, str]]]:
        """
        Extract system message from messages array.
        
        Claude requires system message as a separate parameter, not in messages array.
        
        Returns:
            Tuple of (system_message, remaining_messages)
        """
        system_message = None
        remaining_messages = []
        
        for msg in messages:
            if msg.get("role") == "system":
                # Combine multiple system messages if present
                if system_message:
                    system_message += "\n\n" + msg.get("content", "")
                else:
                    system_message = msg.get("content", "")
            else:
                remaining_messages.append(msg)
        
        return system_message, remaining_messages
    
    def _convert_tools_to_anthropic_format(self, tools: List[Dict]) -> List[Dict]:
        """
        Convert OpenAI-style tool definitions to Anthropic format.
        
        OpenAI format:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}
            }
        }
        
        Anthropic format:
        {
            "name": "...",
            "description": "...",
            "input_schema": {...}
        }
        """
        anthropic_tools = []
        
        for tool in tools:
            if tool.get("type") == "function":
                func_def = tool.get("function", {})
                anthropic_tools.append({
                    "name": func_def.get("name", ""),
                    "description": func_def.get("description", ""),
                    "input_schema": func_def.get("parameters", {})
                })
        
        return anthropic_tools
    
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        session: Dict[str, Any],
        server_id: str,
        tools: Optional[List[Dict]] = None,
        tool_context: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """Generate a response from Claude API with optional tool calling and vision support."""
        model = self.resolve_model(session, server_id, "claude-3-5-sonnet-20241022")
        llm_params = self.get_llm_params(session, server_id)
        client = self.create_client(session, server_id)
        
        try:
            # Extract system message (Claude requires it separate)
            system_message, user_messages = self._extract_system_message(messages)
            
            # Process images if vision is enabled and images are provided
            if images and self.supports_vision() and llm_params.get('vision_enabled', False):
                # Modify the last user message to include images
                if user_messages and user_messages[-1].get('role') == 'user':
                    last_message = user_messages[-1]
                    text_content = last_message.get('content', '')
                    
                    # Prepare multimodal content
                    multimodal_content = self.prepare_multimodal_content(text_content, images)
                    
                    # Replace the last message with multimodal version
                    user_messages[-1] = {
                        'role': 'user',
                        'content': multimodal_content
                    }
            
            # Build API parameters
            api_params = {
                "model": model,
                "messages": user_messages,
                "max_tokens": llm_params.get("max_tokens", 1000),
                "temperature": llm_params.get("temperature", 0.7),
                "top_p": llm_params.get("top_p", 1.0),
            }
            
            if system_message:
                api_params["system"] = system_message
            
            # Add thinking if enabled
            think_switch = llm_params.get("think_switch", False)
            if think_switch:
                think_depth = llm_params.get("think_depth", 3)
                budget_tokens = think_depth * 2000  # 2000 tokens per level
                
                api_params["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": budget_tokens
                }
            
            # Merge custom_extra_body if provided
            custom_extra = llm_params.get("custom_extra_body")
            if custom_extra:
                api_params.update(custom_extra)
            
            # Add tools if provided (convert to Anthropic format)
            if tools:
                anthropic_tools = self._convert_tools_to_anthropic_format(tools)
                api_params["tools"] = anthropic_tools
            
            async def make_request():
                return await client.messages.create(**api_params)
            
            response = await self.retry_with_backoff(
                make_request,
                max_retries=2,
                base_delay=2,
                circuit_breaker_key="claude_api"
            )
            
            # Handle tool calls if present
            if tools and response.stop_reason == "tool_use":
                tool_results = await self._handle_tool_calls_anthropic_format(
                    response, user_messages, tools, tool_context, client, api_params, system_message
                )
                
                if tool_results is None:
                    func.log.warning("Tool execution failed or LLM returned empty response")
                
                if tool_results:
                    return tool_results
            
            # Extract response content and thinking
            ai_response = ""
            thinking_content = ""
            
            for content_block in response.content:
                if content_block.type == "text":
                    ai_response += content_block.text
                elif content_block.type == "thinking":
                    thinking_content += content_block.thinking
            
            hide_tags = llm_params.get("hide_thinking_tags", True)
            
            # If has thinking and should not hide, add to content
            if thinking_content and not hide_tags:
                ai_response = f"<thinking>\n{thinking_content}\n</thinking>\n\n{ai_response}"
            
            if not ai_response or ai_response.isspace():
                func.log.warning("Received empty response from Claude")
                return self.create_error_response(
                    Exception("Claude returned an empty response"),
                    error_type="EmptyResponse"
                )
            
            return ai_response
            
        except APIConnectionError as e:
            func.log.error(f"Claude connection error: {e}")
            return self.create_error_response(e)
            
        except APITimeoutError as e:
            func.log.error(f"Claude timeout error: {e}")
            return self.create_error_response(e)
            
        except RateLimitError as e:
            func.log.error(f"Claude rate limit error: {e}")
            return self.create_error_response(e)
            
        except APIError as e:
            func.log.error(f"Claude API error: {e}")
            return self.create_error_response(e)
            
        except Exception as e:
            func.log.error(f"Error generating Claude response: {str(e)}")
            return self.create_error_response(e)
            
        finally:
            try:
                await client.close()
            except Exception as e:
                func.log.error(f"Error closing client session: {str(e)}")
    
    async def _handle_tool_calls_anthropic_format(
        self,
        response,
        messages: List[Dict],
        tools: List[Dict],
        tool_context: Optional[Dict[str, Any]],
        client: AsyncAnthropic,
        api_params: Dict[str, Any],
        system_message: Optional[str]
    ) -> Optional[str]:
        """
        Handle tool calls for Claude API with support for multiple rounds.
        
        Claude's tool calling format is different from OpenAI:
        - Tool calls are in content blocks with type="tool_use"
        - Tool results are sent as content blocks with type="tool_result"
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
                        max_rounds = max(1, min(max_rounds, 10))
            
            func.log.debug(f"Tool calling configured with max_rounds={max_rounds}")
            
            for round_num in range(max_rounds):
                # Check if current response has tool calls
                tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
                
                if not tool_use_blocks:
                    # No more tool calls - extract and return text content
                    final_content = ""
                    for block in response.content:
                        if block.type == "text":
                            final_content += block.text
                    
                    if not final_content or final_content.isspace():
                        func.log.error(
                            f"Claude returned empty response after {round_num} tool round(s). "
                            f"Total messages: {len(current_messages)}"
                        )
                        return None
                    
                    func.log.info(f"Received final response after {round_num + 1} tool round(s) ({len(final_content)} chars)")
                    return final_content
                
                # Process tool calls for this round
                func.log.info(f"Tool round {round_num + 1}: Processing {len(tool_use_blocks)} tool call(s)")
                
                # Convert Claude tool calls to OpenAI format for executor
                class ToolCall:
                    def __init__(self, block):
                        self.id = block.id
                        self.type = "function"
                        import json
                        self.function = type('obj', (object,), {
                            'name': block.name,
                            'arguments': json.dumps(block.input)
                        })()
                
                tool_call_objects = [ToolCall(block) for block in tool_use_blocks]
                
                # Execute all tool calls
                tool_results = await executor.execute_tool_calls(tool_call_objects, tool_context or {})
                
                # Build assistant message with tool use blocks
                assistant_content = []
                for block in response.content:
                    if block.type == "text":
                        assistant_content.append({
                            "type": "text",
                            "text": block.text
                        })
                    elif block.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input
                        })
                
                current_messages.append({
                    "role": "assistant",
                    "content": assistant_content
                })
                
                # Build user message with tool results
                tool_result_content = []
                for result in tool_results:
                    tool_result_content.append({
                        "type": "tool_result",
                        "tool_use_id": result["tool_call_id"],
                        "content": result["content"]
                    })
                
                current_messages.append({
                    "role": "user",
                    "content": tool_result_content
                })
                
                func.log.debug(f"Prepared {len(current_messages)} messages (including tool results from round {round_num + 1})")
                
                # Make next API call with tool results
                api_params_next = api_params.copy()
                api_params_next["messages"] = current_messages
                # Keep tools available for potential additional calls
                anthropic_tools = self._convert_tools_to_anthropic_format(tools)
                api_params_next["tools"] = anthropic_tools
                
                async def make_request():
                    return await client.messages.create(**api_params_next)
                
                func.log.info(f"Requesting response from Claude after tool round {round_num + 1}")
                
                try:
                    response = await self.retry_with_backoff(
                        make_request,
                        max_retries=2,
                        base_delay=2,
                        circuit_breaker_key="claude_api_tools"
                    )
                except Exception as e:
                    func.log.error(f"Failed to make API call after tool round {round_num + 1}: {e}", exc_info=True)
                    return None
                
                # Validate response
                if not response or not hasattr(response, 'content'):
                    func.log.error(f"Invalid response after tool round {round_num + 1}")
                    return None
                
                # Continue to next round (will check for more tool calls at top of loop)
            
            # If we hit max rounds, return what we have
            func.log.warning(f"Reached maximum tool rounds ({max_rounds}), returning current response")
            final_content = ""
            for block in response.content:
                if block.type == "text":
                    final_content += block.text
            return final_content if final_content else None
            
        except Exception as e:
            func.log.error(f"Error handling tool calls: {e}", exc_info=True)
            return None
    
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
        Generate a structured response following a JSON Schema using Claude's tool use.
        
        Claude doesn't have native structured outputs like OpenAI, but we can
        achieve the same result by defining a tool that returns the desired schema.
        """
        model = self.resolve_model(session, server_id, "claude-3-5-sonnet-20241022")
        client = self.create_client(session, server_id)
        
        try:
            # Extract system message
            system_message, user_messages = self._extract_system_message(messages)
            
            # Create a tool that represents the structured output
            tool_def = {
                "name": schema_name,
                "description": f"Return a structured response following the {schema_name} schema",
                "input_schema": json_schema
            }
            
            api_params = {
                "model": model,
                "messages": user_messages,
                "max_tokens": kwargs.get("max_tokens", 1000),
                "temperature": kwargs.get("temperature", 0.3),
                "tools": [tool_def],
                "tool_choice": {"type": "tool", "name": schema_name}
            }
            
            if system_message:
                api_params["system"] = system_message
            
            async def make_request():
                return await client.messages.create(**api_params)
            
            response = await self.retry_with_backoff(
                make_request,
                max_retries=2,
                base_delay=2,
                circuit_breaker_key="claude_api_structured"
            )
            
            # Extract tool use result
            for block in response.content:
                if block.type == "tool_use" and block.name == schema_name:
                    return block.input
            
            raise ValueError("Claude did not return the expected structured output")
            
        except Exception as e:
            func.log.error(f"Error in generate_response_structured: {e}")
            raise
            
        finally:
            try:
                await client.close()
            except Exception as e:
                func.log.error(f"Error closing client session: {str(e)}")
    
    async def get_bot_info(
        self,
        session: Dict[str, Any],
        server_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves the model information.
        
        Note: Anthropic doesn't have a models list endpoint, so we return
        hardcoded information based on the model name.
        """
        model = self.resolve_model(session, server_id, default_model="claude-3-5-sonnet-20241022")
        if not model:
            func.log.error("No model provided to get_bot_info")
            return None

        # Hardcoded model information
        model_info = {
            "claude-3-opus-20240229": {
                "description": "Most capable Claude model for complex tasks",
                "context_window": "200K tokens"
            },
            "claude-3-5-sonnet-20241022": {
                "description": "Best combination of intelligence and speed",
                "context_window": "200K tokens"
            },
            "claude-3-sonnet-20240229": {
                "description": "Balanced performance and speed",
                "context_window": "200K tokens"
            },
            "claude-3-haiku-20240307": {
                "description": "Fastest and most compact model",
                "context_window": "200K tokens"
            }
        }
        
        info = model_info.get(model, {
            "description": f"Claude model: {model}",
            "context_window": "200K tokens"
        })
        
        return {
            "name": model,
            "avatar_url": None,
            "title": model,
            "description": f"Anthropic Claude - {info['description']} ({info['context_window']})",
            "visibility": "public",
            "num_interactions": None,
            "author_username": "Anthropic"
        }
    
    async def validate_token(self, token: str, base_url: Optional[str] = None) -> bool:
        """Validates a Claude API token by making a simple API call with 1-hour caching."""
        import hashlib
        import time
        
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        cache_key = (self.provider_name, token_hash, base_url or "")
        
        if cache_key in BaseAIClient._token_validation_cache:
            is_valid, timestamp = BaseAIClient._token_validation_cache[cache_key]
            if time.time() - timestamp < BaseAIClient._token_cache_ttl:
                return is_valid
        
        try:
            client_kwargs = {"api_key": token, "timeout": 10.0}
            if base_url:
                client_kwargs["base_url"] = base_url
            
            client = AsyncAnthropic(**client_kwargs)
            try:
                # Make a minimal API call to validate the token
                # We'll use a very short message to minimize cost
                await client.messages.create(
                    model="claude-3-haiku-20240307",  # Use cheapest model
                    max_tokens=1,
                    messages=[{"role": "user", "content": "Hi"}]
                )
                BaseAIClient._token_validation_cache[cache_key] = (True, time.time())
                return True
            finally:
                await client.close()
        except Exception as e:
            func.log.error(f"Claude token validation failed: {e}")
            BaseAIClient._token_validation_cache[cache_key] = (False, time.time() - BaseAIClient._token_cache_ttl + 300)
            return False

_claude_client = ClaudeClient()


def create_client(session: Dict[str, Any], server_id: Optional[str] = None) -> AsyncAnthropic:
    """Create a Claude client instance."""
    return _claude_client.create_client(session, server_id)


def get_model(session: Dict[str, Any], server_id: Optional[str] = None) -> str:
    """Get model name from session/connection."""
    return _claude_client.resolve_model(session, server_id, default_model="claude-3-5-sonnet-20241022")


def get_llm_params(session: Dict[str, Any], server_id: Optional[str] = None) -> Dict[str, Any]:
    """Get LLM parameters from session/connection."""
    return _claude_client.get_llm_params(session, server_id)


def count_tokens(text: str, model: str) -> int:
    """Count tokens in text using approximation."""
    return _claude_client.count_tokens(text, model)


async def validate_token(token: str, base_url: Optional[str] = None) -> bool:
    """Validate an API token."""
    return await _claude_client.validate_token(token, base_url)


async def get_bot_info(
    session: Optional[Dict[str, Any]] = None,
    server_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get bot/model information."""
    if session is None:
        session = {}
    
    return await _claude_client.get_bot_info(session, server_id)

from AI.provider_registry import register_provider

register_provider(
    name="claude",
    client_class=ClaudeClient,
    display_name="Anthropic",
    color="orange",
    icon="✴️ ",
    default_model="claude-3-5-sonnet",
    supports_thinking=True,
    description="Anthropic's Claude models"
)
