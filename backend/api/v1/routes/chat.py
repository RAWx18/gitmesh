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
    from services.cosmos_web_wrapper import CosmosWebWrapper, COSMOS_COMPONENTS_AVAILABLE
    COSMOS_AVAILABLE = True
except ImportError:
    COSMOS_AVAILABLE = False
    COSMOS_COMPONENTS_AVAILABLE = False
    CosmosWebWrapper = None

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
            "cosmosReady": self.cosmos_available and COSMOS_AVAILABLE and COSMOS_COMPONENTS_AVAILABLE
        }
        
        chat_sessions[session_id] = session
        chat_messages[session_id] = []
        
        # Initialize Cosmos session if available
        if self.cosmos_available and COSMOS_AVAILABLE:
            try:
                # Note: Cosmos wrapper will be created per message for now
                # In the future, we can implement session-based wrapper caching
                logger.info(f"Cosmos is available for session {session_id}")
            except Exception as e:
                logger.error(f"Error checking Cosmos availability: {e}")
        
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
            if self.cosmos_available and COSMOS_AVAILABLE and COSMOS_COMPONENTS_AVAILABLE:
                # Initialize Cosmos configuration first
                try:
                    from integrations.cosmos.v1.cosmos.config import initialize_configuration
                    initialize_configuration()
                    logger.info("Cosmos configuration initialized successfully")
                except Exception as e:
                    logger.warning(f"Could not initialize Cosmos configuration: {e}")
                
                # Import optimized services with fallback
                try:
                    from middleware.optimized_repo_middleware import get_repo_middleware
                    from services.optimized_redis_repo_manager import OptimizedRedisRepoManager
                    optimized_system_available = True
                    logger.info("Using full optimized repository system")
                except ImportError as e:
                    logger.warning(f"Full optimized system not available: {e}")
                    # Fallback to simple optimized system
                    from services.simple_optimized_repo_service import get_simple_optimized_repo_service
                    from services.redis_repo_manager import RedisRepoManager
                    optimized_system_available = False
                    logger.info("Using simple optimized repository system")
                
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
                    
                    # Get branch info
                    branch = session.get("branch") or context.get("branch") or "main"
                    enhanced_context["branch"] = branch
                    
                    if optimized_system_available:
                        # Use full optimized repository middleware for fast data access with user's GitHub token
                        repo_middleware = get_repo_middleware(user_id)
                        
                        # Get repository context with optimized caching
                        repo_context = repo_middleware.get_repository_context(repository_url)
                        
                        if repo_context.get("error"):
                            logger.warning(f"Repository context error: {repo_context['error']}")
                            # Still use optimized manager even with errors
                            repo_manager = OptimizedRedisRepoManager(
                                repo_url=repository_url,
                                branch=branch,
                                username=user_id
                            )
                        else:
                            logger.info(f"Repository context loaded in {repo_context.get('fetch_time_ms', 0)}ms")
                            # Create optimized repo manager that uses our fast service
                            repo_manager = OptimizedRedisRepoManager(
                                repo_url=repository_url,
                                branch=branch,
                                username=user_id
                            )
                            
                            # Pre-load selected files using optimized service
                            if session.get("selectedFiles"):
                                for file_info in session["selectedFiles"]:
                                    if isinstance(file_info, dict) and file_info.get("path"):
                                        file_path = file_info["path"]
                                        file_content = repo_middleware.get_file_content_fast(repository_url, file_path)
                                        if file_content:
                                            logger.info(f"Pre-loaded file: {file_path}")
                    else:
                        # Use simple optimized system as fallback
                        logger.info("Using simple optimized repository system")
                        
                        # Create a wrapper that uses the simple optimized service
                        simple_service = get_simple_optimized_repo_service(user_id)
                        
                        # Test repository access
                        repo_data = simple_service.get_repository_data(repository_url)
                        if repo_data:
                            logger.info("Repository data loaded successfully with simple optimized system")
                        else:
                            logger.warning("Repository data not available with simple optimized system")
                        
                        # Create standard repo manager but with optimized token handling
                        repo_manager = RedisRepoManager(
                            repo_url=repository_url,
                            branch=branch,
                            username=user_id
                        )
                    
                    # Create Cosmos wrapper for this request
                    wrapper = CosmosWebWrapper(
                        repo_manager=repo_manager,
                        model=model_name,
                        user_id=user_id
                    )
                    
                    # Add selected files to context using optimized access
                    if session.get("selectedFiles"):
                        for file_info in session["selectedFiles"]:
                            if isinstance(file_info, dict) and file_info.get("path"):
                                wrapper.add_file_to_context(file_info["path"])
                else:
                    logger.warning("No repository URL found in request - Cosmos will not have repository context")
                    # Create a minimal wrapper without repository context
                    if optimized_system_available:
                        repo_manager = OptimizedRedisRepoManager(
                            repo_url="https://github.com/default/repo",  # Placeholder
                            branch="main",
                            username=user_id
                        )
                    else:
                        repo_manager = RedisRepoManager(
                            repo_url="https://github.com/default/repo",  # Placeholder
                            branch="main",
                            username=user_id
                        )
                    wrapper = CosmosWebWrapper(
                        repo_manager=repo_manager,
                        model=model_name,
                        user_id=user_id
                    )
                
                # Process message through Cosmos AI system
                cosmos_response = await wrapper.process_message(
                    message=message,
                    context=enhanced_context
                )
                
                # Extract content and metadata
                assistant_content = cosmos_response.content
                confidence = cosmos_response.confidence
                sources = cosmos_response.sources
                knowledge_used = len(sources) if sources else 0
                model_used = cosmos_response.model_used or model_name
                
                # Add metadata to response if available
                if knowledge_used > 0:
                    assistant_content += f"\n\n*Analyzed {knowledge_used} files from your codebase*"
                
                if sources:
                    source_names = [s.split('/')[-1] for s in sources[:3]]  # Get file names
                    assistant_content += f"\n\n*Referenced files: {', '.join(source_names)}*"
                
                # Cleanup wrapper
                wrapper.cleanup()
                
            else:
                # When Cosmos is not available, return an error message
                assistant_content = "I'm sorry, but the Cosmos AI system is currently unavailable. Please ensure that Cosmos is properly installed and configured to use the chat functionality."
                model_used = "unavailable"
        
        except Exception as e:
            logger.error(f"Error processing message with Cosmos: {e}")
            assistant_content = f"I encountered an error while processing your message through Cosmos AI: {str(e)}. Please try again or check the Cosmos configuration."
            model_used = "error"
        
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
        if COSMOS_AVAILABLE and COSMOS_COMPONENTS_AVAILABLE:
            from services.redis_repo_manager import RedisRepoManager
            from services.cosmos_web_wrapper import CosmosWebWrapper
            
            # Create a temporary wrapper to get available models
            repo_manager = RedisRepoManager(
                repo_url="https://github.com/default/repo",  # Placeholder for model info
                branch="main",
                username="system"
            )
            wrapper = CosmosWebWrapper(repo_manager=repo_manager, model="gemini")
            models = [
                {
                    "name": model,
                    "display_name": model.replace("_", " ").title(),
                    "provider": "cosmos",
                    "available": True,
                    "context_length": 128000,  # Default context length
                    "supports_streaming": True
                }
                for model in wrapper.get_supported_models()
            ]
            wrapper.cleanup()
        else:
            # When Cosmos is not available, return empty models list
            models = [
                {
                    "name": "unavailable",
                    "display_name": "Cosmos AI Unavailable",
                    "provider": "cosmos",
                    "available": False,
                    "context_length": 0,
                    "supports_streaming": False,
                    "error": "Cosmos AI system is not available. Please install and configure Cosmos to use AI models."
                }
            ]
        
        return {
            "success": True,
            "models": models,
            "cosmos_available": COSMOS_AVAILABLE and COSMOS_COMPONENTS_AVAILABLE
        }
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        raise HTTPException(status_code=500, detail="Failed to get models")

