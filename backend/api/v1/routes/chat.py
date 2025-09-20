"""
Chat API routes using Cosmos AI Integration
"""
import uuid
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
import structlog

from .dependencies import get_current_user
from models.api.auth_models import User

# Safe imports for Cosmos integration
try:
    from integrations.cosmos.v1.cosmos_wrapper import GitMeshCosmosWrapper
    COSMOS_AVAILABLE = True
except ImportError:
    COSMOS_AVAILABLE = False
    GitMeshCosmosWrapper = None

logger = structlog.get_logger(__name__)
router = APIRouter()

# In-memory storage for demo (in production, use database)
chat_sessions: Dict[str, Dict[str, Any]] = {}
chat_messages: Dict[str, List[Dict[str, Any]]] = {}

class ChatCosmosService:
    """Service to bridge chat interface to Cosmos AI system"""
    
    def __init__(self):
        if COSMOS_AVAILABLE:
            self.cosmos_available = True
        else:
            self.cosmos_available = False
    
    def _generate_intelligent_response(self, message: str, context: Dict[str, Any] = None) -> str:
        """Generate an intelligent response based on message content when TARS is not available"""
        message_lower = message.lower().strip()
        
        # Code-related queries
        if any(word in message_lower for word in ['code', 'function', 'class', 'method', 'variable', 'bug', 'error', 'debug']):
            return f"I can help you analyze the code. Based on your message about '{message}', I'd need to examine the relevant files in your repository. Could you share more context about which files or components you're working with?"
        
        # Repository queries
        elif any(word in message_lower for word in ['repo', 'repository', 'branch', 'commit', 'file', 'directory']):
            return f"I can help you explore the repository structure. For your question about '{message}', I can analyze the codebase and provide insights. What specific aspect would you like me to focus on?"
        
        # Documentation queries
        elif any(word in message_lower for word in ['how', 'what', 'why', 'explain', 'documentation', 'readme']):
            return f"I'll help explain that for you. Regarding '{message}', let me analyze the available documentation and code to provide you with a comprehensive answer. What level of detail would be most helpful?"
        
        # Implementation queries
        elif any(word in message_lower for word in ['implement', 'create', 'build', 'develop', 'add', 'feature']):
            return f"I can assist with implementation. For '{message}', I'll need to understand the current codebase structure and requirements. Could you provide more details about what you're trying to achieve?"
        
        # General questions
        elif any(word in message_lower for word in ['help', 'support', 'assist', 'guide']):
            return f"I'm here to help! Regarding '{message}', I can analyze your codebase, explain functionality, help with debugging, or assist with implementation. What would be most useful for you right now?"
        
        # Default intelligent response
        else:
            return f"I understand you're asking about: '{message}'. I can analyze your codebase and provide insights. Could you provide a bit more context about what you're trying to accomplish or which part of the project you're focusing on?"
    
    async def create_session(self, user_id: str, title: str = None, repository_id: str = None, branch: str = None, repository_url: str = None):
        """Create a new chat session"""
        session_id = str(uuid.uuid4())
        
        # Auto-detect repository context if not provided
        if not repository_id and not repository_url:
            # This would typically come from the current user's repository context
            # For now, we'll use a default that can be overridden by the frontend
            repository_id = "default"
            repository_url = None
        
        session = {
            "id": session_id,
            "title": title or f"Chat Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "repositoryId": repository_id,
            "repositoryUrl": repository_url,
            "branch": branch or "main",
            "messages": [],
            "selectedFiles": [],
            "createdAt": datetime.now().isoformat(),
            "updatedAt": datetime.now().isoformat(),
            "userId": user_id,
            "cosmosReady": self.cosmos_available and COSMOS_AVAILABLE
        }
        
        chat_sessions[session_id] = session
        chat_messages[session_id] = []
        
        # Initialize Cosmos session if available
        if self.cosmos_available and COSMOS_AVAILABLE:
            try:
                from integrations.cosmos.v1.cosmos_wrapper import session_manager
                wrapper = session_manager.get_wrapper(
                    user_id=user_id,
                    repository_id=repository_id or "default",
                    branch=branch or "main"
                )
                logger.info(f"Initialized Cosmos session for {session_id}")
            except Exception as e:
                logger.error(f"Error initializing Cosmos session: {e}")
        
        return session
    
    async def get_session(self, session_id: str, user_id: str):
        """Get a chat session"""
        if session_id not in chat_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = chat_sessions[session_id]
        if session.get("userId") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Include messages
        session["messages"] = chat_messages.get(session_id, [])
        return session
    
    async def send_message(self, session_id: str, user_id: str, message: str, context: Dict[str, Any] = None, model_name: str = "gpt-4o-mini"):
        """Send a message and get AI response via Cosmos"""
        if session_id not in chat_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = chat_sessions[session_id]
        if session.get("userId") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Debug: Log the incoming request
        logger.info(f"Chat request - session: {session_id}, model: {model_name}, message: {message[:100]}...")
        logger.info(f"Chat context received: {context}")
        if context and context.get("files"):
            files = context.get("files", [])
            logger.info(f"Files in context: {len(files)} files")
            for i, file in enumerate(files[:3]):  # Log first 3 files
                logger.info(f"  File {i+1}: {file.get('path', 'unknown')} - content length: {len(file.get('content', ''))}")
        
        # Create user message
        user_message = {
            "id": str(uuid.uuid4()),
            "type": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
            "files": [],
            "model": model_name
        }
        
        # Add user message to history
        if session_id not in chat_messages:
            chat_messages[session_id] = []
        chat_messages[session_id].append(user_message)
        
        # Generate AI response via Cosmos with full AI capabilities
        confidence = 0.8
        knowledge_used = 0
        sources = []
        model_used = model_name
        
        try:
            if self.cosmos_available and COSMOS_AVAILABLE:
                # Get or create Cosmos wrapper for this session using session manager
                from integrations.cosmos.v1.cosmos_wrapper import session_manager
                wrapper = session_manager.get_wrapper(
                    user_id=user_id,
                    repository_id=session.get("repositoryId", "default"),
                    branch=session.get("branch", "main")
                )
                
                # Get chat history for context
                session_history = chat_messages.get(session_id, [])
                
                # Build enhanced context with repository information
                enhanced_context = context or {}
                
                # Extract repository URL from different possible sources
                repository_url = None
                
                # Method 1: From session repositoryId (most common case)
                if session.get("repositoryId"):
                    repo_id = session["repositoryId"]
                    if "/" in repo_id and not repo_id.startswith("http"):
                        # Format: "owner/repo" -> "https://github.com/owner/repo"
                        repository_url = f"https://github.com/{repo_id}"
                        logger.info(f"Repository URL from session: {repository_url}")
                    elif repo_id.startswith("http"):
                        repository_url = repo_id
                
                # Method 2: From context repository_id
                if not repository_url and context and context.get("repository_id"):
                    repo_id = context["repository_id"]
                    if "/" in repo_id and not repo_id.startswith("http"):
                        repository_url = f"https://github.com/{repo_id}"
                        logger.info(f"Repository URL from request: {repository_url}")
                    elif repo_id.startswith("http"):
                        repository_url = repo_id
                
                # Method 3: From context.repository (legacy)
                if not repository_url and context and context.get("repository"):
                    repo_info = context["repository"]
                    if isinstance(repo_info, dict):
                        # Build GitHub URL from repository info
                        owner = repo_info.get("owner", "")
                        name = repo_info.get("name", "")
                        if owner and name:
                            repository_url = f"https://github.com/{owner}/{name}"
                            logger.info(f"Repository URL from context dict: {repository_url}")
                    elif isinstance(repo_info, str) and repo_info.startswith("http"):
                        # Direct URL provided
                        repository_url = repo_info
                        logger.info(f"Repository URL from context string: {repository_url}")
                
                # Method 4: Extract from files context (if available)
                if not repository_url and context and context.get("files"):
                    files = context["files"]
                    if files and len(files) > 0:
                        first_file = files[0]
                        if isinstance(first_file, dict):
                            owner = first_file.get("owner")
                            repo = first_file.get("repo")
                            if owner and repo:
                                repository_url = f"https://github.com/{owner}/{repo}"
                                logger.info(f"Repository URL from file context: {repository_url}")
                
                # Set the repository URL in enhanced context
                if repository_url:
                    enhanced_context["repository_url"] = repository_url
                    logger.info(f"Using repository URL for Cosmos: {repository_url}")
                else:
                    logger.warning("No repository URL found in request - Cosmos will not have repository context")
                
                # Add branch info
                if session.get("branch"):
                    enhanced_context["branch"] = session["branch"]
                elif context and context.get("branch"):
                    enhanced_context["branch"] = context["branch"]
                
                # Process message through comprehensive Cosmos AI system
                cosmos_response = await wrapper.process_chat_message(
                    message=message,
                    context=enhanced_context,
                    session_history=session_history,
                    selected_files=session.get("selectedFiles", []),
                    model_name=model_name
                )
                
                # Extract content and metadata
                assistant_content = cosmos_response.get("content", "I'm processing your request...")
                confidence = cosmos_response.get("confidence", 0.8)
                sources = cosmos_response.get("sources", [])
                knowledge_used = cosmos_response.get("knowledge_entries_used", 0)
                model_used = cosmos_response.get("model_used", model_name)
                
                # Add metadata to response if available
                if knowledge_used > 0:
                    assistant_content += f"\n\n*Analyzed {knowledge_used} files from your codebase*"
                
                if sources:
                    source_names = [s.split('/')[-1] for s in sources[:3]]  # Get file names
                    assistant_content += f"\n\n*Referenced files: {', '.join(source_names)}*"
                
            else:
                # Intelligent fallback when Cosmos is not available
                assistant_content = self._generate_intelligent_response(message, context)
                model_used = "fallback"
        
        except Exception as e:
            logger.error(f"Error processing message with Cosmos: {e}")
            assistant_content = f"I encountered an error accessing the AI system. Let me help you with: '{message}'. Could you provide more context about what you're trying to accomplish?"
            model_used = "error_fallback"
        
        # Create assistant message
        assistant_message = {
            "id": str(uuid.uuid4()),
            "type": "assistant", 
            "content": assistant_content,
            "timestamp": datetime.now().isoformat(),
            "files": [],
            "model": model_used,
            "metadata": {
                "confidence": confidence,
                "knowledge_used": knowledge_used,
                "sources_count": len(sources),
                "cosmos_available": self.cosmos_available and COSMOS_AVAILABLE
            }
        }
        
        # Add assistant message to history
        chat_messages[session_id].append(assistant_message)
        
        # Update session timestamp
        session["updatedAt"] = datetime.now().isoformat()
        session["messages"] = chat_messages[session_id]
        
        return {
            "userMessage": user_message,
            "assistantMessage": assistant_message,
            "session": session
        }

