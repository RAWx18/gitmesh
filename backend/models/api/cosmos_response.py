"""
Cosmos Response Models

Enhanced response models for web-safe Cosmos chat integration with
syntax highlighting, diff visualization, and interactive elements.
"""

from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum


class ResponseType(str, Enum):
    """Response content type enumeration."""
    TEXT = "text"
    CODE = "code"
    DIFF = "diff"
    ERROR = "error"
    SHELL_OUTPUT = "shell_output"
    FILE_LIST = "file_list"
    INTERACTIVE_PROMPT = "interactive_prompt"
    REPO_MAP = "repo_map"


class CodeLanguage(str, Enum):
    """Supported code languages for syntax highlighting."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    HTML = "html"
    CSS = "css"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"
    BASH = "bash"
    SQL = "sql"
    JAVA = "java"
    CPP = "cpp"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    PHP = "php"
    RUBY = "ruby"
    UNKNOWN = "unknown"


class CodeBlock(BaseModel):
    """Code block with syntax highlighting information."""
    content: str = Field(..., description="Code content")
    language: CodeLanguage = Field(..., description="Programming language")
    filename: Optional[str] = Field(None, description="Associated filename")
    start_line: Optional[int] = Field(None, description="Starting line number")
    end_line: Optional[int] = Field(None, description="Ending line number")
    is_diff: bool = Field(False, description="Whether this is a diff block")
    diff_type: Optional[str] = Field(None, description="Type of diff: addition, deletion, modification")


class DiffLine(BaseModel):
    """Individual line in a diff."""
    type: str = Field(..., description="Line type: addition, deletion, context")
    content: str = Field(..., description="Line content")
    line_number: int = Field(..., description="Line number")


class DiffBlock(BaseModel):
    """Diff visualization block."""
    filename: str = Field(..., description="File being modified")
    old_content: Optional[str] = Field(None, description="Original file content")
    new_content: str = Field(..., description="New file content")
    diff_lines: List[DiffLine] = Field(default_factory=list, description="Individual diff lines")
    language: CodeLanguage = Field(..., description="Programming language")
    change_type: str = Field(..., description="Type of change: create, modify, delete")


class InteractiveElement(BaseModel):
    """Interactive UI element for web display."""
    element_type: str = Field(..., description="Type of element: button, dropdown, checkbox, input")
    label: str = Field(..., description="Element label")
    value: Optional[str] = Field(None, description="Current value")
    options: Optional[List[str]] = Field(None, description="Available options")
    action: Optional[str] = Field(None, description="Action to perform")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class FileListItem(BaseModel):
    """File list item with metadata."""
    path: str = Field(..., description="File path")
    name: str = Field(..., description="File name")
    size: Optional[int] = Field(None, description="File size in bytes")
    language: Optional[CodeLanguage] = Field(None, description="Programming language")
    is_directory: bool = Field(False, description="Whether this is a directory")
    is_tracked: bool = Field(True, description="Whether file is tracked in repository")
    last_modified: Optional[datetime] = Field(None, description="Last modification time")


class ConversionInfo(BaseModel):
    """Information about CLI-to-web conversions."""
    total_commands: int = Field(..., description="Total shell commands converted")
    commands: List[str] = Field(default_factory=list, description="List of converted commands")
    conversion_timestamp: datetime = Field(default_factory=datetime.now, description="When conversion occurred")
    conversion_notes: Optional[str] = Field(None, description="Additional conversion notes")


class ProcessedCosmosResponse(BaseModel):
    """Processed Cosmos response with web-safe formatting."""
    content: str = Field(..., description="Processed response content")
    response_type: ResponseType = Field(..., description="Type of response")
    code_blocks: List[CodeBlock] = Field(default_factory=list, description="Extracted code blocks")
    diff_blocks: List[DiffBlock] = Field(default_factory=list, description="Diff visualization blocks")
    interactive_elements: List[InteractiveElement] = Field(default_factory=list, description="Interactive UI elements")
    file_lists: List[List[FileListItem]] = Field(default_factory=list, description="File listings")
    shell_commands_converted: List[str] = Field(default_factory=list, description="Shell commands that were converted")
    conversion_notes: Optional[str] = Field(None, description="Notes about CLI-to-web conversions")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    raw_content: str = Field(..., description="Original raw content")
    processing_timestamp: datetime = Field(default_factory=datetime.now, description="When response was processed")


class CosmosMessageRequest(BaseModel):
    """Request to send a message to Cosmos."""
    session_id: str = Field(..., description="Chat session identifier")
    message: str = Field(..., description="User message")
    context_files: Optional[List[str]] = Field(None, description="Files to include in context")
    model: Optional[str] = Field(None, description="AI model to use")
    
    @validator('message')
    def validate_message(cls, v):
        if not v.strip():
            raise ValueError("Message cannot be empty")
        if len(v) > 50000:
            raise ValueError("Message too long (max 50000 characters)")
        return v.strip()


class CosmosMessageResponse(BaseModel):
    """Response from Cosmos message processing."""
    message_id: str = Field(..., description="Unique message identifier")
    session_id: str = Field(..., description="Chat session identifier")
    processed_response: ProcessedCosmosResponse = Field(..., description="Processed response content")
    context_files_used: List[str] = Field(default_factory=list, description="Files that were in context")
    model_used: str = Field(..., description="AI model that was used")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    timestamp: datetime = Field(default_factory=datetime.now, description="Response timestamp")
    error: Optional[str] = Field(None, description="Error message if processing failed")


class CosmosSessionInfo(BaseModel):
    """Information about a Cosmos chat session."""
    session_id: str = Field(..., description="Session identifier")
    title: str = Field(..., description="Session title")
    repository_url: Optional[str] = Field(None, description="Repository URL")
    branch: Optional[str] = Field(None, description="Repository branch")
    model: str = Field(..., description="Current AI model")
    context_files_count: int = Field(..., description="Number of files in context")
    message_count: int = Field(..., description="Number of messages in session")
    created_at: datetime = Field(..., description="Session creation time")
    updated_at: datetime = Field(..., description="Last update time")


class ContextFileInfo(BaseModel):
    """Information about a file in session context."""
    path: str = Field(..., description="File path")
    name: str = Field(..., description="File name")
    size: int = Field(..., description="File size in bytes")
    language: str = Field(..., description="Programming language")
    added_at: datetime = Field(..., description="When file was added to context")
    is_modified: bool = Field(False, description="Whether file has been modified")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional file metadata")


class AddContextFilesRequest(BaseModel):
    """Request to add files to session context."""
    session_id: str = Field(..., description="Session identifier")
    file_paths: List[str] = Field(..., description="List of file paths to add")
    repository_url: Optional[str] = Field(None, description="Repository URL (optional)")
    branch: Optional[str] = Field(None, description="Branch name (optional)")
    
    @validator('file_paths')
    def validate_file_paths(cls, v):
        if not v:
            raise ValueError("At least one file path is required")
        if len(v) > 50:
            raise ValueError("Too many files (max 50 at once)")
        return v


class AddContextFilesResponse(BaseModel):
    """Response from adding files to context."""
    added_count: int = Field(..., description="Number of files successfully added")
    failed_count: int = Field(..., description="Number of files that failed to add")
    added_files: List[ContextFileInfo] = Field(default_factory=list, description="Successfully added files")
    failed_files: List[Dict[str, str]] = Field(default_factory=list, description="Failed files with error messages")
    total_context_files: int = Field(..., description="Total files now in context")
    total_context_size: int = Field(..., description="Total size of context in bytes")


class RemoveContextFilesRequest(BaseModel):
    """Request to remove files from session context."""
    session_id: str = Field(..., description="Session identifier")
    file_paths: List[str] = Field(..., description="List of file paths to remove")
    
    @validator('file_paths')
    def validate_file_paths(cls, v):
        if not v:
            raise ValueError("At least one file path is required")
        return v


class RemoveContextFilesResponse(BaseModel):
    """Response from removing files from context."""
    removed_count: int = Field(..., description="Number of files successfully removed")
    not_found_count: int = Field(..., description="Number of files not found in context")
    removed_files: List[Dict[str, Any]] = Field(default_factory=list, description="Successfully removed files")
    not_found_files: List[Dict[str, str]] = Field(default_factory=list, description="Files not found in context")
    total_context_files: int = Field(..., description="Total files remaining in context")
    total_context_size: int = Field(..., description="Total size of remaining context in bytes")


class ContextStatsResponse(BaseModel):
    """Context statistics for a session."""
    total_files: int = Field(..., description="Total number of files in context")
    total_size: int = Field(..., description="Total size of context in bytes")
    average_file_size: float = Field(..., description="Average file size")
    languages: Dict[str, int] = Field(default_factory=dict, description="Language distribution")
    oldest_file: Optional[Dict[str, str]] = Field(None, description="Oldest file in context")
    newest_file: Optional[Dict[str, str]] = Field(None, description="Newest file in context")


class ModelInfo(BaseModel):
    """Information about an available AI model."""
    name: str = Field(..., description="Canonical model name")
    alias: str = Field(..., description="Model alias")
    provider: str = Field(..., description="Model provider")
    tier_required: str = Field("free", description="Required user tier")
    max_tokens: int = Field(4096, description="Maximum tokens")
    supports_code: bool = Field(True, description="Whether model supports code")
    supports_reasoning: bool = Field(False, description="Whether model supports reasoning")


class AvailableModelsResponse(BaseModel):
    """Response with available AI models."""
    models: List[ModelInfo] = Field(..., description="List of available models")
    current_model: Optional[str] = Field(None, description="Currently selected model")
    total_models: int = Field(..., description="Total number of available models")


class SetModelRequest(BaseModel):
    """Request to set AI model for a session."""
    session_id: str = Field(..., description="Session identifier")
    model: str = Field(..., description="Model alias to set")


class SetModelResponse(BaseModel):
    """Response from setting AI model."""
    success: bool = Field(..., description="Whether model was set successfully")
    previous_model: Optional[str] = Field(None, description="Previous model alias")
    new_model: str = Field(..., description="New model alias")
    message: str = Field(..., description="Status message")


class ConversionStatusResponse(BaseModel):
    """Shell-to-web conversion status."""
    total_operations: int = Field(..., description="Total operations attempted")
    converted_operations: int = Field(..., description="Successfully converted operations")
    pending_conversions: List[str] = Field(default_factory=list, description="Operations pending conversion")
    conversion_percentage: float = Field(..., description="Conversion success percentage")
    last_conversion: Optional[datetime] = Field(None, description="Last successful conversion")


class CosmosErrorResponse(BaseModel):
    """Error response from Cosmos operations."""
    error: str = Field(..., description="Error message")
    error_code: str = Field(..., description="Error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    suggested_action: Optional[str] = Field(None, description="Suggested action to resolve error")
    retry_after: Optional[int] = Field(None, description="Seconds to wait before retry")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp")