"""
Cosmos CLI Wrapper with Shell Command Interception

Adapts existing CLI-based Cosmos functionality for web use with minimal code changes.
Provides progressive shell-to-web conversion and smart command interception.
"""

import os
import sys
import json
import logging
import asyncio
import tempfile
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from io import StringIO

# Import configuration and models
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from config.settings import get_settings
from config.cosmos_models import MODEL_ALIASES
from services.redis_repo_manager import RedisRepoManager
from services.response_processor import ResponseProcessor
from services.conversion_tracking_service import conversion_tracking_service
from models.api.conversion_tracking import ConversionRequest, ConversionUpdateRequest, ConversionType, ConversionStatus, ConversionPriority

# For now, we'll create mock classes for Cosmos components since they have complex dependencies
# In a real implementation, these would be properly imported once the Cosmos integration is complete

class MockInputOutput:
    """Mock InputOutput class for testing."""
    def __init__(self, pretty=True, yes=False, chat_history_file=None):
        self.pretty = pretty
        self.yes = yes
        self.chat_history_file = chat_history_file
        self.encoding = 'utf-8'
    
    def tool_output(self, *args, **kwargs):
        pass
    
    def tool_error(self, *args, **kwargs):
        pass
    
    def tool_warning(self, *args, **kwargs):
        pass
    
    def read_text(self, filename):
        return None
    
    def write_text(self, filename, content):
        return True

class MockModel:
    """Mock Model class for testing."""
    def __init__(self, name):
        self.name = name

class MockCoder:
    """Mock Coder class for testing."""
    def __init__(self, main_model, io, **kwargs):
        self.main_model = main_model
        self.io = io
        self.abs_fnames = set()
        self.shell_commands = []
    
    def run(self, with_message=None, preproc=True):
        return f"Mock response to: {with_message}"

# Use mock classes
InputOutput = MockInputOutput
Model = MockModel
EditBlockCoder = MockCoder

# Mock run_cmd module
class MockRunCmd:
    """Mock run_cmd module for testing."""
    @staticmethod
    def run_cmd(command, **kwargs):
        return 0, f"Mock output for: {command}"

run_cmd = MockRunCmd()

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ContextFile:
    """File currently in Cosmos context."""
    path: str
    name: str
    size: int
    language: str
    added_at: datetime
    is_modified: bool = False


@dataclass
class ConversionStatus:
    """Track shell-to-web conversion progress."""
    total_operations: int
    converted_operations: int
    pending_conversions: List[str]
    conversion_percentage: float
    last_conversion: Optional[datetime] = None


