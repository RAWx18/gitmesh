"""
Cosmos Chat API Routes

API endpoints for Cosmos AI chat integration with web-safe response processing.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime

# Import models and services
from backend.models.api.cosmos_response import (
    CosmosMessageRequest,
    CosmosMessageResponse,
    ProcessedCosmosResponse,
    AddContextFilesRequest,
    AddContextFilesResponse,
    RemoveContextFilesRequest,
    RemoveContextFilesResponse,
    ContextStatsResponse,
    AvailableModelsResponse,
    SetModelRequest,
    SetModelResponse,
    ConversionStatusResponse,
    CosmosErrorResponse
)
from backend.services.cosmos_web_service import CosmosWebService
from backend.services.cosmos_web_wrapper import CosmosWebWrapper
from backend.services.redis_repo_manager import RedisRepoManager
from backend.services.response_processor import ResponseProcessor

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/cosmos", tags=["cosmos-chat"])

# Initialize services
cosmos_service = CosmosWebService()
response_processor = ResponseProcessor()


async def get_cosmos_wrapper(
    session_id: str,
    repository_url: Optional[str] = None,
    branch: Optional[str] = None,
    user_id: str = "default_user"
) -> CosmosWebWrapper:
    """Get or create a Cosmos wrapper for the session."""
    try:
        # Get session info
        session = await cosmos_service.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
        
        # Use session repository info or provided values
        repo_url = repository_url or session.repository_url
        repo_branch = branch or session.branch or "main"
        
        if not repo_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository URL is required"
            )
        
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize Cosmos wrapper: {str(e)}"
        )


@router.post("/message", response_model=CosmosMessageResponse)
async def send_message(request: CosmosMessageRequest):
    """
    Send a message to Cosmos AI and get a processed response.
    
    This endpoint processes the message through Cosmos AI and returns
    a web-safe formatted response with syntax highlighting, diff visualization,
    and interactive elements.
    """
    try:
        start_time = datetime.now()
        
        # Get Cosmos wrapper
        wrapper = await get_cosmos_wrapper(
            session_id=request.session_id,
            user_id="default_user"  # TODO: Get from auth context
        )
        
        # Add any additional context files
        if request.context_files:
            for file_path in request.context_files:
                wrapper.add_file_to_context(file_path)
        
        # Set model if specified
        if request.model:
            if not wrapper.set_model(request.model):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid model: {request.model}"
                )
        
        # Process message
        cosmos_response = await wrapper.process_message(request.message)
        
        # Process response for web display
        processed_response = response_processor.process_response(
            content=cosmos_response.content,
            shell_commands_converted=cosmos_response.shell_commands_converted,
            conversion_notes=cosmos_response.conversion_notes,
            metadata=cosmos_response.metadata
        )
        
        # Add message to session
        message_id = await cosmos_service.add_message(
            session_id=request.session_id,
            role="user",
            content=request.message
        )
        
        assistant_message_id = await cosmos_service.add_message(
            session_id=request.session_id,
            role="assistant",
            content=processed_response.content,
            metadata=processed_response.metadata,
            context_files_used=cosmos_response.context_files_used,
            shell_commands_converted=cosmos_response.shell_commands_converted,
            conversion_notes=cosmos_response.conversion_notes
        )
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Create processed response model
        processed_cosmos_response = ProcessedCosmosResponse(
            content=processed_response.content,
            response_type=processed_response.response_type,
            code_blocks=processed_response.code_blocks,
            diff_blocks=processed_response.diff_blocks,
            interactive_elements=processed_response.interactive_elements,
            file_lists=processed_response.file_lists,
            shell_commands_converted=processed_response.shell_commands_converted,
            conversion_notes=processed_response.conversion_notes,
            metadata=processed_response.metadata,
            raw_content=processed_response.raw_content,
            processing_timestamp=processed_response.processing_timestamp if hasattr(processed_response, 'processing_timestamp') else datetime.now()
        )
        
        return CosmosMessageResponse(
            message_id=assistant_message_id,
            session_id=request.session_id,
            processed_response=processed_cosmos_response,
            context_files_used=cosmos_response.context_files_used,
            model_used=wrapper.model,
            processing_time_ms=int(processing_time),
            timestamp=datetime.now(),
            error=cosmos_response.error
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )


@router.get("/models", response_model=AvailableModelsResponse)
async def get_available_models():
    """Get list of available AI models."""
    try:
        models = cosmos_service.get_available_models()
        
        return AvailableModelsResponse(
            models=models,
            current_model=None,  # No session context
            total_models=len(models)
        )
        
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available models: {str(e)}"
        )


@router.post("/session/{session_id}/model", response_model=SetModelResponse)
async def set_session_model(session_id: str, request: SetModelRequest):
    """Set the AI model for a session."""
    try:
        # Validate model
        if not cosmos_service.is_valid_model(request.model):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid model: {request.model}"
            )
        
        # Get current session
        session = await cosmos_service.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
        
        previous_model = session.model
        
        # Update session model
        success = await cosmos_service.update_session(session_id, model=request.model)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update session model"
            )
        
        return SetModelResponse(
            success=True,
            previous_model=previous_model,
            new_model=request.model,
            message=f"Model updated from {previous_model} to {request.model}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting session model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set session model: {str(e)}"
        )


@router.post("/session/{session_id}/context/add", response_model=AddContextFilesResponse)
async def add_context_files(session_id: str, request: AddContextFilesRequest):
    """Add files to session context."""
    try:
        result = await cosmos_service.add_context_files(
            session_id=session_id,
            file_paths=request.file_paths,
            repository_url=request.repository_url,
            branch=request.branch
        )
        
        return AddContextFilesResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding context files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add context files: {str(e)}"
        )


@router.post("/session/{session_id}/context/remove", response_model=RemoveContextFilesResponse)
async def remove_context_files(session_id: str, request: RemoveContextFilesRequest):
    """Remove files from session context."""
    try:
        result = await cosmos_service.remove_context_files(
            session_id=session_id,
            file_paths=request.file_paths
        )
        
        return RemoveContextFilesResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing context files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove context files: {str(e)}"
        )


@router.get("/session/{session_id}/context/stats", response_model=ContextStatsResponse)
async def get_context_stats(session_id: str):
    """Get context statistics for a session."""
    try:
        stats = await cosmos_service.get_context_stats(session_id)
        
        return ContextStatsResponse(**stats)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting context stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get context stats: {str(e)}"
        )


@router.get("/session/{session_id}/conversion-status", response_model=ConversionStatusResponse)
async def get_conversion_status(session_id: str):
    """Get shell-to-web conversion status for a session."""
    try:
        # Get wrapper to access conversion status
        wrapper = await get_cosmos_wrapper(session_id=session_id)
        
        conversion_status = wrapper.get_conversion_status()
        
        return ConversionStatusResponse(
            total_operations=conversion_status.total_operations,
            converted_operations=conversion_status.converted_operations,
            pending_conversions=conversion_status.pending_conversions,
            conversion_percentage=conversion_status.conversion_percentage,
            last_conversion=conversion_status.last_conversion
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversion status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get conversion status: {str(e)}"
        )


from pydantic import BaseModel
from typing import List, Optional

class DemoProcessRequest(BaseModel):
    content: str
    shell_commands: Optional[List[str]] = None
    conversion_notes: Optional[str] = None

@router.post("/demo/process-response")
async def demo_process_response(request: DemoProcessRequest):
    """
    Demo endpoint to test response processing functionality.
    
    This endpoint allows testing the response processor directly
    without needing a full Cosmos session.
    """
    try:
        processed = response_processor.process_response(
            content=request.content,
            shell_commands_converted=request.shell_commands or [],
            conversion_notes=request.conversion_notes
        )
        
        return response_processor.format_for_json_response(processed)
        
    except Exception as e:
        logger.error(f"Error in demo response processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process response: {str(e)}"
        )