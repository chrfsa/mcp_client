# models.py

from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


class ServerConfigRequest(BaseModel):
    """Ajouter un serveur MCP"""
    name: str
    transport: Literal["stdio", "sse", "streamable_http"]
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    timeout: Optional[float] = None


class ServerResponse(BaseModel):
    """Info serveur"""
    name: str
    transport: str
    tools_count: int
    tools: List[str]
    connected_at: datetime


class ToolResponse(BaseModel):
    """Info tool"""
    server_name: str
    tool_name: str
    full_name: str
    description: str


class ChatRequest(BaseModel):
    """Message utilisateur"""
    message: str


class ChatResponse(BaseModel):
    """Réponse assistant"""
    message: str
    tool_calls_count: int
    iterations: int