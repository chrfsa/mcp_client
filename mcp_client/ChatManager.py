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
