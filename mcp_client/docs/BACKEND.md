# Backend Documentation

This document provides comprehensive documentation for the backend components of the MCP Client application, explaining **what each component does**, **why it's designed this way**, and **how everything works together**.

## Table of Contents

1. [Overview](#overview)
2. [Understanding MCP (Model Context Protocol)](#understanding-mcp)
3. [MCP_Client.py - Universal MCP Client](#mcp_clientpy---universal-mcp-client)
4. [ChatManager.py - LLM Orchestration](#chatmanagerpy---llm-orchestration)
5. [app.py - FastAPI Application](#apppy---fastapi-application)
6. [Database Layer](#database-layer)
7. [How Everything Works Together](#how-everything-works-together)

---

## Overview

The backend serves as the bridge between the user interface and AI capabilities. It has three main responsibilities:

1. **Connect to MCP Servers** - External tools that extend what the AI can do
2. **Orchestrate Conversations** - Manage the back-and-forth between user, AI, and tools
3. **Expose an API** - Allow the frontend to interact with everything

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         app.py (FastAPI)                             │
│                                                                       │
│   Responsibilities:                                                   │
│   • HTTP endpoints for frontend                                       │
│   • SSE streaming for real-time responses                            │
│   • Session & message persistence                                     │
│   • Request routing and error handling                               │
├─────────────────────────────────────────────────────────────────────┤
│                         ChatManager                                   │
│                                                                       │
│   Responsibilities:                                                   │
│   • Conversation history management                                   │
│   • LLM API calls (via OpenRouter)                                   │
│   • Automatic tool call detection and execution                      │
│   • Streaming token-by-token responses                               │
├─────────────────────────────────────────────────────────────────────┤
│                         MCP_Client                                    │
│                                                                       │
│   Responsibilities:                                                   │
│   • Connect to external MCP servers                                   │
│   • Execute tool calls on those servers                              │
│   • Manage server lifecycle (connect, disconnect, reconnect)         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Understanding MCP

### What is MCP?

**MCP (Model Context Protocol)** is a standardized protocol created by Anthropic that allows AI models to interact with external tools and data sources. Think of it like USB for AI - a universal way for AI to plug into different capabilities.

### Why Use MCP?

Without MCP, if you wanted an AI to:
- Read files from your computer
- Query a database
- Search documentation
- Execute code

You would need to write custom integrations for each. MCP standardizes this:

```
┌──────────┐     MCP Protocol      ┌──────────────┐
│   AI     │ ◄─────────────────────► MCP Server   │
│ (Claude) │                        │ (any tool)   │
└──────────┘                        └──────────────┘
```

### Transport Types

MCP supports different ways to communicate:

| Transport | How it Works | Best For |
|-----------|--------------|----------|
| **stdio** | Spawns a process, talks via stdin/stdout | Local tools (filesystem, git) |
| **SSE** | HTTP with Server-Sent Events | Remote servers, long-running |
| **streamable_http** | HTTP with streaming support | Modern remote servers |

---

## MCP_Client.py - Universal MCP Client

### Purpose

The `UniversalMCPClient` is your gateway to MCP servers. It handles all the complexity of:
- Connecting to servers using different transport methods
- Managing multiple server connections simultaneously
- Executing tool calls and handling responses
- Gracefully shutting down connections

### Key Design Decisions

#### 1. Why a Single Client for Multiple Servers?

```python
class UniversalMCPClient:
    def __init__(self):
        self._servers: Dict[str, ServerInfo] = {}  # All servers in one place
```

**Reason**: In a chat application, the AI might need to use tools from multiple servers in a single conversation. For example:
- Ask about a GitHub repo → uses `deepwiki` server
- Then read a local file → uses `filesystem` server

Having one client manage all servers simplifies orchestration.

#### 2. Why AsyncExitStack for Each Server?

```python
@dataclass
class ServerInfo:
    stack: AsyncExitStack  # For cleanup
```

**Reason**: MCP connections involve multiple resources (subprocess, streams, sessions). `AsyncExitStack` ensures proper cleanup in reverse order, even if errors occur during shutdown.

### ServerConfig Explained

```python
@dataclass
class ServerConfig:
    name: str                          # Unique identifier - how you'll reference this server
    transport: TransportType           # How to connect
    
    # For stdio transport (local processes):
    command: Optional[str] = None      # e.g., "npx", "python", "node"
    args: Optional[List[str]] = None   # e.g., ["-y", "@anthropics/deepwiki-mcp"]
    env: Optional[Dict[str, str]] = None  # Extra environment variables
    cwd: Optional[Union[str, Path]] = None  # Working directory for the process
    
    # For network transports (SSE, HTTP):
    url: Optional[str] = None          # Server URL
    headers: Optional[Dict[str, str]] = None  # Auth headers, etc.
    timeout: Optional[float] = None    # Connection timeout
```

**Example - Adding a Local Tool Server:**

```python
# This spawns "npx -y @anthropics/deepwiki-mcp" as a subprocess
# and communicates via its stdin/stdout
config = ServerConfig(
    name="deepwiki",
    transport="stdio",
    command="npx",
    args=["-y", "@anthropics/deepwiki-mcp"]
)
```

**What Happens When You Add This Server:**

1. Client spawns the subprocess
2. Waits for the MCP handshake
3. Requests the list of available tools
4. Stores the connection for later use

### Core Methods Explained

#### `add_server()` - Connection Flow

```python
async def add_server(self, config: ServerConfig, retry_attempts: int = 0):
    """
    This method:
    1. Validates the config (checks required fields based on transport)
    2. Creates an AsyncExitStack for resource management
    3. Establishes the connection based on transport type
    4. Performs MCP initialization handshake
    5. Fetches available tools from the server
    6. Stores everything in self._servers
    """
```

**Why Retry Support?**

```python
retry_attempts: int = 0,  # Number of retries
retry_delay: float = 2.0  # Seconds between retries
```

Some MCP servers (especially those starting via npx) take time to initialize. Retries handle this gracefully.

#### `call_tool()` - Tool Execution Flow

```python
async def call_tool(
    self,
    server_name: str,    # Which server has the tool
    tool_name: str,      # Which tool to call
    arguments: Dict = None,  # Tool parameters
    timeout: float = None    # Max execution time
):
    """
    This method:
    1. Looks up the server in self._servers
    2. Validates the tool exists on that server
    3. Sends the tool call request via MCP protocol
    4. Waits for and returns the response
    5. Handles timeouts gracefully
    """
```

**Why Separate server_name and tool_name?**

Different servers might have tools with the same name. For example, both a GitHub server and a GitLab server might have a `get_repo` tool. The server name disambiguates.

---

## ChatManager.py - LLM Orchestration

### Purpose

The `ChatManager` is the brain of the operation. It:
- Maintains conversation context
- Sends prompts to the LLM (via OpenRouter)
- Detects when the LLM wants to use tools
- Executes those tools via MCP_Client
- Feeds results back to the LLM
- Repeats until the LLM has a final answer

### Why OpenRouter?

OpenRouter is an API gateway that provides access to multiple LLM providers (Claude, GPT-4, Llama, etc.) through a single, OpenAI-compatible API. This means:

- Same code works with any model
- Easy to switch models
- Unified billing

### The Agentic Loop Explained

This is the core innovation - the LLM can call tools, get results, and continue reasoning:

```
User: "What are the main components of React?"
                    │
                    ▼
┌────────────────────────────────────────────────────────────────┐
│                      ITERATION 1                                │
├────────────────────────────────────────────────────────────────┤
│ ChatManager sends to LLM:                                       │
│   - System prompt                                               │
│   - Available tools (with descriptions)                         │
│   - User message                                                │
│                                                                 │
│ LLM responds:                                                   │
│   "I'll look up the React documentation."                       │
│   + tool_call: deepwiki.read_wiki_structure(repo="facebook/react")│
└────────────────────────────────────────────────────────────────┘
                    │
                    ▼ ChatManager detects tool_call
                    │
┌────────────────────────────────────────────────────────────────┐
│                    TOOL EXECUTION                               │
├────────────────────────────────────────────────────────────────┤
│ ChatManager asks MCP_Client to execute the tool                 │
│                                                                 │
│ Result: "Available pages: 1. Overview, 2. Components, ..."      │
└────────────────────────────────────────────────────────────────┘
                    │
                    ▼ Result added to conversation
                    │
┌────────────────────────────────────────────────────────────────┐
│                      ITERATION 2                                │
├────────────────────────────────────────────────────────────────┤
│ ChatManager sends to LLM:                                       │
│   - Previous messages                                           │
│   - Tool result                                                 │
│                                                                 │
│ LLM responds (no tool calls this time):                         │
│   "Based on the documentation, React's main components are..."  │
└────────────────────────────────────────────────────────────────┘
                    │
                    ▼ No tool calls = Final answer!
```

### Key Data Classes

#### ToolCall - Representing What the LLM Wants

```python
@dataclass
class ToolCall:
    id: str           # Unique ID (for matching results later)
    server_name: str  # Which MCP server
    tool_name: str    # Which tool
    arguments: Dict   # Parameters for the tool
```

**Why is `id` Important?**

When the LLM makes multiple tool calls, we need to match each result to its request. The ID enables this:

```
LLM says: Call tool A (id: "call_1"), Call tool B (id: "call_2")
Results come back: Result for call_1, Result for call_2
LLM knows which result belongs to which call
```

#### ToolDefinition - Telling the LLM What's Available

```python
@dataclass
class ToolDefinition:
    server_name: str
    tool_name: str
    description: str        # What the tool does (LLM reads this!)
    parameters: Dict        # JSON Schema of accepted parameters
```

**The `parameters` Schema:**

This tells the LLM exactly what arguments the tool expects:

```python
{
    "type": "object",
    "properties": {
        "repoName": {
            "type": "string",
            "description": "GitHub repository in owner/repo format"
        }
    },
    "required": ["repoName"]
}
```

The LLM uses this to construct valid tool calls.

### Streaming Implementation

#### Why Streaming?

Without streaming, users wait 5-30 seconds staring at "Loading..." before seeing anything. With streaming:

- Users see tokens appear in real-time
- Tool calls are visible as they happen
- Much better user experience

#### How Streaming Works

```python
async def send_message_stream(self, content: str):
    """
    Yields events as they occur:
    
    1. User message added to history
    2. LLM called with streaming enabled
    3. As tokens arrive → yield {"type": "token", "content": "..."}
    4. If tool_call detected → yield {"type": "tool_call", ...}
    5. Execute tool → yield {"type": "tool_result", ...}
    6. Continue loop with tool result
    7. When done → yield {"type": "done", "content": full_response}
    """
```

**Token Accumulation During Streaming:**

The OpenAI streaming API sends tool calls in pieces:

```
chunk 1: {tool_calls: [{index: 0, function: {name: "deep"}}]}
chunk 2: {tool_calls: [{index: 0, function: {name: "wiki__"}}]}
chunk 3: {tool_calls: [{index: 0, function: {arguments: '{"repo'}}]}
chunk 4: {tool_calls: [{index: 0, function: {arguments: 'Name":'}}]}
...
```

The code accumulates these into complete tool calls before executing:

```python
tool_calls_buffer = {}  # Accumulate chunks by index

async for chunk in stream:
    if chunk.tool_calls:
        for tc_delta in chunk.tool_calls:
            idx = tc_delta.index
            if idx not in tool_calls_buffer:
                tool_calls_buffer[idx] = {...}  # Initialize
            # Append to existing data
            tool_calls_buffer[idx]['function']['name'] += tc_delta.function.name or ''
            tool_calls_buffer[idx]['function']['arguments'] += tc_delta.function.arguments or ''
```

---

## app.py - FastAPI Application

### Purpose

The FastAPI application is the HTTP layer that:
- Exposes REST endpoints for the frontend
- Manages chat sessions and persistence
- Handles SSE streaming for real-time responses
- Coordinates MCP_Client and ChatManager

### Lifecycle Management

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    This runs once when the server starts and once when it stops.
    
    STARTUP:
    1. Initialize the database
    2. Create the global MCP client
    3. Load saved server configs from DB
    4. Reconnect to those servers
    
    SHUTDOWN:
    1. Gracefully close all MCP connections
    """
    global mcp_client
    init_db()
    mcp_client = UniversalMCPClient()
    
    # Reconnect to saved servers...
    
    yield  # Server runs here
    
    await mcp_client.close_all()  # Cleanup
```

**Why Global MCP Client?**

MCP connections are expensive to establish. We reuse one client for all requests instead of creating new connections per request.

### Message Reconstruction Challenge

When loading chat history from the database, we need to perfectly reconstruct messages including tool calls:

```python
def reconstruct_message_from_db(msg) -> Message:
    """
    The LLM API requires messages to be in a specific format.
    For tool-related messages, this includes:
    
    - Assistant messages with tool_calls must have the full tool_call objects
    - Tool result messages must have matching tool_call_id
    
    If these don't match, the API returns errors like:
    "tool_use_id: Field required"
    """
    tool_calls = None
    if msg.tool_calls:
        tool_calls = [ToolCall.from_dict(tc) for tc in msg.tool_calls]
    
    return Message(
        role=msg.role,
        content=msg.content,
        tool_calls=tool_calls,
        tool_call_id=msg.tool_call_id,  # Critical for tool messages!
        name=msg.name,
        timestamp=msg.timestamp
    )
```

### SSE Streaming Endpoint

```python
@app.get("/chat/{session_id}/stream")
async def chat_stream(session_id: str, message: str, db: Session = Depends(get_db)):
    """
    This endpoint:
    1. Loads session history from DB
    2. Creates a ChatManager with that history
    3. Returns a StreamingResponse
    4. The async generator yields SSE events as they occur
    """
```

**SSE Headers Explained:**

```python
headers={
    "Cache-Control": "no-cache, no-store, must-revalidate",  # Don't cache events
    "Pragma": "no-cache",
    "Expires": "0",
    "Connection": "keep-alive",      # Keep connection open
    "X-Accel-Buffering": "no",       # Disable nginx buffering (important!)
    "Content-Type": "text/event-stream; charset=utf-8",
}
```

Without `X-Accel-Buffering: no`, proxies like nginx may buffer events, breaking real-time streaming.

---

## Database Layer

### Why SQLite?

For a desktop/personal application, SQLite offers:
- Zero configuration
- Single file database
- Good performance for moderate data
- Easy backups (just copy the file)

### Schema Design

```
┌─────────────────────┐     ┌─────────────────────┐
│  server_configs     │     │      sessions       │
├─────────────────────┤     ├─────────────────────┤
│ id (PK)             │     │ id (PK, UUID)       │
│ name (unique)       │     │ created_at          │
│ transport           │     │                     │
│ config (JSON)       │     │                     │
│ created_at          │     │                     │
└─────────────────────┘     └──────────┬──────────┘
                                       │
                                       │ 1:N
                                       ▼
                            ┌─────────────────────┐
                            │      messages       │
                            ├─────────────────────┤
                            │ id (PK)             │
                            │ session_id (FK)     │
                            │ role                │
                            │ content             │
                            │ tool_calls (JSON)   │
                            │ tool_call_id        │
                            │ name                │
                            │ timestamp           │
                            └─────────────────────┘
```

**Why Store tool_calls as JSON?**

Tool calls have complex, nested structure. JSON storage:
- Preserves the exact structure
- Flexible for future changes
- Easy to serialize/deserialize

---

## How Everything Works Together

### Complete Request Flow

```
1. USER types "What are the main features of React?"
   │
   ▼
2. FRONTEND sends request:
   GET /chat/{session}/stream?message=What%20are%20the%20main...
   │
   ▼
3. APP.PY receives request:
   • Loads session history from database
   • Creates ChatManager with history
   • Returns StreamingResponse
   │
   ▼
4. CHATMANAGER.send_message_stream():
   • Adds user message to history
   • Calls LLM with streaming
   │
   ▼
5. LLM decides to use a tool:
   "I'll search the React documentation"
   + tool_call: deepwiki.read_wiki_structure
   │
   ▼
6. CHATMANAGER detects tool_call:
   • Yields {"type": "tool_call", ...} event
   • Calls mcp_client.call_tool()
   │
   ▼
7. MCP_CLIENT executes on deepwiki server:
   • Sends MCP request
   • Waits for response
   • Returns result
   │
   ▼
8. CHATMANAGER with result:
   • Yields {"type": "tool_result", ...} event
   • Adds tool result to history
   • Calls LLM again (iteration 2)
   │
   ▼
9. LLM provides final answer:
   "React's main features are: 1. Components..."
   │
   ▼
10. CHATMANAGER.send_message_stream():
    • Yields {"type": "token", ...} for each token
    • Yields {"type": "done", ...}
    │
    ▼
11. APP.PY:
    • Saves new messages to database
    • Closes SSE connection
    │
    ▼
12. FRONTEND receives events:
    • Displays tokens as they arrive
    • Shows tool execution
    • Reloads history on "done"
```

### Error Handling Throughout

Each layer handles errors appropriately:

| Layer | Error Type | Handling |
|-------|------------|----------|
| MCP_Client | Connection failed | Retry or raise exception |
| MCP_Client | Tool execution failed | Return error in ToolResult |
| ChatManager | LLM API error | Yield error event |
| ChatManager | Max iterations reached | Return graceful message |
| app.py | Session not found | HTTP 404 |
| app.py | Any exception | Log and yield error SSE event |

---

## Best Practices

### 1. Always Use Async Context Managers

```python
async with UniversalMCPClient() as client:
    await client.add_server(config)
    result = await client.call_tool(...)
# Automatically cleans up on exit
```

### 2. Log Everything Important

```python
logger.info("🔌 Connecting to %s", server_name)
logger.info("🔧 Calling tool: %s.%s", server, tool)
logger.info("✅ Tool completed successfully")
logger.error("❌ Tool failed: %s", error)
```

### 3. Handle Streaming Errors Gracefully

```python
try:
    async for event in chat_manager.send_message_stream(message):
        yield f"data: {json.dumps(event)}\n\n"
except Exception as e:
    error_event = {"type": "error", "content": str(e)}
    yield f"data: {json.dumps(error_event)}\n\n"
```

### 4. Validate Before Executing

```python
# In call_tool():
server_info = self._servers.get(server_name)
if not server_info:
    raise ValueError(f"Server '{server_name}' not found")

tool = server_info.get_tool(tool_name)
if not tool:
    raise ValueError(f"Tool '{tool_name}' not found on server '{server_name}'")
```
