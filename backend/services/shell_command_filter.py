"""Shell Command Filter Service

Filters out shell command suggestions from AI responses and replaces them
with web-safe alternatives or explanatory text.

SECURITY: This service ensures no shell commands are suggested to users,
preventing any potential command injection vulnerabilities.
"""

import re
import logging
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ShellCommandType(str, Enum):
    """Types of shell commands that need filtering."""
    PACKAGE_INSTALL = "package_install"
    FILE_OPERATION = "file_operation"
    GIT_OPERATION = "git_operation"
    SYSTEM_COMMAND = "system_command"
    BUILD_COMMAND = "build_command"
    TEST_COMMAND = "test_command"
    DEPLOYMENT = "deployment"
    NETWORK_COMMAND = "network_command"

@dataclass
class ShellCommandMatch:
    """A detected shell command in text."""
    original_text: str
    command_type: ShellCommandType
    start_pos: int
    end_pos: int
    suggested_alternative: str

@dataclass
class FilterResult:
    """Result of shell command filtering."""
    filtered_content: str
    commands_filtered: List[ShellCommandMatch]
    alternatives_suggested: int
    security_notes_added: int

class ShellCommandFilter:
    """Service for filtering shell commands from AI responses."""
    
    def __init__(self):
        """Initialize the shell command filter."""
        self.shell_patterns = self._initialize_shell_patterns()
        self.alternative_suggestions = self._initialize_alternatives()
        logger.info("ShellCommandFilter initialized - will filter all shell command suggestions")
    
    def _initialize_shell_patterns(self) -> Dict[ShellCommandType, List[str]]:
        """Initialize regex patterns for detecting shell commands."""
        return {
            ShellCommandType.PACKAGE_INSTALL: [
                r'pip\s+install\s+[\w\-\[\]\.]+',
                r'npm\s+install\s+[\w\-@/]+',
                r'yarn\s+add\s+[\w\-@/]+',
                r'apt\s+install\s+[\w\-]+',
                r'brew\s+install\s+[\w\-]+',
                r'conda\s+install\s+[\w\-]+',
                r'poetry\s+add\s+[\w\-]+',
                r'composer\s+install\s+[\w\-/]+',
                r'gem\s+install\s+[\w\-]+',
                r'cargo\s+install\s+[\w\-]+',
            ],
            ShellCommandType.FILE_OPERATION: [
                r'ls\s+[\-\w\s]*',
                r'cat\s+[\w\./\-]+',
                r'grep\s+[\-\w\s"\']+',
                r'find\s+[\w\./\-\s]+',
                r'mkdir\s+[\-\w\s/\.]+',
                r'rm\s+[\-\w\s/\.]+',
                r'cp\s+[\-\w\s/\.]+',
                r'mv\s+[\-\w\s/\.]+',
                r'chmod\s+[\d\w\s/\.]+',
                r'chown\s+[\w:\s/\.]+',
                r'touch\s+[\w/\.]+',
                r'head\s+[\-\w\s/\.]+',
                r'tail\s+[\-\w\s/\.]+',
                r'wc\s+[\-\w\s/\.]+',
                r'sort\s+[\-\w\s/\.]+',
                r'uniq\s+[\-\w\s/\.]+',
            ],
            ShellCommandType.GIT_OPERATION: [
                r'git\s+clone\s+[\w\-\.:/@]+',
                r'git\s+add\s+[\w\./\-\s]+',
                r'git\s+commit\s+[\-\w\s"\']+',
                r'git\s+push\s+[\w\-\s]*',
                r'git\s+pull\s+[\w\-\s]*',
                r'git\s+checkout\s+[\w\-\s/\.]+',
                r'git\s+branch\s+[\w\-\s]*',
                r'git\s+merge\s+[\w\-\s/\.]+',
                r'git\s+status',
                r'git\s+log\s+[\-\w\s]*',
                r'git\s+diff\s+[\w\-\s/\.]*',
                r'git\s+reset\s+[\-\w\s/\.]+',
                r'git\s+rebase\s+[\w\-\s/\.]+',
            ],
            ShellCommandType.SYSTEM_COMMAND: [
                r'sudo\s+[\w\-\s/\.]+',
                r'ps\s+[\-\w\s]*',
                r'kill\s+[\-\d\w\s]+',
                r'killall\s+[\w\-]+',
                r'top\s*',
                r'htop\s*',
                r'df\s+[\-\w\s]*',
                r'du\s+[\-\w\s/\.]*',
                r'free\s+[\-\w\s]*',
                r'uname\s+[\-\w\s]*',
                r'whoami\s*',
                r'id\s*',
                r'which\s+[\w\-]+',
                r'whereis\s+[\w\-]+',
                r'locate\s+[\w\-/\.]+',
                r'systemctl\s+[\w\-\s]+',
                r'service\s+[\w\-\s]+',
            ],
            ShellCommandType.BUILD_COMMAND: [
                r'make\s+[\w\-\s]*',
                r'cmake\s+[\w\-\s/\.]+',
                r'gcc\s+[\w\-\s/\.]+',
                r'g\+\+\s+[\w\-\s/\.]+',
                r'javac\s+[\w\-\s/\.]+',
                r'java\s+[\w\-\s/\.]+',
                r'python\s+[\w\-\s/\.]+',
                r'node\s+[\w\-\s/\.]+',
                r'go\s+build\s+[\w\-\s/\.]*',
                r'cargo\s+build\s+[\w\-\s]*',
                r'mvn\s+[\w\-\s]+',
                r'gradle\s+[\w\-\s]+',
                r'ant\s+[\w\-\s]*',
            ],
            ShellCommandType.TEST_COMMAND: [
                r'pytest\s+[\w\-\s/\.]*',
                r'python\s+\-m\s+pytest\s+[\w\-\s/\.]*',
                r'npm\s+test\s*',
                r'yarn\s+test\s*',
                r'jest\s+[\w\-\s/\.]*',
                r'mocha\s+[\w\-\s/\.]*',
                r'phpunit\s+[\w\-\s/\.]*',
                r'rspec\s+[\w\-\s/\.]*',
                r'go\s+test\s+[\w\-\s/\.]*',
                r'cargo\s+test\s+[\w\-\s]*',
                r'mvn\s+test\s*',
                r'gradle\s+test\s*',
            ],
            ShellCommandType.DEPLOYMENT: [
                r'docker\s+[\w\-\s/\.]+',
                r'docker\-compose\s+[\w\-\s/\.]+',
                r'kubectl\s+[\w\-\s/\.]+',
                r'helm\s+[\w\-\s/\.]+',
                r'terraform\s+[\w\-\s/\.]+',
                r'ansible\s+[\w\-\s/\.]+',
                r'ssh\s+[\w\-@\.:]+',
                r'scp\s+[\w\-@\.:\/\s]+',
                r'rsync\s+[\w\-@\.:\/\s]+',
            ],
            ShellCommandType.NETWORK_COMMAND: [
                r'curl\s+[\w\-\s/\.:@]+',
                r'wget\s+[\w\-\s/\.:@]+',
                r'ping\s+[\w\-\.]+',
                r'netstat\s+[\-\w\s]*',
                r'ss\s+[\-\w\s]*',
                r'nslookup\s+[\w\-\.]+',
                r'dig\s+[\w\-\.\s]+',
                r'telnet\s+[\w\-\.\s]+',
            ]
        }
    
    def _initialize_alternatives(self) -> Dict[ShellCommandType, str]:
        """Initialize alternative suggestions for different command types."""
        return {
            ShellCommandType.PACKAGE_INSTALL: (
                "📦 **Package Installation Required**\n\n"
                "This operation requires manual package installation outside this application:\n"
                "• Install packages using your system's package manager\n"
                "• Use pip, npm, or other package managers in your terminal\n"
                "• Contact your system administrator for package installation\n"
                "• Refer to the project's installation documentation\n\n"
                "**Security Note**: Automatic package installation has been disabled for security reasons."
            ),
            ShellCommandType.FILE_OPERATION: (
                "📁 **File Operations Available Through Interface**\n\n"
                "File operations can be performed through the web interface:\n"
                "• Use the file browser to navigate and view files\n"
                "• Upload files directly through the interface\n"
                "• Use the secure file operations API for programmatic access\n"
                "• View file contents through the built-in file viewer\n\n"
                "**Security Note**: Shell-based file operations have been disabled for security."
            ),
            ShellCommandType.GIT_OPERATION: (
                "🔧 **Git Operations Must Be Done Manually**\n\n"
                "Git operations should be performed outside this application:\n"
                "• Use git commands in your local terminal\n"
                "• Use your preferred Git GUI client\n"
                "• Use your IDE's built-in Git integration\n"
                "• Use web-based Git interfaces (GitHub, GitLab, etc.)\n\n"
                "**Security Note**: Git operations through shell commands have been disabled."
            ),
            ShellCommandType.SYSTEM_COMMAND: (
                "⚙️ **System Commands Not Available**\n\n"
                "System commands cannot be executed through this interface:\n"
                "• Use your system's terminal for system operations\n"
                "• Access system information through dedicated tools\n"
                "• Use system monitoring applications\n"
                "• Contact your system administrator for system-level tasks\n\n"
                "**Security Note**: System commands have been disabled for security reasons."
            ),
            ShellCommandType.BUILD_COMMAND: (
                "🔨 **Build Commands Must Be Run Manually**\n\n"
                "Build operations should be performed outside this application:\n"
                "• Run build commands in your local development environment\n"
                "• Use your IDE's build integration\n"
                "• Set up automated build pipelines (CI/CD)\n"
                "• Use project-specific build tools directly\n\n"
                "**Security Note**: Build commands have been disabled for security."
            ),
            ShellCommandType.TEST_COMMAND: (
                "🧪 **Test Commands Must Be Run Manually**\n\n"
                "Test execution should be performed outside this application:\n"
                "• Run tests in your local development environment\n"
                "• Use your IDE's test runner integration\n"
                "• Set up automated testing in CI/CD pipelines\n"
                "• Use dedicated testing tools and frameworks\n\n"
                "**Security Note**: Test commands have been disabled for security."
            ),
            ShellCommandType.DEPLOYMENT: (
                "🚀 **Deployment Commands Not Available**\n\n"
                "Deployment operations should be performed through proper channels:\n"
                "• Use dedicated deployment tools and platforms\n"
                "• Set up automated deployment pipelines\n"
                "• Use container orchestration platforms directly\n"
                "• Follow your organization's deployment procedures\n\n"
                "**Security Note**: Deployment commands have been disabled for security."
            ),
            ShellCommandType.NETWORK_COMMAND: (
                "🌐 **Network Commands Not Available**\n\n"
                "Network operations should be performed outside this application:\n"
                "• Use network tools in your local terminal\n"
                "• Use web-based network testing tools\n"
                "• Use dedicated network monitoring applications\n"
                "• Contact your network administrator for network tasks\n\n"
                "**Security Note**: Network commands have been disabled for security."
            )
        }
    
    def filter_response(self, content: str) -> FilterResult:
        """Filter shell commands from response content.
        
        Args:
            content: Original response content
            
        Returns:
            FilterResult with filtered content and metadata
        """
        logger.debug("Filtering shell commands from response content")
        
        filtered_content = content
        commands_filtered = []
        alternatives_suggested = 0
        security_notes_added = 0
        
        # Process each command type
        for command_type, patterns in self.shell_patterns.items():
            for pattern in patterns:
                matches = list(re.finditer(pattern, filtered_content, re.IGNORECASE | re.MULTILINE))
                
                # Process matches in reverse order to maintain positions
                for match in reversed(matches):
                    original_text = match.group(0)
                    start_pos = match.start()
                    end_pos = match.end()
                    
                    # Get alternative suggestion
                    alternative = self.alternative_suggestions[command_type]
                    
                    # Create shell command match record
                    command_match = ShellCommandMatch(
                        original_text=original_text,
                        command_type=command_type,
                        start_pos=start_pos,
                        end_pos=end_pos,
                        suggested_alternative=alternative
                    )
                    commands_filtered.append(command_match)
                    
                    # Replace the shell command with alternative text
                    filtered_content = (
                        filtered_content[:start_pos] + 
                        alternative + 
                        filtered_content[end_pos:]
                    )
                    
                    alternatives_suggested += 1
                    security_notes_added += 1
                    
                    logger.info(f"Filtered shell command: {original_text} ({command_type})")
        
        # Also filter code blocks that contain shell commands
        filtered_content, additional_filtered = self._filter_code_blocks(filtered_content)
        commands_filtered.extend(additional_filtered)
        
        result = FilterResult(
            filtered_content=filtered_content,
            commands_filtered=commands_filtered,
            alternatives_suggested=alternatives_suggested,
            security_notes_added=security_notes_added
        )
        
        logger.info(f"Shell command filtering complete: {len(commands_filtered)} commands filtered")
        return result
    
    def _filter_code_blocks(self, content: str) -> Tuple[str, List[ShellCommandMatch]]:
        """Filter shell commands from code blocks.
        
        Args:
            content: Content with code blocks
            
        Returns:
            Tuple of (filtered_content, additional_filtered_commands)
        """
        filtered_content = content
        additional_filtered = []
        
        # Find code blocks (both ``` and ` styles)
        code_block_pattern = r'```(?:bash|shell|sh|zsh|fish)?\n(.*?)\n```'
        inline_code_pattern = r'`([^`]*(?:pip|npm|git|sudo|docker|kubectl)[^`]*)`'
        
        # Process multi-line code blocks
        for match in re.finditer(code_block_pattern, filtered_content, re.DOTALL | re.IGNORECASE):
            code_content = match.group(1)
            
            # Check if this code block contains shell commands
            contains_shell_commands = False
            for command_type, patterns in self.shell_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, code_content, re.IGNORECASE):
                        contains_shell_commands = True
                        break
                if contains_shell_commands:
                    break
            
            if contains_shell_commands:
                # Replace the entire code block with a security message
                security_message = (
                    "```text\n"
                    "🔒 SECURITY: Shell command code block removed for security reasons.\n"
                    "Please perform these operations manually outside this application.\n"
                    "```"
                )
                
                filtered_content = filtered_content.replace(match.group(0), security_message)
                
                additional_filtered.append(ShellCommandMatch(
                    original_text=match.group(0),
                    command_type=ShellCommandType.SYSTEM_COMMAND,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    suggested_alternative=security_message
                ))
        
        # Process inline code that might contain shell commands
        for match in re.finditer(inline_code_pattern, filtered_content, re.IGNORECASE):
            code_content = match.group(1)
            
            # Replace inline shell commands with security notice
            security_message = "`[Shell command removed for security]`"
            filtered_content = filtered_content.replace(match.group(0), security_message)
            
            additional_filtered.append(ShellCommandMatch(
                original_text=match.group(0),
                command_type=ShellCommandType.SYSTEM_COMMAND,
                start_pos=match.start(),
                end_pos=match.end(),
                suggested_alternative=security_message
            ))
        
        return filtered_content, additional_filtered
    
    def get_alternative_for_command_type(self, command_type: ShellCommandType) -> str:
        """Get alternative suggestion for a specific command type.
        
        Args:
            command_type: Type of shell command
            
        Returns:
            Alternative suggestion text
        """
        return self.alternative_suggestions.get(command_type, 
            "**Command Not Available**: This operation has been disabled for security reasons.")
    
    def is_shell_command(self, text: str) -> bool:
        """Check if text contains shell commands.
        
        Args:
            text: Text to check
            
        Returns:
            True if text contains shell commands
        """
        for patterns in self.shell_patterns.values():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return True
        return False
    
    def get_command_type(self, command: str) -> Optional[ShellCommandType]:
        """Identify the type of a shell command.
        
        Args:
            command: Shell command to analyze
            
        Returns:
            ShellCommandType if identified, None otherwise
        """
        for command_type, patterns in self.shell_patterns.items():
            for pattern in patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    return command_type
        return None

# Global instance
shell_command_filter = ShellCommandFilter()

# Convenience functions
def filter_shell_commands(content: str) -> str:
    """Filter shell commands from content and return filtered text.
    
    Args:
        content: Original content
        
    Returns:
        Filtered content with shell commands removed
    """
    result = shell_command_filter.filter_response(content)
    return result.filtered_content

def check_for_shell_commands(content: str) -> bool:
    """Check if content contains shell commands.
    
    Args:
        content: Content to check
        
    Returns:
        True if shell commands are found
    """
    return shell_command_filter.is_shell_command(content)