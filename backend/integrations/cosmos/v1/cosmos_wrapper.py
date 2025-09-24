"""
GitMesh Cosmos Wrapper
Integrates Cosmos CLI functionality into GitMesh web interface
"""
import os
import sys
import asyncio
import tempfile
import shutil
import uuid
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
import structlog
from unittest.mock import MagicMock

logger = structlog.get_logger(__name__)

# Add cosmos to path if available
current_dir = Path(__file__).parent
cosmos_dir = current_dir / "cosmos"
if cosmos_dir.exists():
    sys.path.insert(0, str(cosmos_dir.parent))

# Safe imports for Cosmos with fallback handling  
try:
    # Only mock audio modules that aren't needed for web interface
    
    # Mock pydub and its submodules comprehensively
    mock_pydub = MagicMock()
    mock_pydub.AudioSegment = MagicMock()
    mock_pydub.exceptions = MagicMock()
    mock_pydub.playback = MagicMock()
    
    # Patch the audio modules before importing cosmos
    sys.modules['audioop'] = MagicMock()
    sys.modules['pyaudioop'] = MagicMock()
    sys.modules['pydub'] = mock_pydub
    sys.modules['pydub.AudioSegment'] = mock_pydub.AudioSegment
    sys.modules['pydub.exceptions'] = mock_pydub.exceptions
    sys.modules['pydub.playback'] = mock_pydub.playbook
    
    # Import core cosmos components first (skip main.py for now)
    from cosmos.io import InputOutput
    from cosmos.models import Model, MODEL_ALIASES
    from cosmos import models
    
    # Try to import main later - if it fails, we'll use a direct approach
    try:
        from cosmos.main import main as cosmos_main
        COSMOS_MAIN_AVAILABLE = True
    except Exception as main_error:
        logger.warning(f"Cosmos main.py has issues, using direct approach: {main_error}")
        cosmos_main = None
        COSMOS_MAIN_AVAILABLE = False
    
    COSMOS_AVAILABLE = True
    logger.info("✓ Cosmos core components successfully imported")
except ImportError as e:
    COSMOS_AVAILABLE = False
    COSMOS_MAIN_AVAILABLE = False
    models = None
    logger.warning(f"Failed to import cosmos: {e}")
except Exception as e:
    COSMOS_AVAILABLE = False
    COSMOS_MAIN_AVAILABLE = False
    models = None
    logger.error(f"Error importing cosmos: {e}")

