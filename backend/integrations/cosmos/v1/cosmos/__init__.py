from packaging import version

# Initialize web module loader first to set up mocks
try:
    from .web_module_loader import initialize_web_cosmos
    initialize_web_cosmos()
except Exception as e:
    # If web module loader fails, continue without it
    import logging
    logging.getLogger(__name__).warning(f"Web module loader initialization failed: {e}")

__version__ = "1.0.dev"
safe_version = __version__

try:
    from cosmos._version import __version__
except Exception:
    __version__ = safe_version + "+import"

if type(__version__) is not str:
    __version__ = safe_version + "+type"
else:
    try:
        if version.parse(__version__) < version.parse(safe_version):
            __version__ = safe_version + "+less"
    except Exception:
        __version__ = safe_version + "+parse"

__all__ = [__version__]
