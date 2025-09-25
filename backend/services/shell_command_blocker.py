"""
Shell Command Execution Documentation and Logging

SECURITY: This file documents the complete removal of shell command execution
capabilities from the codebase. All shell command execution has been eliminated
for security reasons.

PURPOSE: This module now serves only to:
1. Document what shell functionality was previously available
2. Log any attempts to use shell command functionality
3. Provide security audit trails
4. Explain to developers why shell commands are not available

IMPORTANT: No shell commands can be executed by this system. All subprocess,
os.system, and related shell execution code has been permanently disabled.
"""

import os
import sys
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ShellCommandAttempt:
    """Information about an attempt to use shell command functionality."""
    attempted_operation: str
    user_id: Optional[str]
    session_id: Optional[str]
    timestamp: datetime
    context: str
    security_message: str


class ShellCommandDocumentation:
    """
    Documentation and logging service for shell command removal.
    
    This class serves as documentation of the security measures taken
    and provides logging for any attempts to use shell functionality.
    
    SECURITY: This class cannot and will not execute any shell commands.
    All shell execution capabilities have been permanently removed.
    """
    
    def __init__(self):
        """Initialize the documentation service."""
        self.command_attempts: List[ShellCommandAttempt] = []
        self.is_active = False
        logger.info("SECURITY: Shell command documentation service initialized - no shell execution possible")
    
    def activate(self, user_id: Optional[str] = None, session_id: Optional[str] = None):
        """
        SECURITY: Shell command execution completely disabled for security.
        
        This method now serves as documentation only. All shell command execution
        capabilities have been completely removed from the codebase for security.
        No shell commands can be executed by this system under any circumstances.
        
        Args:
            user_id: User identifier for audit logging
            session_id: Session identifier for audit logging
        """
        self.is_active = True
        
        security_message = (
            "SECURITY: Shell command execution has been completely removed from the codebase. "
            "No shell commands can be executed under any circumstances. This ensures complete "
            "protection against command injection vulnerabilities."
        )
        
        logger.critical(security_message)
        
        # Log the security status
        attempt = ShellCommandAttempt(
            attempted_operation="shell_blocker_activation",
            user_id=user_id,
            session_id=session_id,
            timestamp=datetime.now(),
            context="Shell command blocker activation requested",
            security_message=security_message
        )
        self.command_attempts.append(attempt)
    
    def deactivate(self):
        """
        SECURITY: Shell command execution cannot be reactivated.
        
        This method logs the attempt but does not change security posture.
        Shell commands remain permanently disabled for security.
        """
        logger.warning("SECURITY: Attempt to deactivate shell command blocker - shell commands remain disabled")
        
        attempt = ShellCommandAttempt(
            attempted_operation="shell_blocker_deactivation",
            user_id=None,
            session_id=None,
            timestamp=datetime.now(),
            context="Attempt to deactivate shell command blocker",
            security_message="Shell commands remain permanently disabled for security"
        )
        self.command_attempts.append(attempt)
    
    def log_shell_attempt(self, operation: str, context: str = "", user_id: Optional[str] = None, session_id: Optional[str] = None):
        """
        Log an attempt to use shell command functionality.
        
        Args:
            operation: The shell operation that was attempted
            context: Additional context about the attempt
            user_id: User identifier
            session_id: Session identifier
        """
        security_message = (
            f"SECURITY: Attempt to use shell functionality '{operation}' blocked. "
            "Shell command execution has been completely disabled for security reasons."
        )
        
        logger.warning(security_message)
        
        attempt = ShellCommandAttempt(
            attempted_operation=operation,
            user_id=user_id,
            session_id=session_id,
            timestamp=datetime.now(),
            context=context,
            security_message=security_message
        )
        self.command_attempts.append(attempt)
    
    def get_security_status(self) -> Dict[str, Any]:
        """
        Get the current security status.
        
        Returns:
            Dictionary with security status information
        """
        return {
            "shell_execution_enabled": False,
            "shell_execution_permanently_disabled": True,
            "security_level": "MAXIMUM",
            "total_shell_attempts_logged": len(self.command_attempts),
            "last_attempt": self.command_attempts[-1].timestamp if self.command_attempts else None,
            "security_message": "Shell command execution completely removed for security"
        }
    
    def get_attempt_history(self, limit: int = 100) -> List[ShellCommandAttempt]:
        """
        Get history of shell command attempts.
        
        Args:
            limit: Maximum number of attempts to return
            
        Returns:
            List of recent shell command attempts
        """
        return self.command_attempts[-limit:] if self.command_attempts else []
    
    def clear_attempt_history(self):
        """Clear the attempt history."""
        self.command_attempts.clear()
        logger.info("Shell command attempt history cleared")