class GitMeshCosmosWrapper:
    """
    Wrapper that bridges GitMesh web interface to Cosmos CLI functionality
    Provides same features as CLI but adapted for web usage
    """
    
    def __init__(self, user_id: str, project_id: str, repository_id: str = None, branch: str = "main"):
        self.user_id = user_id
        self.project_id = project_id
        self.repository_id = repository_id or project_id
        self.branch = branch
        self.temp_dir = None
        self.cosmos_available = COSMOS_AVAILABLE
        self.active_sessions = {}  # Track active cosmos sessions
        
        # Initialize models list if cosmos is available
        self.available_models = []
        if COSMOS_AVAILABLE:
            self._load_available_models()
    
    def _load_available_models(self):
        """Load available models from cosmos"""
        try:
            # Get models that are compatible with cosmos
            from cosmos.models import MODEL_ALIASES, model_info_manager
            
            # Use model aliases from cosmos, with gemini as default
            self.available_models = []
            
            # Add gemini as the first/default option
            default_aliases = ["gemini", "sonnet", "4o", "flash", "haiku", "deepseek", "35turbo"]
            processed_aliases = set()
            
            # First add prioritized aliases
            for alias in default_aliases:
                if alias in MODEL_ALIASES:
                    canonical_name = MODEL_ALIASES[alias]
                    try:
                        # Test if model is actually available
                        test_model = Model(alias, verbose=False)  # Use alias, not canonical
                        self.available_models.append({
                            "name": alias,
                            "display_name": f"{alias} ({canonical_name.replace('/', ' / ')})",
                            "provider": canonical_name.split("/")[0] if "/" in canonical_name else "openai",
                            "available": True,
                            "context_length": getattr(test_model, 'max_context_tokens', 8192),
                            "supports_streaming": getattr(test_model, 'streaming', True),
                            "is_default": alias == "gemini"
                        })
                        processed_aliases.add(alias)
                    except Exception as e:
                        logger.debug(f"Model alias {alias} not available: {e}")
                        continue
            
            # Then add remaining aliases
            for alias, canonical_name in MODEL_ALIASES.items():
                if alias not in processed_aliases:
                    try:
                        test_model = Model(alias, verbose=False)
                        self.available_models.append({
                            "name": alias,
                            "display_name": f"{alias} ({canonical_name.replace('/', ' / ')})",
                            "provider": canonical_name.split("/")[0] if "/" in canonical_name else "openai",
                            "available": True,
                            "context_length": getattr(test_model, 'max_context_tokens', 8192),
                            "supports_streaming": getattr(test_model, 'streaming', True),
                            "is_default": False
                        })
                    except Exception as e:
                        logger.debug(f"Model alias {alias} not available: {e}")
                        continue
            
            logger.info(f"Loaded {len(self.available_models)} available model aliases for cosmos")
            
        except Exception as e:
            logger.error(f"Error loading cosmos models: {e}")
            self.available_models = []
            raise Exception(f"Failed to load cosmos models: {str(e)}")
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available models (equivalent to cosmos --list-models)"""
        if not self.cosmos_available:
            raise Exception("Cosmos is not available - check installation and dependencies")
        
        return self.available_models
    
    def _setup_temp_environment(self, repository_url: str = None):
        """Setup temporary environment for cosmos operation"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            return self.temp_dir
        
        # Create temp directory for this session
        self.temp_dir = tempfile.mkdtemp(prefix=f"cosmos_session_{self.user_id}_")
        
        # For GitMesh, we'll use Redis-cached repository data
        # No need to clone since cosmos will use Redis backend
        logger.info(f"Created temp environment: {self.temp_dir}")
        return self.temp_dir
    
    def _cleanup_temp_environment(self):
        """Clean up temporary files and directories."""
        try:
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temp directory: {self.temp_dir}")
                self.temp_dir = None
        except Exception as e:
            logger.warning(f"Failed to cleanup temp directory: {e}")
        
        # Clean up temporary repository directory
        try:
            if hasattr(self, 'temp_repo_dir') and self.temp_repo_dir and os.path.exists(self.temp_repo_dir):
                import shutil
                shutil.rmtree(self.temp_repo_dir)
                logger.info(f"Cleaned up temp repository directory: {self.temp_repo_dir}")
                self.temp_repo_dir = None
        except Exception as e:
            logger.warning(f"Failed to cleanup temp repository directory: {e}")

    def _parse_content_to_files(self, content: str) -> dict:
        """
        Parse gitingest content to extract individual files.
        
        Args:
            content: The content string from gitingest with file boundaries
            
        Returns:
            Dictionary mapping file paths to their content
        """
        import re
        
        files = {}
        if not content:
            return files
        
        # Split content by file boundaries
        # Pattern: ================================================
        #          FILE: path/to/file.ext
        #          ================================================
        #          content here...
        file_sections = re.split(r'={40,}', content)  # Allow more flexible separator length
        
        logger.info(f"File parsing: found {len(file_sections)} sections after splitting")
        
        current_file_path = None
        
        for i, section in enumerate(file_sections):
            section = section.strip()
            if not section:
                continue
                
            lines = section.split('\n')
            if len(lines) < 1:
                continue
                
            first_line = lines[0].strip()
            logger.info(f"Section {i}: First line = '{first_line[:50]}...'")
            
            # Check if this section has a FILE: header
            if first_line.startswith('FILE: '):
                current_file_path = first_line[6:].strip()  # Remove 'FILE: '
                # Content might be in the same section (after the FILE: line) or in the next section
                file_content = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""
                if file_content:
                    files[current_file_path] = file_content
                    logger.info(f"Extracted file (same section): {current_file_path} ({len(file_content)} chars)")
                    current_file_path = None  # Reset since we found content
            elif current_file_path and section:
                # This section contains the content for the previous FILE: header
                files[current_file_path] = section
                logger.info(f"Extracted file (next section): {current_file_path} ({len(section)} chars)")
                current_file_path = None  # Reset
            elif 'FILE: ' in first_line:
                # Handle cases where FILE: might not be at the very start
                file_start = first_line.find('FILE: ')
                if file_start >= 0:
                    current_file_path = first_line[file_start + 6:].strip()
                    file_content = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""
                    if file_content:
                        files[current_file_path] = file_content
                        logger.info(f"Extracted file (alt): {current_file_path} ({len(file_content)} chars)")
                        current_file_path = None
        
        return files
    
    def _create_temp_repository_structure(self, virtual_files: dict, repo_name: str) -> str:
        """
        Create a temporary directory structure with the virtual files.
        
        Args:
            virtual_files: Dictionary mapping file paths to content
            repo_name: Name of repository for temp directory
            
        Returns:
            Path to temporary repository directory
        """
        import tempfile
        import shutil
        from pathlib import Path
        
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix=f"cosmos_repo_{repo_name.replace('/', '_')}_")
            temp_path = Path(temp_dir)
            
            # Create files
            for file_path, content in virtual_files.items():
                full_path = temp_path / file_path
                
                # Create parent directories if needed
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Write file content
                try:
                    full_path.write_text(content, encoding='utf-8')
                except UnicodeDecodeError:
                    # Handle binary files or encoding issues
                    full_path.write_bytes(content.encode('utf-8', errors='ignore'))
            
            return str(temp_path)
            
        except Exception as e:
            logger.error(f"Failed to create temp repository structure: {e}")
            return None

    async def process_chat_message(
        self, 
        message: str, 
        context: Dict[str, Any] = None,
        session_history: List[Dict[str, Any]] = None,
        selected_files: List[Dict[str, Any]] = None,
        model_name: str = "gpt-4o-mini"
    ) -> Dict[str, Any]:
        """
        Process a chat message through cosmos
        This is the main interface method that replaces cosmos CLI interaction
        """
        if not self.cosmos_available:
            raise Exception("Cosmos is not available - check installation and dependencies")
        
        try:
            # Setup environment - use temp directory for Redis cache mode (not local git)
            import os
            original_cwd = os.getcwd()
            
            # Create temp directory for Redis cache operations
            import tempfile
            temp_dir = tempfile.mkdtemp(prefix="cosmos_gitmesh_")
            os.chdir(temp_dir)
            
            # Create a custom IO handler for capturing cosmos output
            captured_output = []
            
            class GitMeshIO(InputOutput):
                def __init__(self, output_capture):
                    self.output_capture = output_capture
                    # Initialize with minimal required parameters
                    super().__init__(
                        pretty=False,
                        yes=True,  # Fixed: was yes_always=True
                        input_history_file=None,
                        chat_history_file=None,
                        user_input_color=None,
                        tool_output_color=None,
                        tool_warning_color=None,
                        tool_error_color=None,
                        assistant_output_color=None,
                        code_theme="default",
                        dry_run=False,
                        encoding="utf-8"
                    )
                
                def tool_output(self, *args, **kwargs):
                    output = " ".join(str(arg) for arg in args)
                    self.output_capture.append(("tool_output", output))
                
                def ai_output(self, content):
                    """Capture AI responses"""
                    self.output_capture.append(("ai_output", content))
                    return super().ai_output(content) if hasattr(super(), 'ai_output') else None
                
                def assistant_output(self, message, pretty=None):
                    """Capture assistant responses"""
                    self.output_capture.append(("assistant_output", message))
                    return super().assistant_output(message, pretty) if hasattr(super(), 'assistant_output') else None
                
                def confirm_ask(self, question):
                    return True  # Auto-confirm for web interface
                
                def prompt_ask(self, prompt, default=""):
                    # Log the exact prompt for debugging
                    logger.info(f"Cosmos prompt: '{prompt}' (default: '{default}')")
                    
                    # For repository selection prompts, automatically select current repo
                    if "repository" in prompt.lower() or "select repository" in prompt.lower():
                        # Use the current repository from GitMesh context
                        current_repo = getattr(self, 'current_repo_url', None)
                        if current_repo:
                            logger.info(f"Auto-selecting repository URL: {current_repo}")
                            return current_repo
                        # Fallback to first cached repo if available to avoid interactive prompt
                        logger.info("Auto-selecting first cached repository (option 1)")
                        return "1"  # Select first repository from cached list
                    
                    # Handle specific repository selection format: "Select repository (1-2), N for new, or D to delete:"
                    if "select repository" in prompt.lower() and "1-2" in prompt:
                        logger.info("Auto-selecting repository option 1 from cached list")  
                        return "1"
                    
                    # For any other prompts, return sensible defaults to avoid interactive mode
                    if "github token" in prompt.lower():
                        logger.info("Skipping GitHub token prompt")
                        return ""  # Skip GitHub token for now
                    if "delete" in prompt.lower():
                        logger.info("Responding 'N' to delete prompt")
                        return "N"  # Don't delete anything
                    if "fetch new" in prompt.lower():
                        logger.info("Responding 'N' to fetch new prompt")
                        return "N"  # Don't fetch new repos
                    
                    logger.info(f"Using default response: '{default}'")
                    return default
                
                def responds_to_cpr(self):
                    """Cursor Position Report - required by prompt_toolkit"""
                    return False
                
                def scroll_buffer_to_prompt(self):
                    """Scroll buffer method - required by prompt_toolkit"""
                    pass
                
                def reset_cursor_shape(self):
                    """Reset cursor shape method - required by prompt_toolkit"""
                    pass
                
                def show_cursor(self):
                    """Show cursor method - required by prompt_toolkit"""
                    pass
                
                def flush(self):
                    """Flush method - required by IO"""
                    pass
                
                def user_input(self, prompt=""):
                    """Override user input to provide automatic responses"""
                    logger.info(f"User input requested: '{prompt}'")
                    
                    # Handle repository selection specifically
                    if "select repository" in prompt.lower():
                        logger.info("Auto-responding '1' to repository selection")
                        return "1"
                    
                    # Default to first option or empty string
                    logger.info("Auto-responding with empty string")
                    return ""
            
            # Create IO handler with repository context
            io_handler = GitMeshIO(captured_output)
            # Pass current repository URL to IO handler for auto-selection
            if context and context.get("repository_url"):
                io_handler.current_repo_url = context["repository_url"]
            else:
                # Default to GitMesh repository
                io_handler.current_repo_url = "https://github.com/LF-Decentralized-Trust-Mentorships/gitmesh"
            
            # Get repository context from Redis cache (gitingest data)
            repo_context = ""
            try:
                if context and context.get("repository_url"):
                    # Try to get repository data from Redis cache
                    try:
                        import redis
                    except ImportError:
                        logger.warning("Redis module not available - cannot access repository cache")
                        redis = None
                    
                    import json
                    import os
                    
                    # Use GitMesh Redis configuration
                    redis_url = os.environ.get("REDIS_URL") or os.environ.get("REDIS_CLOUD_URL")
                    if redis_url and redis:
                        r = redis.from_url(redis_url, decode_responses=True)
                        
                        # Try different cache key formats that gitingest might use
                        repo_url = context["repository_url"]
                        repo_name = repo_url.split('/')[-1] if '/' in repo_url else repo_url
                        owner_repo = '/'.join(repo_url.split('/')[-2:]) if '/' in repo_url else repo_url
                        
                        # Try different possible cache keys (matching actual Redis structure)
                        possible_keys = [
                            f"repo:{owner_repo}:content",
                            f"repo:{owner_repo}:summary", 
                            f"repo:{owner_repo}:tree",
                            f"repo:{owner_repo}:metadata",
                            f"cosmos:repo:{owner_repo}",
                            f"gitingest:{owner_repo}",
                            f"repo:{owner_repo}",
                            owner_repo,
                            repo_name
                        ]
                        
                        logger.info(f"Looking for Redis cache for {owner_repo}, trying keys: {possible_keys[:3]}...")
                        
                        # Build comprehensive repository context from gitingest data
                        repo_context_parts = []
                        
                        # Get summary first (most important)
                        summary_key = f"repo:{owner_repo}:summary"
                        try:
                            summary_data = r.get(summary_key)
                            if summary_data:
                                repo_context_parts.append(f"REPOSITORY SUMMARY:\n{summary_data}\n")
                                logger.info(f"Found repository summary in Redis cache")
                        except:
                            pass
                        
                        # Get directory structure
                        tree_key = f"repo:{owner_repo}:tree"
                        try:
                            tree_data = r.get(tree_key)
                            if tree_data:
                                repo_context_parts.append(f"DIRECTORY STRUCTURE:\n{tree_data[:800]}\n")
                                logger.info(f"Found repository tree in Redis cache")
                        except:
                            pass
                        
                        # Get file contents (most important for answering questions)
                        content_key = f"repo:{owner_repo}:content"
                        virtual_files = {}
                        try:
                            content_data = r.get(content_key)
                            if content_data:
                                # Parse content to extract individual files for virtual file system
                                virtual_files = self._parse_content_to_files(content_data)
                                logger.info(f"Found repository content in Redis cache")
                                logger.info(f"Extracted {len(virtual_files)} files from repository content")
                                logger.info(f"Redis content format sample: {content_data[:500]}")  # Debug: show first 500 chars
                                
                                # Show full content to AI for context but also create virtual files
                                repo_context_parts.append(f"REPOSITORY FILES CONTENT:\n{content_data}\n")
                        except:
                            pass
                        
                        # Get metadata
                        metadata_key = f"repo:{owner_repo}:metadata"  
                        try:
                            metadata_data = r.get(metadata_key)
                            if metadata_data:
                                repo_context_parts.append(f"METADATA:\n{metadata_data}\n")
                                logger.info(f"Found repository metadata in Redis cache")
                        except:
                            pass
                        
                        if repo_context_parts:
                            repo_context = f"Repository: {repo_url}\n\n" + "\n".join(repo_context_parts)
                            logger.info(f"Built comprehensive repository context ({len(repo_context)} chars)")
                            
                            # Create or reuse temporary directory structure if we have files
                            if virtual_files:
                                # Check if we already have a valid temp directory for this repo
                                if (hasattr(self, 'temp_repo_dir') and self.temp_repo_dir and 
                                    os.path.exists(self.temp_repo_dir)):
                                    logger.info(f"Reusing existing temporary repository structure at {self.temp_repo_dir}")
                                else:
                                    temp_repo_dir = self._create_temp_repository_structure(virtual_files, owner_repo)
                                    if temp_repo_dir:
                                        logger.info(f"Created temporary repository structure at {temp_repo_dir}")
                                        # Store for cleanup later
                                        self.temp_repo_dir = temp_repo_dir
                        else:
                            # Fallback: try other key formats
                            for key in possible_keys:
                                try:
                                    cached_data = r.get(key)
                                    if cached_data:
                                        logger.info(f"Found repository data in Redis cache with key: {key}")
                                        repo_context = f"Repository: {repo_url}\nCached Data: {cached_data[:1000]}\n"
                                        break
                                except Exception as key_error:
                                    logger.debug(f"Failed to get key {key}: {key_error}")
                                    continue
                        
                        if not repo_context:
                            logger.warning(f"No repository data found in Redis cache for {owner_repo}")
                            logger.info(f"Tried keys: {', '.join(possible_keys)}")
                            
                            # List available keys for debugging
                            try:
                                available_keys = r.keys("*repo*") + r.keys("*git*") + r.keys("*cache*")
                                if available_keys:
                                    logger.info(f"Available cache keys: {available_keys[:10]}")
                                else:
                                    logger.info("No cache keys found matching repo/git/cache patterns")
                            except:
                                pass
                    else:
                        logger.warning("No Redis URL configured for repository cache access")
                        
            except Exception as cache_error:
                logger.warning(f"Could not access repository cache: {cache_error}")
            
            # Enhance the message with repository context if available
            enhanced_message = message
            if repo_context:
                # Format the message to clearly indicate we have repository data
                enhanced_message = f"""You are analyzing the repository at {context.get("repository_url", "this repository")}. 

Here is the complete repository information:

{repo_context}

Based on this repository data above, please answer the following question:

{message}

Please provide a comprehensive answer based on the repository's README, code structure, and files shown above. Do not ask for the repository URL as you already have all the information needed."""
                logger.info(f"Enhanced message with repository context ({len(repo_context)} chars)")
            else:
                # If no repository context found, let the user know
                if context and context.get("repository_url"):
                    repo_url = context["repository_url"]
                    enhanced_message = f"Repository: {repo_url}\n\nNote: Repository data not found in cache. Please ensure the repository has been processed by gitingest.\n\nUser Question: {message}"
            
            # Prepare cosmos arguments (equivalent to CLI args)
            cosmos_args = [
                "--model", model_name,
                "--yes-always",  # Don't prompt user
                "--message", enhanced_message,  # Use enhanced message with repository context
                "--no-pretty",  # Disable pretty output for parsing
                "--no-stream",  # Disable streaming for simpler parsing
                "--map-tokens", "2048"  # Enable repository mapping with moderate token limit
            ]
            
            # Add selected files if provided
            if selected_files:
                for file_info in selected_files[:10]:  # Limit to 10 files to avoid overwhelming
                    if file_info.get("path"):
                        cosmos_args.extend(["--file", file_info["path"]])
            
            # Add context as environment variables if needed
            if context:
                if context.get("repository_url"):
                    os.environ["GITMESH_REPO_URL"] = context["repository_url"]
                if context.get("branch"):
                    os.environ["GITMESH_BRANCH"] = context["branch"]
            
            # Set repository context for cosmos
            os.environ["GITMESH_REPO_ID"] = self.repository_id
            os.environ["GITMESH_BRANCH"] = self.branch
            os.environ["GITMESH_USER_ID"] = self.user_id
            
            # Set up Redis credentials for accessing gitingest-cached repository data
            # Use the same Redis instance that stores gitingest repository context
            if not os.environ.get("REDIS_URL"):
                # Load Redis configuration from GitMesh backend
                try:
                    import os
                    import sys
                    backend_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')
                    sys.path.insert(0, backend_path)
                    
                    from config.settings import get_settings
                    settings = get_settings()
                    
                    if hasattr(settings, 'redis_url') and settings.redis_url:
                        os.environ["REDIS_URL"] = settings.redis_url
                        if hasattr(settings, 'redis_password') and settings.redis_password:
                            os.environ["REDIS_PASSWORD"] = settings.redis_password
                        logger.info("Using GitMesh Redis configuration for repository cache access")
                    else:
                        # Fallback to production Redis Cloud if available
                        redis_url = os.environ.get("REDIS_CLOUD_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
                        if redis_url:
                            os.environ["REDIS_URL"] = redis_url
                            logger.info("Using production Redis for repository cache access")
                        else:
                            logger.warning("No Redis configuration found - cosmos may not access cached repository data")
                except Exception as e:
                    logger.warning(f"Could not load Redis configuration: {e}")
            
            # Set GitMesh mode environment variables
            os.environ["GITMESH_MODE"] = "true"
            if context and context.get("repository_url"):
                os.environ["GITMESH_REPO"] = context["repository_url"]
            
            # Check API key for Gemini if available
            if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
                logger.warning("No Gemini API key found in environment variables GEMINI_API_KEY or GOOGLE_API_KEY")
            
            # Execute cosmos with arguments
            logger.info(f"Executing cosmos with args: {' '.join(cosmos_args)}")
            
            try:
                # Use direct approach if main.py is not available due to syntax issues
                if COSMOS_MAIN_AVAILABLE and cosmos_main:
                    # Call cosmos main function with our arguments
                    result = cosmos_main(
                        argv=cosmos_args,
                        input=None,
                        output=io_handler,
                        force_git_root=None,
                        return_coder=False
                    )
                else:
                    # Direct approach: create coder and run manually
                    logger.info("Using direct cosmos approach (bypassing main.py)")
                    
                    # Create model directly
                    from cosmos.models import Model
                    model = Model(model_name, verbose=True)
                    
                    # Create a simple coder session
                    from cosmos.coders import AskCoder
                    
                    # Configure for GitMesh/Redis mode - use only valid parameters
                    coder_args = {
                        'main_model': model,
                        'io': io_handler,
                        'use_git': False,  # Use Redis instead of git
                        'auto_commits': False,
                        'dirty_commits': True,
                        'stream': False,
                        'map_tokens': 2048,
                        'show_diffs': False,
                        'verbose': True,
                        'restore_chat_history': False
                    }
                    
                    # Change to temporary repository directory if available
                    original_cwd = os.getcwd()
                    if hasattr(self, 'temp_repo_dir') and self.temp_repo_dir and os.path.exists(self.temp_repo_dir):
                        os.chdir(self.temp_repo_dir)
                        logger.info(f"Changed working directory to temporary repository: {self.temp_repo_dir}")
                    else:
                        logger.warning("No temporary repository directory available, staying in current directory")
                    
                    # Create coder instance using AskCoder for questions/chat
                    coder = AskCoder(**coder_args)
                    
                    # Process the message directly
                    try:
                        # Add the user message
                        coder.partial_response_content = ""
                        
                        # Create a simple chat turn - skip ChatHistory since it doesn't exist
                        # Initialize basic attributes if needed
                        if not hasattr(coder, 'chat_history'):
                            setattr(coder, 'chat_history', [])
                        
                        # Process the user message through the coder
                        response = coder.run_one(message, preproc=True)
                        
                        # Capture the response
                        if hasattr(coder, 'partial_response_content') and coder.partial_response_content:
                            captured_output.append(("ai_output", coder.partial_response_content))
                        elif response:
                            captured_output.append(("ai_output", str(response)))
                        else:
                            captured_output.append(("ai_output", "Response processed successfully"))
                        
                        result = 0  # Success
                        
                    except Exception as coder_error:
                        logger.error(f"Direct coder approach failed: {coder_error}")
                        # Try even more basic approach
                        try:
                            # Just get a simple model response using send_completion
                            messages = [{"role": "user", "content": message}]
                            
                            # Try different methods based on what the model supports
                            if hasattr(model, 'send_completion'):
                                response_content = model.send_completion(messages, functions=None, stream=False, temperature=0.1)
                                
                                # Handle different response formats
                                if isinstance(response_content, tuple):
                                    # Extract the actual response from tuple format
                                    if len(response_content) > 1 and hasattr(response_content[1], 'choices'):
                                        actual_response = response_content[1].choices[0].message.content
                                        captured_output.append(("ai_output", actual_response))
                                    else:
                                        captured_output.append(("ai_output", str(response_content)))
                                elif isinstance(response_content, str):
                                    captured_output.append(("ai_output", response_content))
                                else:
                                    # Handle other response formats
                                    if hasattr(response_content, 'choices') and response_content.choices:
                                        actual_response = response_content.choices[0].message.content
                                        captured_output.append(("ai_output", actual_response))
                                    else:
                                        captured_output.append(("ai_output", str(response_content)))
                                
                                result = 0
                            elif hasattr(model, '__call__'):
                                # Try calling the model directly
                                response_content = model(message)
                                captured_output.append(("ai_output", response_content))
                                result = 0
                            else:
                                raise Exception("No suitable method found on model")
                                
                        except Exception as basic_error:
                            logger.error(f"Basic model approach also failed: {basic_error}")
                            captured_output.append(("ai_output", f"Error: Unable to process request - {str(basic_error)}"))
                            result = 1
                    
                    finally:
                        # Always restore original working directory
                        try:
                            os.chdir(original_cwd)
                            logger.info(f"Restored working directory to: {original_cwd}")
                        except Exception as e:
                            logger.warning(f"Failed to restore working directory: {e}")
                
                # Extract response from captured output
                response_parts = []
                sources = []
                
                # Debug: log all captured output
                logger.info(f"Captured {len(captured_output)} outputs:")
                for i, (output_type, content) in enumerate(captured_output):
                    logger.info(f"  [{i}] {output_type}: {content[:100]}...")
                
                for output_type, content in captured_output:
                    # Prioritize AI and assistant outputs for the actual response
                    if output_type in ["ai_output", "assistant_output"] and content.strip():
                        response_parts.append(content)
                    elif output_type == "tool_output" and content.strip():
                        # Filter out system messages and keep actual responses
                        if not any(skip in content.lower() for skip in [
                            "loading", "initializing", "cached", "redis", "repository", "can't initialize"
                        ]):
                            response_parts.append(content)
                
                # Combine response parts
                response_content = "\n".join(response_parts) if response_parts else "No response generated from Cosmos."
                
                # If no meaningful response, indicate the issue
                if not response_content.strip() or len(response_content) < 10:
                    response_content = "No response generated from Cosmos. Please check model availability and configuration."
                
                return {
                    "content": response_content,
                    "confidence": 0.9,
                    "sources": sources,
                    "knowledge_entries_used": len(selected_files) if selected_files else 0,
                    "model_used": model_name,
                    "cosmos_version": "integrated"
                }
                
            except Exception as cosmos_error:
                logger.error(f"Cosmos execution error: {cosmos_error}")
                raise Exception(f"Cosmos chat failed: {str(cosmos_error)}")
            finally:
                # Restore original working directory (but keep temp directory for session)
                os.chdir(original_cwd)
                logger.info(f"Restored working directory to: {original_cwd}")
                # Note: temp_repo_dir is preserved for the session duration
            
        except Exception as e:
            logger.error(f"Error in process_chat_message: {e}")
            # Ensure we restore directory even on outer exception (but preserve temp directory)
            if 'original_cwd' in locals():
                os.chdir(original_cwd)
            raise
    

    
    def cleanup_session(self, session_id: str = None):
        """Cleanup session resources (equivalent to leaving chat page)"""
        try:
            # Clean up temp environment
            self._cleanup_temp_environment()
            
            # Clean up Redis cache if configured
            if session_id and session_id in self.active_sessions:
                try:
                    # Clear Redis cache for this repository session
                    from cosmos.redis_cache import SmartRedisCache
                    cache = SmartRedisCache()
                    cache_key = f"{self.repository_id}:{self.branch}"
                    cache.smart_invalidate(cache_key)
                    logger.info(f"Cleaned up Redis cache for {cache_key}")
                except Exception as cache_error:
                    logger.error(f"Error cleaning up Redis cache: {cache_error}")
                
                del self.active_sessions[session_id]
            
            logger.info(f"Session cleanup completed for user {self.user_id}")
            
        except Exception as e:
            logger.error(f"Error during session cleanup: {e}")
    
    def __del__(self):
        """Ensure cleanup on object destruction"""
        try:
            self._cleanup_temp_environment()
        except:
            pass

# Utility functions for the wrapper

def get_model_info(model_name: str) -> Dict[str, Any]:
    """Get information about a specific model"""
    if not COSMOS_AVAILABLE:
        return {"available": False, "error": "Cosmos not available"}
    
    try:
        model = Model(model_name, verbose=False)
        return {
            "available": True,
            "name": model_name,
            "context_length": getattr(model, 'max_context_tokens', 8192),
            "supports_streaming": getattr(model, 'streaming', True),
            "edit_format": getattr(model, 'edit_format', 'whole'),
            "info": getattr(model, 'info', {})
        }
    except Exception as e:
        return {
            "available": False,
            "name": model_name,
            "error": str(e)
        }

def list_all_models() -> List[Dict[str, Any]]:
    """List all available models (equivalent to cosmos --list-models)"""
    wrapper = GitMeshCosmosWrapper("temp", "temp")
    return wrapper.get_available_models()

# Session management for automatic cleanup
class CosmosSessionManager:
    """Manages cosmos sessions and automatic cleanup"""
    
    def __init__(self):
        self.active_wrappers = {}
    
    def get_wrapper(self, user_id: str, repository_id: str, branch: str = "main") -> GitMeshCosmosWrapper:
        """Get or create a cosmos wrapper for a user session"""
        session_key = f"{user_id}:{repository_id}:{branch}"
        
        if session_key not in self.active_wrappers:
            wrapper = GitMeshCosmosWrapper(user_id, repository_id, repository_id, branch)
            self.active_wrappers[session_key] = wrapper
        
        return self.active_wrappers[session_key]
    
    def cleanup_session(self, user_id: str, repository_id: str, branch: str = "main"):
        """Cleanup a specific session"""
        session_key = f"{user_id}:{repository_id}:{branch}"
        
        if session_key in self.active_wrappers:
            wrapper = self.active_wrappers[session_key]
            wrapper.cleanup_session(session_key)
            del self.active_wrappers[session_key]
    
    def cleanup_all_user_sessions(self, user_id: str):
        """Cleanup all sessions for a user"""
        keys_to_remove = [key for key in self.active_wrappers.keys() if key.startswith(f"{user_id}:")]
        
        for key in keys_to_remove:
            wrapper = self.active_wrappers[key]
            wrapper.cleanup_session(key)
            del self.active_wrappers[key]

# Global session manager instance
session_manager = CosmosSessionManager()
