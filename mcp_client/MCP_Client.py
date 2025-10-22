"""
Universal MCP Client - Simple & Clean Implementation
Supports: stdio, SSE, and Streamable HTTP transports
"""

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Tool

import logging
logger = logging.getLogger(__name__)
# ============================================================================
# CONFIGURATION TYPES
# ============================================================================

# Transport type (automatic validation by Python)
TransportType = Literal["stdio", "sse", "streamable_http"]


@dataclass
class ServerConfig:
    """MCP server configuration
    
    For stdio:
        ServerConfig(
            name="weather",
            transport="stdio",
            command="python",
            args=["weather.py"]
        )
    
    For HTTP:
        ServerConfig(
            name="github",
            transport="streamable_http",
            url="http://localhost:8080/mcp"
        )
    for SSE:
        ServerConfig(
            name="deepwiki",
            transport="sse",
            url="https://mcp.deepwiki.com/sse"
        )
    """
    name: str
    transport: TransportType
    
    # stdio params
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    cwd: Optional[Union[str, Path]] = None
    
    # HTTP params (SSE & Streamable HTTP)
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    timeout: Optional[float] = None
    sse_read_timeout: Optional[float] = None


@dataclass
class ServerInfo:
    """Information about a connected server"""
    name: str
    config: ServerConfig
    session: ClientSession
    tools: List[Tool]
    connected_at: datetime


# ============================================================================
# MAIN CLIENT
# ============================================================================

