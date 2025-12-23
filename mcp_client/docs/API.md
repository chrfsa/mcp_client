# API Reference

This document provides detailed documentation for all REST API endpoints.

## Table of Contents

1. [Base URL](#base-url)
2. [Health Check](#health-check)
3. [Server Management](#server-management)
4. [Session Management](#session-management)
5. [Chat](#chat)
6. [Error Handling](#error-handling)

---

## Base URL

```
http://localhost:8000
```

---

## Health Check

### GET /

Check if the API is running.

**Response:**

```json
{
    "status": "ok",
    "message": "MCP Chat API is running"
}
```

---

## Server Management

### POST /servers

Add one or more MCP servers.

**Request Body:**

```json
[
    {
        "name": "deepwiki",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropics/deepwiki-mcp"]
    }
]
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Unique server identifier |
| `transport` | string | ✅ | "stdio", "sse", or "streamable_http" |
| `command` | string | stdio only | Command to execute |
| `args` | string[] | ❌ | Command arguments |
| `env` | object | ❌ | Environment variables |
| `cwd` | string | ❌ | Working directory |
| `url` | string | sse/http only | Server URL |
| `headers` | object | ❌ | HTTP headers |
| `timeout` | number | ❌ | Connection timeout (seconds) |

**Response (200 OK):**

```json
[
    {
        "name": "deepwiki",
        "transport": "stdio",
        "tools_count": 3,
        "tools": [
            {
                "name": "read_wiki_structure",
                "description": "Get a list of documentation topics"
            },
            {
                "name": "read_wiki_contents",
                "description": "View documentation about a repository"
            },
            {
                "name": "ask_question",
                "description": "Ask any question about a repository"
            }
        ],
        "connected_at": "2024-01-15T10:30:00Z"
    }
]
```

**Errors:**

- `500`: Failed to connect to server

---

### GET /servers

List all connected servers.

**Response (200 OK):**

```json
[
    {
        "name": "deepwiki",
        "transport": "stdio",
        "tools_count": 3,
        "tools": [...],
        "connected_at": "2024-01-15T10:30:00Z"
    }
]
```

---

### DELETE /servers/{server_name}

Remove a server.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `server_name` | path | Name of the server to remove |

**Response (200 OK):**

```json
{
    "message": "Server 'deepwiki' removed"
}
```

**Errors:**

- `404`: Server not found

---

### GET /tools

List all available tools across all servers.

**Response (200 OK):**

```json
[
    {
        "server_name": "deepwiki",
        "tool_name": "read_wiki_structure",
        "full_name": "deepwiki__read_wiki_structure",
        "description": "Get a list of documentation topics for a GitHub repository"
    },
    {
        "server_name": "deepwiki",
        "tool_name": "read_wiki_contents",
        "full_name": "deepwiki__read_wiki_contents",
        "description": "View documentation about a GitHub repository"
    }
]
```

---

## Session Management

### POST /sessions

Create a new chat session.

**Response (200 OK):**

```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### GET /sessions

List all sessions.

**Response (200 OK):**

```json
[
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "created_at": "2024-01-15T10:30:00Z",
        "message_count": 5
    },
    {
        "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "created_at": "2024-01-14T15:20:00Z",
        "message_count": 12
    }
]
```

---

### GET /sessions/{session_id}/history

Get message history for a session.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | path | Session UUID |

**Response (200 OK):**

```json
[
    {
        "role": "user",
        "content": "Hello!",
        "timestamp": "2024-01-15T10:30:00Z"
    },
    {
        "role": "assistant",
        "content": "Hello! How can I help you?",
        "timestamp": "2024-01-15T10:30:05Z"
    },
    {
        "role": "tool",
        "content": "{\"result\": \"...\"}",
        "name": "deepwiki__read_wiki_structure",
        "tool_call_id": "call_abc123",
        "timestamp": "2024-01-15T10:31:00Z"
    }
]
```

**Errors:**

- `404`: Session not found

---

## Chat

### POST /chat/{session_id}

Send a message (non-streaming).

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | path | Session UUID |

**Request Body:**

```json
{
    "message": "What is React?"
}
```

**Response (200 OK):**

```json
{
    "message": "React is a JavaScript library for building user interfaces...",
    "tool_calls_count": 0,
    "iterations": 1
}
```

**Response with Tool Calls:**

```json
{
    "message": "Based on the documentation, React provides...",
    "tool_calls_count": 2,
    "iterations": 2
}
```

**Errors:**

- `404`: Session not found
- `500`: Chat error

---

### GET /chat/{session_id}/stream

Send a message with streaming response (SSE).

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | path | Session UUID |
| `message` | query | Message text (URL encoded) |

**Example:**

```
GET /chat/550e8400-e29b-41d4-a716-446655440000/stream?message=Hello
```

**Response (SSE Stream):**

```
Content-Type: text/event-stream

data: {"type": "token", "content": "Hello"}

data: {"type": "token", "content": "! How"}

data: {"type": "token", "content": " can I"}

data: {"type": "token", "content": " help you?"}

data: {"type": "done", "content": "Hello! How can I help you?"}
```

**Event Types:**

| Type | Description | Content |
|------|-------------|---------|
| `token` | Text chunk | String token |
| `tool_call` | Tool being called | `{server, tool, arguments}` |
| `tool_result` | Tool result | `{server, tool, success, result}` |
| `done` | Stream complete | Full response text |
| `error` | Error occurred | Error message |

**Example with Tool Call:**

```
data: {"type": "token", "content": "I'll look that up..."}

data: {"type": "tool_call", "content": {"server": "deepwiki", "tool": "read_wiki_structure", "arguments": {"repoName": "facebook/react"}}}

data: {"type": "tool_result", "content": {"server": "deepwiki", "tool": "read_wiki_structure", "success": true, "result": "..."}}

data: {"type": "token", "content": "Based on the documentation..."}

data: {"type": "done", "content": "I'll look that up... Based on the documentation..."}
```

**Headers:**

```http
Cache-Control: no-cache, no-store, must-revalidate
Connection: keep-alive
X-Accel-Buffering: no
Content-Type: text/event-stream; charset=utf-8
```

---

## Error Handling

### Error Response Format

All errors follow this format:

```json
{
    "detail": "Error message here"
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `400` | Bad request (invalid parameters) |
| `404` | Not found (server, session, etc.) |
| `500` | Internal server error |

### Common Errors

**Session not found:**

```json
{
    "detail": "Session not found"
}
```

**Server not found:**

```json
{
    "detail": "Server not found"
}
```

**MCP connection error:**

```json
{
    "detail": "Failed to connect to server: [error details]"
}
```

---

## cURL Examples

### Add a Server

```bash
curl -X POST http://localhost:8000/servers \
  -H "Content-Type: application/json" \
  -d '[{
    "name": "deepwiki",
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@anthropics/deepwiki-mcp"]
  }]'
```

### List Servers

```bash
curl http://localhost:8000/servers
```

### List Tools

```bash
curl http://localhost:8000/tools
```

### Create Session

```bash
curl -X POST http://localhost:8000/sessions
```

### Send Message (Non-streaming)

```bash
curl -X POST http://localhost:8000/chat/SESSION_ID \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}'
```

### Send Message (Streaming)

```bash
curl -N "http://localhost:8000/chat/SESSION_ID/stream?message=Hello"
```

---

## JavaScript Examples

### Using Fetch (Non-streaming)

```javascript
const response = await fetch(`http://localhost:8000/chat/${sessionId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: 'Hello!' })
});
const data = await response.json();
console.log(data.message);
```

### Using EventSource (Streaming)

```javascript
const eventSource = new EventSource(
    `http://localhost:8000/chat/${sessionId}/stream?message=${encodeURIComponent('Hello!')}`
);

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'token') {
        process.stdout.write(data.content);
    } else if (data.type === 'done') {
        console.log('\nDone!');
        eventSource.close();
    }
};

eventSource.onerror = (error) => {
    console.error('Error:', error);
    eventSource.close();
};
```

---

## Python Examples

### Using requests

```python
import requests

# Add server
response = requests.post('http://localhost:8000/servers', json=[{
    'name': 'deepwiki',
    'transport': 'stdio',
    'command': 'npx',
    'args': ['-y', '@anthropics/deepwiki-mcp']
}])
print(response.json())

# Send message
response = requests.post(f'http://localhost:8000/chat/{session_id}', 
    json={'message': 'Hello!'})
print(response.json()['message'])
```

### Using sseclient (Streaming)

```python
import sseclient
import requests

url = f'http://localhost:8000/chat/{session_id}/stream?message=Hello'
response = requests.get(url, stream=True)
client = sseclient.SSEClient(response)

for event in client.events():
    data = json.loads(event.data)
    if data['type'] == 'token':
        print(data['content'], end='', flush=True)
    elif data['type'] == 'done':
        print('\nDone!')
        break
```
