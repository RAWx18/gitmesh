"""
Web-optimized module loader for Cosmos
Provides selective import system that skips CLI-specific modules
"""
import sys
import logging
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

logger = logging.getLogger(__name__)

class WebModuleLoader:
    """
    Selective module loader that mocks or skips CLI-specific components
    """
    
    # Modules to completely mock (not needed for web)
    MOCK_MODULES = {
        'voice', 'gui', 'onboarding', 'watch', 'watch_prompts',
        'copypaste', 'editor', 'help', 'help_pats', 'args', 
        'args_formatter', 'run_cmd', 'scrape', 'dump', 'deprecated',
        'versioncheck', 'startup_checks', 'waiting', '__main__',
        
        # Audio/GUI dependencies
        'pydub', 'pydub.AudioSegment', 'pydub.exceptions', 'pydub.playback',
        'soundfile', 'sounddevice', 'audioop', 'pyaudioop',
        'streamlit', 'pyperclip', 'PIL.ImageGrab',
        
        # CLI-specific prompt_toolkit features
        'prompt_toolkit.shortcuts.prompt',
        'shtab',
    }
    
    # Modules to lazy load (load only when needed)
    LAZY_MODULES = {
        'analytics', 'monitoring', 'report', 'github_pr',
        'history', 'special'
    }
    
    def __init__(self):
        self._mocked_modules = {}
        self._lazy_modules = {}
        self._setup_mocks()
    
    def _setup_mocks(self):
        """Setup mock modules for CLI-specific components"""
        for module_name in self.MOCK_MODULES:
            if module_name not in sys.modules:
                mock_module = MagicMock()
                mock_module.__name__ = module_name
                mock_module.__file__ = f"<mocked:{module_name}>"
                sys.modules[module_name] = mock_module
                self._mocked_modules[module_name] = mock_module
                logger.debug(f"Mocked module: {module_name}")
    
    def safe_import(self, module_name: str, fallback=None) -> Any:
        """
        Safely import a module with fallback handling
        
        Args:
            module_name: Name of module to import
            fallback: Fallback value if import fails
            
        Returns:
            Imported module or fallback
        """
        try:
            if module_name in self.MOCK_MODULES:
                return self._mocked_modules.get(module_name, MagicMock())
            
            if module_name in self.LAZY_MODULES:
                if module_name not in self._lazy_modules:
                    self._lazy_modules[module_name] = __import__(module_name)
                return self._lazy_modules[module_name]
            
            return __import__(module_name)
            
        except ImportError as e:
            logger.warning(f"Failed to import {module_name}: {e}")
            if fallback is not None:
                return fallback
            return MagicMock()
    
    def patch_cosmos_imports(self):
        """
        Patch cosmos module imports to use web-safe versions
        """
        # Mock CLI-specific imports that might be referenced
        cosmos_mocks = {
            'cosmos.voice': MagicMock(),
            'cosmos.gui': MagicMock(),
            'cosmos.onboarding': MagicMock(),
            'cosmos.watch': MagicMock(),
            'cosmos.watch_prompts': MagicMock(),
            'cosmos.copypaste': MagicMock(),
            'cosmos.editor': MagicMock(),
            'cosmos.help': MagicMock(),
            'cosmos.help_pats': MagicMock(),
            'cosmos.args': MagicMock(),
            'cosmos.args_formatter': MagicMock(),
            'cosmos.run_cmd': MagicMock(),
            'cosmos.scrape': MagicMock(),
            'cosmos.dump': MagicMock(),
            'cosmos.deprecated': MagicMock(),
            'cosmos.versioncheck': MagicMock(),
            'cosmos.startup_checks': MagicMock(),
            'cosmos.waiting': MagicMock(),
        }
        
        for module_name, mock_obj in cosmos_mocks.items():
            if module_name not in sys.modules:
                sys.modules[module_name] = mock_obj
                logger.debug(f"Patched cosmos import: {module_name}")
    
    def setup_web_environment(self):
        """
        Setup web environment by patching cosmos imports
        """
        self.patch_cosmos_imports()
        logger.info("Web environment setup completed")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for module loading
        
        Returns:
            Dictionary with performance metrics
        """
        return {
            'mocked_modules': len(self._mocked_modules),
            'lazy_modules': len(self._lazy_modules),
            'total_modules': len(sys.modules),
            'memory_saved_estimate': len(self._mocked_modules) * 50  # Rough estimate in KB
        }

# Global instance - initialize immediately
web_loader = WebModuleLoader()
# Patch cosmos imports immediately when this module is loaded
web_loader.patch_cosmos_imports()

def initialize_web_cosmos():
    """
    Initialize cosmos for web usage with optimized module loading
    """
    logger.info("Initializing cosmos for web usage...")
    
    # Setup mocks and patches (already done at module level)
    web_loader.patch_cosmos_imports()
    
    # Performance metrics
    metrics = web_loader.get_performance_metrics()
    logger.info(f"Web cosmos initialized - Mocked: {metrics['mocked_modules']} modules, "
               f"Lazy: {metrics['lazy_modules']} modules, "
               f"Estimated memory saved: {metrics['memory_saved_estimate']}KB")
    
    return web_loader

def safe_import(module_name: str, fallback=None):
    """
    Convenience function for safe module importing
    """
    return web_loader.safe_import(module_name, fallback)