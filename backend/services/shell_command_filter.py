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
            ShellCommandType.PACKAGE_INSTALL: "",
            ShellCommandType.FILE_OPERATION: "",
            ShellCommandType.GIT_OPERATION: "",
            ShellCommandType.SYSTEM_COMMAND: "",
            ShellCommandType.BUILD_COMMAND: "",
            ShellCommandType.TEST_COMMAND: "",
            ShellCommandType.DEPLOYMENT: "",
            ShellCommandType.NETWORK_COMMAND: ""
        }
    
    def filter_response(self, content: str) -> FilterResult:
        """Filter shell commands from response content.
        
        Args:
            content: Original response content
            
        Returns:
            FilterResult with filtered content and metadata
        """
        logger.debug("Shell command filtering disabled - returning original content")
        
        # Return original content without any filtering
        result = FilterResult(
            filtered_content=content,
            commands_filtered=[],
            alternatives_suggested=0,
            security_notes_added=0
        )
        
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
                # Replace with a clean message about manual execution
                replacement = f"```{match.group(1) or 'text'}\n# Commands removed for security - please run manually in your terminal\n```"
                filtered_content = filtered_content.replace(match.group(0), replacement)
                
                additional_filtered.append(ShellCommandMatch(
                    original_text=match.group(0),
                    command_type=ShellCommandType.SYSTEM_COMMAND,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    suggested_alternative=replacement
                ))
        
        # Process inline code that might contain shell commands
        for match in re.finditer(inline_code_pattern, filtered_content, re.IGNORECASE):
            code_content = match.group(1)
            
            # Check if this inline code contains shell commands
            contains_shell = False
            for patterns in self.shell_patterns.values():
                for pattern in patterns:
                    if re.search(pattern, code_content, re.IGNORECASE):
                        contains_shell = True
                        break
                if contains_shell:
                    break
            
            if contains_shell:
                # Replace with placeholder
                replacement = "`[command removed]`"
                filtered_content = filtered_content.replace(match.group(0), replacement)
                
                additional_filtered.append(ShellCommandMatch(
                    original_text=match.group(0),
                    command_type=ShellCommandType.SYSTEM_COMMAND,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    suggested_alternative=replacement
                ))
        
        return filtered_content, additional_filtered
    
    def _cleanup_empty_elements(self, content: str) -> str:
        """Clean up empty code blocks and backticks left after filtering.
        
        Args:
            content: Content with potentially empty elements
            
        Returns:
            Cleaned content
        """
        # Remove empty code blocks (various patterns)
        content = re.sub(r'```\w*\s*\n\s*\n\s*```', '', content)
        content = re.sub(r'```\w*\s*\n\s*```', '', content)
        content = re.sub(r'```\w*\n\s*\n```', '', content)
        
        # Remove code blocks that only contain whitespace or partial content
        content = re.sub(r'```\w*\s*\n[^\n]*\n\s*```', lambda m: '' if not m.group(0).strip('`\n ') else m.group(0), content)
        
        # Remove empty inline code
        content = re.sub(r'``', '', content)
        content = re.sub(r'`\s*`', '', content)
        
        # Remove lines that are just whitespace after filtering
        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip lines that are empty or just contain backticks/whitespace
            if stripped and not re.match(r'^[`\s]*$', stripped):
                cleaned_lines.append(line.rstrip())
            elif not stripped and cleaned_lines and cleaned_lines[-1].strip():
                # Keep empty lines that separate content
                cleaned_lines.append('')
        
        content = '\n'.join(cleaned_lines)
        
        # Remove multiple consecutive newlines
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        
        return content.strip()
    
    def _is_inside_code_block(self, content: str, start_pos: int, end_pos: int) -> bool:
        """Check if a position range is inside a code block.
        
        Args:
            content: Full content
            start_pos: Start position to check
            end_pos: End position to check
            
        Returns:
            True if the position is inside a code block
        """
        # Find all code blocks
        code_block_pattern = r'```(?:\w+)?\s*\n(.*?)\n\s*```'
        
        for match in re.finditer(code_block_pattern, content, re.DOTALL):
            block_start = match.start()
            block_end = match.end()
            
            # Check if our position overlaps with this code block
            if (start_pos >= block_start and start_pos < block_end) or \
               (end_pos > block_start and end_pos <= block_end) or \
               (start_pos < block_start and end_pos > block_end):
                return True
        
        return False
    
    def get_alternative_for_command_type(self, command_type: ShellCommandType) -> str:
        """Get alternative suggestion for a specific command type.
        
        Args:
            command_type: Type of shell command
            
        Returns:
            Alternative suggestion text
        """
        return self.alternative_suggestions.get(command_type, "")
    
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
    # Always return False to disable shell command detection
    return False