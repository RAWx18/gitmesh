"""
Simple Chat API Routes

Basic chat functionality that works with the current codebase without complex configuration.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
import os

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/simple-chat", tags=["simple-chat"])


class ChatMessage(BaseModel):
    message: str
    repository_path: Optional[str] = None
    model: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    model_used: str
    timestamp: str
    repository: Optional[str] = None


@router.post("/message", response_model=ChatResponse)
async def send_message(chat_request: ChatMessage):
    """
    Send a message to the AI chat system.
    Enhanced implementation that uses the actual AI service.
    """
    try:
        # Use the configured AI model from environment
        model = chat_request.model or os.getenv('AI_DEFAULT_MODEL', 'gemini-2.0-flash')
        
        # Try to use the actual AI service if available
        try:
            from backend.services.ai_service import get_ai_service
            ai_service = get_ai_service()
            
            # Prepare the prompt with repository context if available
            prompt = chat_request.message
            if chat_request.repository_path:
                prompt = f"Repository context: {chat_request.repository_path}\n\nUser question: {chat_request.message}"
            
            # Get AI response
            ai_response = await ai_service.generate_response(
                prompt=prompt,
                model=model
            )
            
            response_text = ai_response.get('content', 'No response generated')
            
        except Exception as ai_error:
            logger.warning(f"AI service not available, using fallback: {ai_error}")
            # Fallback response
            response_text = f"I'm a GitMesh AI assistant. You asked: {chat_request.message}"
            
            if chat_request.repository_path:
                response_text += f"\n\nI can see you're working with repository: {chat_request.repository_path}"
                response_text += "\n\nTo enable full AI capabilities, please ensure your AI service is properly configured."
        
        return ChatResponse(
            response=response_text,
            model_used=model,
            timestamp=datetime.now().isoformat(),
            repository=chat_request.repository_path
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat service error: {str(e)}"
        )


@router.get("/models")
async def get_available_models():
    """Get list of available AI models."""
    return {
        "models": [
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash"
        ],
        "default": os.getenv('AI_DEFAULT_MODEL', 'gemini-2.0-flash')
    }


@router.get("/health")
async def chat_health():
    """Simple health check for chat functionality."""
    return {
        "status": "healthy",
        "service": "simple-chat",
        "timestamp": datetime.now().isoformat()
    }