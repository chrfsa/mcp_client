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
