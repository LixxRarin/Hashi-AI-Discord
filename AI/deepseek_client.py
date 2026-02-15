from typing import Dict, Any, List, Optional

from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError

import utils.func as func
from AI.base_client import BaseAIClient

class DeepSeekClient(BaseAIClient):
    """DeepSeek API client for chat completions and structured outputs (OpenAI-compatible)."""
    
    provider_name = "DeepSeek"
    DEFAULT_BASE_URL = "https://api.deepseek.com"
    
    def supports_structured_outputs(self) -> bool:
        """DeepSeek supports Structured Outputs (OpenAI-compatible)."""
        return True
    
    def supports_vision(self) -> bool:
        """DeepSeek does not currently support vision/image analysis."""
        return False
    
    def create_client(self, session: Dict[str, Any], server_id: Optional[str] = None) -> AsyncOpenAI:
        """Creates an AsyncOpenAI client configured for DeepSeek."""
        api_key = self.resolve_api_key(session, server_id)
        base_url = self.resolve_base_url(session, server_id) or self.DEFAULT_BASE_URL
        
        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=60.0
        )
    
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
        **kwargs
    ) -> str:
        """Generate a response from DeepSeek API with optional tool calling support."""
        model = self.resolve_model(session, server_id, "deepseek-chat")
        llm_params = self.get_llm_params(session, server_id)
        client = self.create_client(session, server_id)
        
        try:
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
                circuit_breaker_key="deepseek_api"
            )
            
            if tools and response.choices[0].message.tool_calls:
                tool_results = await self._handle_tool_calls_openai_format(
                    response, messages, tools, tool_context, client, api_params
                )
                
                if tool_results is None:
                    func.log.warning("Tool execution failed or LLM returned empty response")
                
                if tool_results:
                    return tool_results
            
            api_message = response.choices[0].message
            ai_response = api_message.content or ""
            ai_response = self._handle_reasoning_tokens(api_message, ai_response, llm_params)
            
            if not ai_response or ai_response.isspace():
                func.log.warning("Received empty response from DeepSeek API")
                return self.create_error_response(
                    Exception("The API returned an empty response"),
                    error_type="EmptyResponse"
                )
            
            return ai_response
            
        except (APIConnectionError, APITimeoutError) as e:
            func.log.error(f"DeepSeek connection error: {e}")
            return self.create_error_response(e)
            
        except RateLimitError as e:
            func.log.error(f"DeepSeek rate limit error: {e}")
            return self.create_error_response(e)
            
        except APIError as e:
            func.log.error(f"DeepSeek API error: {e}")
            return self.create_error_response(e)
            
        except Exception as e:
            func.log.error(f"Error generating DeepSeek response: {str(e)}")
            return self.create_error_response(e)
            
        finally:
            try:
                await client.close()
            except Exception as e:
                func.log.error(f"Error closing DeepSeek client session: {str(e)}")
    
    async def generate_response_structured(
        self,
        messages: List[Dict[str, str]],
        json_schema: Dict[str, Any],
        session: Dict[str, Any],
        server_id: str,
        schema_name: str = "response",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate a structured response following a JSON Schema using DeepSeek's OpenAI-compatible API."""
        model = self.resolve_model(session, server_id, "deepseek-chat")
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
                circuit_breaker_key="deepseek_api_structured"
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from DeepSeek API")
            
            import json
            result = json.loads(content)
            
            return result
            
        except Exception as e:
            func.log.error(f"Error in DeepSeek generate_response_structured: {e}")
            raise
            
        finally:
            try:
                await client.close()
            except Exception as e:
                func.log.error(f"Error closing DeepSeek client session: {str(e)}")
    
    def _build_api_params(self, model: str, messages: List[Dict], llm_params: Dict) -> Dict[str, Any]:
        """Build API request parameters including thinking/reasoning configuration."""
        params = {
            "model": model,
            "messages": messages,
            "max_tokens": llm_params.get("max_tokens", 1000),
            "temperature": llm_params.get("temperature", 0.7),
            "top_p": llm_params.get("top_p", 1.0),
            "frequency_penalty": llm_params.get("frequency_penalty", 0.0),
            "presence_penalty": llm_params.get("presence_penalty", 0.0)
        }
        
        think_switch = llm_params.get("think_switch", False)
        
        if model == "deepseek-reasoner":
            think_switch = True
        
        if think_switch:
            think_depth = llm_params.get("think_depth", 3)
            think_depth = max(1, min(5, think_depth))
            
            effort_levels = ["minimal", "low", "medium", "high", "xhigh"]
            reasoning_effort = effort_levels[think_depth - 1]
            
            hide_tags = llm_params.get("hide_thinking_tags", True)
            params["extra_body"] = {
                "reasoning": {
                    "effort": reasoning_effort,
                    "exclude": hide_tags
                }
            }
        else:
            params["extra_body"] = {"reasoning": {"effort": "none"}}
        
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
        model = self.resolve_model(session, server_id, default_model="deepseek-chat")
        if not model:
            func.log.error("No model provided to get_bot_info")
            return None

        model_info = {
            "deepseek-chat": {
                "name": "deepseek-chat",
                "avatar_url": None,
                "title": "DeepSeek Chat",
                "description": "DeepSeek's standard chat model with advanced conversation capabilities",
                "visibility": "public",
                "num_interactions": None,
                "author_username": "DeepSeek"
            },
            "deepseek-reasoner": {
                "name": "deepseek-reasoner",
                "avatar_url": None,
                "title": "DeepSeek Reasoner",
                "description": "Model with advanced reasoning and complex problem-solving capabilities",
                "visibility": "public",
                "num_interactions": None,
                "author_username": "DeepSeek"
            }
        }
        
        if model in model_info:
            return model_info[model]
        else:
            func.log.warning(f"Unknown DeepSeek model: {model}")
            return {
                "name": model,
                "avatar_url": None,
                "title": model,
                "description": f"DeepSeek Model: {model}",
                "visibility": "unknown",
                "num_interactions": None,
                "author_username": "DeepSeek"
            }
    
    async def validate_token(self, token: str, base_url: Optional[str] = None) -> bool:
        """Validates a DeepSeek API token by making a simple API call with 1-hour caching."""
        import hashlib
        import time
        
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        cache_key = (self.provider_name, token_hash, base_url or self.DEFAULT_BASE_URL)
        
        if cache_key in BaseAIClient._token_validation_cache:
            is_valid, timestamp = BaseAIClient._token_validation_cache[cache_key]
            if time.time() - timestamp < BaseAIClient._token_cache_ttl:
                return is_valid
        
        try:
            client = AsyncOpenAI(
                api_key=token,
                base_url=base_url or self.DEFAULT_BASE_URL,
                timeout=10.0
            )
            try:
                await client.models.list()
                BaseAIClient._token_validation_cache[cache_key] = (True, time.time())
                return True
            finally:
                await client.close()
        except Exception as e:
            func.log.error(f"DeepSeek token validation failed: {e}")
            BaseAIClient._token_validation_cache[cache_key] = (False, time.time() - BaseAIClient._token_cache_ttl + 300)
            return False

_deepseek_client = DeepSeekClient()


def create_client(session: Dict[str, Any], server_id: Optional[str] = None) -> AsyncOpenAI:
    """Create a DeepSeek client instance."""
    return _deepseek_client.create_client(session, server_id)


def get_model(session: Dict[str, Any], server_id: Optional[str] = None) -> str:
    """Get model name from session/connection."""
    return _deepseek_client.resolve_model(session, server_id, default_model="deepseek-chat")


def get_llm_params(session: Dict[str, Any], server_id: Optional[str] = None) -> Dict[str, Any]:
    """Get LLM parameters from session/connection."""
    return _deepseek_client.get_llm_params(session, server_id)


def count_tokens(text: str, model: str) -> int:
    """Count tokens in text using tiktoken."""
    return _deepseek_client.count_tokens(text, model)


async def validate_token(token: str, base_url: Optional[str] = None) -> bool:
    """Validate an API token."""
    return await _deepseek_client.validate_token(token, base_url)


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
    
    return await _deepseek_client.get_bot_info(session, server_id)

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


async def deepseek_response(
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
    name="deepseek",
    client_class=DeepSeekClient,
    display_name="DeepSeek",
    color="blue",
    icon="🐋",
    default_model="deepseek-chat",
    supports_thinking=True,
    description="DeepSeek's chat and reasoning models with advanced capabilities"
)
