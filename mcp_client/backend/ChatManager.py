from MCP_Client import UniversalMCPClient, ServerConfig


"""
Chat Manager for LLM conversations with MCP tool integration
Supports OpenRouter API via OpenAI SDK
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from openai import AsyncOpenAI
import os 
from mcp.types import Tool as MCPTool
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ToolCall:
    """Represents a tool call requested by the LLM in our case OpenAI"""
    id: str
    server_name: str
    tool_name: str
    arguments: Dict[str, Any]
    
    @classmethod
    def from_openai_tool_call(
        cls,
        tool_call: Any,
        tool_definitions: Dict[str, 'ToolDefinition']
    ) -> 'ToolCall':
        """Parse from OpenAI tool call format"""
        function_name = tool_call.function.name
        
        # Parse server__tool format
        if "__" in function_name:
            server_name, tool_name = function_name.split("__", 1)
        else:
            # Fallback: try to find in tool_definitions
            tool_def = tool_definitions.get(function_name)
            if tool_def:
                server_name = tool_def.server_name
                tool_name = tool_def.tool_name
            else:
                raise ValueError(f"Cannot parse tool name: {function_name}")
        
        # Parse arguments
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            arguments = {}
        
        return cls(
            id=tool_call.id,
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolCall':
        """Reconstruct ToolCall from dict (e.g., from database)"""
        return cls(
            id=data.get('id', ''),
            server_name=data.get('server_name', ''),
            tool_name=data.get('tool_name', ''),
            arguments=data.get('arguments', {})
        )
    
    async def execute(self, mcp_client: UniversalMCPClient) -> 'ToolResult':
        """Execute this tool call via MCP client"""
        try:
            result = await mcp_client.call_tool(
                self.server_name,
                self.tool_name,
                self.arguments
            )
            
            return ToolResult(
                tool_call_id=self.id,
                server_name=self.server_name,
                tool_name=self.tool_name,
                result=result,
                success=True,
                error=None
            )
        except Exception as e:
            logger.error(f"Tool execution failed: {self.server_name}.{self.tool_name}: {e}")
            return ToolResult(
                tool_call_id=self.id,
                server_name=self.server_name,
                tool_name=self.tool_name,
                result=None,
                success=False,
                error=str(e)
            )


@dataclass
class ToolResult:
    """Represents the result of a tool execution"""
    tool_call_id: str
    server_name: str
    tool_name: str
    result: Any
    success: bool
    error: Optional[str] = None
    
    def _serialize_result(self, result: Any) -> str:
        """Serialize MCP result to JSON string
        
        Handles various MCP result types:
        - CallToolResult objects
        - Plain dicts/lists
        - Strings
        - Complex objects
        """
        try:
            if isinstance(result, str):
                return result
            
            if hasattr(result, 'content'):
                content_items = []
                for item in result.content:
                    if hasattr(item, 'type'):
                        # TextContent
                        if item.type == 'text':
                            content_items.append({
                                'type': 'text',
                                'text': item.text
                            })
                        # ImageContent
                        elif item.type == 'image':
                            content_items.append({
                                'type': 'image',
                                'data': item.data,
                                'mimeType': item.mimeType
                            })
                        # ResourceContent
                        elif item.type == 'resource':
                            content_items.append({
                                'type': 'resource',
                                'resource': {
                                    'uri': item.resource.uri,
                                    'mimeType': getattr(item.resource, 'mimeType', None),
                                    'text': getattr(item.resource, 'text', None)
                                }
                            })
                    else:
                        # Fallback pour types inconnus
                        content_items.append({'data': str(item)})
                
                # Construire le résultat final
                result_dict = {
                    'content': content_items,
                    'isError': getattr(result, 'isError', False)
                }
                
                return json.dumps(result_dict, ensure_ascii=False)
            
            if isinstance(result, (dict, list, int, float, bool, type(None))):
                return json.dumps(result, ensure_ascii=False)
            
            if hasattr(result, '__dict__'):
                return json.dumps(result.__dict__, ensure_ascii=False, default=str)
            
            return json.dumps({'result': str(result)}, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Failed to serialize result: {e}")
            # Retourner une erreur sérialisable
            return json.dumps({
                'error': 'Serialization failed',
                'message': str(e),
                'result_type': type(result).__name__
            }, ensure_ascii=False)
    
    def to_openai_tool_message(self) -> Dict[str, Any]:
        """Convert to OpenAI tool message format"""
        if self.success:
            content = self._serialize_result(self.result)
        else:
            content = json.dumps({
                "error": self.error,
                "message": f"Tool {self.tool_name} failed"
            }, ensure_ascii=False)
        
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "name": f"{self.server_name}__{self.tool_name}",
            "content": content
        }

@dataclass
class ToolDefinition:
    """Represents a tool definition in OpenAI format"""
    server_name: str
    tool_name: str
    description: str
    parameters: Dict[str, Any]
    
    @classmethod
    def from_mcp_tool(cls, server_name: str, mcp_tool: MCPTool) -> 'ToolDefinition':
        """Convert MCP tool to OpenAI tool definition"""
        # MCP tools already use JSON Schema format
        parameters = mcp_tool.inputSchema if hasattr(mcp_tool, 'inputSchema') else {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        return cls(
            server_name=server_name,
            tool_name=mcp_tool.name,
            description=mcp_tool.description or f"Tool {mcp_tool.name} from {server_name}",
            parameters=parameters
        )
    
    def to_openai_function(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format"""
        return {
            "type": "function",
            "function": {
                "name": f"{self.server_name}__{self.tool_name}",
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    @property
    def full_name(self) -> str:
        """Get full tool name (server__tool)"""
        return f"{self.server_name}__{self.tool_name}"


@dataclass
class Message:
    """Represents a message in the conversation"""
    role: str  # "user" | "assistant" | "system" | "tool"
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI message format"""
        message = {"role": self.role}
        
        if self.content is not None:
            message["content"] = self.content
        
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": f"{tc.server_name}__{tc.tool_name}",
                        "arguments": json.dumps(tc.arguments)
                    }
                }
                for tc in self.tool_calls
            ]
        
        if self.tool_call_id:
            message["tool_call_id"] = self.tool_call_id
        
        if self.name:
            message["name"] = self.name
        
        return message
    
    @classmethod
    def from_openai_response(
        cls,
        response_message: Any,
        tool_definitions: Dict[str, ToolDefinition]
    ) -> 'Message':
        """Create message from OpenAI response"""
        tool_calls = None
        
        if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
            tool_calls = [
                ToolCall.from_openai_tool_call(tc, tool_definitions)
                for tc in response_message.tool_calls
            ]
        
        return cls(
            role=response_message.role,
            content=response_message.content,
            tool_calls=tool_calls
        )


# ============================================================================
# MAIN CHAT MANAGER
# ============================================================================

class ChatManager:
    """
    Manages LLM conversations with automatic MCP tool integration
    """
    
    def __init__(
        self,
        mcp_client: UniversalMCPClient,
        model: str = "anthropic/claude-3.5-sonnet",
        base_url: str = "https://openrouter.ai/api/v1",
        system_prompt: Optional[str] = None,
        max_iterations: int = 10,
        temperature: float = 0.7,
        history: Optional[List[Message]] = None
    ):
        """
        Initialize ChatManager
        
        Args:
            mcp_client: Initialized UniversalMCPClient with connected servers
            model: Model name (OpenRouter format)
            api_key: OpenRouter API key
            base_url: API base URL (default: OpenRouter)
            system_prompt: Optional system prompt
            max_iterations: Max tool call iterations to prevent infinite loops
            temperature: LLM temperature (0-1)
            history: Existing conversation history
        """
        self.mcp_client = mcp_client
        self.model = model
        self.max_iterations = max_iterations
        self.temperature = temperature
        
        # Initialize OpenAI client for OpenRouter
        self.openai_client = AsyncOpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url=base_url
        )
        
        # Conversation state
        self.conversation_history: List[Message] = history if history is not None else []
        self.system_prompt = system_prompt or (
            "You are a helpful assistant with access to various tools. "
            "Use the available tools when needed to answer user questions accurately."
        )
        
        # Add system message if history is empty
        if not self.conversation_history and self.system_prompt:
            self.conversation_history.append(
                Message(role="system", content=self.system_prompt)
            )
        
        # Build tool definitions
        self.tool_definitions: Dict[str, ToolDefinition] = {}
        self._build_tools_schema()
        
        logger.info(f"ChatManager initialized with model {model}")
        logger.info(f"Available tools: {len(self.tool_definitions)}")
    
    def _build_tools_schema(self):
        """Build tool definitions from MCP client"""
        self.tool_definitions.clear()
        
        # Get all tools from all servers
        all_tools = self.mcp_client.list_tools()
        
        for server_name, tools in all_tools.items():
            for mcp_tool in tools:
                tool_def = ToolDefinition.from_mcp_tool(server_name, mcp_tool)
                self.tool_definitions[tool_def.full_name] = tool_def
        
        logger.info(f"Built {len(self.tool_definitions)} tool definitions")
    
    def _get_tools_for_openai(self) -> List[Dict[str, Any]]:
        """Get tools in OpenAI format"""
        return [
            tool_def.to_openai_function()
            for tool_def in self.tool_definitions.values()
        ]
    
    async def send_message(self, user_message: str) -> str:
        """
        Send a message and get response (with automatic tool calling)
        
        Args:
            user_message: User's message
            
        Returns:
            Assistant's final response
        """
        # Add user message to history
        self.conversation_history.append(
            Message(role="user", content=user_message)
        )
        
        logger.info(f"User message: {user_message}")
        
        # Process conversation with tool calling loop
        final_response = await self._process_conversation_loop()
        
        logger.info(f"Assistant response: {final_response}")
        
        return final_response
    
    async def send_message_stream(self, user_message: str):
        """
        Send a message and stream the response token by token
        
        Args:
            user_message: User's message
            
        Yields:
            Dict with 'type' and 'content' for each event:
            - {'type': 'token', 'content': str} - Text token
            - {'type': 'tool_call', 'content': {...}} - Tool call started
            - {'type': 'tool_result', 'content': {...}} - Tool result
            - {'type': 'done', 'content': str} - Final message
        """
        # Add user message to history
        self.conversation_history.append(
            Message(role="user", content=user_message)
        )
        
        logger.info(f"User message (streaming): {user_message}")
        
        # Process conversation with tool calling loop (streaming)
        async for event in self._process_conversation_loop_stream():
            yield event
    
    async def _process_conversation_loop_stream(self):
        """Main conversation loop with streaming support"""
        iteration = 0
        logger.info("🚀 Starting streaming conversation loop")
        
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"Conversation iteration {iteration}/{self.max_iterations}")
            
            # Call LLM with streaming
            full_content = ""
            tool_calls_data = []
            
            async for chunk in self._call_llm_stream():
                if chunk.get('type') == 'content':
                    # Stream text tokens
                    token = chunk.get('content', '')
                    full_content += token
                    yield {'type': 'token', 'content': token}
                elif chunk.get('type') == 'tool_call':
                    # Tool call being built
                    tool_calls_data.append(chunk.get('data'))
            
            # If we have tool calls, execute them
            if tool_calls_data:
                # Parse tool calls
                tool_calls = []
                for tc_data in tool_calls_data:
                    try:
                        tool_call = ToolCall.from_openai_tool_call(
                            tc_data,
                            self.tool_definitions
                        )
                        tool_calls.append(tool_call)
                    except Exception as e:
                        logger.error(f"Failed to parse tool call: {e}")
                
                # Add assistant message with tool calls to history
                assistant_message = Message(
                    role="assistant",
                    content=full_content if full_content else None,
                    tool_calls=tool_calls
                )
                self.conversation_history.append(assistant_message)
                
                # Notify about tool calls
                for tc in tool_calls:
                    yield {
                        'type': 'tool_call',
                        'content': {
                            'server': tc.server_name,
                            'tool': tc.tool_name,
                            'arguments': tc.arguments
                        }
                    }
                
                # Execute tools
                tool_results = await self._execute_tool_calls(tool_calls)
                
                # Add tool results to history and yield them
                for result in tool_results:
                    tool_message_dict = result.to_openai_tool_message()
                    tool_message = Message(
                        role="tool",
                        content=tool_message_dict["content"],
                        tool_call_id=tool_message_dict["tool_call_id"],
                        name=tool_message_dict["name"]
                    )
                    self.conversation_history.append(tool_message)
                    
                    
                    # Serialize the result properly for JSON
                    result_content = result._serialize_result(result.result) if result.success else result.error
                    
                    yield {
                        'type': 'tool_result',
                        'content': {
                            'server': result.server_name,
                            'tool': result.tool_name,
                            'success': result.success,
                            'result': result_content
                        }
                    }
                
                # Continue loop to process tool results
                continue
            
            # No tool calls - we have the final response
            if full_content:
                # Add final assistant message to history
                assistant_message = Message(
                    role="assistant",
                    content=full_content
                )
                self.conversation_history.append(assistant_message)
                
                yield {'type': 'done', 'content': full_content}
                return
            else:
                logger.warning("LLM returned no content and no tool calls")
                yield {'type': 'done', 'content': "I apologize, but I couldn't generate a response."}
                return
        
        # Max iterations reached
        logger.warning(f"Max iterations ({self.max_iterations}) reached")
        yield {'type': 'done', 'content': "I apologize, but I couldn't complete the task within the allowed steps."}
    
    async def _call_llm_stream(self):
        """Call the LLM with streaming enabled"""
        # Prepare messages
        messages = [
            msg.to_openai_format()
            for msg in self.conversation_history
        ]
        
        # Prepare tools
        tools = self._get_tools_for_openai()
        
        logger.info(f"🔄 Starting LLM stream with {len(messages)} messages and {len(tools)} tools")
        
        # Call OpenAI API with streaming
        try:
            stream = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                temperature=self.temperature,
                stream=True
            )
            
            tool_calls_buffer = {}
            token_count = 0
            
            async for chunk in stream:
                delta = chunk.choices[0].delta
                
                # Handle content tokens
                if delta.content:
                    token_count += 1
                    if token_count <= 5 or token_count % 50 == 0:
                        logger.debug(f"📝 Token {token_count}: {delta.content[:20]}...")
                    yield {'type': 'content', 'content': delta.content}
                
                # Handle tool calls
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_buffer:
                            logger.info(f"🔧 Tool call started at index {idx}")
                            tool_calls_buffer[idx] = {
                                'id': tc_delta.id or '',
                                'type': 'function',
                                'function': {
                                    'name': '',
                                    'arguments': ''
                                }
                            }
                        
                        if tc_delta.id:
                            tool_calls_buffer[idx]['id'] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_calls_buffer[idx]['function']['name'] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_calls_buffer[idx]['function']['arguments'] += tc_delta.function.arguments
            
            logger.info(f"📊 Stream complete: {token_count} tokens, {len(tool_calls_buffer)} tool calls")
            
            # Yield completed tool calls
            for tc in tool_calls_buffer.values():
                logger.info(f"🔧 Yielding tool call: {tc['function']['name']}")
                # Create a mock object similar to OpenAI's tool call structure
                class MockToolCall:
                    def __init__(self, data):
                        self.id = data['id']
                        self.type = data['type']
                        self.function = type('obj', (object,), {
                            'name': data['function']['name'],
                            'arguments': data['function']['arguments']
                        })()
                
                yield {'type': 'tool_call', 'data': MockToolCall(tc)}
                
        except Exception as e:
            logger.error(f"LLM streaming API call failed: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    async def _process_conversation_loop(self) -> str:
        """
        Main conversation loop with automatic tool calling
        
        Returns:
            Final assistant response
        """
        iteration = 0
        
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"Conversation iteration {iteration}/{self.max_iterations}")
            
            # Call LLM
            response_message = await self._call_llm()
            
            # Add assistant message to history
            assistant_message = Message.from_openai_response(
                response_message,
                self.tool_definitions
            )
            self.conversation_history.append(assistant_message)
            
            # Check if LLM wants to call tools
            if assistant_message.tool_calls:
                logger.info(f"LLM requested {len(assistant_message.tool_calls)} tool calls")
                
                # Execute all tool calls
                tool_results = await self._execute_tool_calls(assistant_message.tool_calls)
                
                # Add tool results to history
                for result in tool_results:
                    tool_message_dict = result.to_openai_tool_message()
                    tool_message = Message(
                        role="tool",
                        content=tool_message_dict["content"],
                        tool_call_id=tool_message_dict["tool_call_id"],
                        name=tool_message_dict["name"]
                    )
                    self.conversation_history.append(tool_message)
                
                # Continue loop to let LLM process tool results
                continue
            
            # No tool calls - we have the final response
            if assistant_message.content:
                return assistant_message.content
            else:
                # Edge case: no content and no tool calls
                logger.warning("LLM returned no content and no tool calls")
                return "I apologize, but I couldn't generate a response."
        
        # Max iterations reached
        logger.warning(f"Max iterations ({self.max_iterations}) reached")
        return "I apologize, but I couldn't complete the task within the allowed steps."
    
    async def _call_llm(self) -> Any:
        """Call the LLM with current conversation history"""
        # Prepare messages
        messages = [
            msg.to_openai_format()
            for msg in self.conversation_history
        ]
        
        # Prepare tools
        tools = self._get_tools_for_openai()
        
        # Call OpenAI API
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                temperature=self.temperature
            )
            
            return response.choices[0].message
            
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise
    
    async def _execute_tool_calls(
        self,
        tool_calls: List[ToolCall]
    ) -> List[ToolResult]:
        """Execute multiple tool calls (in parallel if possible)"""
        logger.info(f"Executing {len(tool_calls)} tool calls")
        
        # Execute all tool calls in parallel
        tasks = [
            tool_call.execute(self.mcp_client)
            for tool_call in tool_calls
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to failed ToolResults
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tool_call = tool_calls[i]
                final_results.append(
                    ToolResult(
                        tool_call_id=tool_call.id,
                        server_name=tool_call.server_name,
                        tool_name=tool_call.tool_name,
                        result=None,
                        success=False,
                        error=str(result)
                    )
                )
            else:
                final_results.append(result)
        
        # Log results
        for result in final_results:
            if result.success:
                logger.info(f"✅ {result.server_name}.{result.tool_name} succeeded")
            else:
                logger.error(f"❌ {result.server_name}.{result.tool_name} failed: {result.error}")
        
        return final_results
    
    def get_history(self) -> List[Message]:
        """Get conversation history"""
        return self.conversation_history.copy()
    
    def clear_history(self):
        """Clear conversation history (keeps system prompt)"""
        self.conversation_history = []
        if self.system_prompt:
            self.conversation_history.append(
                Message(role="system", content=self.system_prompt)
            )
        logger.info("Conversation history cleared")
    
    def add_system_message(self, content: str):
        """Add a system message to the conversation"""
        self.conversation_history.append(
            Message(role="system", content=content)
        )
        logger.info(f"System message added: {content}")
    
    def refresh_tools(self):
        """Refresh tool definitions from MCP client"""
        logger.info("Refreshing tool definitions")
        self._build_tools_schema()
