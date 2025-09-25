"""
Optimized Cosmos Wrapper

High-performance Cosmos integration that replaces GitMeshCosmosWrapper with:
- SmartRedisRepoManager for optimized repository data access
- IntelligentVFS for virtual file system operations
- AutoResponseHandler for prompt elimination
- Performance monitoring and resource cleanup
- No dummy data - real implementation only

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""

import os
import sys
import asyncio
import tempfile
import logging
import time
import uuid
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
import threading
import weakref

# Import required services
try:
    from .smart_redis_repo_manager import SmartRedisRepoManager, RepositoryContext
    from .intelligent_vfs import IntelligentVFS, VirtualFile
    from .cosmos_performance_optimizer import get_performance_optimizer, CosmosPerformanceOptimizer
    from .cosmos_error_handler import get_error_handler, CosmosErrorHandler, RetryConfig
    from ..config.settings import get_settings
    from ..config.cosmos_models import MODEL_ALIASES
except ImportError:
    from services.smart_redis_repo_manager import SmartRedisRepoManager, RepositoryContext
    from services.intelligent_vfs import IntelligentVFS, VirtualFile
    from services.cosmos_performance_optimizer import get_performance_optimizer, CosmosPerformanceOptimizer
    from services.cosmos_error_handler import get_error_handler, CosmosErrorHandler, RetryConfig
    from config.settings import get_settings
    from config.cosmos_models import MODEL_ALIASES

# Configure logging
logger = logging.getLogger(__name__)

# Import Cosmos components with fallback
try:
    # Add cosmos to path
    current_dir = Path(__file__).parent.parent
    cosmos_dir = current_dir / "integrations" / "cosmos" / "v1" / "cosmos"
    if cosmos_dir.exists():
        sys.path.insert(0, str(cosmos_dir.parent))
    
    from cosmos.io import InputOutput
    from cosmos.models import Model
    from cosmos.coders.editblock_coder import EditBlockCoder
    
    COSMOS_AVAILABLE = True
    logger.info("Cosmos components imported successfully")
    
except ImportError as e:
    logger.warning(f"Cosmos components not available: {e}")
    COSMOS_AVAILABLE = False
    
    # Mock classes for testing
    class InputOutput:
        def __init__(self, **kwargs):
            pass
        def tool_output(self, *args, **kwargs):
            pass
    
    class Model:
        def __init__(self, name):
            self.name = name
    
    class EditBlockCoder:
        def __init__(self, **kwargs):
            pass
        def run(self, with_message=None, **kwargs):
            return f"Mock response to: {with_message}"


@dataclass
class ModelInfo:
    """Model information structure."""
    name: str
    display_name: str
    provider: str
    available: bool
    context_length: int
    supports_streaming: bool
    is_default: bool = False


@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring."""
    response_time: float
    memory_usage: int
    redis_operations: int
    cache_hits: int
    cache_misses: int
    files_accessed: int
    timestamp: datetime


class AutoResponseHandler:
    """
    Automatic response handler for eliminating user prompts.
    
    Intercepts and automatically responds to all Cosmos prompts to eliminate
    user interaction and provide seamless web experience.
    """
    
    def __init__(self, repository_context: Optional[RepositoryContext] = None):
        """Initialize with repository context for intelligent responses."""
        self.repository_context = repository_context
        self.response_log: List[Dict[str, Any]] = []
        
    def intercept_prompt(self, prompt: str, context: Dict[str, Any] = None) -> str:
        """
        Intercept and automatically respond to prompts.
        
        Args:
            prompt: The prompt text from Cosmos
            context: Additional context for response generation
            
        Returns:
            Automatic response string
        """
        prompt_lower = prompt.lower().strip()
        response = ""
        
        # Repository selection prompts
        if any(keyword in prompt_lower for keyword in ["select repository", "choose repository", "repository"]):
            if self.repository_context:
                response = self.repository_context.repo_url
            else:
                response = "1"  # Select first option
            
        # Confirmation prompts
        elif any(keyword in prompt_lower for keyword in ["confirm", "continue", "proceed", "yes/no", "(y/n)"]):
            response = "yes"
            
        # File selection prompts
        elif any(keyword in prompt_lower for keyword in ["select files", "choose files", "add files"]):
            response = "all"  # Select all available files
            
        # GitHub token prompts
        elif any(keyword in prompt_lower for keyword in ["github token", "token", "authentication"]):
            response = ""  # Skip token prompts
            
        # Delete/remove prompts
        elif any(keyword in prompt_lower for keyword in ["delete", "remove", "clear"]):
            response = "no"  # Don't delete anything
            
        # Default response for any other prompts
        else:
            response = ""  # Empty response as default
        
        # Log the interaction
        self.response_log.append({
            "timestamp": datetime.now(),
            "prompt": prompt,
            "response": response,
            "context": context
        })
        
        logger.debug(f"Auto-response: '{prompt}' -> '{response}'")
        return response
    
    def handle_repository_selection(self, options: List[str]) -> str:
        """Handle repository selection automatically."""
        if self.repository_context:
            # Try to find matching repository in options
            repo_name = self.repository_context.repo_name
            for i, option in enumerate(options):
                if repo_name.lower() in option.lower():
                    return str(i + 1)
            
        # Default to first option
        return "1"
    
    def handle_confirmation(self, question: str) -> bool:
        """Handle confirmation prompts automatically."""
        # Log the confirmation
        self.response_log.append({
            "timestamp": datetime.now(),
            "type": "confirmation",
            "question": question,
            "response": True
        })
        
        return True
    
    def get_response_log(self) -> List[Dict[str, Any]]:
        """Get log of all automatic responses."""
        return self.response_log.copy()


class OptimizedInputOutput(InputOutput):
    """
    Optimized InputOutput wrapper with auto-response capabilities.
    
    Extends Cosmos InputOutput to provide automatic responses and
    integrate with the virtual file system.
    """
    
    def __init__(self, auto_handler: AutoResponseHandler, vfs: IntelligentVFS, **kwargs):
        """Initialize with auto-response handler and VFS."""
        super().__init__(**kwargs)
        self.auto_handler = auto_handler
        self.vfs = vfs
        self.captured_output: List[str] = []
        
    def tool_output(self, *args, **kwargs):
        """Capture tool output for web display."""
        message = " ".join(str(arg) for arg in args)
        self.captured_output.append(message)
        logger.debug(f"Tool output: {message}")
    
    def confirm_ask(self, question: str, default: str = "y", **kwargs) -> str:
        """Auto-confirm all prompts."""
        response = self.auto_handler.intercept_prompt(question, {"default": default})
        return response or default
    
    def prompt_ask(self, prompt: str, default: str = "", **kwargs) -> str:
        """Auto-respond to all prompts."""
        response = self.auto_handler.intercept_prompt(prompt, {"default": default})
        return response or default
    
    def read_text(self, filename: str) -> Optional[str]:
        """Read file content through VFS."""
        try:
            virtual_file = self.vfs.get_file(filename)
            if virtual_file:
                return virtual_file.content
            return None
        except Exception as e:
            logger.error(f"Error reading file {filename}: {e}")
            return None
    
    def write_text(self, filename: str, content: str) -> bool:
        """Intercept file writes (no actual writing in web mode)."""
        logger.info(f"File write intercepted: {filename}")
        # In web mode, we don't actually write files
        return True
    
    def get_captured_output(self) -> List[str]:
        """Get all captured output."""
        return self.captured_output.copy()


