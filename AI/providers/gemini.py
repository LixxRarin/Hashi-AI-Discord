from typing import Dict, Any, List, Optional
import json

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

import utils.func as func
from AI.core.base_client import BaseAIClient


class GeminiClient(BaseAIClient):
    """Google Gemini API client for chat completions and structured outputs."""

    provider_name = "Gemini"
    DEFAULT_BASE_URL = None  # Gemini uses Google's default endpoint

    def supports_structured_outputs(self) -> bool:
        """Gemini supports JSON mode for structured outputs."""
        return True

    def supports_vision(self) -> bool:
        """Gemini supports vision/image analysis."""
        return True

    def create_client(self, session: Dict[str, Any], server_id: Optional[str] = None):
        """Creates a Gemini client configured with API key."""
        api_key = self.resolve_api_key(session, server_id)
        genai.configure(api_key=api_key)
        return genai

    def count_tokens(self, text: str, model: str) -> int:
        """Count the number of tokens in a text string using tiktoken."""
        return self.count_tokens_with_tiktoken(text, model)

    def prepare_multimodal_content(
        self,
        text: str,
        images: List[Dict[str, Any]]
    ) -> List[Any]:
        """
        Prepare multimodal content in Gemini format.

        Gemini format uses a list with text and image parts.

        Args:
            text: Text content
            images: List of processed image dicts with base64, format, detail

        Returns:
            List of content parts for Gemini API
        """
        import base64

        content = []

        # Add text first
        if text:
            content.append(text)

        # Add images as bytes
        for image in images:
            base64_data = image.get('base64')
            # Decode base64 to bytes
            image_bytes = base64.b64decode(base64_data)
            content.append(image_bytes)

        return content

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
        """Generate a response from Gemini API with optional tool calling and vision support."""
        model_name = self.resolve_model(session, server_id, "gemini-1.5-flash")
        llm_params = self.get_llm_params(session, server_id)
        self.create_client(session, server_id)

        try:
            # Configure safety settings (permissive for chat bot use)
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            # Create generation config
            generation_config = {
                "temperature": llm_params.get("temperature", 0.7),
                "top_p": llm_params.get("top_p", 1.0),
                "max_output_tokens": llm_params.get("max_tokens", 1000),
            }

            # Convert messages to Gemini format
            gemini_messages = self._convert_messages_to_gemini(messages, images)

            # Create model
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config=generation_config,
                safety_settings=safety_settings
            )

            # Handle tool calling if tools are provided
            if tools:
                gemini_tools = self._convert_tools_to_gemini(tools)
                model = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config=generation_config,
                    safety_settings=safety_settings,
                    tools=gemini_tools
                )

            # Generate response (wrap in asyncio.to_thread to avoid blocking)
            import asyncio
            if len(gemini_messages) == 1 and isinstance(gemini_messages[0], list):
                # Single message with multimodal content
                response = await asyncio.to_thread(model.generate_content, gemini_messages[0])
            else:
                # Chat conversation
                chat = model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
                response = await asyncio.to_thread(chat.send_message, gemini_messages[-1])

            # Handle tool calls
            if tools and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        tool_results = await self._handle_tool_calls_gemini(
                            response, messages, tools, tool_context, model, gemini_messages
                        )
                        if tool_results:
                            return tool_results

            # Extract text response
            ai_response = response.text if response.text else ""

            if not ai_response or ai_response.isspace():
                func.log.warning("Received empty response from Gemini API")
                return self.create_error_response(
                    Exception("The API returned an empty response"),
                    error_type="EmptyResponse"
                )

            return ai_response

        except Exception as e:
            func.log.error(f"Error generating Gemini response: {str(e)}")
            return self.create_error_response(e)

    async def generate_response_structured(
        self,
        messages: List[Dict[str, str]],
        json_schema: Dict[str, Any],
        session: Dict[str, Any],
        server_id: str,
        schema_name: str = "response",
        **kwargs
    ) -> Dict[str, Any]:
        """Generate a structured response following a JSON Schema using Gemini's JSON mode."""
        model_name = self.resolve_model(session, server_id, "gemini-1.5-flash")
        self.create_client(session, server_id)

        try:
            # Configure for JSON output
            generation_config = {
                "temperature": kwargs.get("temperature", 0.3),
                "max_output_tokens": kwargs.get("max_tokens", 300),
                "response_mime_type": "application/json",
            }

            # Add schema instruction to the last message
            schema_instruction = f"\n\nRespond with valid JSON matching this schema: {json.dumps(json_schema)}"
            messages_copy = messages.copy()
            if messages_copy:
                messages_copy[-1]["content"] += schema_instruction

            # Create model
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config=generation_config
            )

            # Convert messages
            gemini_messages = self._convert_messages_to_gemini(messages_copy)

            # Generate response (wrap in asyncio.to_thread to avoid blocking)
            import asyncio
            if len(gemini_messages) == 1:
                response = await asyncio.to_thread(model.generate_content, gemini_messages[0])
            else:
                chat = model.start_chat(history=gemini_messages[:-1])
                response = await asyncio.to_thread(chat.send_message, gemini_messages[-1])

            content = response.text
            if not content:
                raise ValueError("Empty response from Gemini API")

            result = json.loads(content)
            return result

        except Exception as e:
            func.log.error(f"Error in Gemini generate_response_structured: {e}")
            raise

    def _convert_messages_to_gemini(
        self,
        messages: List[Dict[str, str]],
        images: Optional[List[Dict[str, Any]]] = None
    ) -> List[Any]:
        """Convert OpenAI-style messages to Gemini format."""
        gemini_messages = []

        for i, msg in enumerate(messages):
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Map roles
            if role == "system":
                # Gemini doesn't have system role, prepend to first user message
                continue
            elif role == "assistant":
                gemini_role = "model"
            else:
                gemini_role = "user"

            # Handle multimodal content for last message
            if images and i == len(messages) - 1 and role == "user":
                multimodal_content = self.prepare_multimodal_content(content, images)
                gemini_messages.append(multimodal_content)
            else:
                gemini_messages.append({
                    "role": gemini_role,
                    "parts": [content]
                })

        # Prepend system message to first user message if exists
        system_msg = next((m for m in messages if m.get("role") == "system"), None)
        if system_msg and gemini_messages:
            first_msg = gemini_messages[0]
            if isinstance(first_msg, dict):
                first_msg["parts"][0] = f"{system_msg['content']}\n\n{first_msg['parts'][0]}"
            elif isinstance(first_msg, list) and isinstance(first_msg[0], str):
                first_msg[0] = f"{system_msg['content']}\n\n{first_msg[0]}"

        return gemini_messages

    def _convert_tools_to_gemini(self, tools: List[Dict]) -> List[Any]:
        """Convert OpenAI-style tools to Gemini function declarations."""
        from google.generativeai.types import FunctionDeclaration, Tool

        function_declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                func_def = tool.get("function", {})
                function_declarations.append(
                    FunctionDeclaration(
                        name=func_def.get("name"),
                        description=func_def.get("description"),
                        parameters=func_def.get("parameters", {})
                    )
                )

        return [Tool(function_declarations=function_declarations)] if function_declarations else []

    async def _handle_tool_calls_gemini(
        self,
        response,
        messages: List[Dict],
        tools: List[Dict],
        tool_context: Optional[Dict[str, Any]],
        model,
        gemini_messages: List[Any]
    ) -> Optional[str]:
        """Handle tool calls in Gemini format."""
        from AI.tool_executor import ToolExecutor

        tool_executor = ToolExecutor()
        function_responses = []

        for part in response.candidates[0].content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                func_call = part.function_call
                func_name = func_call.name
                func_args = dict(func_call.args)

                # Execute tool
                result = await tool_executor.execute_tool(
                    func_name,
                    func_args,
                    tool_context or {}
                )

                function_responses.append({
                    "name": func_name,
                    "response": result
                })

        if function_responses:
            # Send function responses back to model (wrap in asyncio.to_thread to avoid blocking)
            from google.generativeai.types import content_types
            import asyncio

            response_parts = [
                content_types.to_part({
                    "function_response": {
                        "name": fr["name"],
                        "response": fr["response"]
                    }
                })
                for fr in function_responses
            ]

            chat = model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
            final_response = await asyncio.to_thread(chat.send_message, response_parts)

            return final_response.text if final_response.text else None

        return None

    async def get_bot_info(
        self,
        session: Dict[str, Any],
        server_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieves the bot's information (model info and configuration)."""
        model = self.resolve_model(session, server_id, default_model="gemini-1.5-flash")
        if not model:
            func.log.error("No model provided to get_bot_info")
            return None

        model_info = {
            "gemini-1.5-flash": {
                "name": "gemini-1.5-flash",
                "avatar_url": None,
                "title": "Gemini 1.5 Flash",
                "description": "Fast and efficient model for everyday tasks",
                "visibility": "public",
                "num_interactions": None,
                "author_username": "Google"
            },
            "gemini-1.5-pro": {
                "name": "gemini-1.5-pro",
                "avatar_url": None,
                "title": "Gemini 1.5 Pro",
                "description": "Advanced model with superior reasoning and multimodal capabilities",
                "visibility": "public",
                "num_interactions": None,
                "author_username": "Google"
            },
            "gemini-2.0-flash-exp": {
                "name": "gemini-2.0-flash-exp",
                "avatar_url": None,
                "title": "Gemini 2.0 Flash (Experimental)",
                "description": "Next-generation experimental model with enhanced capabilities",
                "visibility": "public",
                "num_interactions": None,
                "author_username": "Google"
            }
        }

        if model in model_info:
            return model_info[model]
        else:
            func.log.warning(f"Unknown Gemini model: {model}")
            return {
                "name": model,
                "avatar_url": None,
                "title": model,
                "description": f"Google Gemini Model: {model}",
                "visibility": "unknown",
                "num_interactions": None,
                "author_username": "Google"
            }

    async def validate_token(self, token: str, base_url: Optional[str] = None) -> bool:
        """Validates a Gemini API token by making a simple API call with 1-hour caching."""
        import hashlib
        import time
        import asyncio

        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        cache_key = (self.provider_name, token_hash, base_url or "")

        if cache_key in BaseAIClient._token_validation_cache:
            is_valid, timestamp = BaseAIClient._token_validation_cache[cache_key]
            if time.time() - timestamp < BaseAIClient._token_cache_ttl:
                return is_valid

        try:
            genai.configure(api_key=token)
            # Try to list models as a validation check (wrap in asyncio.to_thread to avoid blocking)
            await asyncio.to_thread(lambda: list(genai.list_models()))
            BaseAIClient._token_validation_cache[cache_key] = (True, time.time())
            return True
        except Exception as e:
            func.log.error(f"Gemini token validation failed: {e}")
            BaseAIClient._token_validation_cache[cache_key] = (False, time.time() - BaseAIClient._token_cache_ttl + 300)
            return False


def create_client(session: Dict[str, Any], server_id: Optional[str] = None):
    """Create a Gemini client instance using registry."""
    from AI.core.registry import get_client
    client = get_client("gemini", {"session": session, "server_id": server_id})
    return client.create_client(session, server_id)


def get_model(session: Dict[str, Any], server_id: Optional[str] = None) -> str:
    """Get model name from session/connection."""
    from AI.core.registry import get_client
    client = get_client("gemini", {"session": session, "server_id": server_id})
    return client.resolve_model(session, server_id, default_model="gemini-1.5-flash")


def get_llm_params(session: Dict[str, Any], server_id: Optional[str] = None) -> Dict[str, Any]:
    """Get LLM parameters from session/connection."""
    from AI.core.registry import get_client
    client = get_client("gemini", {"session": session, "server_id": server_id})
    return client.get_llm_params(session, server_id)


def count_tokens(text: str, model: str) -> int:
    """Count tokens in text using Gemini's token counter."""
    from AI.core.registry import get_client
    client = get_client("gemini", {})
    return client.count_tokens(text, model)


async def validate_token(token: str, base_url: Optional[str] = None) -> bool:
    """Validate an API token."""
    from AI.core.registry import get_client
    client = get_client("gemini", {})
    return await client.validate_token(token, base_url)


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

    from AI.core.registry import get_client
    client = get_client("gemini", {"session": session, "server_id": server_id})
    return await client.get_bot_info(session, server_id)


async def load_conversation_history() -> None:
    """Load conversation history. Delegates to chat service."""
    from AI.services.chat_service import get_service
    await get_service().load_conversation_history()


async def save_conversation_history() -> bool:
    """Save conversation history. Delegates to chat service."""
    from AI.services.chat_service import get_service
    return await get_service().save_conversation_history()


async def get_ai_history(server_id: str, channel_id: str, ai_name: str) -> list:
    """Get conversation history. Delegates to chat service."""
    from AI.services.chat_service import get_service
    return await get_service().get_ai_history(server_id, channel_id, ai_name)


def set_ai_history(server_id: str, channel_id: str, ai_name: str, messages: list) -> None:
    """Set conversation history. Delegates to chat service."""
    from AI.services.chat_service import get_service
    get_service().set_ai_history(server_id, channel_id, ai_name, messages)


def append_to_history(server_id: str, channel_id: str, ai_name: str, role: str, content: str) -> None:
    """Append to conversation history. Delegates to chat service."""
    from AI.services.chat_service import get_service
    get_service().append_to_history(server_id, channel_id, ai_name, role, content)


def clear_ai_history(server_id: str, channel_id: str, ai_name: str) -> bool:
    """Clear conversation history. Delegates to chat service."""
    from AI.services.chat_service import get_service
    return get_service().clear_ai_history(server_id, channel_id, ai_name)


async def new_chat_id(
    create_new: bool,
    session: Dict[str, Any],
    server_id: str,
    channel_id_str: str
) -> tuple[Optional[str], Optional[Any]]:
    """Create new chat session. Delegates to chat service."""
    from AI.services.chat_service import get_service
    return await get_service().new_chat_id(create_new, session, server_id, channel_id_str)


async def initialize_session_messages(
    session: Dict[str, Any],
    server_id: str,
    channel_id: str
) -> Optional[str]:
    """Initialize session messages. Delegates to chat service."""
    from AI.services.chat_service import get_service
    return await get_service().initialize_session_messages(session, server_id, channel_id)


async def gemini_response(
    messages: Dict[str, Any],
    message,
    server_id: str,
    channel_id: str,
    ai_name: str,
    chat_id: Optional[str] = None,
    session: Optional[Dict[str, Any]] = None
) -> str:
    """Generate AI response. Delegates to chat service."""
    from AI.services.chat_service import get_service
    return await get_service().generate_response(
        messages, message, server_id, channel_id, ai_name, chat_id, session
    )


async def process_response_queue():
    """Process response queue. Delegates to response queue."""
    from AI.response_queue import get_queue
    await get_queue().process_queue()


from AI.core.registry import register_provider

register_provider(
    name="gemini",
    client_class=GeminiClient,
    display_name="Google Gemini",
    color="purple",
    icon="✨",
    default_model="gemini-2.5-flash",
    supports_thinking=True,
    description="Google's advanced multimodal AI with vision and reasoning capabilities"
)