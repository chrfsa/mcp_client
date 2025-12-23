# MCP Client - Chat Application with MCP Integration

A modern chat application that integrates the **Model Context Protocol (MCP)** to enable LLMs (Large Language Models) to use external tools in real-time.

![Architecture](https://img.shields.io/badge/Architecture-React%20%2B%20FastAPI-blue)
![MCP](https://img.shields.io/badge/MCP-Compatible-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 🎯 Features

- **Real-time chat** with token-by-token streaming
- **MCP integration** to connect external tool servers
- **Multi-transport support**: stdio, SSE, streamable HTTP
- **Persistent history** with SQLite
- **Modern interface** Claude Desktop style
- **Visible tool calls** with collapsible results

## 📁 Project Structure

```
mcp_client/
├── backend/                 # FastAPI Server
│   ├── app.py              # REST API & endpoints
│   ├── ChatManager.py      # LLM + Tools orchestration
│   ├── MCP_Client.py       # Universal MCP client
│   ├── database.py         # SQLAlchemy models
│   └── models.py           # Pydantic schemas
│
├── frontend/               # React Application
│   ├── src/
│   │   ├── components/     # UI Components
│   │   ├── lib/            # API client & utils
│   │   └── types/          # TypeScript types
│   └── package.json
│
├── docs/                   # Detailed documentation
│   ├── BACKEND.md          # Backend docs
│   ├── FRONTEND.md         # Frontend docs
│   └── API.md              # REST API docs
│
└── README.md               # This file
```

## 🚀 Installation

### Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **uv** (fast Python package manager)

### Backend

```bash
cd backend

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your OpenRouter key

# Start server
uv run uvicorn app:app --reload
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

## ⚙️ Configuration

### Environment Variables (backend/.env)

```env
OPENROUTER_API_KEY=sk-or-v1-xxxxx    # OpenRouter API key
DEFAULT_MODEL=anthropic/claude-3.5-sonnet
```

### Adding an MCP Server

Via API or interface:

```json
{
  "name": "deepwiki",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@anthropics/deepwiki-mcp"]
}
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React)                        │
│  ├─ ChatInterface.tsx    = Chat interface                   │
│  ├─ Layout.tsx           = Sidebar + Sessions               │
│  └─ api.ts               = HTTP Client + SSE                │
├─────────────────────────────────────────────────────────────┤
│                      Backend (FastAPI)                       │
│  ├─ app.py               = REST API & SSE Streaming         │
│  ├─ ChatManager          = LLM ↔ Tools Orchestration        │
│  └─ MCP_Client           = MCP server connections           │
├─────────────────────────────────────────────────────────────┤
│                    External MCP Servers                      │
│  └─ Tools (deepwiki, filesystem, git, etc.)                 │
└─────────────────────────────────────────────────────────────┘
```

## 📚 Documentation

- **[Backend Documentation](docs/BACKEND.md)** - MCP_Client, ChatManager classes, etc.
- **[Frontend Documentation](docs/FRONTEND.md)** - React components and data flow
- **[API Reference](docs/API.md)** - REST endpoints with examples

## 🔄 Data Flow

### Simple Message

```
User → Frontend → API → ChatManager → LLM → Response → Stream → Frontend
```

### With Tool Call

```
User → Frontend → API → ChatManager → LLM
                                      ↓
                              Tool Call Request
                                      ↓
                      ChatManager → MCP_Client → MCP Server
                                      ↓
                              Tool Result
                                      ↓
                      ChatManager → LLM → Final Response
                                      ↓
                              Stream → Frontend
```

## 🛠️ Development

### Useful Commands

```bash
# Backend - start with reload
cd backend && uv run uvicorn app:app --reload --port 8000

# Frontend - start dev server
cd frontend && npm run dev

# API tests with curl
curl http://localhost:8000/servers
curl http://localhost:8000/tools
```

### Logs and Debug

The backend displays detailed logs:
- 🔌 MCP server connections
- 🔧 Tool calls
- 🔄 LLM streaming
- ✅/❌ Results

## 📖 Technologies

| Component | Technologies |
|-----------|--------------|
| Backend | Python, FastAPI, SQLAlchemy, OpenAI SDK |
| Frontend | React, TypeScript, Vite, TailwindCSS |
| MCP | Protocol anthropic/mcp-sdk |
| LLM | OpenRouter (Claude, GPT-4, etc.) |

## 🐛 Troubleshooting

### "tool_use_id: Field required"
→ Tool messages must include `tool_call_id`. Check `reconstruct_message_from_db()`.

### Streaming not working
→ Check SSE headers and that `X-Accel-Buffering: no` is present.

### MCP Server not connecting
→ Verify the command exists and args are correct.

## 📝 License

MIT License - See [LICENSE](LICENSE) for details.

---

**Built with ❤️ to simplify MCP integration in chat applications.**
