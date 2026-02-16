from typing import Dict, Any, List, Optional

import ollama

import utils.func as func
from AI.base_client import BaseAIClient


class OllamaClient(BaseAIClient):
    """Ollama client for running local AI models."""
    
    provider_name = "Ollama"
    
    def supports_structured_outputs(self) -> bool:
        """Ollama has limited structured output support."""
        return False
    
    def supports_vision(self) -> bool:
        """Ollama supports vision - let the model/API decide if it can handle images."""
        return True
    
    def prepare_multimodal_content(
        self,
        text: str,
        images: List[Dict[str, Any]]
    ) -> tuple[str, List[bytes]]:
        """
        Prepare multimodal content in Ollama format.
        
        Ollama Python SDK expects raw bytes, not base64 strings.
        The REST API expects base64, but the SDK handles the conversion internally.
        
        Args:
            text: Text content
            images: List of processed image dicts with base64
            
        Returns:
            Tuple of (text, images_array) where images_array contains bytes objects
        """
        import base64
        images_array = []
        
        # Convert base64 strings to raw bytes for Ollama SDK
        for image in images:
            base64_data = image.get('base64')
            if base64_data:
                try:
                    # Decode base64 string to bytes
                    image_bytes = base64.b64decode(base64_data)
                    images_array.append(image_bytes)
                except Exception as e:
                    func.log.error(f"Failed to decode image base64: {e}")
        
        return text, images_array
    
    def create_client(self, session: Dict[str, Any], server_id: Optional[str] = None) -> ollama.AsyncClient:
        """Creates an Ollama AsyncClient with optional custom endpoint."""
        base_url = self.resolve_base_url(session, server_id)
        
        # Default to localhost if no base_url specified
        if not base_url:
            base_url = "http://localhost:11434"
        
        client_kwargs = {
            "host": base_url,
            "timeout": 60.0,
        }
        
        return ollama.AsyncClient(**client_kwargs)
    
    def count_tokens(self, text: str, model: str) -> int:
        """Count the number of tokens in a text string using tiktoken approximation."""
        # Ollama doesn't provide native token counting, use tiktoken approximation
        return self.count_tokens_with_tiktoken(text, model)
    
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
        """Generate a response from Ollama with optional tool calling and vision support."""
        model = self.resolve_model(session, server_id, "llama3")
        llm_params = self.get_llm_params(session, server_id)
        client = self.create_client(session, server_id)
        
        try:
            # Process images if vision is enabled and images are provided
            if images and self.supports_vision() and llm_params.get('vision_enabled', False):
                # Modify the last user message to include images
                if messages and messages[-1].get('role') == 'user':
                    last_message = messages[-1]
                    text_content = last_message.get('content', '')
                    
                    # Prepare multimodal content (Ollama format)
                    _, images_array = self.prepare_multimodal_content(text_content, images)
                    
                    # Add images array to the last message
                    messages[-1] = {
                        'role': 'user',
                        'content': text_content,
                        'images': images_array
                    }
                    
                    func.log.info(
                        f"Added {len(images_array)} images to Ollama request for model {model} "
                        f"(format: {type(images_array[0]).__name__ if images_array else 'none'}, "
                        f"size: {len(images_array[0]) if images_array else 0} bytes)"
                    )
            
            api_params = {
                "model": model,
                "messages": messages,
                "options": {
                    "temperature": llm_params.get("temperature", 0.7),
                    "num_predict": llm_params.get("max_tokens", 1000),
                    "top_p": llm_params.get("top_p", 1.0),
                }
            }
            
            # Ollama uses 'think' as a direct parameter (not in extra_body or options)
            think_switch = llm_params.get("think_switch", False)
            api_params["think"] = think_switch
            
            # Merge custom_extra_body if provided (ensure it's JSON-serializable)
            custom_extra = llm_params.get("custom_extra_body")
            if custom_extra and isinstance(custom_extra, dict):
                # Only merge simple, JSON-serializable values
                import json
                try:
                    # Test if it's serializable
                    json.dumps(custom_extra)
                    api_params.update(custom_extra)
                except (TypeError, ValueError) as e:
                    func.log.warning(f"custom_extra_body contains non-serializable data, skipping: {e}")
            
            # Add tools if provided (Ollama supports OpenAI-compatible tool calling)
            if tools:
                api_params["tools"] = tools
            
            async def make_request():
                return await client.chat(**api_params)
            
            response = await self.retry_with_backoff(
                make_request,
                max_retries=2,
                base_delay=2,
                circuit_breaker_key="ollama_api"
            )
            
            # Handle tool calls if present
            if tools and response.get("message", {}).get("tool_calls"):
                tool_results = await self._handle_tool_calls_openai_format(
                    response, messages, tools, tool_context, client, api_params
                )
                
                if tool_results is None:
                    func.log.warning("Tool execution failed or LLM returned empty response")
                
                if tool_results:
                    return tool_results
            
            # Extract response content and handle thinking
            message = response.get("message", {})
            ai_response = message.get("content", "")
            thinking_content = message.get("thinking", "")
            
            hide_tags = llm_params.get("hide_thinking_tags", True)
            
            # If has thinking and should not hide, add to content
            if thinking_content and not hide_tags:
                ai_response = f"<thinking>\n{thinking_content}\n</thinking>\n\n{ai_response}"
            
            if not ai_response or ai_response.isspace():
                func.log.warning("Received empty response from Ollama")
                return self.create_error_response(
                    Exception("Ollama returned an empty response"),
                    error_type="EmptyResponse"
                )
            
            return ai_response
            
        except ollama.ResponseError as e:
            func.log.error(f"Ollama API error: {e}")
            return self.create_error_response(e)
            
        except ollama.RequestError as e:
            func.log.error(f"Ollama connection error: {e}")
            return self.create_error_response(
                e,
                friendly_message="Cannot connect to Ollama. Make sure Ollama is running locally."
            )
            
        except Exception as e:
            func.log.error(f"Error generating Ollama response: {str(e)}")
            return self.create_error_response(e)
    
    def _sanitize_for_json(self, obj: Any) -> Any:
        """
        Recursively sanitize an object to ensure it's JSON serializable.
        Converts non-serializable objects to their string representation.
        """
        import json
        
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        
        if isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        
        if isinstance(obj, (list, tuple)):
            return [self._sanitize_for_json(item) for item in obj]
        
        # Try to serialize, if it fails, convert to string
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            func.log.warning(f"Converting non-serializable object to string: {type(obj).__name__}")
            return str(obj)
    
    async def _handle_tool_calls_openai_format(
        self,
        response: Dict[str, Any],
        messages: List[Dict],
        tools: List[Dict],
        tool_context: Optional[Dict[str, Any]],
        client: ollama.AsyncClient,
        api_params: Dict[str, Any]
    ) -> Optional[str]:
        """
        Handle tool calls for Ollama (OpenAI-compatible format).
        
        Ollama uses the same tool calling format as OpenAI, so we can adapt
        the base implementation.
        """
        try:
            from AI.tool_executor import get_executor
            
            executor = get_executor()
            # Deep copy messages to avoid carrying non-serializable objects
            current_messages = []
            for msg in messages:
                new_msg = {
                    "role": msg.get("role"),
                    "content": msg.get("content", "")
                }
                # Preserve images field if present (for vision support)
                if "images" in msg:
                    new_msg["images"] = msg["images"]
                    func.log.debug(f"Preserved {len(msg['images'])} images in message copy for tool calling")
                current_messages.append(new_msg)
            
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
                message = response.get("message", {})
                tool_calls = message.get("tool_calls")
                
                if not tool_calls:
                    # No more tool calls - return the content
                    final_content = message.get("content", "")
                    
                    if not final_content or final_content.isspace():
                        func.log.error(
                            f"Ollama returned empty response after {round_num} tool round(s). "
                            f"Total messages: {len(current_messages)}"
                        )
                        return None
                    
                    func.log.info(f"Received final response after {round_num + 1} tool round(s) ({len(final_content)} chars)")
                    return final_content
                
                # Process tool calls for this round
                func.log.info(f"Tool round {round_num + 1}: Processing {len(tool_calls)} tool call(s)")
                
                # Convert Ollama tool calls to OpenAI format for executor
                class ToolCall:
                    def __init__(self, tc_dict):
                        self.id = tc_dict.get("id", "")
                        self.type = tc_dict.get("type", "function")
                        self.function = type('obj', (object,), {
                            'name': tc_dict.get("function", {}).get("name", ""),
                            'arguments': tc_dict.get("function", {}).get("arguments", "{}")
                        })()
                
                tool_call_objects = [ToolCall(tc) for tc in tool_calls]
                
                # Execute all tool calls
                tool_results = await executor.execute_tool_calls(tool_call_objects, tool_context or {})
                
                # Add assistant message with tool calls (Ollama format)
                # Ollama expects tool_calls with function.arguments as dict (not JSON string)
                serialized_tool_calls = []
                for tc in tool_calls:
                    func_data = tc.get("function", {})
                    args = func_data.get("arguments", {})
                    
                    # Ensure arguments is a dict, not a JSON string
                    if isinstance(args, str):
                        try:
                            import json
                            args = json.loads(args)
                        except (json.JSONDecodeError, ValueError):
                            func.log.warning(f"Failed to parse tool arguments as JSON: {args}")
                            args = {}
                    
                    serialized_tool_calls.append({
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": func_data.get("name", ""),
                            "arguments": args
                        }
                    })
                
                assistant_message = {
                    "role": "assistant",
                    "content": message.get("content", ""),
                    "tool_calls": serialized_tool_calls
                }
                current_messages.append(assistant_message)
                
                # Add tool results (Ollama format uses "tool_name" not "name", no "tool_call_id")
                for result in tool_results:
                    current_messages.append({
                        "role": "tool",
                        "tool_name": result["name"],
                        "content": result["content"]
                    })
                
                func.log.debug(f"Prepared {len(current_messages)} messages (including tool results from round {round_num + 1})")
                
                # Sanitize all messages to ensure JSON serializability
                sanitized_messages = self._sanitize_for_json(current_messages)
                
                # Validate that all messages are now JSON serializable
                import json
                try:
                    json.dumps(sanitized_messages)
                    func.log.debug("All messages validated as JSON serializable")
                except (TypeError, ValueError) as e:
                    func.log.error(f"Messages still contain non-serializable objects after sanitization: {e}")
                    # Try to identify which message is problematic
                    for i, msg in enumerate(sanitized_messages):
                        try:
                            json.dumps(msg)
                        except (TypeError, ValueError) as msg_error:
                            func.log.error(f"Message {i} is not serializable: {msg_error}")
                            func.log.error(f"Message content: {msg}")
                    return None
                
                # Make next API call with tool results
                api_params_next = api_params.copy()
                api_params_next["messages"] = sanitized_messages
                api_params_next["tools"] = tools
                
                async def make_request():
                    return await client.chat(**api_params_next)
                
                func.log.info(f"Requesting response from Ollama after tool round {round_num + 1}")
                
                try:
                    response = await self.retry_with_backoff(
                        make_request,
                        max_retries=2,
                        base_delay=2,
                        circuit_breaker_key="ollama_api_tools"
                    )
                except Exception as e:
                    func.log.error(f"Failed to make API call after tool round {round_num + 1}: {e}", exc_info=True)
                    return None
                
                # Validate response
                if not response or not response.get("message"):
                    func.log.error(f"Invalid response after tool round {round_num + 1}")
                    return None
                
                # Continue to next round
            
            # If we hit max rounds, return what we have
            func.log.warning(f"Reached maximum tool rounds ({max_rounds}), returning current response")
            final_content = response.get("message", {}).get("content", "")
            return final_content if final_content else None
            
        except Exception as e:
            func.log.error(f"Error handling tool calls: {e}", exc_info=True)
            return None
    
    async def get_bot_info(
        self,
        session: Dict[str, Any],
        server_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieves the model information from Ollama."""
        model = self.resolve_model(session, server_id, default_model="llama3")
        if not model:
            func.log.error("No model provided to get_bot_info")
            return None

        try:
            client = self.create_client(session, server_id)
            
            try:
                # List available models
                models_response = await client.list()
                models = models_response.get("models", [])
                
                # Find the specified model
                for m in models:
                    if m.get("name") == model or m.get("model") == model:
                        return {
                            "name": m.get("name", model),
                            "avatar_url": None,
                            "title": m.get("name", model),
                            "description": f"Ollama Model: {m.get('name', model)} ({m.get('size', 'unknown size')})",
                            "visibility": "local",
                            "num_interactions": None,
                            "author_username": "local"
                        }
                
                # Model not found in list, return basic info
                func.log.warning(f"Model {model} not found in Ollama models list")
                return {
                    "name": model,
                    "avatar_url": None,
                    "title": model,
                    "description": f"Ollama Model: {model}",
                    "visibility": "local",
                    "num_interactions": None,
                    "author_username": "local"
                }
                
            except Exception as e:
                func.log.error(f"Error listing Ollama models: {e}")
                return {
                    "name": model,
                    "avatar_url": None,
                    "title": model,
                    "description": f"Ollama Model: {model}",
                    "visibility": "local",
                    "num_interactions": None,
                    "author_username": "local"
                }
                
        except Exception as e:
            func.log.critical("Unable to get model information from Ollama: %s", e)
            return {
                "name": model,
                "avatar_url": None,
                "title": model,
                "description": f"Ollama Model: {model}",
                "visibility": "local",
                "num_interactions": None,
                "author_username": "local"
            }
    
    async def validate_token(self, token: str, base_url: Optional[str] = None) -> bool:
        """
        Validate Ollama connection by pinging the endpoint.
        
        For local Ollama instances, no token is needed. For remote instances,
        this checks if the endpoint is accessible.
        """
        import hashlib
        import time
        
        # For Ollama, we validate the connection, not a token
        # Use base_url as the cache key
        token_hash = hashlib.sha256((base_url or "localhost").encode()).hexdigest()[:16]
        cache_key = (self.provider_name, token_hash, base_url or "")
        
        if cache_key in BaseAIClient._token_validation_cache:
            is_valid, timestamp = BaseAIClient._token_validation_cache[cache_key]
            if time.time() - timestamp < BaseAIClient._token_cache_ttl:
                return is_valid
        
        try:
            if not base_url:
                base_url = "http://localhost:11434"
            
            client = ollama.AsyncClient(host=base_url, timeout=10.0)
            
            try:
                # Try to list models to verify connection
                await client.list()
                BaseAIClient._token_validation_cache[cache_key] = (True, time.time())
                return True
            except Exception as e:
                func.log.error(f"Ollama connection validation failed: {e}")
                BaseAIClient._token_validation_cache[cache_key] = (False, time.time() - BaseAIClient._token_cache_ttl + 300)
                return False
                
        except Exception as e:
            func.log.error(f"Ollama validation error: {e}")
            BaseAIClient._token_validation_cache[cache_key] = (False, time.time() - BaseAIClient._token_cache_ttl + 300)
            return False

_ollama_client = OllamaClient()


def create_client(session: Dict[str, Any], server_id: Optional[str] = None) -> ollama.AsyncClient:
    """Create an Ollama client instance."""
    return _ollama_client.create_client(session, server_id)


def get_model(session: Dict[str, Any], server_id: Optional[str] = None) -> str:
    """Get model name from session/connection."""
    return _ollama_client.resolve_model(session, server_id, default_model="llama3")


def get_llm_params(session: Dict[str, Any], server_id: Optional[str] = None) -> Dict[str, Any]:
    """Get LLM parameters from session/connection."""
    return _ollama_client.get_llm_params(session, server_id)


def count_tokens(text: str, model: str) -> int:
    """Count tokens in text using tiktoken approximation."""
    return _ollama_client.count_tokens(text, model)


async def validate_token(token: str, base_url: Optional[str] = None) -> bool:
    """Validate Ollama connection."""
    return await _ollama_client.validate_token(token, base_url)


async def get_bot_info(
    session: Optional[Dict[str, Any]] = None,
    server_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get bot/model information."""
    if session is None:
        session = {}
    
    return await _ollama_client.get_bot_info(session, server_id)

from AI.provider_registry import register_provider

register_provider(
    name="ollama",
    client_class=OllamaClient,
    display_name="Ollama",
    color="white",
    icon="🦙",
    default_model="deepseek-r1:8b",
    supports_thinking=True,
    description="Local AI models running on your machine!"
)
