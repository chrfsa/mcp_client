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
