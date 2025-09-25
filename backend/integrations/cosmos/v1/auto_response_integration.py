"""
Auto Response Integration Module
Integrates all auto-response components for seamless Cosmos automation
"""
from typing import Dict, Any, Optional, List, Union
import re
import structlog
try:
    from .auto_response_handler import AutoResponseHandler, PromptType
    from .repository_selector import RepositorySelector
    from .input_automation import InputAutomation
except ImportError:
    # Handle direct imports when not in package
    from auto_response_handler import AutoResponseHandler, PromptType
    from repository_selector import RepositorySelector
    from input_automation import InputAutomation

logger = structlog.get_logger(__name__)

class CosmosAutoResponseSystem:
    """
    Comprehensive auto-response system that integrates all automation components.
    
    This class provides a unified interface for handling all types of Cosmos prompts
    and inputs automatically, eliminating the need for user interaction.
    """
    
    def __init__(self, 
                 repository_context: Dict[str, Any] = None,
                 redis_client = None):
        """
        Initialize the complete auto-response system.
        
        Args:
            repository_context: Current repository context
            redis_client: Redis client for repository cache access
        """
        self.repository_context = repository_context or {}
        
        # Initialize all components
        self.response_handler = AutoResponseHandler(repository_context)
        self.repository_selector = RepositorySelector(redis_client)
        self.input_automation = InputAutomation(repository_context)
        
        logger.info("CosmosAutoResponseSystem initialized",
                   has_repo_context=bool(repository_context),
                   has_redis=bool(redis_client))
    
    def handle_prompt(self, prompt: str, context: Dict[str, Any] = None) -> str:
        """
        Handle any type of prompt from Cosmos with automatic response.
        
        This is the main entry point for all prompt handling.
        
        Args:
            prompt: The prompt from Cosmos
            context: Additional context for the prompt
            
        Returns:
            Automatic response string
        """
        merged_context = {**self.repository_context, **(context or {})}
        
        # First, try the main response handler
        response = self.response_handler.intercept_prompt(prompt, merged_context)
        
        # If it's a repository selection prompt with numbered options, use the response handler result
        if "repository" in prompt.lower() and re.search(r"\(1-\d+\)", prompt):
            # For numbered repository selection, use the response handler's result
            return response
        
        # If it's a repository URL request, use specialized handler
        if "repository" in prompt.lower() and ("url" in prompt.lower() or "enter" in prompt.lower()):
            try:
                repo_response, reasoning = self.repository_selector.select_repository_automatically(
                    merged_context, self._extract_options_from_prompt(prompt))
                logger.info("Repository selection handled", response=repo_response, reasoning=reasoning)
                return repo_response
            except Exception as e:
                logger.warning("Repository selection failed, using fallback", error=str(e))
                fallback_response, reasoning = self.repository_selector.handle_repository_selection_failure(e, merged_context)
                return fallback_response
        
        # For input requests, use input automation
        if self._is_input_request(prompt):
            input_response = self.input_automation.handle_input_request(prompt, merged_context)
            if input_response:  # Only override if input automation provides a response
                return input_response
        
        return response
    
    def handle_confirmation(self, question: str, context: Dict[str, Any] = None) -> bool:
        """
        Handle confirmation questions with automatic boolean response.
        
        Args:
            question: The confirmation question
            context: Additional context
            
        Returns:
            Boolean confirmation response
        """
        merged_context = {**self.repository_context, **(context or {})}
        return self.input_automation.handle_confirmation(question, merged_context)
    
    def handle_repository_selection(self, 
                                  available_repositories: List[str] = None,
                                  context: Dict[str, Any] = None) -> str:
        """
        Handle repository selection with automatic choice.
        
        Args:
            available_repositories: List of available repository options
            context: Additional context for selection
            
        Returns:
            Selected repository identifier
        """
        merged_context = {**self.repository_context, **(context or {})}
        
        try:
            selection, reasoning = self.repository_selector.select_repository_automatically(
                merged_context, available_repositories)
            logger.info("Repository selection completed", selection=selection, reasoning=reasoning)
            return selection
        except Exception as e:
            logger.error("Repository selection failed", error=str(e))
            fallback_selection, reasoning = self.repository_selector.handle_repository_selection_failure(e, merged_context)
            logger.info("Using fallback repository selection", selection=fallback_selection, reasoning=reasoning)
            return fallback_selection
    
    def _extract_options_from_prompt(self, prompt: str) -> Optional[List[str]]:
        """
        Extract available options from a prompt text.
        
        Args:
            prompt: The prompt containing options
            
        Returns:
            List of extracted options or None
        """
        import re
        
        # Look for numbered options in the prompt
        option_pattern = r"(\d+)\.\s*([^\n]+)"
        matches = re.findall(option_pattern, prompt)
        
        if matches:
            return [match[1].strip() for match in matches]
        
        # Look for other option formats
        lines = prompt.split('\n')
        options = []
        for line in lines:
            line = line.strip()
            if re.match(r"^\d+[\.\)]\s+", line):  # Numbered list
                option = re.sub(r"^\d+[\.\)]\s+", "", line)
                options.append(option)
            elif line.startswith('- '):  # Bullet list
                options.append(line[2:])
        
        return options if options else None
    
    def _is_input_request(self, prompt: str) -> bool:
        """
        Check if a prompt is requesting input rather than just confirmation.
        
        Args:
            prompt: The prompt to check
            
        Returns:
            True if this appears to be an input request
        """
        input_indicators = [
            "enter",
            "input",
            "type",
            "provide",
            "specify",
            "path",
            "token",
            "key"
        ]
        
        normalized_prompt = prompt.lower()
        return any(indicator in normalized_prompt for indicator in input_indicators)
    
    def update_repository_context(self, repository_context: Dict[str, Any]):
        """
        Update repository context for all components.
        
        Args:
            repository_context: New repository context
        """
        self.repository_context.update(repository_context)
        self.response_handler.update_repository_context(repository_context)
        self.input_automation.update_context(repository_context)
        
        logger.info("Repository context updated for all components",
                   repository_url=repository_context.get("repository_url"))
    
    def get_comprehensive_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics from all auto-response components.
        
        Returns:
            Dictionary with statistics from all components
        """
        return {
            "response_handler": self.response_handler.get_statistics(),
            "repository_selector": self.repository_selector.get_repository_statistics(),
            "input_automation": self.input_automation.get_statistics(),
            "system_info": {
                "has_repository_context": bool(self.repository_context),
                "current_repository": self.repository_context.get("repository_url"),
                "cached_repositories": len(self.repository_selector.get_cached_repositories())
            }
        }
    
    def get_debug_logs(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get debug logs from all components for troubleshooting.
        
        Returns:
            Dictionary with logs from all components
        """
        return {
            "response_handler_log": self.response_handler.get_response_log(),
            "input_automation_log": self.input_automation.get_input_log(),
            "cached_repositories": [
                {
                    "url": repo.url,
                    "name": repo.name,
                    "owner": repo.owner,
                    "cached": repo.cached,
                    "last_updated": repo.last_updated
                }
                for repo in self.repository_selector.get_cached_repositories()
            ]
        }
    
    def clear_all_logs(self):
        """Clear all debug logs from all components."""
        self.response_handler.clear_response_log()
        self.input_automation.clear_input_log()
        logger.info("All auto-response logs cleared")
    
    def refresh_repository_cache(self):
        """Refresh the repository cache for better selection."""
        self.repository_selector.refresh_cache()
        logger.info("Repository cache refreshed")


# Convenience function for easy integration
def create_auto_response_system(repository_context: Dict[str, Any] = None,
                               redis_client = None) -> CosmosAutoResponseSystem:
    """
    Create a configured auto-response system.
    
    Args:
        repository_context: Current repository context
        redis_client: Redis client for cache access
        
    Returns:
        Configured CosmosAutoResponseSystem instance
    """
    return CosmosAutoResponseSystem(repository_context, redis_client)