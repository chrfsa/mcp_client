"""
Backend Configuration Constants

This module contains all configuration constants used across the backend.
Centralizing these values makes the codebase easier to maintain and configure.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# API Configuration
# =============================================================================

# OpenRouter API settings
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Default LLM model to use
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "anthropic/claude-3.5-sonnet")

# =============================================================================
# Chat Manager Defaults
# =============================================================================

# Maximum number of LLM iterations (prevents infinite loops)
MAX_CHAT_ITERATIONS = 10

# Default temperature for LLM responses (0.0 = deterministic, 1.0 = creative)
DEFAULT_TEMPERATURE = 0.7

# Default system prompt for the chat assistant
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant with access to MCP (Model Context Protocol) tools.

You can use these tools to:
- Access external data sources
- Execute operations on connected servers
- Retrieve information from various APIs

When using tools:
1. Explain what you're about to do
2. Call the appropriate tool
3. Interpret and explain the results

Always be helpful, accurate, and concise in your responses."""

# =============================================================================
# MCP Client Defaults
# =============================================================================

# Default timeout for MCP tool calls (seconds)
DEFAULT_TOOL_TIMEOUT = 30.0

# Default retry attempts when connecting to MCP servers
DEFAULT_RETRY_ATTEMPTS = 2

# Delay between connection retries (seconds)
DEFAULT_RETRY_DELAY = 2.0

# =============================================================================
# Database Configuration
# =============================================================================

# SQLite database file path
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mcp_chat.db")

# =============================================================================
# Server Configuration
# =============================================================================

# FastAPI server settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# CORS origins (comma-separated in env, or "*" for all)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# =============================================================================
# Logging Configuration
# =============================================================================

# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