@dataclass
class CosmosResponse:
    """Response from Cosmos processing."""
    content: str
    context_files_used: List[str]
    shell_commands_converted: List[str]
    conversion_notes: Optional[str]
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class WebSafeInputOutput(InputOutput):
    """
    Web-safe InputOutput wrapper that intercepts shell commands.
    
    This class extends the standard Cosmos InputOutput to provide web-safe
    operations by intercepting and converting shell commands to web equivalents.
    """
    
    def __init__(self, original_io: InputOutput, wrapper: 'CosmosWebWrapper'):
        """Initialize with original IO and wrapper reference."""
        super().__init__()
        self.original_io = original_io
        self.wrapper = wrapper
        self.intercepted_commands: List[str] = []
        self.conversion_notes: List[str] = []
        
        # Copy important attributes from original IO
        self.pretty = getattr(original_io, 'pretty', True)
        self.yes = getattr(original_io, 'yes', False)
        self.chat_history_file = getattr(original_io, 'chat_history_file', None)
        self.encoding = getattr(original_io, 'encoding', 'utf-8')
    
    def tool_output(self, *args, **kwargs):
        """Override tool output to capture for web display."""
        # Capture output for web display instead of printing
        message = ' '.join(str(arg) for arg in args)
        logger.debug(f"Tool output: {message}")
        
        # Store output for later retrieval
        if not hasattr(self, '_captured_output'):
            self._captured_output = []
        self._captured_output.append(message)
    
    def tool_error(self, *args, **kwargs):
        """Override tool error to capture for web display."""
        message = ' '.join(str(arg) for arg in args)
        logger.error(f"Tool error: {message}")
        
        # Store error for later retrieval
        if not hasattr(self, '_captured_errors'):
            self._captured_errors = []
        self._captured_errors.append(message)
    
    def tool_warning(self, *args, **kwargs):
        """Override tool warning to capture for web display."""
        message = ' '.join(str(arg) for arg in args)
        logger.warning(f"Tool warning: {message}")
        
        # Store warning for later retrieval
        if not hasattr(self, '_captured_warnings'):
            self._captured_warnings = []
        self._captured_warnings.append(message)
    
    def read_text(self, filename: str) -> Optional[str]:
        """Read file content through Redis repository manager."""
        try:
            # Use the wrapper's repo manager for file operations
            if self.wrapper.repo_manager:
                content = self.wrapper.repo_manager.get_file_content(filename)
                if content is not None:
                    logger.debug(f"Read file via Redis: {filename}")
                    return content
            
            # Fall back to original IO if needed
            logger.debug(f"Falling back to original IO for: {filename}")
            return self.original_io.read_text(filename)
            
        except Exception as e:
            logger.error(f"Error reading file {filename}: {e}")
            return None
    
    def write_text(self, filename: str, content: str) -> bool:
        """Intercept file write operations for web safety."""
        try:
            # In web mode, we don't actually write files to disk
            # Instead, we track the intended changes
            logger.info(f"Intercepted file write: {filename}")
            
            # Track the file modification
            self.wrapper._track_file_modification(filename, content)
            
            # Add conversion note
            self.conversion_notes.append(f"File write intercepted: {filename}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error intercepting file write {filename}: {e}")
            return False
    
    def confirm_ask(self, question: str, default: str = "y") -> str:
        """Override confirmation prompts for web safety."""
        # In web mode, we auto-confirm with default values
        logger.info(f"Auto-confirming prompt: {question} -> {default}")
        self.conversion_notes.append(f"Auto-confirmed prompt: {question}")
        return default
    
    def get_captured_output(self) -> Dict[str, List[str]]:
        """Get all captured output for web display."""
        return {
            'output': getattr(self, '_captured_output', []),
            'errors': getattr(self, '_captured_errors', []),
            'warnings': getattr(self, '_captured_warnings', []),
            'conversion_notes': self.conversion_notes
        }