class UniversalMCPClient:
    """Universal MCP client with persistent sessions
    
    Basic usage:
        async with UniversalMCPClient() as client:
            # Add servers
            await client.add_server(ServerConfig(
                name="weather",
                transport="stdio",
                command="python",
                args=["weather.py"]
            ))
            
            # List tools
            tools = client.list_tools()
            print(tools)
            
            # Call a tool
            result = await client.call_tool(
                "weather",
                "get_weather",
                {"city": "Paris"}
            )
    Production use:
        client = UniversalMCPClient()
        await client.add_server(ServerConfig(
            name="weather",
            transport="stdio",
            command="python",
            args=["weather.py"]
        ))
        await client.call_tool(
            "weather",
            "get_weather",
            {"city": "Paris"}
        ))
        ...
    """
    
    def __init__(self):
        self._exit_stack: Dict[str, AsyncExitStack] = {}
        self._user_servers: Dict[str, dict[str, ServerInfo]] = {}
    def _get_stack(self, user_id: str) -> AsyncExitStack:
        stack = self._exit_stack.get(user_id)
        if not stack:
            stack = AsyncExitStack()
            self._exit_stack[user_id] = stack
        return stack
    def _get_user_servers(self, user_id: str) -> dict[str, ServerInfo]:
        return self._user_servers.get(user_id, {})

    async def add_server(self, config: ServerConfig) -> ServerInfo:
        """Add a single server"""
        if config.name in self._servers:
            raise ValueError(f"Server '{config.name}' already exists")
        
        logger.info(f"🔌 Connecting to {config.name}...")
        
        # Connexion selon le transport
        if config.transport == "stdio":
            session = await self._connect_stdio(config)
        elif config.transport == "sse":
            session = await self._connect_sse(config)
        elif config.transport == "streamable_http":
            session = await self._connect_streamable_http(config)
        
        # Récupérer les tools
        tools_response = await session.list_tools()
        
        # Stocker les infos
        server_info = ServerInfo(
            name=config.name,
            config=config,
            session=session,
            tools=tools_response.tools,
            connected_at=datetime.utcnow()
        )
        self._servers[config.name] = server_info
        
        logger.info(f"✅ Connected to {config.name}")
        return server_info
    
    async def add_servers(
        self, 
        configs: List[ServerConfig],
        fail_fast: bool = False
    ) -> Dict[str, Union[ServerInfo, Exception]]:
        """Add multiple servers sequentially"""
        logger.info(f"🔌 Connecting to {len(configs)} servers...")
        results = {}
        
        for config in configs:
            try:
                server_info = await self.add_server(config)
                results[config.name] = server_info
            except Exception as e:
                logger.error(f"❌ Failed: {config.name}: {e}")
                results[config.name] = e
                if fail_fast:
                    raise
        
        successful = sum(1 for r in results.values() if isinstance(r, ServerInfo))
        logger.info(f"✅ Connected: {successful}/{len(configs)} servers")
        
        return results
    
    async def _connect_stdio(self, config: ServerConfig, stack: AsyncExitStack) -> ClientSession:
        """Connect via stdio using global exit_stack"""
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env,
            cwd=config.cwd
        )
        
        # Utilise self._exit_stack (le global)
        transport = await stack.enter_async_context(
            stdio_client(server_params)
        )
        read, write = transport
        
        session = await stack.enter_async_context(
            ClientSession(read, write)
        )
        
        await session.initialize()
        return session
    
    async def _connect_sse(self, config: ServerConfig, stack: AsyncExitStack) -> ClientSession:
        """Connect via SSE using global exit_stack"""
        transport = await stack.enter_async_context(
            sse_client(
                config.url,
                config.headers,
                config.timeout or 5.0,
                config.sse_read_timeout or 300.0
            )
        )
        read, write = transport
        
        session = await stack.enter_async_context(
            ClientSession(read, write)
        )
        
        await session.initialize()
        return session
    
    async def _connect_streamable_http(self, config: ServerConfig, stack: AsyncExitStack) -> ClientSession:
        """Connect via Streamable HTTP using global exit_stack"""
        transport = await stack.enter_async_context(
            streamablehttp_client(
                config.url,
                config.headers,
                timedelta(seconds=config.timeout or 30),
                timedelta(seconds=config.sse_read_timeout or 300),
                terminate_on_close=True
            )
        )
        read, write, session_id = transport
        logger.info(f"🔌 Connected to {config.name} with session ID: {session_id}")
        session = await stack.enter_async_context(
            ClientSession(read, write)
        )
        
        await session.initialize()
        return session
    
    async def call_tool(self, server_name: str, tool_name: str, 
                       arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Call a tool on a server"""
        if server_name not in self._servers:
            raise ValueError(f"Server '{server_name}' not found")
        
        server = self._servers[server_name]
        result = await server.session.call_tool(tool_name, arguments or {})
        return result
    
    def list_servers(self) -> List[str]:
        """List connected servers"""
        return list(self._servers.keys())
    
    def list_tools(self, server_name: Optional[str] = None) -> Dict[str, List[Tool]]:
        """List available tools"""
        if server_name:
            if server_name not in self._servers:
                return {}
            return {server_name: self._servers[server_name].tools}
        
        return {name: info.tools for name, info in self._servers.items()}
    
    def get_server_info(self, server_name: str) -> Optional[ServerInfo]:
        """Get server information"""
        return self._servers.get(server_name)
    
    async def disconnect_all(self):
        """Disconnect all servers gracefully"""
        if not self._servers:
            return
        
        logger.info("🔌 Disconnecting all servers...")
        await self._exit_stack.aclose()
        self._servers.clear()
        logger.info("✅ All servers disconnected")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect_all()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_stdio_config(
    name: str,
    script_path: str,
    env: Optional[Dict[str, str]] = None
) -> ServerConfig:
    """Helper to create a stdio config
    
    Automatically detects Python or Node.js based on file extension
    
    Args:
        name: Server name
        script_path: Path to script (.py or .js)
        env: Optional environment variables
        
    Returns:
        ServerConfig for stdio
        
    Example:
        config = create_stdio_config("weather", "weather.py")
    """
    path = Path(script_path)
    
    if path.suffix == ".py":
        command = "python"
    elif path.suffix == ".js":
        command = "node"
    else:
        raise ValueError(f"Unknown script type: {path.suffix}")
    
    return ServerConfig(
        name=name,
        transport="stdio",
        command=command,
        args=[str(path)],
        env=env
    )


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

import asyncio

async def main():
    """Complete example of using the MCP client"""
    
    print("=" * 60)
    print("Universal MCP Client - Example")
    print("=" * 60)
    print()
    
    client = UniversalMCPClient()  # ← PAS de "async with"
    
    try:
        await client.add_servers([
            ServerConfig(
                name="weather",
                transport="stdio",
                command="python",
                args=["/home/said/Bureau/MCP/weather/weather.py"]
            ),
            ServerConfig(
                name="deepwiki",
                transport="sse",
                url="https://mcp.deepwiki.com/sse"
            ),
            ServerConfig(
                name="firecrawl-mcp",
                transport="stdio",
                command="npx",
                args=["-y", "firecrawl-mcp"],
                env={"FIRECRAWL_API_KEY": "fc-51f662a6cb2543a9a18df427bc368b2f"}
            ),
            ServerConfig(
                name="filesystem",
                transport="stdio",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem"]
            )
        ])
        
        print()
        print("=" * 60)
        print("CONNECTED SERVERS & THEIR TOOLS")
        print("=" * 60)
        
        print(f"\n📋 Connected servers: {client.list_servers()}")
        
        all_tools = client.list_tools()
        for server_name, tools in all_tools.items():
            print(f"\n🔧 {server_name}:")
            for tool in tools:
                print(f"   - {tool.name}: {tool.description}")
        
        print()
        print("=" * 60)
        print("CALLING TOOLS")
        print("=" * 60)
        print()
        
        try:
            result = await client.call_tool(
                "weather",
                "get_alerts",
                {"state": "CA"}
            )
            print(f"\n📊 Weather Result:")
            print(result)
        except Exception as e:
            print(f"\n❌ Error: {e}")
        
        print()
        print("=" * 60)
        print("SERVER DETAILS")
        print("=" * 60)
        
        weather_info = client.get_server_info("weather")
        if weather_info:
            print(f"\n📡 {weather_info.name}:")
            print(f"   Transport: {weather_info.config.transport}")
            print(f"   Connected at: {weather_info.connected_at}")
            print(f"   Available tools: {len(weather_info.tools)}")
    
    finally:
        # Disconnect explicitly before finishing
        print()
        print("=" * 60)
        print("Disconnecting...")
        print("=" * 60)
        await client.disconnect_all()
        print("✅ All servers disconnected")


if __name__ == "__main__":
    asyncio.run(main())