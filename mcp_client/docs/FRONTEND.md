# Frontend Documentation

This document provides comprehensive documentation for the frontend, explaining **how the UI works**, **why it's designed this way**, and **how data flows through the application**.

## Table of Contents

1. [Overview](#overview)
2. [Understanding the Architecture](#understanding-the-architecture)
3. [Components Deep Dive](#components-deep-dive)
4. [The Streaming Challenge](#the-streaming-challenge)
5. [API Client](#api-client)
6. [State Management](#state-management)
7. [Styling Approach](#styling-approach)

---

## Overview

The frontend is a **React + TypeScript** single-page application (SPA) that provides a chat interface similar to Claude Desktop or ChatGPT.

### Key Features

- **Real-time streaming** - See the AI's response appear token by token
- **Tool visibility** - Watch as the AI calls external tools
- **Session management** - Multiple conversations with history
- **Collapsible tool outputs** - Large tool results don't clutter the UI

### Technology Choices

| Technology | Why We Use It |
|------------|---------------|
| **React** | Component-based UI, great ecosystem |
| **TypeScript** | Type safety, better IDE support |
| **Vite** | Fast dev server, quick builds |
| **TailwindCSS** | Rapid styling, consistent design |
| **React Router** | Client-side navigation between sessions |
| **React Markdown** | Render AI responses with formatting |

---

## Understanding the Architecture

### Component Hierarchy

```
App.tsx
└── BrowserRouter
    └── Routes
        └── Layout.tsx (persistent sidebar)
            ├── Sidebar
            │   ├── Logo
            │   ├── New Chat Button
            │   ├── Session List
            │   └── Settings Button
            │
            └── <Outlet> (renders child routes)
                └── ChatInterface.tsx (main chat area)
                    ├── Messages List
                    ├── Streaming Content
                    ├── Loading Indicator
                    └── Input Form
```

### Why This Structure?

**Layout with Outlet:**
The sidebar should persist across all views (different chat sessions). React Router's `<Outlet>` lets us define this "shell" once in Layout.tsx, and swap only the main content area.

```tsx
// Layout.tsx (simplified)
export function Layout() {
    return (
        <div className="flex">
            <Sidebar />           {/* Always visible */}
            <main>
                <Outlet />         {/* Changes based on URL */}
            </main>
        </div>
    );
}
```

---

## Components Deep Dive

### ChatInterface.tsx

This is the heart of the application - where messages are displayed and streaming happens.

#### State Variables Explained

```tsx
// Messages from the backend (persisted history)
const [messages, setMessages] = useState<Message[]>([]);

// Current text in the input field
const [input, setInput] = useState('');

// Are we waiting for a response?
const [isLoading, setIsLoading] = useState(false);

// Text currently being streamed (temporary display)
const [streamingContent, setStreamingContent] = useState<string>('');

// Is streaming actively happening?
const [isStreaming, setIsStreaming] = useState(false);

// Reference for auto-scrolling to bottom
const messagesEndRef = useRef<HTMLDivElement>(null);
```

**Why Two States for Content (`messages` vs `streamingContent`)?**

This is crucial for understanding the streaming approach:

```
BEFORE (problematic approach):
┌──────────────────────────────────────────────────┐
│ messages = [user_msg, partial_assistant_msg]     │
│                       │                          │
│         Update this every token ❌                │
│         Causes ordering issues with tool calls   │
└──────────────────────────────────────────────────┘

AFTER (our approach):
┌──────────────────────────────────────────────────┐
│ messages = [user_msg]  ← Stable, from backend    │
│                                                  │
│ streamingContent = "Currently streaming text..." │
│                    ← Visual only, temporary      │
│                                                  │
│ When done:                                       │
│ 1. Clear streamingContent                        │
│ 2. Reload messages from backend (correct order) │
└──────────────────────────────────────────────────┘
```

#### The handleSubmit Function

This is where all the streaming magic happens:

```tsx
const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Guard clauses
    if (!input.trim() || !sessionId || isLoading) return;

    // STEP 1: Optimistically add user message
    // We show it immediately, don't wait for the server
    const userMsg = { role: 'user', content: input, timestamp: new Date().toISOString() };
    setMessages(prev => [...prev, userMsg]);
    
    // STEP 2: Prepare for streaming
    const messageText = input;
    setInput('');           // Clear input immediately (better UX)
    setIsLoading(true);     // Show loading state
    setIsStreaming(true);   // Enable streaming display
    setStreamingContent(''); // Clear any previous streaming content

    try {
        // STEP 3: Connect to SSE endpoint
        mcpApi.streamMessage(sessionId, messageText, {
            
            // STEP 4a: Handle tokens
            onToken: (token) => {
                // Simply append to streaming content
                // React will re-render and show updated text
                setStreamingContent(prev => prev + token);
            },
            
            // STEP 4b: Handle tool calls
            onToolCall: (toolCall) => {
                // Show tool call inline with the streaming content
                // This is just for visual feedback
                setStreamingContent(prev => 
                    prev + `\n\n⏳ *Calling ${toolCall.server}.${toolCall.tool}...*\n\n`
                );
            },
            
            // STEP 4c: Handle tool results
            onToolResult: (result) => {
                const status = result.success ? '✅' : '❌';
                setStreamingContent(prev => 
                    prev + `${status} *${result.tool} completed*\n\n`
                );
            },
            
            // STEP 5: Stream complete
            onDone: () => {
                // Clear streaming state
                setIsStreaming(false);
                setStreamingContent('');
                setIsLoading(false);
                
                // CRITICAL: Reload history from backend
                // This gives us the correct message order including tool calls
                loadHistory(sessionId);
            },
            
            // Error handling
            onError: (error) => {
                setIsStreaming(false);
                setIsLoading(false);
                setStreamingContent('');
                // Show error message
                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: `Error: ${error}`,
                    timestamp: new Date().toISOString()
                }]);
            }
        });

    } catch (error) {
        // Handle connection errors
        setIsStreaming(false);
        setIsLoading(false);
        setStreamingContent('');
        // Show error...
    }
};
```

#### Why Reload History on Done?

You might ask: "Why not just add the streamed content to messages directly?"

The problem is **tool calls create multiple messages**, and the order matters:

```
User: "Tell me about React"
Assistant: "I'll look that up..." [partial]
Tool Call: deepwiki.read_wiki_structure
Tool Result: "Available pages: ..."
Assistant: "Based on the docs, React is..." [continuation]
```

If we try to manage this client-side, we get:
- Race conditions between events
- Wrong message order
- Duplicate messages

**Solution**: Let the frontend just display the stream visually, then reload the authoritative history from the backend.

#### CollapsibleToolOutput Component

Tool results can be very large (hundreds or thousands of characters). Showing them all inline would overwhelm the UI:

```tsx
const CollapsibleToolOutput = ({ name, content }) => {
    // Start collapsed by default
    const [isExpanded, setIsExpanded] = useState(false);
    
    // Show a preview (first 100 chars) when collapsed
    const preview = content && content.length > 100 
        ? content.substring(0, 100) + '...' 
        : content;
    
    return (
        <div>
            {/* Clickable header */}
            <button onClick={() => setIsExpanded(!isExpanded)}>
                {isExpanded ? <ChevronDown /> : <ChevronRight />}
                🔧 {name}
            </button>
            
            {/* Content - full or preview */}
            {isExpanded ? (
                <div className="full-content">
                    {content}
                </div>
            ) : (
                <div className="preview">
                    {preview}
                </div>
            )}
        </div>
    );
};
```

**Why This Design?**

1. **Default collapsed** - Keeps the UI clean
2. **Preview shown** - User knows there's content without expanding
3. **Click to expand** - User can see full content when needed
4. **Max height with scroll** - Even expanded, very long content doesn't break the layout

---

### Layout.tsx

The persistent layout that wraps all pages.

#### Session Management

```tsx
export function Layout() {
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    
    // Load sessions on mount
    useEffect(() => {
        loadSessions();
    }, []);
    
    const loadSessions = async () => {
        const data = await mcpApi.getSessions();
        setSessions(data);
    };
    
    const createNewSession = async () => {
        const { session_id } = await mcpApi.createSession();
        navigate(`/chat/${session_id}`);
        loadSessions(); // Refresh the list
    };
    
    // ...
}
```

**Why Load Sessions in Layout?**

The session list is in the sidebar (part of Layout). If we loaded it in ChatInterface, we'd lose it when navigating between sessions.

---

## The Streaming Challenge

### Understanding SSE (Server-Sent Events)

SSE is a standard for one-way real-time communication from server to client:

```
Client ─── GET /stream ───► Server
       ◄── text/event-stream ──
       ◄── data: {"type":"token","content":"Hello"}\n\n ──
       ◄── data: {"type":"token","content":" World"}\n\n ──
       ◄── data: {"type":"done",...}\n\n ──
       ─── Connection Closed ───
```

**Why SSE Instead of WebSocket?**

| SSE | WebSocket |
|-----|-----------|
| One-way (server → client) | Two-way |
| Standard HTTP | Separate protocol |
| Auto-reconnection | Manual reconnection |
| Simpler to implement | More complex |
| Perfect for our use case | Overkill for streaming |

### The EventSource API

Browsers provide `EventSource` for SSE connections:

```typescript
// Create connection
const eventSource = new EventSource(url);

// Handle connection open
eventSource.onopen = () => {
    console.log('Connected!');
};

// Handle incoming messages
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // Process data...
};

// Handle errors
eventSource.onerror = (error) => {
    console.error('Connection error:', error);
    eventSource.close(); // Close on error
};
```

### Event Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     STREAMING TIMELINE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  0ms     User clicks Send                                        │
│          │                                                       │
│  10ms    EventSource connects                                    │
│          │                                                       │
│  500ms   Connection established (onopen)                         │
│          │                                                       │
│  600ms   First token: "Hello"                                    │
│          │                                                       │
│  650ms   Second token: " there!"                                 │
│          │                                                       │
│  700ms   Third token: " I'll"                                    │
│          │                                                       │
│  ...     (continues for each token)                              │
│          │                                                       │
│  2000ms  Tool call detected                                      │
│          │                                                       │
│  5000ms  Tool result received                                    │
│          │                                                       │
│  5100ms  More tokens...                                          │
│          │                                                       │
│  8000ms  Done event received                                     │
│          │                                                       │
│  8001ms  Streaming display cleared                               │
│          │                                                       │
│  8050ms  History reloaded from backend                           │
│          │                                                       │
│          ▼                                                       │
│          Complete! User sees final message                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## API Client

### lib/api.ts Design

The API client encapsulates all backend communication:

```typescript
const API_BASE = 'http://localhost:8000';

export const mcpApi = {
    // Each method is a simple wrapper around fetch
    
    // Servers
    addServers: async (configs) => {
        const res = await fetch(`${API_BASE}/servers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configs)
        });
        return res.json();
    },
    
    // Sessions
    createSession: async () => {
        const res = await fetch(`${API_BASE}/sessions`, { method: 'POST' });
        return res.json();
    },
    
    // Streaming (special case - uses EventSource)
    streamMessage: (sessionId, message, callbacks) => {
        // Returns EventSource for caller to close if needed
        const url = `${API_BASE}/chat/${sessionId}/stream?message=${encodeURIComponent(message)}`;
        const eventSource = new EventSource(url);
        
        // Wire up callbacks...
        
        return eventSource;
    }
};
```

**Why Return EventSource?**

The caller might need to abort the stream (e.g., user navigates away):

```typescript
// In component
const eventSourceRef = useRef<EventSource | null>(null);

// When starting stream
eventSourceRef.current = mcpApi.streamMessage(...);

// When component unmounts
useEffect(() => {
    return () => {
        eventSourceRef.current?.close(); // Cleanup!
    };
}, []);
```

### Error Handling Strategy

```typescript
eventSource.onerror = (error) => {
    console.error('[SSE] Connection error:', error);
    console.log('[SSE] ReadyState:', eventSource.readyState);
    
    // ReadyState values:
    // 0 = CONNECTING (trying to reconnect)
    // 1 = OPEN (connected)
    // 2 = CLOSED (connection closed)
    
    if (eventSource.readyState === EventSource.CLOSED) {
        // Connection was closed, possibly by server completing
        console.log('[SSE] Connection closed');
    }
    
    // Always close and notify
    eventSource.close();
    callbacks.onError?.('Connection error');
};
```

---

## State Management

### Why No Redux/Zustand?

For this application, React's built-in state is sufficient:

| Concern | Solution |
|---------|----------|
| Component state | `useState` |
| Persistent values during render | `useRef` |
| Side effects | `useEffect` |
| Shared state | Props or context (minimal need) |

### State Location Guidelines

```
┌───────────────────────────────────────────────────────────────┐
│ Layout.tsx                                                     │
│ ├── sessions (list of all sessions)                           │
│ ├── showSettings (modal visibility)                           │
│ └── Connected servers (via Settings modal)                    │
├───────────────────────────────────────────────────────────────┤
│ ChatInterface.tsx                                              │
│ ├── messages (current session's history)                      │
│ ├── input (current input text)                                │
│ ├── isLoading / isStreaming (loading states)                  │
│ └── streamingContent (current streaming text)                 │
└───────────────────────────────────────────────────────────────┘
```

**Rule**: State lives in the component that needs it. Lift up only when multiple components need access.

---

## Styling Approach

### TailwindCSS Utility Classes

Instead of writing CSS files, we use utility classes directly:

```tsx
// Traditional CSS approach
<div className="message-container">...</div>
// .message-container { display: flex; gap: 1rem; padding: 1rem; }

// Tailwind approach
<div className="flex gap-4 p-4">...</div>
```

**Why Tailwind?**

1. **No context switching** - Write styles right where you use them
2. **Consistent spacing** - All values come from a design system
3. **No dead CSS** - Only used classes are in the final bundle
4. **Easy responsive** - `md:flex-row sm:flex-col`

### Common Patterns Used

```tsx
// Card with border and shadow
<div className="bg-card border rounded-lg shadow-sm">

// Flexbox with gap
<div className="flex gap-4 items-center">

// Markdown content styling
<div className="prose prose-sm dark:prose-invert">
    <ReactMarkdown>{content}</ReactMarkdown>
</div>

// Muted secondary text
<span className="text-muted-foreground text-sm">

// Button with hover state
<button className="px-4 py-2 bg-primary hover:bg-primary/90 rounded-lg">
```

### Dark Mode Support

The app uses TailwindCSS's dark mode with CSS variables:

```css
:root {
    --background: white;
    --foreground: black;
    --card: #f8f9fa;
}

@media (prefers-color-scheme: dark) {
    :root {
        --background: #1a1a1a;
        --foreground: white;
        --card: #2a2a2a;
    }
}
```

---

## Best Practices Summary

### 1. Always Clean Up

```tsx
useEffect(() => {
    return () => {
        eventSource?.close(); // Close SSE connections
    };
}, []);
```

### 2. Optimistic UI Updates

Show the user's message immediately, don't wait for the server:

```tsx
setMessages(prev => [...prev, userMsg]); // Immediate
// Then make the API call
```

### 3. Separate Streaming from Persistent State

```tsx
// Temporary (streaming)
const [streamingContent, setStreamingContent] = useState('');

// Permanent (from backend)
const [messages, setMessages] = useState([]);
```

### 4. Reload Source of Truth

After any complex operation, reload from the backend:

```tsx
onDone: () => {
    loadHistory(sessionId); // Get authoritative data
}
```

### 5. Console Logging for Debug

```tsx
console.log('[SSE] Connecting to:', url);
console.log('[SSE] Received event:', data);
console.log('[SSE] Stream complete');
```

Use prefixes like `[SSE]` to filter in browser console.
