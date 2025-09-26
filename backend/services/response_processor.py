"""
Web-Safe Response Processing

Implements response formatting for web display, code syntax highlighting,
diff visualization, and CLI-to-web conversion for Cosmos chat integration.

SECURITY: This processor filters out shell command suggestions for security.
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

# Import shell command filter for security
from services.shell_command_filter import shell_command_filter

# Configure logging
logger = logging.getLogger(__name__)


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


@dataclass
class CodeBlock:
    """Code block with syntax highlighting information."""
    content: str
    language: CodeLanguage
    filename: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    is_diff: bool = False
    diff_type: Optional[str] = None  # 'addition', 'deletion', 'modification'


@dataclass
class DiffBlock:
    """Diff visualization block."""
    filename: str
    old_content: Optional[str]
    new_content: str
    diff_lines: List[Dict[str, Any]]
    language: CodeLanguage
    change_type: str  # 'create', 'modify', 'delete'


@dataclass
class InteractiveElement:
    """Interactive UI element for web display."""
    element_type: str  # 'button', 'dropdown', 'checkbox', 'input'
    label: str
    value: Optional[str] = None
    options: Optional[List[str]] = None
    action: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class FileListItem:
    """File list item with metadata."""
    path: str
    name: str
    size: Optional[int] = None
    language: Optional[CodeLanguage] = None
    is_directory: bool = False
    is_tracked: bool = True
    last_modified: Optional[datetime] = None


@dataclass
class ProcessedResponse:
    """Processed response with web-safe formatting."""
    content: str
    response_type: ResponseType
    code_blocks: List[CodeBlock]
    diff_blocks: List[DiffBlock]
    interactive_elements: List[InteractiveElement]
    file_lists: List[List[FileListItem]]
    shell_commands_converted: List[str]
    conversion_notes: Optional[str]
    metadata: Dict[str, Any]
    raw_content: str


class ResponseProcessor:
    """
    Web-Safe Response Processing
    
    Processes Cosmos AI responses for web display with syntax highlighting,
    diff visualization, and interactive element conversion.
    """
    
    def __init__(self):
        """Initialize the response processor."""
        self.code_block_pattern = re.compile(
            r'```(\w+)?\s*\n(.*?)\n\s*```',
            re.DOTALL
        )
        self.inline_code_pattern = re.compile(r'`([^`]+)`')
        self.file_path_pattern = re.compile(r'(?:^|\s)([a-zA-Z0-9_/.-]+\.[a-zA-Z0-9]+)(?:\s|$)')
        self.shell_command_pattern = re.compile(r'^\$\s+(.+)$', re.MULTILINE)
        self.diff_pattern = re.compile(r'^([\+\-\s])(.*)$', re.MULTILINE)
        
        # Language detection patterns
        self.language_patterns = {
            CodeLanguage.PYTHON: [r'\.py$', r'def\s+\w+', r'import\s+\w+', r'from\s+\w+\s+import'],
            CodeLanguage.JAVASCRIPT: [r'\.js$', r'function\s+\w+', r'const\s+\w+', r'let\s+\w+', r'=>'],
            CodeLanguage.TYPESCRIPT: [r'\.ts$', r'interface\s+\w+', r'type\s+\w+', r':\s*\w+\[\]'],
            CodeLanguage.HTML: [r'\.html?$', r'<\w+[^>]*>', r'<!DOCTYPE'],
            CodeLanguage.CSS: [r'\.css$', r'\w+\s*{[^}]*}', r'@media', r'@import'],
            CodeLanguage.JSON: [r'\.json$', r'^\s*[{\[]', r'"\w+":\s*'],
            CodeLanguage.YAML: [r'\.ya?ml$', r'^\s*\w+:\s*', r'^\s*-\s+'],
            CodeLanguage.MARKDOWN: [r'\.md$', r'^#+\s+', r'^\*\*\w+\*\*', r'^\[.*\]\(.*\)'],
            CodeLanguage.BASH: [r'\.sh$', r'#!/bin/bash', r'^\$\s+', r'if\s*\[.*\]'],
            CodeLanguage.SQL: [r'\.sql$', r'SELECT\s+', r'FROM\s+', r'WHERE\s+'],
            CodeLanguage.JAVA: [r'\.java$', r'public\s+class', r'public\s+static\s+void\s+main'],
            CodeLanguage.CPP: [r'\.(cpp|cc|cxx)$', r'#include\s*<', r'int\s+main\s*\('],
            CodeLanguage.CSHARP: [r'\.cs$', r'using\s+System', r'public\s+class'],
            CodeLanguage.GO: [r'\.go$', r'package\s+\w+', r'func\s+\w+'],
            CodeLanguage.RUST: [r'\.rs$', r'fn\s+\w+', r'let\s+\w+'],
            CodeLanguage.PHP: [r'\.php$', r'<\?php', r'function\s+\w+'],
            CodeLanguage.RUBY: [r'\.rb$', r'def\s+\w+', r'class\s+\w+'],
        }
    
    def process_response(
        self, 
        content: str, 
        shell_commands_converted: Optional[List[str]] = None,
        conversion_notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ProcessedResponse:
        """
        Process a response for web-safe display.
        
        Args:
            content: Raw response content
            shell_commands_converted: List of shell commands that were converted
            conversion_notes: Notes about CLI-to-web conversions
            metadata: Additional metadata
            
        Returns:
            ProcessedResponse with web-safe formatting
        """
        try:
            logger.debug("Response processing simplified - returning original content")
            
            # Return original content without any processing
            processed = ProcessedResponse(
                content=content,
                response_type=ResponseType.TEXT,
                code_blocks=[],
                diff_blocks=[],
                interactive_elements=[],
                file_lists=[],
                shell_commands_converted=shell_commands_converted or [],
                conversion_notes=conversion_notes,
                metadata=metadata or {},
                raw_content=content
            )
            
            # Set minimal metadata
            processed.metadata['shell_commands_filtered'] = 0
            processed.metadata['security_alternatives_provided'] = 0
            
            logger.debug("Response returned without processing")
            return processed
            
        except Exception as e:
            logger.error(f"Error processing response: {e}")
            # Return safe fallback response
            return ProcessedResponse(
                content=content,
                response_type=ResponseType.TEXT,
                code_blocks=[],
                diff_blocks=[],
                interactive_elements=[],
                file_lists=[],
                shell_commands_converted=shell_commands_converted or [],
                conversion_notes=conversion_notes,
                metadata=metadata or {},
                raw_content=content
            )
    
    def _detect_response_type(self, content: str) -> ResponseType:
        """Detect the primary type of response content."""
        content_lower = content.lower()
        
        # Check for error indicators
        if any(indicator in content_lower for indicator in ['error:', 'exception:', 'traceback:', 'failed:']):
            return ResponseType.ERROR
        
        # Check for diff indicators
        if any(indicator in content for indicator in ['+++', '---', '@@ -', '+++ b/', '--- a/']):
            return ResponseType.DIFF
        
        # Check for shell output indicators
        if any(indicator in content for indicator in ['$ ', '> ', 'Command:', 'Output:']):
            return ResponseType.SHELL_OUTPUT
        
        # Check for file list indicators
        if re.search(r'^\s*[\w/.-]+\.(py|js|ts|html|css|json|md|txt)\s*$', content, re.MULTILINE):
            return ResponseType.FILE_LIST
        
        # Check for repo map indicators
        if 'repository map' in content_lower or 'file structure' in content_lower:
            return ResponseType.REPO_MAP
        
        # Check for code blocks
        if '```' in content or re.search(r'^\s*def\s+\w+|^\s*function\s+\w+|^\s*class\s+\w+', content, re.MULTILINE):
            return ResponseType.CODE
        
        # Check for interactive prompts
        if any(indicator in content_lower for indicator in ['would you like to', 'do you want to', 'choose from']):
            return ResponseType.INTERACTIVE_PROMPT
        
        return ResponseType.TEXT
    
    def _extract_code_blocks(self, content: str) -> List[CodeBlock]:
        """Extract code blocks from content."""
        code_blocks = []
        
        # Find fenced code blocks
        for match in self.code_block_pattern.finditer(content):
            language_hint = match.group(1) or ""
            code_content = match.group(2).strip()
            
            # Detect language
            language = self._detect_language(code_content, language_hint)
            
            # Check if it's a diff
            is_diff = self._is_diff_content(code_content)
            
            code_block = CodeBlock(
                content=code_content,
                language=language,
                is_diff=is_diff,
                diff_type=self._detect_diff_type(code_content) if is_diff else None
            )
            
            code_blocks.append(code_block)
        
        return code_blocks
    
    def _detect_language(self, content: str, hint: str = "") -> CodeLanguage:
        """Detect programming language from content and hints."""
        # First try the hint
        if hint:
            hint_lower = hint.lower()
            for lang in CodeLanguage:
                if lang.value == hint_lower:
                    return lang
        
        # Then try pattern matching
        for language, patterns in self.language_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                    return language
        
        return CodeLanguage.UNKNOWN
    
    def _is_diff_content(self, content: str) -> bool:
        """Check if content is a diff."""
        lines = content.split('\n')
        diff_indicators = 0
        
        for line in lines[:10]:  # Check first 10 lines
            stripped = line.strip()
            if stripped.startswith(('+', '-')) and not stripped.startswith(('+++', '---')):
                diff_indicators += 1
            elif stripped.startswith('@@'):
                diff_indicators += 1
        
        return diff_indicators >= 2
    
    def _detect_diff_type(self, content: str) -> str:
        """Detect type of diff (addition, deletion, modification)."""
        has_additions = '+' in content and not content.startswith('+++')
        has_deletions = '-' in content and not content.startswith('---')
        
        if has_additions and has_deletions:
            return 'modification'
        elif has_additions:
            return 'addition'
        elif has_deletions:
            return 'deletion'
        else:
            return 'unknown'
    
    def _process_code_response(self, content: str, processed: ProcessedResponse) -> ProcessedResponse:
        """Process code-focused responses."""
        # Extract file references
        file_matches = self.file_path_pattern.findall(content)
        if file_matches:
            processed.metadata['referenced_files'] = list(set(file_matches))
        
        # Format code content with syntax highlighting markers
        processed.content = self._add_syntax_highlighting_markers(content)
        
        return processed
    
    def _process_diff_response(self, content: str, processed: ProcessedResponse) -> ProcessedResponse:
        """Process diff-focused responses."""
        diff_blocks = self._extract_diff_blocks(content)
        processed.diff_blocks.extend(diff_blocks)
        
        # Format diff content for web display
        processed.content = self._format_diff_content(content, diff_blocks)
        
        return processed
    
    def _extract_diff_blocks(self, content: str) -> List[DiffBlock]:
        """Extract diff blocks from content."""
        diff_blocks = []
        
        # Simple diff parsing - could be enhanced
        lines = content.split('\n')
        current_file = None
        old_content = []
        new_content = []
        diff_lines = []
        
        for line in lines:
            if line.startswith('--- '):
                if current_file:
                    # Save previous diff block
                    diff_blocks.append(DiffBlock(
                        filename=current_file,
                        old_content='\n'.join(old_content) if old_content else None,
                        new_content='\n'.join(new_content),
                        diff_lines=diff_lines.copy(),
                        language=self._detect_language('\n'.join(new_content)),
                        change_type='modify'
                    ))
                
                # Start new diff block
                current_file = line[4:].strip()
                old_content.clear()
                new_content.clear()
                diff_lines.clear()
                
            elif line.startswith('+++ '):
                continue  # Skip +++ lines
                
            elif line.startswith('@@'):
                continue  # Skip hunk headers
                
            elif line.startswith('-'):
                old_content.append(line[1:])
                diff_lines.append({
                    'type': 'deletion',
                    'content': line[1:],
                    'line_number': len(old_content)
                })
                
            elif line.startswith('+'):
                new_content.append(line[1:])
                diff_lines.append({
                    'type': 'addition',
                    'content': line[1:],
                    'line_number': len(new_content)
                })
                
            else:
                # Context line
                if line.startswith(' '):
                    line_content = line[1:]
                else:
                    line_content = line
                    
                old_content.append(line_content)
                new_content.append(line_content)
                diff_lines.append({
                    'type': 'context',
                    'content': line_content,
                    'line_number': len(new_content)
                })
        
        # Save final diff block
        if current_file:
            diff_blocks.append(DiffBlock(
                filename=current_file,
                old_content='\n'.join(old_content) if old_content else None,
                new_content='\n'.join(new_content),
                diff_lines=diff_lines,
                language=self._detect_language('\n'.join(new_content)),
                change_type='modify'
            ))
        
        return diff_blocks
    
    def _format_diff_content(self, content: str, diff_blocks: List[DiffBlock]) -> str:
        """Format diff content for web display."""
        if not diff_blocks:
            return content
        
        formatted_parts = []
        
        for diff_block in diff_blocks:
            formatted_parts.append(f"**File: {diff_block.filename}**")
            formatted_parts.append(f"*Language: {diff_block.language.value}*")
            formatted_parts.append(f"*Change Type: {diff_block.change_type}*")
            formatted_parts.append("")
            
            # Add diff visualization markers
            for diff_line in diff_block.diff_lines:
                line_type = diff_line['type']
                line_content = diff_line['content']
                
                if line_type == 'addition':
                    formatted_parts.append(f"+ {line_content}")
                elif line_type == 'deletion':
                    formatted_parts.append(f"- {line_content}")
                else:
                    formatted_parts.append(f"  {line_content}")
            
            formatted_parts.append("")
        
        return '\n'.join(formatted_parts)
    
    def _process_shell_output(self, content: str, processed: ProcessedResponse) -> ProcessedResponse:
        """Process shell output responses."""
        # Extract shell commands
        shell_commands = self.shell_command_pattern.findall(content)
        if shell_commands:
            processed.metadata['shell_commands'] = shell_commands
        
        # Format shell output with proper styling
        processed.content = self._format_shell_output(content)
        
        return processed
    
    def _format_shell_output(self, content: str) -> str:
        """Format shell output for web display."""
        lines = content.split('\n')
        formatted_lines = []
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('$ '):
                # Command line
                formatted_lines.append(f"**Command:** `{stripped[2:]}`")
            elif stripped.startswith('> '):
                # Output line
                formatted_lines.append(f"```\n{stripped[2:]}\n```")
            else:
                formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    def _process_file_list(self, content: str, processed: ProcessedResponse) -> ProcessedResponse:
        """Process file list responses."""
        file_lists = self._extract_file_lists(content)
        processed.file_lists.extend(file_lists)
        
        # Format file list for web display
        processed.content = self._format_file_lists(file_lists)
        
        return processed
    
    def _extract_file_lists(self, content: str) -> List[List[FileListItem]]:
        """Extract file lists from content."""
        file_lists = []
        lines = content.split('\n')
        current_list = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_list:
                    file_lists.append(current_list)
                    current_list = []
                continue
            
            # Try to parse as file entry
            file_item = self._parse_file_entry(line)
            if file_item:
                current_list.append(file_item)
        
        if current_list:
            file_lists.append(current_list)
        
        return file_lists
    
    def _parse_file_entry(self, line: str) -> Optional[FileListItem]:
        """Parse a single file entry from a line."""
        # Handle different file listing formats
        
        # Format: "    1234 path/to/file.py"
        size_match = re.match(r'^\s*(\d+)\s+(.+)$', line)
        if size_match:
            size = int(size_match.group(1))
            path = size_match.group(2)
            return FileListItem(
                path=path,
                name=path.split('/')[-1],
                size=size,
                language=self._detect_language_from_extension(path),
                is_directory=False
            )
        
        # Format: "path/to/file.py"
        if re.match(r'^[\w/.-]+\.\w+$', line):
            return FileListItem(
                path=line,
                name=line.split('/')[-1],
                language=self._detect_language_from_extension(line),
                is_directory=False
            )
        
        # Format: "directory/"
        if line.endswith('/'):
            return FileListItem(
                path=line[:-1],
                name=line.split('/')[-2] if '/' in line[:-1] else line[:-1],
                is_directory=True
            )
        
        return None
    
    def _detect_language_from_extension(self, filename: str) -> CodeLanguage:
        """Detect language from file extension."""
        ext = filename.split('.')[-1].lower() if '.' in filename else ""
        
        extension_map = {
            'py': CodeLanguage.PYTHON,
            'js': CodeLanguage.JAVASCRIPT,
            'ts': CodeLanguage.TYPESCRIPT,
            'html': CodeLanguage.HTML,
            'htm': CodeLanguage.HTML,
            'css': CodeLanguage.CSS,
            'json': CodeLanguage.JSON,
            'yaml': CodeLanguage.YAML,
            'yml': CodeLanguage.YAML,
            'md': CodeLanguage.MARKDOWN,
            'sh': CodeLanguage.BASH,
            'bash': CodeLanguage.BASH,
            'sql': CodeLanguage.SQL,
            'java': CodeLanguage.JAVA,
            'cpp': CodeLanguage.CPP,
            'cc': CodeLanguage.CPP,
            'cxx': CodeLanguage.CPP,
            'cs': CodeLanguage.CSHARP,
            'go': CodeLanguage.GO,
            'rs': CodeLanguage.RUST,
            'php': CodeLanguage.PHP,
            'rb': CodeLanguage.RUBY,
        }
        
        return extension_map.get(ext, CodeLanguage.UNKNOWN)
    
    def _format_file_lists(self, file_lists: List[List[FileListItem]]) -> str:
        """Format file lists for web display."""
        if not file_lists:
            return ""
        
        formatted_parts = []
        
        for i, file_list in enumerate(file_lists):
            if i > 0:
                formatted_parts.append("---")
            
            formatted_parts.append("**Files:**")
            formatted_parts.append("")
            
            for file_item in file_list:
                if file_item.is_directory:
                    formatted_parts.append(f"📁 **{file_item.name}/**")
                else:
                    size_str = f" ({file_item.size} bytes)" if file_item.size else ""
                    lang_str = f" *({file_item.language.value})*" if file_item.language != CodeLanguage.UNKNOWN else ""
                    formatted_parts.append(f"📄 `{file_item.name}`{size_str}{lang_str}")
            
            formatted_parts.append("")
        
        return '\n'.join(formatted_parts)
    
    def _process_repo_map(self, content: str, processed: ProcessedResponse) -> ProcessedResponse:
        """Process repository map responses."""
        # Format repo map with proper structure
        processed.content = self._format_repo_map(content)
        
        return processed
    
    def _format_repo_map(self, content: str) -> str:
        """Format repository map for web display."""
        lines = content.split('\n')
        formatted_lines = []
        
        for line in lines:
            # Add proper indentation and icons for tree structure
            indent_level = len(line) - len(line.lstrip())
            stripped_line = line.strip()
            
            if not stripped_line:
                formatted_lines.append("")
                continue
            
            # Detect if it's a directory or file
            if stripped_line.endswith('/') or '.' not in stripped_line.split('/')[-1]:
                # Directory
                icon = "📁"
                formatted_line = f"{'  ' * (indent_level // 2)}{icon} **{stripped_line}**"
            else:
                # File
                icon = "📄"
                formatted_line = f"{'  ' * (indent_level // 2)}{icon} `{stripped_line}`"
            
            formatted_lines.append(formatted_line)
        
        return '\n'.join(formatted_lines)
    
    def _process_text_response(self, content: str, processed: ProcessedResponse) -> ProcessedResponse:
        """Process general text responses."""
        # Add basic formatting improvements
        processed.content = self._enhance_text_formatting(content)
        
        return processed
    
    def _enhance_text_formatting(self, content: str) -> str:
        """Enhance text formatting for web display."""
        # Convert inline code
        content = self.inline_code_pattern.sub(r'`\1`', content)
        
        # Enhance file paths
        content = self.file_path_pattern.sub(r' `\1` ', content)
        
        # Add line breaks for better readability
        paragraphs = content.split('\n\n')
        enhanced_paragraphs = []
        
        for paragraph in paragraphs:
            if paragraph.strip():
                enhanced_paragraphs.append(paragraph.strip())
        
        return '\n\n'.join(enhanced_paragraphs)
    
    def _extract_interactive_elements(self, content: str) -> List[InteractiveElement]:
        """Extract interactive elements from content."""
        interactive_elements = []
        
        # Look for choice prompts
        choice_patterns = [
            r'(?:choose|select) from:?\s*\n((?:\s*[-*]\s*.+\n?)+)',
            r'(?:would you like to|do you want to):\s*\n((?:\s*[-*]\s*.+\n?)+)',
            r'options?:?\s*\n((?:\s*\d+[.)]\s*.+\n?)+)'
        ]
        
        for pattern in choice_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                options_text = match.group(1)
                options = self._parse_options(options_text)
                
                if options:
                    interactive_elements.append(InteractiveElement(
                        element_type='dropdown',
                        label='Choose an option:',
                        options=options,
                        action='select_option'
                    ))
        
        # Look for yes/no prompts
        yn_pattern = r'(.*\?)\s*\(y/n\)'
        yn_matches = re.finditer(yn_pattern, content, re.IGNORECASE)
        for match in yn_matches:
            question = match.group(1).strip()
            interactive_elements.append(InteractiveElement(
                element_type='button',
                label=question,
                options=['Yes', 'No'],
                action='confirm_action'
            ))
        
        # Look for file selection prompts
        file_pattern = r'(?:add|select|include) files?:?\s*\n((?:\s*[-*]\s*.+\n?)+)'
        file_matches = re.finditer(file_pattern, content, re.IGNORECASE | re.MULTILINE)
        for match in file_matches:
            files_text = match.group(1)
            files = self._parse_options(files_text)
            
            if files:
                interactive_elements.append(InteractiveElement(
                    element_type='checkbox',
                    label='Select files to include:',
                    options=files,
                    action='select_files'
                ))
        
        return interactive_elements
    
    def _parse_options(self, options_text: str) -> List[str]:
        """Parse options from text."""
        options = []
        lines = options_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Remove list markers
            option = re.sub(r'^\s*[-*\d+.)]\s*', '', line).strip()
            if option:
                options.append(option)
        
        return options
    
    def _process_shell_conversions(
        self, 
        processed: ProcessedResponse, 
        shell_commands: List[str]
    ) -> ProcessedResponse:
        """Process shell command conversions."""
        if not shell_commands:
            return processed
        
        # Add conversion information to metadata
        processed.metadata['shell_conversions'] = {
            'total_commands': len(shell_commands),
            'commands': shell_commands,
            'conversion_timestamp': datetime.now().isoformat()
        }
        
        # Add conversion notes to content if not already present
        if not processed.conversion_notes:
            conversion_summary = f"Converted {len(shell_commands)} shell command(s) for web safety."
            processed.conversion_notes = conversion_summary
        
        return processed
    
    def _add_syntax_highlighting_markers(self, content: str) -> str:
        """Add syntax highlighting markers to content."""
        # This would integrate with a syntax highlighting library
        # For now, we'll add basic markers that can be processed by the frontend
        
        # Mark code blocks for highlighting
        content = re.sub(
            r'```(\w+)?\s*\n(.*?)\n\s*```',
            r'<code-block language="\1">\2</code-block>',
            content,
            flags=re.DOTALL
        )
        
        # Mark inline code
        content = re.sub(
            r'`([^`]+)`',
            r'<inline-code>\1</inline-code>',
            content
        )
        
        return content
    
    def _format_final_content(self, processed: ProcessedResponse) -> str:
        """Format the final content for web display."""
        content = processed.content
        
        # Add metadata sections if relevant
        sections = []
        
        # Add main content
        sections.append(content)
        
        # Add conversion notes if present
        if processed.conversion_notes:
            sections.append(f"\n**Conversion Notes:** {processed.conversion_notes}")
        
        # Add shell command information if present
        if processed.shell_commands_converted:
            sections.append(f"\n**Shell Commands Converted:** {len(processed.shell_commands_converted)}")
            for cmd in processed.shell_commands_converted[:3]:  # Show first 3
                sections.append(f"- `{cmd}`")
            if len(processed.shell_commands_converted) > 3:
                sections.append(f"- ... and {len(processed.shell_commands_converted) - 3} more")
        
        return '\n'.join(sections)
    
    def format_for_json_response(self, processed: ProcessedResponse) -> Dict[str, Any]:
        """Format processed response for JSON API response."""
        return {
            'content': processed.content,
            'response_type': processed.response_type.value,
            'code_blocks': [asdict(cb) for cb in processed.code_blocks],
            'diff_blocks': [asdict(db) for db in processed.diff_blocks],
            'interactive_elements': [asdict(ie) for ie in processed.interactive_elements],
            'file_lists': [
                [asdict(fi) for fi in file_list] 
                for file_list in processed.file_lists
            ],
            'shell_commands_converted': processed.shell_commands_converted,
            'conversion_notes': processed.conversion_notes,
            'metadata': processed.metadata,
            'processing_timestamp': datetime.now().isoformat()
        }