class CosmosWebWrapper:
    """
    Cosmos CLI Wrapper with Shell Command Interception
    
    Smartly adapts existing CLI-based Cosmos functionality for web use with minimal code changes.
    Provides progressive shell-to-web conversion and smart command interception.
    """
    
    def __init__(
        self, 
        repo_manager: RedisRepoManager, 
        model: str = "gemini",
        user_id: Optional[str] = None
    ):
        """
        Initialize Cosmos Web Wrapper.
        
        Args:
            repo_manager: Redis repository manager for file operations
            model: AI model to use (must be valid alias)
            user_id: User identifier for session tracking
        """
        self.repo_manager = repo_manager
        self.model = model
        self.user_id = user_id
        
        # Validate model
        if model not in MODEL_ALIASES:
            raise ValueError(f"Invalid model: {model}. Must be one of: {list(MODEL_ALIASES.keys())}")
        
        # Initialize settings
        self.settings = get_settings()
        
        # Initialize response processor
        self.response_processor = ResponseProcessor()
        
        # Context tracking
        self._context_files: Dict[str, ContextFile] = {}
        self._file_modifications: Dict[str, str] = {}
        self._shell_commands_intercepted: List[str] = []
        self._conversion_status = ConversionStatus(
            total_operations=0,
            converted_operations=0,
            pending_conversions=[],
            conversion_percentage=0.0
        )
        
        # Initialize Cosmos components
        self._initialize_cosmos_components()
        
        logger.info(f"Initialized CosmosWebWrapper with model: {model}")
    
    def _initialize_cosmos_components(self):
        """Initialize Cosmos coder and related components."""
        try:
            # Create web-safe IO wrapper
            original_io = InputOutput(
                pretty=True,
                yes=False,  # Don't auto-confirm in web mode
                chat_history_file=None  # Disable file-based history
            )
            self.io = WebSafeInputOutput(original_io, self)
            
            # Create model instance
            canonical_model_name = MODEL_ALIASES[self.model]
            self.cosmos_model = Model(canonical_model_name)
            
            # Create temporary directory for virtual filesystem
            self.temp_dir = tempfile.mkdtemp(prefix="cosmos_web_")
            
            # Initialize coder with web-safe configuration
            self.coder = EditBlockCoder(
                main_model=self.cosmos_model,
                io=self.io,
                repo=None,  # No git repo in web mode
                fnames=[],  # Start with no files
                auto_commits=False,  # Disable git commits
                dirty_commits=False,  # Disable dirty commits
                dry_run=False,  # Allow edits but intercept them
                map_tokens=1024,  # Enable repo mapping
                verbose=False,  # Reduce verbosity for web
                stream=False,  # Disable streaming for web
                use_git=False,  # Disable git operations
                suggest_shell_commands=False,  # Disable shell command suggestions
                auto_lint=False,  # Disable auto-linting
                auto_test=False  # Disable auto-testing
            )
            
            # Override shell command execution
            self._patch_shell_execution()
            
            logger.info("Cosmos components initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Cosmos components: {e}")
            raise
    
    def _patch_shell_execution(self):
        """Patch shell command execution to intercept and block commands."""
        # Store original run_cmd function
        self._original_run_cmd = run_cmd.run_cmd
        
        # Replace with our intercepting version
        run_cmd.run_cmd = self._intercept_shell_command
        
        # Also patch the coder's shell command handling
        if hasattr(self.coder, 'shell_commands'):
            self.coder.shell_commands = []
    
    def _intercept_shell_command(self, command: str, **kwargs) -> Tuple[int, str]:
        """
        Intercept shell commands and convert to web-safe operations.
        
        Args:
            command: Shell command to intercept
            **kwargs: Additional arguments
            
        Returns:
            Tuple of (return_code, output)
        """
        logger.info(f"Intercepted shell command: {command}")
        
        # Track the intercepted command
        self._shell_commands_intercepted.append(command)
        self._conversion_status.total_operations += 1
        
        # Create conversion tracking operation
        operation_id = None
        try:
            if hasattr(self, '_current_session_id') and self._current_session_id:
                # Determine operation type based on command
                operation_type = self._classify_command_type(command)
                
                # Create conversion request
                conversion_request = ConversionRequest(
                    operation_type=operation_type,
                    original_command=command,
                    session_id=self._current_session_id,
                    user_id=self.user_id or "anonymous",
                    priority=self._determine_command_priority(command),
                    context_files=list(self._context_files.keys()),
                    metadata={
                        'wrapper_instance': id(self),
                        'model': self.model,
                        'timestamp': datetime.now().isoformat()
                    }
                )
                
                # Create operation in tracking service
                import asyncio
                loop = asyncio.get_event_loop()
                operation_id = loop.run_until_complete(
                    conversion_tracking_service.create_operation(conversion_request)
                )
                
                # Update operation to in-progress
                update_request = ConversionUpdateRequest(
                    operation_id=operation_id,
                    status=ConversionStatus.IN_PROGRESS
                )
                loop.run_until_complete(
                    conversion_tracking_service.update_operation(update_request)
                )
        except Exception as e:
            logger.error(f"Error creating conversion tracking operation: {e}")
        
        # Analyze and convert the command
        converted_output = self._convert_shell_command(command)
        
        if converted_output:
            self._conversion_status.converted_operations += 1
            self._conversion_status.last_conversion = datetime.now()
            
            # Update conversion percentage
            self._conversion_status.conversion_percentage = (
                self._conversion_status.converted_operations / 
                self._conversion_status.total_operations * 100
            )
            
            # Update tracking operation as completed
            if operation_id:
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    update_request = ConversionUpdateRequest(
                        operation_id=operation_id,
                        status=ConversionStatus.COMPLETED,
                        converted_equivalent=f"Web-safe equivalent for: {command}",
                        web_equivalent_output=converted_output,
                        conversion_notes=f"Successfully converted shell command to web operation"
                    )
                    loop.run_until_complete(
                        conversion_tracking_service.update_operation(update_request)
                    )
                except Exception as e:
                    logger.error(f"Error updating conversion tracking operation: {e}")
            
            return 0, converted_output
        else:
            # Command couldn't be converted, add to pending
            self._conversion_status.pending_conversions.append(command)
            
            # Update tracking operation as failed
            if operation_id:
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    update_request = ConversionUpdateRequest(
                        operation_id=operation_id,
                        status=ConversionStatus.FAILED,
                        error_message=f"No web-safe equivalent available for command: {command}",
                        conversion_notes=f"Command type not supported for web conversion"
                    )
                    loop.run_until_complete(
                        conversion_tracking_service.update_operation(update_request)
                    )
                except Exception as e:
                    logger.error(f"Error updating conversion tracking operation: {e}")
            
            # Return a web-safe message
            return 1, f"Shell command blocked for web safety: {command}"
    
    def _convert_shell_command(self, command: str) -> Optional[str]:
        """
        Convert shell command to web-safe equivalent.
        
        Args:
            command: Shell command to convert
            
        Returns:
            Converted output or None if conversion not possible
        """
        command = command.strip()
        
        # Handle common file operations
        if command.startswith('ls') or command.startswith('dir'):
            return self._handle_list_files(command)
        elif command.startswith('cat') or command.startswith('type'):
            return self._handle_cat_file(command)
        elif command.startswith('find'):
            return self._handle_find_files(command)
        elif command.startswith('grep'):
            return self._handle_grep_files(command)
        elif command.startswith('git'):
            return self._handle_git_command(command)
        elif command.startswith('mkdir'):
            return self._handle_mkdir(command)
        elif command.startswith('touch'):
            return self._handle_touch(command)
        elif command.startswith('rm'):
            return self._handle_rm(command)
        elif command.startswith('cp') or command.startswith('copy'):
            return self._handle_copy(command)
        elif command.startswith('mv') or command.startswith('move'):
            return self._handle_move(command)
        else:
            # Command not recognized for conversion
            logger.warning(f"Cannot convert shell command: {command}")
            return None
    
    def _handle_list_files(self, command: str) -> str:
        """Handle ls/dir commands."""
        try:
            files = self.repo_manager.list_files()
            if not files:
                return "No files found in repository"
            
            # Format as directory listing
            output = []
            for file_path in sorted(files):
                metadata = self.repo_manager.get_file_metadata(file_path)
                if metadata:
                    size_str = f"{metadata.size:>8}"
                    output.append(f"{size_str} {file_path}")
                else:
                    output.append(f"        ? {file_path}")
            
            return "\n".join(output)
            
        except Exception as e:
            return f"Error listing files: {e}"
    
    def _handle_cat_file(self, command: str) -> str:
        """Handle cat/type commands."""
        try:
            # Extract filename from command
            parts = command.split()
            if len(parts) < 2:
                return "Usage: cat <filename>"
            
            filename = parts[1]
            content = self.repo_manager.get_file_content(filename)
            
            if content is None:
                return f"File not found: {filename}"
            
            return content
            
        except Exception as e:
            return f"Error reading file: {e}"
    
    def _handle_find_files(self, command: str) -> str:
        """Handle find commands."""
        try:
            files = self.repo_manager.list_files()
            
            # Simple pattern matching (could be enhanced)
            if "-name" in command:
                # Extract pattern after -name
                parts = command.split("-name")
                if len(parts) > 1:
                    pattern = parts[1].strip().strip('"\'')
                    import fnmatch
                    files = [f for f in files if fnmatch.fnmatch(f, pattern)]
            
            return "\n".join(sorted(files))
            
        except Exception as e:
            return f"Error finding files: {e}"
    
    def _handle_grep_files(self, command: str) -> str:
        """Handle grep commands."""
        try:
            # This is a simplified grep implementation
            # In a full implementation, you'd parse the grep options properly
            parts = command.split()
            if len(parts) < 2:
                return "Usage: grep <pattern> [files...]"
            
            # Handle quoted patterns
            pattern = parts[1].strip("'\"")
            files_to_search = parts[2:] if len(parts) > 2 else self.repo_manager.list_files()
            
            results = []
            for file_path in files_to_search:
                content = self.repo_manager.get_file_content(file_path)
                if content:
                    lines = content.split('\n')
                    for line_num, line in enumerate(lines, 1):
                        if pattern in line:
                            results.append(f"{file_path}:{line_num}:{line}")
            
            return "\n".join(results) if results else f"Pattern '{pattern}' not found"
            
        except Exception as e:
            return f"Error searching files: {e}"
    
    def _handle_git_command(self, command: str) -> str:
        """Handle git commands."""
        # Git operations are not supported in web mode
        return f"Git operations are not supported in web mode. Command blocked: {command}"
    
    def _handle_mkdir(self, command: str) -> str:
        """Handle mkdir commands."""
        return "Directory creation is handled automatically in web mode."
    
    def _handle_touch(self, command: str) -> str:
        """Handle touch commands."""
        return "File creation is handled automatically in web mode."
    
    def _handle_rm(self, command: str) -> str:
        """Handle rm commands."""
        return "File deletion is not supported in web mode for safety."
    
    def _handle_copy(self, command: str) -> str:
        """Handle cp/copy commands."""
        return "File copying is not supported in web mode."
    
    def _handle_move(self, command: str) -> str:
        """Handle mv/move commands."""
        return "File moving is not supported in web mode."
    
    def _track_file_modification(self, filename: str, content: str):
        """Track file modifications for web display."""
        self._file_modifications[filename] = content
        
        # Update context if file is in context
        if filename in self._context_files:
            self._context_files[filename].is_modified = True
        
        logger.info(f"Tracked file modification: {filename}")
    
    async def process_message(self, message: str, context: Optional[Dict] = None) -> CosmosResponse:
        """
        Process a message using Cosmos AI logic.
        
        Args:
            message: User message to process
            context: Optional context information
            
        Returns:
            CosmosResponse with AI response and metadata
        """
        try:
            logger.info(f"Processing message with model: {self.model}")
            
            # Clear previous state
            self._shell_commands_intercepted.clear()
            if hasattr(self.io, 'conversion_notes'):
                self.io.conversion_notes.clear()
            
            # Update context files in coder
            self._update_coder_context()
            
            # Process the message through Cosmos
            response_content = ""
            try:
                # Use the coder's run method with the message
                response_content = self.coder.run(with_message=message, preproc=True)
                
                if not response_content:
                    response_content = "I understand your request. How can I help you with your code?"
                
            except Exception as e:
                logger.error(f"Error in Cosmos processing: {e}")
                response_content = f"I encountered an error while processing your request: {str(e)}"
            
            # Get captured output from IO
            captured = self.io.get_captured_output()
            
            # Process response for web-safe display
            processed_response = self.response_processor.process_response(
                content=response_content,
                shell_commands_converted=self._shell_commands_intercepted.copy(),
                conversion_notes="\n".join(captured.get('conversion_notes', [])),
                metadata={
                    'model_used': self.model,
                    'context_file_count': len(self._context_files),
                    'shell_commands_intercepted': len(self._shell_commands_intercepted),
                    'conversion_status': asdict(self._conversion_status),
                    'captured_output': captured
                }
            )
            
            # Prepare response
            response = CosmosResponse(
                content=processed_response.content,
                context_files_used=list(self._context_files.keys()),
                shell_commands_converted=self._shell_commands_intercepted.copy(),
                conversion_notes=processed_response.conversion_notes,
                metadata=processed_response.metadata
            )
            
            logger.info("Message processed successfully")
            return response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return CosmosResponse(
                content="I apologize, but I encountered an error processing your request.",
                context_files_used=[],
                shell_commands_converted=[],
                conversion_notes=None,
                error=str(e)
            )
    
    def _update_coder_context(self):
        """Update the coder with current context files."""
        try:
            # Clear existing files
            self.coder.abs_fnames.clear()
            
            # Add context files to coder
            for file_path in self._context_files.keys():
                # Create a temporary file path for the coder
                temp_file_path = os.path.join(self.temp_dir, file_path.replace('/', '_'))
                
                # Get file content
                content = self.repo_manager.get_file_content(file_path)
                if content:
                    # Write to temp file for coder
                    os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
                    with open(temp_file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    # Add to coder's file list
                    self.coder.abs_fnames.add(temp_file_path)
            
            logger.debug(f"Updated coder context with {len(self._context_files)} files")
            
        except Exception as e:
            logger.error(f"Error updating coder context: {e}")
    
    def get_supported_models(self) -> List[str]:
        """Get list of supported model aliases."""
        return list(MODEL_ALIASES.keys())
    
    def set_model(self, model: str) -> bool:
        """
        Set the AI model to use.
        
        Args:
            model: Model alias to use
            
        Returns:
            True if successful, False if invalid model
        """
        if model not in MODEL_ALIASES:
            logger.error(f"Invalid model: {model}")
            return False
        
        try:
            self.model = model
            
            # Update Cosmos model
            canonical_model_name = MODEL_ALIASES[model]
            self.cosmos_model = Model(canonical_model_name)
            
            # Update coder with new model
            self.coder.main_model = self.cosmos_model
            
            logger.info(f"Model updated to: {model}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting model: {e}")
            return False
    
    def get_repo_context(self) -> Dict[str, Any]:
        """Get repository context information."""
        try:
            repo_info = self.repo_manager.get_repository_info()
            
            return {
                'repository_url': self.repo_manager.repo_url,
                'branch': self.repo_manager.branch,
                'file_count': repo_info.get('file_count', 0),
                'context_files': len(self._context_files),
                'has_repo_map': bool(self.repo_manager.get_repo_map()),
                'repo_info': repo_info
            }
            
        except Exception as e:
            logger.error(f"Error getting repo context: {e}")
            return {}
    
    def get_context_files(self) -> List[ContextFile]:
        """Get list of files currently in context."""
        return list(self._context_files.values())
    
    def add_file_to_context(self, file_path: str) -> bool:
        """
        Add a file to the context.
        
        Args:
            file_path: Path to the file to add
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if file exists in repository
            metadata = self.repo_manager.get_file_metadata(file_path)
            if not metadata:
                logger.error(f"File not found in repository: {file_path}")
                return False
            
            # Create context file entry
            context_file = ContextFile(
                path=file_path,
                name=metadata.name,
                size=metadata.size,
                language=metadata.language,
                added_at=datetime.now(),
                is_modified=False
            )
            
            # Add to context
            self._context_files[file_path] = context_file
            
            logger.info(f"Added file to context: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding file to context: {e}")
            return False
    
    def remove_file_from_context(self, file_path: str) -> bool:
        """
        Remove a file from the context.
        
        Args:
            file_path: Path to the file to remove
            
        Returns:
            True if successful, False if file not in context
        """
        try:
            if file_path in self._context_files:
                del self._context_files[file_path]
                logger.info(f"Removed file from context: {file_path}")
                return True
            else:
                logger.warning(f"File not in context: {file_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing file from context: {e}")
            return False
    
    def get_conversion_status(self) -> ConversionStatus:
        """Get current shell-to-web conversion status."""
        return self._conversion_status
    
    def _classify_command_type(self, command: str) -> ConversionType:
        """
        Classify the type of shell command for conversion tracking.
        
        Args:
            command: Shell command to classify
            
        Returns:
            ConversionType enum value
        """
        command = command.strip().lower()
        
        if command.startswith(('ls', 'dir', 'find')):
            return ConversionType.DIRECTORY_OPERATION
        elif command.startswith(('cat', 'type', 'head', 'tail', 'less', 'more')):
            return ConversionType.FILE_OPERATION
        elif command.startswith(('grep', 'awk', 'sed')):
            return ConversionType.SEARCH_OPERATION
        elif command.startswith('git'):
            return ConversionType.GIT_OPERATION
        elif command.startswith(('mkdir', 'rmdir', 'rm', 'cp', 'mv', 'touch')):
            return ConversionType.FILE_OPERATION
        else:
            return ConversionType.SHELL_COMMAND
    
    def _determine_command_priority(self, command: str) -> ConversionPriority:
        """
        Determine the priority of a command for conversion.
        
        Args:
            command: Shell command to prioritize
            
        Returns:
            ConversionPriority enum value
        """
        command = command.strip().lower()
        
        # High priority commands (commonly used, important for user experience)
        if command.startswith(('ls', 'cat', 'grep', 'find')):
            return ConversionPriority.HIGH
        
        # Critical priority commands (essential for functionality)
        if command.startswith(('git', 'cd')):
            return ConversionPriority.CRITICAL
        
        # Low priority commands (less commonly used)
        if command.startswith(('head', 'tail', 'less', 'more', 'awk', 'sed')):
            return ConversionPriority.LOW
        
        # Default to medium priority
        return ConversionPriority.MEDIUM
    
    def set_session_id(self, session_id: str):
        """
        Set the current session ID for conversion tracking.
        
        Args:
            session_id: Session identifier
        """
        self._current_session_id = session_id
        logger.debug(f"Set session ID for conversion tracking: {session_id}")
    
    async def get_conversion_progress(self) -> Dict[str, Any]:
        """
        Get conversion progress for the current session.
        
        Returns:
            Dictionary with conversion progress information
        """
        try:
            if hasattr(self, '_current_session_id') and self._current_session_id:
                progress = await conversion_tracking_service.get_session_progress(self._current_session_id)
                return {
                    'session_progress': progress.dict(),
                    'local_status': self._conversion_status.__dict__
                }
            else:
                return {
                    'session_progress': None,
                    'local_status': self._conversion_status.__dict__
                }
        except Exception as e:
            logger.error(f"Error getting conversion progress: {e}")
            return {
                'session_progress': None,
                'local_status': self._conversion_status.__dict__,
                'error': str(e)
            }
    
    async def get_conversion_operations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent conversion operations for the current session.
        
        Args:
            limit: Maximum number of operations to return
            
        Returns:
            List of operation dictionaries
        """
        try:
            if hasattr(self, '_current_session_id') and self._current_session_id:
                operations = await conversion_tracking_service.get_session_operations(
                    self._current_session_id, 
                    limit=limit
                )
                return [op.dict() for op in operations]
            else:
                return []
        except Exception as e:
            logger.error(f"Error getting conversion operations: {e}")
            return []
    
    def cleanup(self):
        """Clean up temporary resources."""
        try:
            # Restore original run_cmd function
            if hasattr(self, '_original_run_cmd'):
                run_cmd.run_cmd = self._original_run_cmd
            
            # Clean up temporary directory
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            
            logger.info("Cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()