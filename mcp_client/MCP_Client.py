"""
Universal MCP Client - Optimized for Desktop Apps (Cursor/Claude Desktop style)
Simple, robust, production-ready - FIXED shutdown issues
"""

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Tool

logger = logging.getLogger(__name__)

TransportType = Literal["stdio", "sse", "streamable_http"]


@dataclass
class ServerConfig:
    """MCP server configuration"""
    name: str
    transport: TransportType
    
    # stdio params
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    cwd: Optional[Union[str, Path]] = None
    
    # HTTP/SSE params
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    timeout: Optional[float] = None
    sse_read_timeout: Optional[float] = None
    
    def validate(self) -> None:
        """Validate configuration based on transport type"""
        if self.transport == "stdio":
            if not self.command or not self.args:
                raise ValueError(f"stdio transport requires 'command' and 'args'")
        elif self.transport in ["sse", "streamable_http"]:
            if not self.url:
                raise ValueError(f"{self.transport} transport requires 'url'")


@dataclass
class ServerInfo:
    """Information about a connected server"""
    name: str
    config: ServerConfig
    session: ClientSession
    tools: List[Tool]
    connected_at: datetime
    stack: AsyncExitStack
    _close_task: Optional[asyncio.Task] = field(default=None, init=False)
    _closed: bool = field(default=False, init=False)
    
    @property
    def is_closed(self) -> bool:
        """Check if server is closed"""
        return self._closed
    
    @property
    def tools_count(self) -> int:
        """Number of tools available"""
        return len(self.tools)
    
    @property
    def uptime_seconds(self) -> float:
        """Seconds since connection"""
        return (datetime.utcnow() - self.connected_at).total_seconds()
    
    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Find a tool by name"""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None


class UniversalMCPClient:
    """
    Universal MCP client for desktop applications
    
    Simple usage (recommended for desktop apps):
        client = UniversalMCPClient()
        await client.add_server(ServerConfig(...))
        result = await client.call_tool("server", "tool", {...})
        await client.close_all()  # Important: close properly!
    
    With context manager (for scripts):
        async with UniversalMCPClient() as client:
            await client.add_server(ServerConfig(...))
            result = await client.call_tool("server", "tool", {...})
        # Servers close automatically
    """
    
    def __init__(self):
        self._servers: Dict[str, ServerInfo] = {}
        self._lock = asyncio.Lock()
        self._closed = False
    
    async def add_server(
        self,
        config: ServerConfig,
        retry_attempts: int = 0,
        retry_delay: float = 2.0
    ) -> ServerInfo:
        """
        Add and connect to an MCP server
        
        Args:
            config: Server configuration
            retry_attempts: Number of retry attempts if connection fails
            retry_delay: Delay between retries in seconds
            
        Returns:
            ServerInfo object
            
        Raises:
            ValueError: If config is invalid or server already exists
            ConnectionError: If connection fails after all retries
            RuntimeError: If client is closed
        """
        if self._closed:
            raise RuntimeError("Client is closed")
        
        # Validate config
        config.validate()
        
        async with self._lock:
            if config.name in self._servers:
                raise ValueError(f"Server '{config.name}' already exists")
        
        # Try to connect (with retries)
        last_error = None
        for attempt in range(retry_attempts + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retry {attempt}/{retry_attempts} for '{config.name}'")
                    await asyncio.sleep(retry_delay)
                
                server_info = await self._connect_server(config)
                
                async with self._lock:
                    self._servers[config.name] = server_info
                
                logger.info(f"✅ Connected to '{config.name}' ({len(server_info.tools)} tools)")
                return server_info
                
            except Exception as e:
                last_error = e
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
        
        # All retries failed
        raise ConnectionError(
            f"Failed to connect to '{config.name}' after {retry_attempts + 1} attempts: {last_error}"
        )
    
    async def _connect_server(self, config: ServerConfig) -> ServerInfo:
        """Internal method to connect to a server"""
        stack = AsyncExitStack()
        
        try:
            logger.info(f"🔌 Connecting to '{config.name}' ({config.transport})...")
            
            # Connect based on transport type
            if config.transport == "stdio":
                session = await self._connect_stdio(config, stack)
            elif config.transport == "sse":
                session = await self._connect_sse(config, stack)
            elif config.transport == "streamable_http":
                session = await self._connect_http(config, stack)
            else:
                raise ValueError(f"Unknown transport: {config.transport}")
            
            # Initialize session
            await session.initialize()
            
            # Get available tools
            tools_response = await session.list_tools()
            
            return ServerInfo(
                name=config.name,
                config=config,
                session=session,
                tools=tools_response.tools,
                connected_at=datetime.utcnow(),
                stack=stack
            )
            
        except Exception as e:
            # Cleanup on error
            try:
                await stack.aclose()
            except Exception as cleanup_error:
                logger.warning(f"Error during cleanup: {cleanup_error}")
            raise
    
    async def _connect_stdio(self, config: ServerConfig, stack: AsyncExitStack) -> ClientSession:
        """Connect via stdio transport"""
        params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env,
            cwd=config.cwd
        )
        
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        
        return session
    
    async def _connect_sse(self, config: ServerConfig, stack: AsyncExitStack) -> ClientSession:
        """Connect via SSE transport"""
        read, write = await stack.enter_async_context(
            sse_client(
                config.url,
                config.headers,
                config.timeout or 5.0,
                config.sse_read_timeout or 300.0
            )
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        
        return session
    
    async def _connect_http(self, config: ServerConfig, stack: AsyncExitStack) -> ClientSession:
        """Connect via Streamable HTTP transport"""
        read, write, session_id = await stack.enter_async_context(
            streamablehttp_client(
                config.url,
                config.headers,
                timedelta(seconds=config.timeout or 30),
                timedelta(seconds=config.sse_read_timeout or 300),
                terminate_on_close=True
            )
        )
        
        logger.info(f"Streamable HTTP session ID: {session_id}")
        session = await stack.enter_async_context(ClientSession(read, write))
        
        return session
    
    async def add_servers(
        self,
        configs: List[ServerConfig],
        fail_fast: bool = False
    ) -> Dict[str, Union[ServerInfo, Exception]]:
        """
        Add multiple servers
        
        Args:
            configs: List of server configurations
            fail_fast: If True, stop on first error
            
        Returns:
            Dict mapping server names to ServerInfo or Exception
        """
        results = {}
        
        for config in configs:
            try:
                server_info = await self.add_server(config)
                results[config.name] = server_info
            except Exception as e:
                logger.error(f"❌ Failed to connect '{config.name}': {e}")
                results[config.name] = e
                if fail_fast:
                    raise
        
        successful = sum(1 for r in results.values() if isinstance(r, ServerInfo))
        logger.info(f"📊 Connected {successful}/{len(configs)} servers")
        
        return results
    
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Any:
        """
        Call a tool on a server
        
        Args:
            server_name: Name of the server
            tool_name: Name of the tool
            arguments: Tool arguments
            timeout: Optional timeout in seconds
            
        Returns:
            Tool result
            
        Raises:
            ValueError: If server or tool not found
            RuntimeError: If server is closed
            asyncio.TimeoutError: If timeout is exceeded
        """
        async with self._lock:
            server_info = self._servers.get(server_name)
            if not server_info:
                available = list(self._servers.keys())
                raise ValueError(
                    f"Server '{server_name}' not found. Available: {available}"
                )
            
            if server_info.is_closed:
                raise RuntimeError(f"Server '{server_name}' is closed")
        
        # Check if tool exists
        if not server_info.get_tool(tool_name):
            available_tools = [t.name for t in server_info.tools]
            raise ValueError(
                f"Tool '{tool_name}' not found on server '{server_name}'. "
                f"Available: {available_tools}"
            )
        
        logger.info(f"🔧 Calling {server_name}.{tool_name}({arguments})")
        
        # Call with optional timeout
        try:
            if timeout:
                result = await asyncio.wait_for(
                    server_info.session.call_tool(tool_name, arguments or {}),
                    timeout=timeout
                )
            else:
                result = await server_info.session.call_tool(tool_name, arguments or {})
            
            logger.info(f"✅ Tool call succeeded")
            return result
        except Exception as e:
            logger.error(f"❌ Tool call failed: {e}")
            raise
    
    def list_servers(self) -> List[str]:
        """List all connected server names"""
        return list(self._servers.keys())
    
    def list_tools(self, server_name: Optional[str] = None) -> Dict[str, List[Tool]]:
        """
        List available tools
        
        Args:
            server_name: Optional server name to filter tools
            
        Returns:
            Dict mapping server names to their tools
        """
        if server_name:
            server_info = self._servers.get(server_name)
            return {server_name: server_info.tools if server_info else []}
        
        return {name: info.tools for name, info in self._servers.items()}
    
    def get_server_info(self, server_name: str) -> Optional[ServerInfo]:
        """Get information about a server"""
        return self._servers.get(server_name)
    
    async def _close_server_internal(self, server_info: ServerInfo) -> None:
        """Internal method to close a server - must be called from same task context"""
        if server_info.is_closed:
            return
        
        server_info._closed = True
        logger.info(f"🔌 Closing server '{server_info.name}'...")
        
        try:
            # Close the stack without timeout - let it complete naturally
            await server_info.stack.aclose()
            logger.info(f"✅ Server '{server_info.name}' closed")
        except Exception as e:
            logger.warning(f"⚠️  Error closing '{server_info.name}': {e}")
    
    async def close_server(self, server_name: str) -> None:
        """
        Close a specific server
        
        Args:
            server_name: Name of the server to close
        """
        async with self._lock:
            server_info = self._servers.pop(server_name, None)
        
        if server_info:
            await self._close_server_internal(server_info)
        else:
            logger.warning(f"⚠️  Server '{server_name}' not found")
    async def close_all(self) -> None:
        """Close all servers gracefully"""
        if self._closed:
            return
        
        self._closed = True
        
        if not self._servers:
            logger.info("No servers to close")
            return
        
        logger.info(f"🔌 Closing {len(self._servers)} servers...")
        
        # Get all servers
        async with self._lock:
            servers = list(self._servers.values())
            self._servers.clear()
        
        # Close each server sequentially in the same task context
        for server_info in servers:
            await self._close_server_internal(server_info)
        
        logger.info("✅ All servers closed")
    
    # Context manager support (optional)
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_all()
        # Don't suppress exceptions
        return False
async def main():
    """Example usage"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create client
    client = UniversalMCPClient()
    
    
    await client.add_servers([ServerConfig(
        name="weather",
        transport="stdio",
        command="python",
        args=["/home/said/Bureau/MCP/weather/weather.py"],
    ),ServerConfig(
        name="deepwiki",
        transport="sse",
        url="https://mcp.deepwiki.com/sse",
    ),ServerConfig(
        name="firecrawl",
        transport="stdio",
        command="npx",
        args=["-y", "firecrawl-mcp"],
    )])
    
    # List tools
    tools = client.list_tools()
    print(f"\n📋 Available tools:")
    for server_name, server_tools in tools.items():
        print(f"  {server_name}: {[t.name for t in server_tools]}")
    
    # Call tool
    print("\n🌤️  Fetching weather alerts for CA...")
    result = await client.call_tool("weather", "get_alerts", {"state": "CA"})
    
    print(result)
    await client.close_server("deepwiki")
    servers = client.list_servers()
    print(f"\n📋 Available servers:")
    for server_name in servers:
        print(f"  {server_name}")
    await client.close_all()


if __name__ == "__main__":
    asyncio.run(main())