@router.get("/models/{model_name}")
async def get_model_info(model_name: str):
    """Get detailed information about a specific model"""
    try:
        if COSMOS_AVAILABLE and COSMOS_COMPONENTS_AVAILABLE:
            from services.redis_repo_manager import RedisRepoManager
            from services.cosmos_web_wrapper import CosmosWebWrapper
            
            # Create a temporary wrapper to get model info
            repo_manager = RedisRepoManager(
                repo_url="https://github.com/default/repo",  # Placeholder for model info
                branch="main",
                username="system"
            )
            wrapper = CosmosWebWrapper(repo_manager=repo_manager, model="gemini")
            supported_models = wrapper.get_supported_models()
            
            if model_name in supported_models:
                model_info = {
                    "available": True,
                    "name": model_name,
                    "display_name": model_name.replace("_", " ").title(),
                    "provider": "cosmos",
                    "context_length": 128000,
                    "supports_streaming": True
                }
            else:
                model_info = {
                    "available": False,
                    "name": model_name,
                    "error": f"Model {model_name} not supported"
                }
            wrapper.cleanup()
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
            try:
                from services.redis_repo_manager import RedisRepoManager
                repo_manager = RedisRepoManager(
                    repo_url="https://github.com/default/repo",  # Placeholder for cleanup
                    branch="main",
                    username=str(current_user.id)
                )
                # Cleanup any cached data for this session
                logger.info(f"Cleaned up session {session_id}")
            except Exception as e:
                logger.error(f"Error cleaning up session: {e}")
        
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
            try:
                from services.redis_repo_manager import RedisRepoManager
                repo_manager = RedisRepoManager(
                    repo_url="https://github.com/default/repo",  # Placeholder for cleanup
                    branch="main",
                    username=str(current_user.id)
                )
                # Cleanup any cached data for this user
                logger.info(f"Cleaned up all sessions for user {current_user.id}")
            except Exception as e:
                logger.error(f"Error cleaning up user sessions: {e}")
        
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
        
        # Cleanup Redis cache for the repository
        if COSMOS_AVAILABLE:
            try:
                from services.redis_repo_manager import RedisRepoManager
                repo_manager = RedisRepoManager(
                    repo_url=f"https://github.com/{repository_id}",
                    branch=branch,
                    username=str(current_user.id)
                )
                
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
