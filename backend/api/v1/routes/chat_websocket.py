"""
Real-time Chat Communication WebSocket Routes

WebSocket endpoints for real-time chat messaging with Cosmos AI integration.
Provides message streaming, typing indicators, and connection status management.
"""

import json
import asyncio
import uuid
from typing import Dict, Set, Optional, Any
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.websockets import WebSocketState
import structlog

try:
    # Try relative imports first (when used as module)
    from backend.services.cosmos_web_service import CosmosWebService
    from backend.services.cosmos_web_wrapper import CosmosWebWrapper
    from backend.services.redis_repo_manager import RedisRepoManager
    from backend.services.response_processor import ResponseProcessor
    from backend.utils.auth_utils import jwt_handler
except ImportError:
    # Fall back to absolute imports (when used directly)
    from services.cosmos_web_service import CosmosWebService
    from services.cosmos_web_wrapper import CosmosWebWrapper
    from services.redis_repo_manager import RedisRepoManager
    from services.response_processor import ResponseProcessor
    from utils.auth_utils import jwt_handler

logger = structlog.get_logger(__name__)
router = APIRouter()


class MessageType(str, Enum):
    """WebSocket message types."""
    # Connection management
    CONNECTION_ESTABLISHED = "connection_established"
    CONNECTION_STATUS = "connection_status"
    HEARTBEAT = "heartbeat"
    
    # Chat messages
    USER_MESSAGE = "user_message"
    AI_RESPONSE = "ai_response"
    AI_RESPONSE_CHUNK = "ai_response_chunk"
    AI_RESPONSE_COMPLETE = "ai_response_complete"
    
    # Status indicators
    TYPING_START = "typing_start"
    TYPING_STOP = "typing_stop"
    PROCESSING_START = "processing_start"
    PROCESSING_STOP = "processing_stop"
    
    # Message delivery
    MESSAGE_DELIVERED = "message_delivered"
    MESSAGE_FAILED = "message_failed"
    
    # Errors
    ERROR = "error"
    VALIDATION_ERROR = "validation_error"
    
    # Session management
    SESSION_UPDATED = "session_updated"
    CONTEXT_UPDATED = "context_updated"


