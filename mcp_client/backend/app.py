# main.py

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List, Optional
import logging
import os
import dotenv
import uuid
import json
from sqlalchemy.orm import Session

dotenv.load_dotenv()
from models import (
    ServerConfigRequest, ServerResponse,
    ToolResponse, ChatRequest, ChatResponse,
    ToolInfo
)
from MCP_Client import UniversalMCPClient, ServerConfig
from ChatManager import ChatManager, Message
from database import get_db, init_db, ServerConfigModel, SessionModel, MessageModel

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global MCP Client (still needed as a singleton for connection pooling/management in this simple version, 
# but sessions will be handled separately)
# In a more advanced version, we might want a pool of clients or per-user clients if auth is involved.
# For now, we assume a single "backend" MCP client that connects to tools, and multiple chat sessions using it.
mcp_client: UniversalMCPClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle de l'app"""
    global mcp_client
    
    logger.info("🚀 Starting MCP Chat API...")
    
    # Initialize DB
    init_db()
    
    # Initialize MCP Client
    mcp_client = UniversalMCPClient()
    
    # Load saved servers from DB
    db = next(get_db())
    saved_configs = db.query(ServerConfigModel).all()
    
    if saved_configs:
        logger.info(f"Loading {len(saved_configs)} saved servers...")
        configs = []
        for sc in saved_configs:
            config_dict = sc.config
            # Reconstruct ServerConfig object
            configs.append(ServerConfig(**config_dict))
        
        await mcp_client.add_servers(configs, fail_fast=False)
    
    yield
    
    # Cleanup
    logger.info("🔌 Shutting down...")
    if mcp_client:
        await mcp_client.close_all()


# FastAPI app
app = FastAPI(
    title="MCP Chat API",
    description="Production-ready API for MCP chat with tool calling",
    version="2.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware pour logger toutes les requêtes
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log toutes les requêtes entrantes"""
    logger.info(f"📥 {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"📤 Response status: {response.status_code}")
    return response

# ============================================================================
# HELPERS
# ============================================================================

def get_chat_manager(session_id: str, db: Session) -> ChatManager:
    """Reconstruct ChatManager for a specific session"""
    # Get session history from DB
    db_session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    history = []
    for msg in db_session.messages:
        history.append(Message(
            role=msg.role,
            content=msg.content,
            tool_calls=[
                # Reconstruct tool calls if needed (simplified for now)
            ] if msg.tool_calls else None,
            tool_call_id=msg.tool_call_id,
            name=msg.name,
            timestamp=msg.timestamp
        ))
    
    return ChatManager(
        mcp_client=mcp_client,
        history=history
    )

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "servers_connected": len(mcp_client.list_servers()) if mcp_client else 0,
        "version": "2.0.0"
    }

# --- Server Management ---

@app.post("/servers/add", response_model=List[ServerResponse])
async def add_servers(configs: List[ServerConfigRequest], db: Session = Depends(get_db)):
    """Ajouter un ou plusieurs serveurs MCP et les sauvegarder"""
    if not mcp_client:
        raise HTTPException(status_code=500, detail="MCP client not initialized")
    
    try:
        # Convertir en liste de ServerConfig
        server_configs = []
        for config in configs:
            server_config = ServerConfig(
                name=config.name,
                transport=config.transport,
                command=config.command,
                args=config.args,
                env=config.env,
                url=config.url,
                headers=config.headers,
                timeout=config.timeout
            )
            server_configs.append(server_config)
            
            # Save to DB
            # Check if exists
            existing = db.query(ServerConfigModel).filter(ServerConfigModel.name == config.name).first()
            if existing:
                existing.config = server_config.__dict__
                existing.transport = config.transport
            else:
                db.add(ServerConfigModel(
                    name=config.name,
                    transport=config.transport,
                    config=server_config.__dict__
                ))
        
        db.commit()
        
        # Ajouter tous les serveurs au client actif
        results = await mcp_client.add_servers(server_configs, fail_fast=False)
        
        # Construire les réponses
        responses = []
        errors = []
        
        for config in configs:
            result = results.get(config.name)
            
            if isinstance(result, Exception):
                errors.append({
                    "name": config.name,
                    "error": str(result)
                })
            else:
                responses.append(ServerResponse(
                    name=result.name,
                    transport=result.config.transport,
                    tools_count=len(result.tools),
                    tools=[ToolInfo(
                        name=t.name,
                        description=t.description,
                        input_schema=t.inputSchema
                    ) for t in result.tools],
                    connected_at=result.connected_at
                ))
        
        if not responses and errors:
            raise HTTPException(
                status_code=500,
                detail=f"All servers failed to connect: {errors}"
            )
        
        return responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to add servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/servers", response_model=List[ServerResponse])
async def list_servers():
    """Lister tous les serveurs connectés"""
    if not mcp_client:
        return []
    
    servers = []
    for server_name in mcp_client.list_servers():
        server_info = mcp_client.get_server_info(server_name)
        if server_info:
            servers.append(ServerResponse(
                name=server_info.name,
                transport=server_info.config.transport,
                tools_count=len(server_info.tools),
                tools=[ToolInfo(
                    name=t.name,
                    description=t.description,
                    input_schema=t.inputSchema
                ) for t in server_info.tools],
                connected_at=server_info.connected_at
            ))
    
    return servers

@app.delete("/servers/{server_name}")
async def remove_server(server_name: str, db: Session = Depends(get_db)):
    """Supprimer un serveur"""
    if not mcp_client:
        raise HTTPException(status_code=500, detail="MCP client not initialized")
    
    # Remove from active client
    await mcp_client.close_server(server_name)
    
    # Remove from DB
    db.query(ServerConfigModel).filter(ServerConfigModel.name == server_name).delete()
    db.commit()
    
    return {"status": "removed", "name": server_name}

@app.get("/tools", response_model=List[ToolResponse])
async def list_tools():
    """Lister tous les tools disponibles"""
    if not mcp_client:
        return []
    
    tools = []
    all_tools = mcp_client.list_tools()
    
    for server_name, server_tools in all_tools.items():
        for tool in server_tools:
            tools.append(ToolResponse(
                server_name=server_name,
                tool_name=tool.name,
                full_name=f"{server_name}__{tool.name}",
                description=tool.description or ""
            ))
    
    return tools

# --- Chat / Session Management ---

@app.post("/sessions")
async def create_session(db: Session = Depends(get_db)):
    """Create a new chat session"""
    session_id = str(uuid.uuid4())
    new_session = SessionModel(id=session_id)
    db.add(new_session)
    db.commit()
    return {"session_id": session_id}

@app.get("/sessions")
async def list_sessions(db: Session = Depends(get_db)):
    """List all sessions"""
    sessions = db.query(SessionModel).order_by(SessionModel.created_at.desc()).all()
    return [{"id": s.id, "created_at": s.created_at, "message_count": len(s.messages)} for s in sessions]

@app.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, db: Session = Depends(get_db)):
    """Get history for a specific session"""
    db_session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return [
        {
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.timestamp
        }
        for msg in db_session.messages
    ]

@app.post("/chat/{session_id}", response_model=ChatResponse)
async def chat(session_id: str, request: ChatRequest, db: Session = Depends(get_db)):
    """Envoyer un message dans une session spécifique"""
    
    # 1. Get or create session
    db_session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 2. Reconstruct ChatManager with history
    # We need to convert DB messages back to Message objects
    history = []
    for msg in db_session.messages:
        # Simple reconstruction for now
        history.append(Message(
            role=msg.role,
            content=msg.content,
            # Note: Tool calls reconstruction omitted for brevity in this step, 
            # but would be needed for full context
        ))
    
    # Capture initial length BEFORE ChatManager modifies the list
    initial_history_count = len(history)
    
    chat_manager = ChatManager(
        mcp_client=mcp_client,
        history=history
    )
    
    try:
        # 3. Send message
        response_content = await chat_manager.send_message(request.message)
        
        # 4. Save new messages to DB
        # We only need to save the NEW messages added during this turn
        # The chat_manager.conversation_history has ALL messages.
        
        # Get the difference using the initial count
        new_messages = chat_manager.conversation_history[initial_history_count:]
        
        for msg in new_messages:
            db_msg = MessageModel(
                session_id=session_id,
                role=msg.role,
                content=msg.content,
                tool_calls=[tc.__dict__ for tc in msg.tool_calls] if msg.tool_calls else None,
                tool_call_id=msg.tool_call_id,
                name=msg.name,
                timestamp=msg.timestamp
            )
            db.add(db_msg)
        
        db.commit()
        
        return ChatResponse(
            message=response_content,
            tool_calls_count=sum(1 for m in new_messages if m.role == 'tool'),
            iterations=len(new_messages)
        )
        
    except Exception as e:
        logger.error(f"❌ Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)