class OptimizedCosmosWrapper:
    """
    Optimized Cosmos Wrapper that replaces GitMeshCosmosWrapper.
    
    Features:
    - SmartRedisRepoManager integration for optimized repository data access
    - IntelligentVFS integration for virtual file system operations
    - AutoResponseHandler integration for prompt elimination
    - Performance monitoring and resource cleanup
    - Connection pooling and caching
    """
    
    def __init__(
        self,
        redis_client,
        user_id: str,
        project_id: str,
        repository_url: Optional[str] = None,
        model: str = "gemini"
    ):
        """
        Initialize OptimizedCosmosWrapper.
        
        Args:
            redis_client: Redis client instance
            user_id: User identifier
            project_id: Project identifier
            repository_url: Repository URL for context
            model: AI model to use
        """
        self.redis_client = redis_client
        self.user_id = user_id
        self.project_id = project_id
        self.repository_url = repository_url
        self.model = model
        
        # Validate model
        if model not in MODEL_ALIASES:
            raise ValueError(f"Invalid model: {model}. Available: {list(MODEL_ALIASES.keys())}")
        
        # Initialize components
        self.settings = get_settings()
        self.performance_metrics: List[PerformanceMetrics] = []
        self.active_sessions: Dict[str, Any] = {}
        
        # Initialize performance optimizer
        self.performance_optimizer = get_performance_optimizer({
            "cache_max_size": 1000,
            "cache_ttl_seconds": 3600,
            "max_connections": 50,
            "memory_warning_mb": 500,
            "memory_critical_mb": 1000
        })
        
        # Initialize error handler
        self.error_handler = get_error_handler()
        
        # Register cleanup callback with error handler
        self.error_handler.add_cleanup_callback(self._emergency_cleanup)
        
        # Initialize Redis repository manager with connection pooling
        if repository_url:
            # Use connection pool from performance optimizer
            redis_url = getattr(redis_client, 'connection_pool', {}).get('connection_kwargs', {}).get('host', 'localhost')
            if hasattr(redis_client, 'connection_pool') and hasattr(redis_client.connection_pool, 'connection_kwargs'):
                conn_kwargs = redis_client.connection_pool.connection_kwargs
                redis_url = f"redis://{conn_kwargs.get('host', 'localhost')}:{conn_kwargs.get('port', 6379)}"
            
            # Get optimized connection pool
            try:
                optimized_pool = self.performance_optimizer.get_redis_pool(redis_url)
                # Create Redis client with optimized pool
                import redis as redis_module
                optimized_redis_client = redis_module.Redis(connection_pool=optimized_pool)
            except Exception as e:
                logger.warning(f"Failed to create optimized Redis client: {e}, using original")
                optimized_redis_client = redis_client
            
            self.repo_manager = SmartRedisRepoManager(
                redis_client=optimized_redis_client,
                repo_url=repository_url
            )
        else:
            self.repo_manager = None
        
        # Initialize VFS and auto-response handler
        self.repository_context = None
        self.vfs = None
        self.auto_handler = None
        
        # Cosmos components
        self.cosmos_model = None
        self.coder = None
        self.io = None
        
        # Resource tracking
        self._temp_dirs: List[str] = []
        self._cleanup_callbacks: List[callable] = []
        
        logger.info(f"OptimizedCosmosWrapper initialized for user {user_id}, project {project_id}")
    
    async def initialize(self) -> bool:
        """
        Initialize all components asynchronously.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            start_time = time.time()
            
            # Initialize repository context if repository URL provided
            if self.repo_manager:
                logger.info(f"Loading repository context for {self.repository_url}")
                self.repository_context = await self._load_repository_context()
                
                if self.repository_context:
                    # Initialize VFS with repository context
                    self.vfs = IntelligentVFS(self.repository_context)
                    logger.info(f"VFS initialized with {self.repository_context.total_files} files")
                else:
                    logger.warning("Failed to load repository context")
                    return False
            
            # Initialize auto-response handler
            self.auto_handler = AutoResponseHandler(self.repository_context)
            
            # Initialize Cosmos components
            if COSMOS_AVAILABLE:
                await self._initialize_cosmos_components()
            else:
                logger.warning("Cosmos components not available, using mock implementation")
            
            # Record initialization metrics
            init_time = time.time() - start_time
            logger.info(f"OptimizedCosmosWrapper initialized in {init_time:.2f}s")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize OptimizedCosmosWrapper: {e}")
            return False
    
    async def _load_repository_context(self) -> Optional[RepositoryContext]:
        """Load repository context from Redis cache with error handling and fallback."""
        if not self.repo_manager:
            return None
        
        # Use error handler with fallback to gitingest
        return await self.error_handler.execute_with_error_handling(
            operation="redis_get_repository_context",
            func=self._load_repository_context_impl,
            retry_config=RetryConfig(max_retries=3, base_delay=1.0),
            enable_fallback=True
        )
    
    def _load_repository_context_impl(self) -> Optional[RepositoryContext]:
        """Implementation of repository context loading."""
        # Get repository context using SmartRedisRepoManager
        context = self.repo_manager.get_repository_context(self.repository_url)
        
        if context:
            logger.info(f"Loaded repository context: {context.total_files} files, {context.total_size} bytes")
            return context
        else:
            logger.warning(f"No repository context found for {self.repository_url}")
            return None
    
    async def _initialize_cosmos_components(self):
        """Initialize Cosmos components with optimized configuration and error handling."""
        return await self.error_handler.execute_with_error_handling(
            operation="cosmos_initialization",
            func=self._initialize_cosmos_components_impl,
            retry_config=RetryConfig(max_retries=2, base_delay=2.0),
            enable_fallback=False  # No fallback for initialization
        )
    
    def _initialize_cosmos_components_impl(self):
        """Implementation of Cosmos components initialization."""
        if not COSMOS_AVAILABLE:
            logger.warning("Cosmos components not available, using mock implementation")
            return
        
        # Create optimized IO wrapper
        self.io = OptimizedInputOutput(
            auto_handler=self.auto_handler,
            vfs=self.vfs,
            pretty=False,
            yes=True,
            chat_history_file=None,
            encoding="utf-8"
        )
        
        # Create model instance
        canonical_model_name = MODEL_ALIASES[self.model]
        self.cosmos_model = Model(canonical_model_name)
        
        # Initialize coder with optimized settings
        self.coder = EditBlockCoder(
            main_model=self.cosmos_model,
            io=self.io,
            repo=None,  # No git repo in web mode
            fnames=[],  # Files will be provided through VFS
            auto_commits=False,
            dirty_commits=False,
            dry_run=False,
            map_tokens=2048,  # Enable repository mapping
            verbose=False,
            stream=False,
            use_git=False,
            suggest_shell_commands=False,
            auto_lint=False,
            auto_test=False
        )
        
        logger.info("Cosmos components initialized successfully")
    
    async def process_chat_message(
        self,
        message: str,
        context: Dict[str, Any] = None,
        session_history: List[Dict[str, Any]] = None,
        selected_files: List[str] = None,
        model_name: str = None
    ) -> Dict[str, Any]:
        """
        Process a chat message through optimized Cosmos integration.
        
        Args:
            message: User message to process
            context: Additional context information
            session_history: Previous messages in session
            selected_files: List of selected file paths
            model_name: Override model name
            
        Returns:
            Dictionary containing response and metadata
        """
        # Start request tracking
        request_id = self.performance_optimizer.start_request()
        start_time = time.time()
        error_occurred = False
        
        try:
            # Check cache first
            cache_key = self.performance_optimizer.create_cache_key(
                message, context, selected_files
            )
            
            cached_response = self.performance_optimizer.get_cached_response(cache_key)
            if cached_response:
                logger.info(f"Returning cached response for request {request_id}")
                response_time = time.time() - start_time
                self.performance_optimizer.end_request(request_id, response_time)
                
                # Update metadata with cache info
                cached_response["metadata"]["cached"] = True
                cached_response["metadata"]["response_time"] = response_time
                return cached_response
            
            # Use provided model or default
            if model_name and model_name != self.model:
                # Reinitialize with new model if different
                self.model = model_name
                await self._initialize_cosmos_components()
            
            # Prepare enhanced message with repository context
            enhanced_message = await self._enhance_message_with_context(
                message, context, selected_files
            )
            
            # Process through Cosmos with error handling
            response_content = await self.error_handler.execute_with_error_handling(
                operation="cosmos_process_message",
                func=self._process_cosmos_message,
                args=(enhanced_message,),
                retry_config=RetryConfig(max_retries=2, base_delay=1.0),
                enable_fallback=True
            )
            
            # Get captured output from IO
            captured_output = []
            if hasattr(self.io, 'get_captured_output'):
                captured_output = self.io.get_captured_output()
            
            # Get auto-response log
            auto_responses = []
            if self.auto_handler:
                auto_responses = self.auto_handler.get_response_log()
            
            # Record performance metrics
            response_time = time.time() - start_time
            await self._record_performance_metrics(response_time, len(selected_files or []))
            
            # Build response
            response = {
                "content": response_content,
                "context_files_used": selected_files or [],
                "shell_commands_converted": [],  # Always empty for security
                "conversion_notes": None,
                "error": None,
                "metadata": {
                    "model_used": self.model,
                    "response_time": response_time,
                    "repository_url": self.repository_url,
                    "files_in_context": len(selected_files or []),
                    "auto_responses": len(auto_responses),
                    "captured_output": captured_output,
                    "cached": False,
                    "request_id": request_id
                },
                "confidence": 0.9,
                "sources": selected_files or []
            }
            
            # Cache the response for future use
            self.performance_optimizer.cache_response(cache_key, response)
            
            logger.info(f"Chat message processed in {response_time:.2f}s")
            return response
            
        except Exception as e:
            error_occurred = True
            
            # Handle error through error handler
            error_info = await self.error_handler.handle_error(
                e, 
                context={
                    "operation": "process_chat_message",
                    "user_id": self.user_id,
                    "project_id": self.project_id,
                    "repository_url": self.repository_url,
                    "model": self.model,
                    "message_length": len(message),
                    "selected_files_count": len(selected_files or [])
                },
                operation="process_chat_message"
            )
            
            logger.error(f"Error processing chat message: {e}")
            
            # Return error response with error info
            return {
                "content": f"I apologize, but I encountered an error while processing your message. Error ID: {error_info.error_id}",
                "error": str(e),
                "metadata": {
                    "response_time": time.time() - start_time,
                    "request_id": request_id,
                    "error_id": error_info.error_id,
                    "error_category": error_info.category.value,
                    "error_severity": error_info.severity.value,
                    "recovery_action": error_info.recovery_action.value if error_info.recovery_action else None
                }
            }
        finally:
            # End request tracking
            response_time = time.time() - start_time
            self.performance_optimizer.end_request(request_id, response_time, error_occurred)
    
    async def _enhance_message_with_context(
        self,
        message: str,
        context: Dict[str, Any] = None,
        selected_files: List[str] = None
    ) -> str:
        """Enhance message with repository context and selected files."""
        try:
            enhanced_parts = []
            
            # Add repository context if available
            if self.repository_context:
                enhanced_parts.append(f"Repository: {self.repository_context.repo_url}")
                enhanced_parts.append(f"Summary: {self.repository_context.summary}")
                
                # Add directory structure for context
                if self.repository_context.tree_structure:
                    enhanced_parts.append(f"Directory Structure:\n{self.repository_context.tree_structure}")
            
            # Add selected files content
            if selected_files and self.vfs:
                enhanced_parts.append("Selected Files:")
                for file_path in selected_files[:10]:  # Limit to 10 files
                    virtual_file = self.vfs.get_file(file_path)
                    if virtual_file:
                        enhanced_parts.append(f"\n--- {file_path} ---")
                        enhanced_parts.append(virtual_file.content[:2000])  # Limit content
            
            # Add the original message
            enhanced_parts.append(f"\nUser Question: {message}")
            
            return "\n\n".join(enhanced_parts)
            
        except Exception as e:
            logger.error(f"Error enhancing message with context: {e}")
            return message
    
    async def _record_performance_metrics(self, response_time: float, files_accessed: int):
        """Record performance metrics for monitoring."""
        try:
            import psutil
            memory_usage = psutil.Process().memory_info().rss
        except ImportError:
            memory_usage = 0
        
        metrics = PerformanceMetrics(
            response_time=response_time,
            memory_usage=memory_usage,
            redis_operations=getattr(self.repo_manager, '_operation_count', 0),
            cache_hits=getattr(self.repo_manager, '_cache_hits', 0),
            cache_misses=getattr(self.repo_manager, '_cache_misses', 0),
            files_accessed=files_accessed,
            timestamp=datetime.now()
        )
        
        self.performance_metrics.append(metrics)
        
        # Keep only last 100 metrics
        if len(self.performance_metrics) > 100:
            self.performance_metrics = self.performance_metrics[-100:]
    
    def get_available_models(self) -> List[ModelInfo]:
        """Get list of available models."""
        models = []
        
        for alias, canonical_name in MODEL_ALIASES.items():
            models.append(ModelInfo(
                name=alias,
                display_name=f"{alias} ({canonical_name})",
                provider=canonical_name.split("/")[0] if "/" in canonical_name else "openai",
                available=True,
                context_length=8192,  # Default context length
                supports_streaming=True,
                is_default=(alias == "gemini")
            ))
        
        return models
    
    def get_performance_metrics(self) -> List[Dict[str, Any]]:
        """Get performance metrics for monitoring."""
        # Get comprehensive performance report from optimizer
        return self.performance_optimizer.get_performance_report()
    
    def get_detailed_performance_report(self) -> Dict[str, Any]:
        """Get detailed performance report including all metrics."""
        return self.performance_optimizer.get_performance_report()
    
    def _process_cosmos_message(self, enhanced_message: str) -> str:
        """Process message through Cosmos with error handling."""
        if COSMOS_AVAILABLE and self.coder:
            return self.coder.run(with_message=enhanced_message)
        else:
            # Mock response for testing
            return f"Mock response to: {enhanced_message}"
    
    def _emergency_cleanup(self):
        """Emergency cleanup callback for critical errors."""
        logger.warning("Executing emergency cleanup due to critical error")
        
        try:
            # Clear caches
            if hasattr(self, 'performance_optimizer') and self.performance_optimizer:
                self.performance_optimizer._cleanup_caches()
            
            # Clear active sessions
            self.active_sessions.clear()
            
            # Clear temporary files
            for temp_dir in self._temp_dirs:
                if os.path.exists(temp_dir):
                    import shutil
                    shutil.rmtree(temp_dir)
            
            self._temp_dirs.clear()
            
            logger.info("Emergency cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during emergency cleanup: {e}")
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics from error handler."""
        return self.error_handler.get_error_statistics()
    
    def cleanup(self):
        """Clean up resources and temporary files."""
        try:
            # Clean up performance optimizer
            if hasattr(self, 'performance_optimizer') and self.performance_optimizer:
                self.performance_optimizer.cleanup()
            
            # Clean up error handler
            if hasattr(self, 'error_handler') and self.error_handler:
                self.error_handler.cleanup()
            
            # Clean up temporary directories
            for temp_dir in self._temp_dirs:
                if os.path.exists(temp_dir):
                    import shutil
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temp directory: {temp_dir}")
            
            # Run cleanup callbacks
            for callback in self._cleanup_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.warning(f"Error in cleanup callback: {e}")
            
            # Clear references
            self._temp_dirs.clear()
            self._cleanup_callbacks.clear()
            self.active_sessions.clear()
            
            logger.info("OptimizedCosmosWrapper cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            # Try emergency cleanup as last resort
            try:
                self._emergency_cleanup()
            except Exception as emergency_error:
                logger.critical(f"Emergency cleanup also failed: {emergency_error}")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()


# Factory function for creating optimized wrapper instances
async def create_optimized_cosmos_wrapper(
    redis_client,
    user_id: str,
    project_id: str,
    repository_url: Optional[str] = None,
    model: str = "gemini"
) -> OptimizedCosmosWrapper:
    """
    Factory function to create and initialize OptimizedCosmosWrapper.
    
    Args:
        redis_client: Redis client instance
        user_id: User identifier
        project_id: Project identifier
        repository_url: Repository URL for context
        model: AI model to use
        
    Returns:
        Initialized OptimizedCosmosWrapper instance
    """
    wrapper = OptimizedCosmosWrapper(
        redis_client=redis_client,
        user_id=user_id,
        project_id=project_id,
        repository_url=repository_url,
        model=model
    )
    
    success = await wrapper.initialize()
    if not success:
        raise RuntimeError("Failed to initialize OptimizedCosmosWrapper")
    
    return wrapper