class ConnectionStatus(str, Enum):
    """Connection status types."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class ChatConnectionManager:
    """Manages WebSocket connections for chat sessions."""
    
    def __init__(self):
        # Active connections: connection_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        
        # Session connections: session_id -> set of connection_ids
        self.session_connections: Dict[str, Set[str]] = {}
        
        # Connection metadata: connection_id -> metadata
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        
        # User connections: user_id -> set of connection_ids
        self.user_connections: Dict[str, Set[str]] = {}
        
        # Typing indicators: session_id -> set of connection_ids currently typing
        self.typing_indicators: Dict[str, Set[str]] = {}
    
    async def connect(
        self, 
        websocket: WebSocket, 
        connection_id: str, 
        session_id: str,
        user_id: str = None
    ):
        """Accept a WebSocket connection and store it."""
        await websocket.accept()
        
        # Store connection
        self.active_connections[connection_id] = websocket
        
        # Associate with session
        if session_id not in self.session_connections:
            self.session_connections[session_id] = set()
        self.session_connections[session_id].add(connection_id)
        
        # Associate with user
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(connection_id)
        
        # Store metadata
        self.connection_metadata[connection_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "connected_at": datetime.now(),
            "last_heartbeat": datetime.now(),
            "message_count": 0
        }
        
        logger.info(
            "Chat WebSocket connected",
            connection_id=connection_id,
            session_id=session_id,
            user_id=user_id
        )
    
    def disconnect(self, connection_id: str):
        """Remove a WebSocket connection."""
        if connection_id not in self.connection_metadata:
            return
        
        metadata = self.connection_metadata[connection_id]
        session_id = metadata.get("session_id")
        user_id = metadata.get("user_id")
        
        # Remove from active connections
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        # Remove from session connections
        if session_id and session_id in self.session_connections:
            self.session_connections[session_id].discard(connection_id)
            if not self.session_connections[session_id]:
                del self.session_connections[session_id]
        
        # Remove from user connections
        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        # Remove from typing indicators
        if session_id and session_id in self.typing_indicators:
            self.typing_indicators[session_id].discard(connection_id)
            if not self.typing_indicators[session_id]:
                del self.typing_indicators[session_id]
        
        # Remove metadata
        del self.connection_metadata[connection_id]
        
        logger.info(
            "Chat WebSocket disconnected",
            connection_id=connection_id,
            session_id=session_id,
            user_id=user_id
        )
    
    async def send_to_connection(self, connection_id: str, message: Dict[str, Any]) -> bool:
        """Send message to a specific connection."""
        if connection_id not in self.active_connections:
            return False
        
        websocket = self.active_connections[connection_id]
        if websocket.client_state != WebSocketState.CONNECTED:
            return False
        
        try:
            # Add timestamp and message ID if not present
            if "timestamp" not in message:
                message["timestamp"] = datetime.now().isoformat()
            if "message_id" not in message:
                message["message_id"] = str(uuid.uuid4())
            
            await websocket.send_json(message)
            
            # Update message count
            if connection_id in self.connection_metadata:
                self.connection_metadata[connection_id]["message_count"] += 1
            
            return True
            
        except Exception as e:
            logger.error(
                "Error sending WebSocket message",
                error=str(e),
                connection_id=connection_id
            )
            return False
    
    async def broadcast_to_session(self, session_id: str, message: Dict[str, Any], exclude_connection: str = None) -> int:
        """Broadcast message to all connections in a session."""
        if session_id not in self.session_connections:
            return 0
        
        success_count = 0
        connections = list(self.session_connections[session_id])
        
        for connection_id in connections:
            if exclude_connection and connection_id == exclude_connection:
                continue
            
            if await self.send_to_connection(connection_id, message):
                success_count += 1
        
        return success_count
    
    async def send_typing_indicator(self, session_id: str, connection_id: str, is_typing: bool):
        """Send typing indicator to other connections in the session."""
        if session_id not in self.typing_indicators:
            self.typing_indicators[session_id] = set()
        
        if is_typing:
            self.typing_indicators[session_id].add(connection_id)
        else:
            self.typing_indicators[session_id].discard(connection_id)
        
        # Broadcast typing status to other connections
        message = {
            "type": MessageType.TYPING_START if is_typing else MessageType.TYPING_STOP,
            "session_id": session_id,
            "connection_id": connection_id,
            "typing_users": len(self.typing_indicators[session_id])
        }
        
        await self.broadcast_to_session(session_id, message, exclude_connection=connection_id)
    
    def get_connection_status(self, connection_id: str) -> Dict[str, Any]:
        """Get status information for a connection."""
        if connection_id not in self.connection_metadata:
            return {"status": ConnectionStatus.DISCONNECTED}
        
        metadata = self.connection_metadata[connection_id]
        websocket = self.active_connections.get(connection_id)
        
        return {
            "status": ConnectionStatus.CONNECTED if websocket and websocket.client_state == WebSocketState.CONNECTED else ConnectionStatus.DISCONNECTED,
            "connected_at": metadata["connected_at"].isoformat(),
            "last_heartbeat": metadata["last_heartbeat"].isoformat(),
            "message_count": metadata["message_count"],
            "session_id": metadata["session_id"],
            "user_id": metadata["user_id"]
        }
    
    async def update_heartbeat(self, connection_id: str):
        """Update heartbeat timestamp for a connection."""
        if connection_id in self.connection_metadata:
            self.connection_metadata[connection_id]["last_heartbeat"] = datetime.now()


# Create global connection manager
chat_manager = ChatConnectionManager()

# Initialize services
cosmos_service = CosmosWebService()
response_processor = ResponseProcessor()


async def get_cosmos_wrapper(session_id: str, user_id: str) -> CosmosWebWrapper:
    """Get or create a Cosmos wrapper for the session."""
    try:
        # Get session info
        session = await cosmos_service.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Use session repository info
        repo_url = session.repository_url
        repo_branch = session.branch or "main"
        
        if not repo_url:
            raise ValueError("Repository URL is required")
        
        # Create repository manager
        repo_manager = RedisRepoManager(
            repo_url=repo_url,
            branch=repo_branch,
            user_tier="free",  # TODO: Get from user context
            username=user_id
        )
        
        # Create wrapper
        wrapper = CosmosWebWrapper(
            repo_manager=repo_manager,
            model=session.model,
            user_id=user_id
        )
        
        # Add context files from session
        for context_file in session.context_files:
            wrapper.add_file_to_context(context_file.path)
        
        return wrapper
        
    except Exception as e:
        logger.error(f"Error creating Cosmos wrapper: {e}")
        raise ValueError(f"Failed to initialize Cosmos wrapper: {str(e)}")


@router.websocket("/chat/ws")
async def chat_websocket_endpoint(
    websocket: WebSocket,
    session_id: str = Query(..., description="Chat session ID"),
    token: str = Query(None, description="Authentication token"),
    user_id: str = Query(None, description="User ID")
):
    """
    WebSocket endpoint for real-time chat communication.
    
    Supports:
    - Real-time messaging with AI responses
    - Message streaming for long responses
    - Typing indicators and connection status
    - Message delivery confirmation
    - Error handling and recovery
    """
    
    connection_id = str(uuid.uuid4())
    
    # Validate authentication
    if token:
        try:
            payload = jwt_handler.decode_token(token)
            user_id = payload.get("user_id")
        except Exception as e:
            await websocket.close(code=1008, reason="Invalid authentication token")
            return
    
    # Validate session exists
    try:
        session = await cosmos_service.get_session(session_id)
        if not session:
            await websocket.close(code=1008, reason="Session not found")
            return
    except Exception as e:
        await websocket.close(code=1011, reason="Session validation failed")
        return
    
    # Connect to WebSocket
    try:
        await chat_manager.connect(websocket, connection_id, session_id, user_id)
        
        # Send connection established message
        await chat_manager.send_to_connection(connection_id, {
            "type": MessageType.CONNECTION_ESTABLISHED,
            "connection_id": connection_id,
            "session_id": session_id,
            "user_id": user_id,
            "status": ConnectionStatus.CONNECTED
        })
        
        # Initialize Cosmos wrapper
        cosmos_wrapper = None
        try:
            cosmos_wrapper = await get_cosmos_wrapper(session_id, user_id or "anonymous")
        except Exception as e:
            await chat_manager.send_to_connection(connection_id, {
                "type": MessageType.ERROR,
                "error": "cosmos_initialization_failed",
                "message": f"Failed to initialize AI assistant: {str(e)}"
            })
        
        # Message processing loop
        try:
            while True:
                # Wait for messages
                data = await websocket.receive_text()
                
                try:
                    message = json.loads(data)
                    message_type = message.get("type")
                    message_id = message.get("message_id", str(uuid.uuid4()))
                    
                    # Update heartbeat
                    await chat_manager.update_heartbeat(connection_id)
                    
                    # Handle different message types
                    if message_type == MessageType.HEARTBEAT:
                        await chat_manager.send_to_connection(connection_id, {
                            "type": MessageType.HEARTBEAT,
                            "message_id": message_id,
                            "status": ConnectionStatus.CONNECTED
                        })
                    
                    elif message_type == MessageType.TYPING_START:
                        await chat_manager.send_typing_indicator(session_id, connection_id, True)
                    
                    elif message_type == MessageType.TYPING_STOP:
                        await chat_manager.send_typing_indicator(session_id, connection_id, False)
                    
                    elif message_type == MessageType.USER_MESSAGE:
                        await handle_user_message(
                            connection_id, session_id, message, cosmos_wrapper, user_id
                        )
                    
                    elif message_type == "get_connection_status":
                        status = chat_manager.get_connection_status(connection_id)
                        await chat_manager.send_to_connection(connection_id, {
                            "type": MessageType.CONNECTION_STATUS,
                            "message_id": message_id,
                            **status
                        })
                    
                    else:
                        await chat_manager.send_to_connection(connection_id, {
                            "type": MessageType.VALIDATION_ERROR,
                            "message_id": message_id,
                            "error": f"Unknown message type: {message_type}"
                        })
                
                except json.JSONDecodeError:
                    await chat_manager.send_to_connection(connection_id, {
                        "type": MessageType.ERROR,
                        "error": "invalid_json",
                        "message": "Invalid JSON format"
                    })
                
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {e}")
                    await chat_manager.send_to_connection(connection_id, {
                        "type": MessageType.ERROR,
                        "error": "message_processing_failed",
                        "message": f"Error processing message: {str(e)}"
                    })
        
        except WebSocketDisconnect:
            chat_manager.disconnect(connection_id)
        
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if hasattr(websocket, 'client_state') and websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011, reason="Internal server error")
        chat_manager.disconnect(connection_id)


async def handle_user_message(
    connection_id: str,
    session_id: str,
    message: Dict[str, Any],
    cosmos_wrapper: Optional[CosmosWebWrapper],
    user_id: str
):
    """Handle user message and generate AI response."""
    message_id = message.get("message_id", str(uuid.uuid4()))
    content = message.get("content", "")
    
    if not content.strip():
        await chat_manager.send_to_connection(connection_id, {
            "type": MessageType.VALIDATION_ERROR,
            "message_id": message_id,
            "error": "Empty message content"
        })
        return
    
    try:
        # Send message delivered confirmation
        await chat_manager.send_to_connection(connection_id, {
            "type": MessageType.MESSAGE_DELIVERED,
            "message_id": message_id,
            "original_message": content[:100] + "..." if len(content) > 100 else content
        })
        
        # Add user message to session
        user_message_id = await cosmos_service.add_message(
            session_id=session_id,
            role="user",
            content=content,
            metadata={"connection_id": connection_id, "websocket_message_id": message_id}
        )
        
        # Send processing start indicator
        await chat_manager.broadcast_to_session(session_id, {
            "type": MessageType.PROCESSING_START,
            "message_id": message_id,
            "session_id": session_id
        })
        
        # Generate AI response
        if not cosmos_wrapper:
            # Fallback error response
            error_response = "AI assistant is not available. Please try again later."
            
            await cosmos_service.add_message(
                session_id=session_id,
                role="assistant",
                content=error_response,
                metadata={"error": "cosmos_wrapper_unavailable"}
            )
            
            await chat_manager.send_to_connection(connection_id, {
                "type": MessageType.AI_RESPONSE_COMPLETE,
                "message_id": str(uuid.uuid4()),
                "content": error_response,
                "is_error": True
            })
            
        else:
            # Process message with Cosmos
            try:
                # Start streaming response
                response_id = str(uuid.uuid4())
                full_response = ""
                
                # Get AI response (this should be streaming in a real implementation)
                cosmos_response = await cosmos_wrapper.process_message(
                    message=content,
                    context={"session_id": session_id, "user_id": user_id}
                )
                
                # Process response for web display
                processed_response = response_processor.process_cosmos_response(cosmos_response)
                
                # Stream response in chunks (simulate streaming)
                response_content = processed_response.content
                chunk_size = 50  # Characters per chunk
                
                for i in range(0, len(response_content), chunk_size):
                    chunk = response_content[i:i + chunk_size]
                    full_response += chunk
                    
                    await chat_manager.send_to_connection(connection_id, {
                        "type": MessageType.AI_RESPONSE_CHUNK,
                        "response_id": response_id,
                        "chunk": chunk,
                        "chunk_index": i // chunk_size,
                        "is_final": i + chunk_size >= len(response_content)
                    })
                    
                    # Small delay to simulate streaming
                    await asyncio.sleep(0.1)
                
                # Send complete response
                await chat_manager.send_to_connection(connection_id, {
                    "type": MessageType.AI_RESPONSE_COMPLETE,
                    "response_id": response_id,
                    "content": full_response,
                    "metadata": {
                        "model": cosmos_response.model_used,
                        "context_files_used": processed_response.context_files_used,
                        "shell_commands_converted": processed_response.shell_commands_converted,
                        "conversion_notes": processed_response.conversion_notes
                    }
                })
                
                # Add AI response to session
                await cosmos_service.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    metadata={
                        "model": cosmos_response.model_used,
                        "response_id": response_id,
                        "connection_id": connection_id
                    },
                    context_files_used=processed_response.context_files_used,
                    shell_commands_converted=processed_response.shell_commands_converted,
                    conversion_notes=processed_response.conversion_notes
                )
                
            except Exception as e:
                logger.error(f"Error generating AI response: {e}")
                
                error_response = f"Sorry, I encountered an error while processing your message: {str(e)}"
                
                await cosmos_service.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=error_response,
                    metadata={"error": str(e)}
                )
                
                await chat_manager.send_to_connection(connection_id, {
                    "type": MessageType.MESSAGE_FAILED,
                    "message_id": message_id,
                    "error": str(e),
                    "fallback_response": error_response
                })
        
        # Send processing stop indicator
        await chat_manager.broadcast_to_session(session_id, {
            "type": MessageType.PROCESSING_STOP,
            "message_id": message_id,
            "session_id": session_id
        })
        
    except Exception as e:
        logger.error(f"Error handling user message: {e}")
        await chat_manager.send_to_connection(connection_id, {
            "type": MessageType.MESSAGE_FAILED,
            "message_id": message_id,
            "error": str(e)
        })


# Health check endpoint for WebSocket service
@router.get("/chat/ws/health")
async def websocket_health():
    """Health check for WebSocket chat service."""
    return {
        "status": "healthy",
        "active_connections": len(chat_manager.active_connections),
        "active_sessions": len(chat_manager.session_connections),
        "timestamp": datetime.now().isoformat()
    }


# Get connection statistics
@router.get("/chat/ws/stats")
async def websocket_stats():
    """Get WebSocket connection statistics."""
    return {
        "active_connections": len(chat_manager.active_connections),
        "active_sessions": len(chat_manager.session_connections),
        "active_users": len(chat_manager.user_connections),
        "typing_sessions": len(chat_manager.typing_indicators),
        "connection_metadata": {
            conn_id: {
                "session_id": meta["session_id"],
                "user_id": meta["user_id"],
                "connected_at": meta["connected_at"].isoformat(),
                "message_count": meta["message_count"]
            }
            for conn_id, meta in chat_manager.connection_metadata.items()
        }
    }