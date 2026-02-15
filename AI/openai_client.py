from typing import Dict, Any, List, Optional

from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError

import utils.func as func
from AI.base_client import BaseAIClient


class OpenAIClient(BaseAIClient):
    """Pure OpenAI API client for chat completions and structured outputs."""
    
    provider_name = "OpenAI"
    
    def supports_structured_outputs(self) -> bool:
        """OpenAI supports Structured Outputs (JSON Schema)."""
        return True
    
    def supports_vision(self) -> bool:
        """OpenAI supports vision with gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-4-vision-preview."""
        return True
    
    def prepare_multimodal_content(
        self,
        text: str,
        images: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Prepare multimodal content in OpenAI format.
        
        OpenAI format uses content as an array with text and image_url objects.
        
        Args:
            text: Text content
            images: List of processed image dicts with base64, format, detail
            
        Returns:
            List of content objects for OpenAI API
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
            detail = image.get('detail', 'auto')
            
            # Create data URI
            data_uri = f"data:{image_format};base64,{base64_data}"
            
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": data_uri,
                    "detail": detail
                }
            })
        
        return content
    
    def create_client(self, session: Dict[str, Any], server_id: Optional[str] = None) -> AsyncOpenAI:
        """Creates an AsyncOpenAI client with optional custom endpoint."""
        api_key = self.resolve_api_key(session, server_id)
        base_url = self.resolve_base_url(session, server_id)
        
        client_kwargs = {
            "api_key": api_key,
            "timeout": 60.0,
        }
        
        if base_url:
            client_kwargs["base_url"] = base_url
        
        return AsyncOpenAI(**client_kwargs)
    
    def count_tokens(self, text: str, model: str) -> int:
        """Count the number of tokens in a text string using tiktoken."""
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
        """Generate a response from OpenAI API with optional tool calling and vision support."""
        model = self.resolve_model(session, server_id, "gpt-3.5-turbo")
        llm_params = self.get_llm_params(session, server_id)
        client = self.create_client(session, server_id)
        
        try:
            # Process images if vision is enabled and images are provided
            if images and self.supports_vision() and llm_params.get('vision_enabled', False):
                # Modify the last user message to include images
                if messages and messages[-1].get('role') == 'user':
                    last_message = messages[-1]
                    text_content = last_message.get('content', '')
                    
                    # Prepare multimodal content
                    multimodal_content = self.prepare_multimodal_content(text_content, images)
                    
                    # Replace the last message with multimodal version
                    messages[-1] = {
                        'role': 'user',
                        'content': multimodal_content
                    }
            
            api_params = self._build_api_params(model, messages, llm_params)
            
            if tools:
                api_params["tools"] = tools
                api_params["tool_choice"] = "auto"
            
            async def make_request():
                return await client.chat.completions.create(**api_params)
            
            response = await self.retry_with_backoff(
                make_request,
                max_retries=2,
                base_delay=2,
                circuit_breaker_key="openai_api"
            )
            
            if tools and response.choices[0].message.tool_calls:
                tool_results = await self._handle_tool_calls_openai_format(
                    response, messages, tools, tool_context, client, api_params
                )
                
                if tool_results is None:
                    func.log.warning("Tool execution failed or LLM returned empty response")

                if tool_results:
                    return tool_results
            
            ai_response = response.choices[0].message.content or ""
            ai_response = self._handle_reasoning_tokens(response.choices[0].message, ai_response, llm_params)
            
            if not ai_response or ai_response.isspace():
                func.log.warning("Received empty response from API")
                return self.create_error_response(
                    Exception("The API returned an empty response"),
                    error_type="EmptyResponse"
                )
            
            return ai_response
            
        except (APIConnectionError, APITimeoutError) as e:
            func.log.error(f"Connection error: {e}")
            return self.create_error_response(e)
            
        except RateLimitError as e:
            func.log.error(f"Rate limit error: {e}")
            return self.create_error_response(e)
            
        except APIError as e:
            func.log.error(f"API error: {e}")
            return self.create_error_response(e)
            
        except Exception as e:
            func.log.error(f"Error generating AI response: {str(e)}")
            return self.create_error_response(e)
            
        finally:
            try:
                await client.close()
            except Exception as e:
                func.log.error(f"Error closing client session: {str(e)}")
    
    async def generate_response_structured(
        self,
        messages: List[Dict[str, str]],
        json_schema: Dict[str, Any],
        session: Dict[str, Any],
        server_id: str,
        schema_name: str = "response",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate a structured response following a JSON Schema using OpenAI's Structured Outputs."""
        model = self.resolve_model(session, server_id, "gpt-3.5-turbo")
        client = self.create_client(session, server_id)
        
        try:
            api_params = {
                "model": model,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": json_schema
                    }
                },
                "temperature": kwargs.get("temperature", 0.3),
                "max_tokens": kwargs.get("max_tokens", 300),
            }
            
            async def make_request():
                return await client.chat.completions.create(**api_params)
            
            response = await self.retry_with_backoff(
                make_request,
                max_retries=2,
                base_delay=2,
                circuit_breaker_key="openai_api_structured"
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from API")
            
            import json
            result = json.loads(content)
            
            return result
            
        except Exception as e:
            func.log.error(f"Error in generate_response_structured: {e}")
            raise
            
        finally:
            try:
                await client.close()
            except Exception as e:
                func.log.error(f"Error closing client session: {str(e)}")
    
    def _build_api_params(self, model: str, messages: List[Dict], llm_params: Dict) -> Dict[str, Any]:
        """Build API request parameters for OpenAI."""
        params = {
            "model": model,
            "messages": messages,
            "max_tokens": llm_params.get("max_tokens", 1000),
            "temperature": llm_params.get("temperature", 0.7),
            "top_p": llm_params.get("top_p", 1.0),
            "frequency_penalty": llm_params.get("frequency_penalty", 0.0),
            "presence_penalty": llm_params.get("presence_penalty", 0.0)
        }
        
        # OpenAI: Models o1/o3 do reasoning automatically
        # think_switch does not affect Chat Completions API behavior
        # For reasoning control, would need to use Responses API (future)
        
        # Merge custom_extra_body if provided
        custom_extra = llm_params.get("custom_extra_body")
        if custom_extra:
            if "extra_body" in params:
                params["extra_body"].update(custom_extra)
            else:
                params["extra_body"] = custom_extra.copy()
        
        return params
    
    def _handle_reasoning_tokens(self, message, response: str, llm_params: Dict) -> str:
        """Handle reasoning tokens in the API response."""
        reasoning_content = getattr(message, 'reasoning', None)
        hide_tags = llm_params.get("hide_thinking_tags", True)
        
        if reasoning_content and not hide_tags:
            return f"<thinking>\n{reasoning_content}\n</thinking>\n\n{response}"
        
        return response
    
    async def get_bot_info(
        self,
        session: Dict[str, Any],
        server_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieves the bot's information (model info and configuration)."""
        model = self.resolve_model(session, server_id, default_model="gpt-3.5-turbo")
        if not model:
            func.log.error("No model provided to get_bot_info")
            return None

        try:
            client = self.create_client(session, server_id)
            
            try:
                models = await client.models.list()
                
                for m in models.data:
                    if m.id == model:
                        return {
                            "name": m.id,
                            "avatar_url": None,
                            "title": m.id,
                            "description": f"OpenAI Model: {m.id}",
                            "visibility": "public" if "gpt" in m.id.lower() else "private",
                            "num_interactions": None,
                            "author_username": m.owned_by
                        }
                
                func.log.warning(f"Model {model} not found in API models list")
                return {
                    "name": model,
                    "avatar_url": None,
                    "title": model,
                    "description": f"Model: {model}",
                    "visibility": "unknown",
                    "num_interactions": None,
                    "author_username": "unknown"
                }
            finally:
                await client.close()
                
        except Exception as e:
            func.log.critical("Unable to get model information from API: %s", e)
            return {
                "name": model,
                "avatar_url": None,
                "title": model,
                "description": f"Model: {model}",
                "visibility": "unknown",
                "num_interactions": None,
                "author_username": "unknown"
            }
    
    async def validate_token(self, token: str, base_url: Optional[str] = None) -> bool:
        """Validates an OpenAI API token by making a simple API call with 1-hour caching."""
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
            
            client = AsyncOpenAI(**client_kwargs)
            try:
                await client.models.list()
                BaseAIClient._token_validation_cache[cache_key] = (True, time.time())
                return True
            finally:
                await client.close()
        except Exception as e:
            func.log.error(f"OpenAI token validation failed: {e}")
            BaseAIClient._token_validation_cache[cache_key] = (False, time.time() - BaseAIClient._token_cache_ttl + 300)
            return False

_openai_client = OpenAIClient()


def create_client(session: Dict[str, Any], server_id: Optional[str] = None) -> AsyncOpenAI:
    """Create an OpenAI client instance."""
    return _openai_client.create_client(session, server_id)


def get_model(session: Dict[str, Any], server_id: Optional[str] = None) -> str:
    """Get model name from session/connection."""
    return _openai_client.resolve_model(session, server_id, default_model="gpt-3.5-turbo")


def get_llm_params(session: Dict[str, Any], server_id: Optional[str] = None) -> Dict[str, Any]:
    """Get LLM parameters from session/connection."""
    return _openai_client.get_llm_params(session, server_id)


def count_tokens(text: str, model: str) -> int:
    """Count tokens in text using tiktoken."""
    return _openai_client.count_tokens(text, model)


async def validate_token(token: str, base_url: Optional[str] = None) -> bool:
    """Validate an API token."""
    return await _openai_client.validate_token(token, base_url)


async def get_bot_info(
    token: Optional[str] = None,
    model: Optional[str] = None,
    session: Optional[Dict[str, Any]] = None,
    server_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get bot/model information."""
    if session is None:
        session = {}
        if token:
            session["alt_token"] = token
        if model:
            session["model"] = model
    
    return await _openai_client.get_bot_info(session, server_id)

async def load_conversation_history() -> None:
    """Load conversation history. Delegates to chat service."""
    from AI.chat_service import get_service
    await get_service().load_conversation_history()


async def save_conversation_history() -> bool:
    """Save conversation history. Delegates to chat service."""
    from AI.chat_service import get_service
    return await get_service().save_conversation_history()


def get_ai_history(server_id: str, channel_id: str, ai_name: str) -> list:
    """Get conversation history. Delegates to chat service."""
    from AI.chat_service import get_service
    return get_service().get_ai_history(server_id, channel_id, ai_name)


def set_ai_history(server_id: str, channel_id: str, ai_name: str, messages: list) -> None:
    """Set conversation history. Delegates to chat service."""
    from AI.chat_service import get_service
    get_service().set_ai_history(server_id, channel_id, ai_name, messages)


def append_to_history(server_id: str, channel_id: str, ai_name: str, role: str, content: str) -> None:
    """Append to conversation history. Delegates to chat service."""
    from AI.chat_service import get_service
    get_service().append_to_history(server_id, channel_id, ai_name, role, content)


def clear_ai_history(server_id: str, channel_id: str, ai_name: str) -> bool:
    """Clear conversation history. Delegates to chat service."""
    from AI.chat_service import get_service
    return get_service().clear_ai_history(server_id, channel_id, ai_name)


async def new_chat_id(
    create_new: bool,
    session: Dict[str, Any],
    server_id: str,
    channel_id_str: str
) -> tuple[Optional[str], Optional[Any]]:
    """Create new chat session. Delegates to chat service."""
    from AI.chat_service import get_service
    return await get_service().new_chat_id(create_new, session, server_id, channel_id_str)


async def initialize_session_messages(
    session: Dict[str, Any],
    server_id: str,
    channel_id: str
) -> Optional[str]:
    """Initialize session messages. Delegates to chat service."""
    from AI.chat_service import get_service
    return await get_service().initialize_session_messages(session, server_id, channel_id)


async def openai_response(
    messages: Dict[str, Any],
    message,
    server_id: str,
    channel_id: str,
    ai_name: str,
    chat_id: Optional[str] = None,
    session: Optional[Dict[str, Any]] = None
) -> str:
    """Generate AI response. Delegates to chat service."""
    from AI.chat_service import get_service
    return await get_service().generate_response(
        messages, message, server_id, channel_id, ai_name, chat_id, session
    )


async def process_response_queue():
    """Process response queue. Delegates to response queue."""
    from AI.response_queue import get_queue
    await get_queue().process_queue()

from AI.provider_registry import register_provider

register_provider(
    name="openai",
    client_class=OpenAIClient,
    display_name="OpenAI",
    color="green",
    icon="🟢",
    default_model="gpt-3.5-turbo",
    supports_thinking=True,
    description="OpenAI's GPT models with advanced reasoning capabilities"
)
