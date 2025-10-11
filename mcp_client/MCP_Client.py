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
    exit_stack: AsyncExitStack


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
        self._servers: Dict[str, ServerInfo] = {}
    async def add_servers(
        self, 
        configs: List[ServerConfig],
        fail_fast: bool = False
    ) -> Dict[str, Union[ServerInfo, Exception]]:
        """Add multiple servers at once
        
        Args:
            configs: List of server configurations
            fail_fast: If True, stop on first error. If False, continue and return results
            
        Returns:
            Dict {server_name: ServerInfo or Exception}
            
        Example:
            results = await client.add_servers([
                ServerConfig(name="weather", transport="stdio", ...),
                ServerConfig(name="deepwiki", transport="sse", ...)
            ])
        """
        logger.info(f"🔌 Connecting to {len(configs)} servers...")
        
        results = {}
        
        if fail_fast:
            # Sequential connection - stop on first error
            for config in configs:
                try:
                    server_info = await self.add_server(config)
                    results[config.name] = server_info
                except Exception as e:
                    logger.error(f"❌ Failed to connect to {config.name}: {e}")
                    results[config.name] = e
                    raise
        else:
            # Parallel connection - collect all results
            tasks = []
            for config in configs:
                task = self._add_server_safe(config)
                tasks.append(task)
            
            # Wait for all connections
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Build results dict
            for config, result in zip(configs, task_results):
                if isinstance(result, Exception):
                    logger.error(f"❌ Failed to connect to {config.name}: {result}")
                    results[config.name] = result
                else:
                    results[config.name] = result
        
        # Summary
        successful = sum(1 for r in results.values() if isinstance(r, ServerInfo))
        failed = len(results) - successful
        
        logger.info(f"✅ Connected: {successful}/{len(configs)} servers")
        if failed > 0:
            logger.warning(f"⚠️  Failed: {failed} servers")
        
        return results

    async def _add_server_safe(self, config: ServerConfig) -> Union[ServerInfo, Exception]:
        """Helper to add server and catch exceptions"""
        try:
            return await self._add_server(config)
        except Exception as e:
            return e
    async def _add_server(self, config: ServerConfig) -> ServerInfo:
        """Add and connect to an MCP server
        
        Args:
            config: Server configuration
            
        Returns:
            Information about the connected server
            
        Raises:
            ValueError: If config is invalid or server already exists
            ConnectionError: If connection fails
        """
        # Validation
        if config.name in self._servers:
            raise ValueError(f"Server '{config.name}' already exists")
        
        # Validate transport
        valid_transports = ["stdio", "sse", "streamable_http"]
        if config.transport not in valid_transports:
            raise ValueError(
                f"Invalid transport '{config.transport}'. "
                f"Must be one of: {valid_transports}"
            )
        
        logger.info(f"🔌 Connecting to {config.name} ({config.transport})...")
        
        try:
            # Create session based on transport
            if config.transport == "stdio":
                session = await self._connect_stdio(config)
            elif config.transport == "sse":
                session = await self._connect_sse(config)
            elif config.transport == "streamable_http":
                session = await self._connect_streamable_http(config)
            else:
                raise ValueError(f"Unknown transport: {config.transport}")
            
            # Get available tools
            tools_response = await session.list_tools()
            tools = tools_response.tools
            
            # Store server info
            server_info = ServerInfo(
                name=config.name,
                config=config,
                session=session,
                tools=tools,
                connected_at=datetime.utcnow()
            )
            self._servers[config.name] = server_info
            
            logger.info(f"✅ Connected to {config.name}")
            logger.info(f"   Tools: {[t.name for t in tools]}")
            
            return server_info
            
        except Exception as e:
            print(f"❌ Failed to connect to {config.name}: {e}")
            raise ConnectionError(f"Failed to connect to {config.name}") from e
    async def _connect_stdio(self, config: ServerConfig) -> ClientSession:
        """Connect via stdio transport"""
        if not config.command or not config.args:
            raise ValueError("command and args required for stdio")
        
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env,
            cwd=config.cwd
        )
        
        # Enter context with exit_stack
        transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read, write = transport
        
        session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        
        # Initialize session (MCP handshake)
        await session.initialize()
        
        return session
    
    async def _connect_sse(self, config: ServerConfig) -> ClientSession:
        """Connect via SSE transport"""
        if not config.url:
            raise ValueError("url required for SSE")
        
        timeout = config.timeout or 5.0
        sse_read_timeout = config.sse_read_timeout or 300.0
        
        transport = await self._exit_stack.enter_async_context(
            sse_client(
                config.url,
                config.headers,
                timeout,
                sse_read_timeout
            )
        )
        read, write = transport
        
        session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        
        # Initialize session (MCP handshake)
        await session.initialize()
        
        return session
    
    async def _connect_streamable_http(self, config: ServerConfig) -> ClientSession:
        """Connect via Streamable HTTP transport"""
        if not config.url:
            raise ValueError("url required for Streamable HTTP")
        
        timeout = timedelta(seconds=config.timeout or 30)
        sse_read_timeout = timedelta(seconds=config.sse_read_timeout or 300)
        
        transport = await self._exit_stack.enter_async_context(
            streamablehttp_client(
                config.url,
                config.headers,
                timeout,
                sse_read_timeout,
                terminate_on_close=True
            )
        )
        read, write, session_id = transport
        
        print(f"   Session ID: {session_id}")
        
        session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        
        # Initialize session (MCP handshake)
        await session.initialize()
        
        return session
    
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Call a tool on a server
        
        Args:
            server_name: Name of the server
            tool_name: Name of the tool
            arguments: Tool arguments (optional)
            
        Returns:
            Result of the tool call
            
        Raises:
            ValueError: If server doesn't exist
        """
        

        if server_name not in self._servers:
            available = list(self._servers.keys())
            raise ValueError(
                f"Server '{server_name}' not found. "
                f"Available: {available}"
            )
        
        server = self._servers[server_name]
        arguments = arguments or {}
        
        logger.info(f"🔧 {server_name}.{tool_name}({arguments})")
        
        result = await server.session.call_tool(tool_name, arguments)
        
        logger.info(f"✅ Success")
        return result
    
    def list_servers(self) -> List[str]:
        """List all connected server names"""
        return list(self._servers.keys())
    
    def list_tools(
        self,
        server_name: Optional[str] = None
    ) -> Dict[str, List[Tool]]:
        """List available tools
        
        Args:
            server_name: If specified, list only this server's tools
            
        Returns:
            Dict {server_name: [tools]}
        """
        if server_name:
            if server_name not in self._servers:
                return {}
            return {server_name: self._servers[server_name].tools}
        
        return {
            name: server.tools
            for name, server in self._servers.items()
        }
    
    def get_server_info(self, server_name: str) -> Optional[ServerInfo]:
        """Get information about a server"""
        return self._servers.get(server_name)
    
    async def disconnect_all(self):
        """Disconnect all servers"""
        print("🔌 Disconnecting all servers...")
        await self._exit_stack.aclose()
        self._servers.clear()
        print("✅ All servers disconnected")
    
    # Context manager support
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
    
    async with UniversalMCPClient() as client:
        
        # You can also connect to Streamable HTTP servers
        # await client.add_server(ServerConfig(
        #     name="github",
        #     transport="streamable_http",
        #     url="http://localhost:8080/mcp",
        #     headers={"Authorization": "Bearer your-token"}
        # ))
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
                args=["-y", "@modelcontextprotocol/server-filesystem"])])
        print()
        print("=" * 60)
        print("CONNECTED SERVERS & THEIR TOOLS")
        print("=" * 60)
        
        # List all connected servers
        print(f"\n📋 Connected servers: {client.list_servers()}")
        
        # List all available tools
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
        
        # Call a tool on the weather server
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
        
        # Call a tool on the deepwiki server
        try:
            result = await client.call_tool(
                "deepwiki",
                "read_wiki_structure",
                {"repoName": "facebook/react"}
            )
            print(f"\n📊 DeepWiki Result:")
            print(result)
        except Exception as e:
            print(f"\n❌ Error: {e}")
        
        print()
        print("=" * 60)
        print("SERVER DETAILS")
        print("=" * 60)
        
        # Get detailed info about a server
        weather_info = client.get_server_info("weather")
        if weather_info:
            print(f"\n📡 {weather_info.name}:")
            print(f"   Transport: {weather_info.config.transport}")
            print(f"   Connected at: {weather_info.connected_at}")
            print(f"   Available tools: {len(weather_info.tools)}")
    
    # Cleanup happens automatically here
    print()
    print("=" * 60)
    print("✅ All servers disconnected automatically")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())