class SecurityError(Exception):
    """Exception raised when shell command execution is attempted."""
    pass


# Global instance for backward compatibility
shell_blocker = ShellCommandDocumentation()


def ensure_shell_blocking_active():
    """SECURITY: Shell command execution completely disabled for security.
    
    COMMENTED OUT: This function previously ensured shell blocking was active,
    but now all shell command execution capabilities have been completely removed
    from the codebase for security.
    """
    # SECURITY: Shell blocker activation commented out - no shell execution possible
    # if not shell_blocker.is_active:
    #     logger.warning("Shell command blocking is not active - activating now")
    #     shell_blocker.activate()
    
    logger.info("SECURITY: Shell command execution completely disabled - no activation needed")


# Legacy compatibility functions that now only log security messages
def block_subprocess():
    """SECURITY: subprocess module usage has been completely removed."""
    shell_blocker.log_shell_attempt("subprocess_usage", "Legacy subprocess blocking function called")
    logger.warning("SECURITY: subprocess module usage has been completely removed from codebase")


def block_os_system():
    """SECURITY: os.system usage has been completely removed."""
    shell_blocker.log_shell_attempt("os_system_usage", "Legacy os.system blocking function called")
    logger.warning("SECURITY: os.system usage has been completely removed from codebase")


def block_pexpect():
    """SECURITY: pexpect usage has been completely removed."""
    shell_blocker.log_shell_attempt("pexpect_usage", "Legacy pexpect blocking function called")
    logger.warning("SECURITY: pexpect usage has been completely removed from codebase")


# Documentation of what was previously blocked
PREVIOUSLY_BLOCKED_FUNCTIONS = {
    "subprocess": [
        "subprocess.run", "subprocess.call", "subprocess.Popen", 
        "subprocess.check_call", "subprocess.check_output"
    ],
    "os_module": [
        "os.system", "os.popen", "os.spawn*", "os.exec*"
    ],
    "pexpect": [
        "pexpect.spawn", "pexpect.run", "pexpect.runu"
    ],
    "shell_commands": [
        "bash", "sh", "zsh", "fish", "cmd", "powershell"
    ]
}

SECURITY_DOCUMENTATION = """
SHELL COMMAND EXECUTION REMOVAL - SECURITY DOCUMENTATION

This codebase has had ALL shell command execution capabilities completely removed
for security reasons. The following measures have been implemented:

1. COMPLETE REMOVAL: All subprocess, os.system, and pexpect code has been commented out
2. IMPORT BLOCKING: Shell-related imports have been disabled
3. FUNCTION REPLACEMENT: Shell functions now return security messages
4. RESPONSE FILTERING: AI responses are filtered to remove shell command suggestions
5. AUDIT LOGGING: All attempts to use shell functionality are logged

FUNCTIONS THAT WERE PREVIOUSLY AVAILABLE BUT ARE NOW DISABLED:
- subprocess.run(), subprocess.call(), subprocess.Popen()
- os.system(), os.popen(), os.spawn*(), os.exec*()
- pexpect.spawn(), pexpect.run()
- All shell command execution through any mechanism

SECURITY BENEFITS:
- Complete elimination of command injection vulnerabilities
- No possibility of shell command execution under any circumstances
- Full audit trail of any attempts to use shell functionality
- Clear documentation of security measures taken

ALTERNATIVE APPROACHES:
- Use Python's built-in file operations instead of shell commands
- Use web APIs instead of command-line tools
- Perform system operations manually outside this application
- Use the provided SafeFileOperationsService for secure file access

For more information, see the SHELL_EXECUTION_REMOVAL_SUMMARY.md file.
"""


def get_security_documentation() -> str:
    """Get comprehensive security documentation."""
    return SECURITY_DOCUMENTATION


def get_blocked_functions() -> Dict[str, List[str]]:
    """Get list of functions that were previously blocked."""
    return PREVIOUSLY_BLOCKED_FUNCTIONS.copy()