# Initialize service
chat_service = ChatCosmosService()

@router.post("/sessions")
async def create_chat_session(
    request: Dict[str, Any],
    current_user: Optional[User] = Depends(get_current_user)
):
    """Create a new chat session"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        session = await chat_service.create_session(
            user_id=str(current_user.id),
            title=request.get("title"),
            repository_id=request.get("repositoryId"),
            repository_url=request.get("repositoryUrl"),
            branch=request.get("branch", "main")
        )
        
        return {
            "success": True,
            "session": session
        }
    except Exception as e:
        logger.error(f"Error creating chat session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")

@router.get("/sessions/{session_id}")
async def get_chat_session(
    session_id: str,
    current_user: Optional[User] = Depends(get_current_user)
):
    """Get a chat session"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        session = await chat_service.get_session(session_id, str(current_user.id))
        return {
            "success": True,
            "session": session
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat session: {e}")
        raise HTTPException(status_code=500, detail="Failed to get session")

@router.put("/sessions/{session_id}")
async def update_chat_session(
    session_id: str,
    updates: Dict[str, Any],
    current_user: Optional[User] = Depends(get_current_user)
):
    """Update a chat session"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        if session_id not in chat_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = chat_sessions[session_id]
        if session.get("userId") != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Update allowed fields
        allowed_fields = ["title", "selectedFiles"]
        for field in allowed_fields:
            if field in updates:
                session[field] = updates[field]
        
        session["updatedAt"] = datetime.now().isoformat()
        
        return {
            "success": True,
            "session": session
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating chat session: {e}")
        raise HTTPException(status_code=500, detail="Failed to update session")

@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    current_user: Optional[User] = Depends(get_current_user)
):
    """Delete a chat session"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        if session_id not in chat_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = chat_sessions[session_id]
        if session.get("userId") != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Delete session and messages
        del chat_sessions[session_id]
        if session_id in chat_messages:
            del chat_messages[session_id]
        
        return {
            "success": True,
            "message": "Session deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat session: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete session")

@router.get("/users/{user_id}/sessions")
async def get_user_sessions(
    user_id: str,
    current_user: Optional[User] = Depends(get_current_user)
):
    """Get all sessions for a user"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        user_sessions = []
        for session in chat_sessions.values():
            if session.get("userId") == user_id:
                session_copy = session.copy()
                session_copy["messages"] = chat_messages.get(session["id"], [])
                user_sessions.append(session_copy)
        
        # Sort by updated time (newest first)
        user_sessions.sort(key=lambda x: x["updatedAt"], reverse=True)
        
        return {
            "success": True,
            "sessions": user_sessions
        }
    except Exception as e:
        logger.error(f"Error getting user sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sessions")

@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    request: Dict[str, Any],
    current_user: Optional[User] = Depends(get_current_user)
):
    """Send a message in a chat session"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        message = request.get("message", "")
        context = request.get("context", {})
        model_name = request.get("model", "gpt-4o-mini")  # Default model
        
        if not message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        result = await chat_service.send_message(
            session_id=session_id,
            user_id=str(current_user.id),
            message=message,
            context=context,
            model_name=model_name
        )
        
        return {
            "success": True,
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail="Failed to send message")

@router.get("/sessions/{session_id}/messages")
async def get_chat_history(
    session_id: str,
    current_user: Optional[User] = Depends(get_current_user)
):
    """Get chat history for a session"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        session = await chat_service.get_session(session_id, str(current_user.id))
        messages = chat_messages.get(session_id, [])
        
        return {
            "success": True,
            "messages": messages,
            "session": session
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get chat history")

@router.get("/sessions/{session_id}/context/stats")
async def get_session_context_stats(
    session_id: str,
    current_user: Optional[User] = Depends(get_current_user)
):
    """Get context stats for a session"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        session = await chat_service.get_session(session_id, str(current_user.id))
        selected_files = session.get("selectedFiles", [])
        
        stats = {
            "totalFiles": len(selected_files),
            "totalSources": len(selected_files),
            "totalTokens": sum(len(f.get("content", "").split()) for f in selected_files),
            "averageTokensPerFile": 0,
            "createdAt": session["createdAt"],
            "updatedAt": session["updatedAt"]
        }
        
        if stats["totalFiles"] > 0:
            stats["averageTokensPerFile"] = stats["totalTokens"] / stats["totalFiles"]
        
        return {
            "success": True,
            "stats": stats
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting context stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get context stats")

@router.put("/sessions/{session_id}/context")
async def update_session_context(
    session_id: str,
    request: Dict[str, Any],
    current_user: Optional[User] = Depends(get_current_user)
):
    """Update session context (add/remove files)"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        if session_id not in chat_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = chat_sessions[session_id]
        if session.get("userId") != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        action = request.get("action")
        files = request.get("files", [])
        
        if action == "add_files":
            session["selectedFiles"].extend(files)
        elif action == "remove_files":
            # Remove files by path
            file_paths = {f["path"] for f in files}
            session["selectedFiles"] = [
                f for f in session["selectedFiles"] 
                if f["path"] not in file_paths
            ]
        elif action == "clear_files":
            session["selectedFiles"] = []
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        session["updatedAt"] = datetime.now().isoformat()
        
        return {
            "success": True,
            "session": session
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating session context: {e}")
        raise HTTPException(status_code=500, detail="Failed to update context")

@router.get("/models")
async def get_available_models():
    """Get list of available AI models (equivalent to cosmos --list-models)"""
    try:
        if COSMOS_AVAILABLE:
            from integrations.cosmos.v1.cosmos_wrapper import list_all_models
            models = list_all_models()
        else:
            # Fallback models when Cosmos is not available
            models = [
                {
                    "name": "gpt-4o-mini",
                    "display_name": "GPT-4o Mini",
                    "provider": "openai",
                    "available": False,
                    "context_length": 128000,
                    "supports_streaming": True,
                    "error": "Cosmos not available"
                },
                {
                    "name": "fallback",
                    "display_name": "Fallback Assistant",
                    "provider": "internal",
                    "available": True,
                    "context_length": 4096,
                    "supports_streaming": False,
                    "description": "Basic assistant when AI models are not available"
                }
            ]
        
        return {
            "success": True,
            "models": models,
            "cosmos_available": COSMOS_AVAILABLE
        }
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        raise HTTPException(status_code=500, detail="Failed to get models")

@router.get("/models/{model_name}")
async def get_model_info(model_name: str):
    """Get detailed information about a specific model"""
    try:
        if COSMOS_AVAILABLE:
            from integrations.cosmos.v1.cosmos_wrapper import get_model_info
            model_info = get_model_info(model_name)
        else:
            model_info = {
                "available": False,
                "name": model_name,
                "error": "Cosmos not available"
            }
        
        return {
            "success": True,
            "model": model_info
        }
    except Exception as e:
        logger.error(f"Error getting model info for {model_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model info")

@router.post("/sessions/{session_id}/cleanup")
async def cleanup_chat_session(
    session_id: str,
    current_user: Optional[User] = Depends(get_current_user)
):
    """Cleanup cosmos session and cache when user leaves chat page"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        if session_id not in chat_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = chat_sessions[session_id]
        if session.get("userId") != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Cleanup cosmos session and Redis cache
        if COSMOS_AVAILABLE:
            from integrations.cosmos.v1.cosmos_wrapper import session_manager
            repository_id = session.get("repositoryId", "default")
            branch = session.get("branch", "main")
            session_manager.cleanup_session(str(current_user.id), repository_id, branch)
        
        return {
            "success": True,
            "message": "Session cleaned up successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning up session: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup session")

@router.post("/cleanup/user")
async def cleanup_all_user_sessions(
    current_user: Optional[User] = Depends(get_current_user)
):
    """Cleanup all cosmos sessions for a user when they leave the chat page entirely"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Cleanup all cosmos sessions for this user
        if COSMOS_AVAILABLE:
            from integrations.cosmos.v1.cosmos_wrapper import session_manager
            session_manager.cleanup_all_user_sessions(str(current_user.id))
        
        return {
            "success": True,
            "message": "All user sessions cleaned up successfully"
        }
    except Exception as e:
        logger.error(f"Error cleaning up all user sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup user sessions")

@router.post("/cleanup/repository")
async def cleanup_repository_cache(
    request: Dict[str, Any],
    current_user: Optional[User] = Depends(get_current_user)
):
    """Cleanup Redis cache for a specific repository"""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        repository_id = request.get("repositoryId")
        branch = request.get("branch", "main")
        
        if not repository_id:
            raise HTTPException(status_code=400, detail="Repository ID is required")
        
        # Cleanup Redis cache for the repository using wrapper
        if COSMOS_AVAILABLE:
            try:
                from integrations.cosmos.v1.cosmos_wrapper import session_manager
                
                # Use session manager to cleanup specific repository cache
                wrapper = session_manager.get_wrapper(
                    user_id=str(current_user.id),
                    repository_id=repository_id,
                    branch=branch
                )
                
                # Perform cleanup
                wrapper.cleanup_session(f"{repository_id}:{branch}")
                
                message = f"Repository cache cleared for {repository_id}:{branch}"
                logger.info(message)
                
                return {
                    "success": True,
                    "message": message,
                    "cache_cleared": True
                }
            except Exception as cache_error:
                logger.error(f"Error clearing repository cache: {cache_error}")
                return {
                    "success": False,
                    "message": f"Error clearing cache: {str(cache_error)}"
                }
        else:
            return {
                "success": False,
                "message": "Cosmos not available - no cache to clear"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning up repository cache: {e}")
        raise HTTPException(status_code=500, detail="Failed to cleanup repository cache")
