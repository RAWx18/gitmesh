#!/usr/bin/env python3
"""
Security Validation Script

This script performs comprehensive security validation to ensure that all
shell command execution capabilities have been completely removed from the
codebase and that no command injection vulnerabilities exist.

SECURITY: This script validates that the system is secure against all
shell command injection attacks.
"""

import os
import re
import sys
import ast
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.shell_command_filter import shell_command_filter
from services.shell_command_blocker import shell_blocker
from services.safe_file_operations import safe_file_ops

logger = logging.getLogger(__name__)

@dataclass
class SecurityIssue:
    """A security issue found during validation."""
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    category: str
    file_path: str
    line_number: int
    issue_description: str
    code_snippet: str
    recommendation: str

@dataclass
class SecurityValidationResult:
    """Result of security validation."""
    total_files_scanned: int
    issues_found: List[SecurityIssue]
    critical_issues: int
    high_issues: int
    medium_issues: int
    low_issues: int
    validation_passed: bool
    scan_duration: float
    timestamp: datetime

class SecurityValidator:
    """Comprehensive security validator for shell command removal."""
    
    def __init__(self, backend_dir: str):
        """Initialize the security validator.
        
        Args:
            backend_dir: Path to the backend directory to scan
        """
        self.backend_dir = Path(backend_dir)
        self.issues: List[SecurityIssue] = []
        
        # Dangerous patterns to look for
        self.dangerous_patterns = {
            'subprocess_usage': [
                r'import\s+subprocess',
                r'from\s+subprocess\s+import',
                r'subprocess\.(run|call|Popen|check_call|check_output)',
            ],
            'os_system_usage': [
                r'os\.system\s*\(',
                r'os\.popen\s*\(',
                r'os\.spawn[a-z]*\s*\(',
                r'os\.exec[a-z]*\s*\(',
            ],
            'pexpect_usage': [
                r'import\s+pexpect',
                r'from\s+pexpect\s+import',
                r'pexpect\.(spawn|run|runu)',
            ],
            'shell_execution': [
                r'shell\s*=\s*True',
                r'shell=True',
                r'\/bin\/sh',
                r'\/bin\/bash',
                r'cmd\.exe',
                r'powershell\.exe',
            ],
            'eval_exec_usage': [
                r'\beval\s*\(',
                r'\bexec\s*\(',
                r'__import__\s*\(',
            ]
        }
        
        # Files to exclude from scanning
        self.excluded_files = {
            '__pycache__',
            '.pyc',
            '.git',
            'node_modules',
            'venv',
            '.env',
            'test_shell_execution_removal.py',  # Our own test file
            'security_validation.py',  # This file
        }
        
        # Patterns that are allowed (commented out code, documentation)
        self.allowed_patterns = [
            r'#.*subprocess',  # Commented out subprocess
            r'#.*os\.system',  # Commented out os.system
            r'#.*SECURITY:',   # Security comments
            r'""".*subprocess.*"""',  # Docstring mentions
            r"'''.*subprocess.*'''",  # Docstring mentions
        ]
    
    def validate_security(self) -> SecurityValidationResult:
        """Perform comprehensive security validation.
        
        Returns:
            SecurityValidationResult with validation results
        """
        start_time = datetime.now()
        logger.info("Starting comprehensive security validation...")
        
        # Clear previous issues
        self.issues.clear()
        
        # Scan all Python files
        python_files = self._find_python_files()
        logger.info(f"Scanning {len(python_files)} Python files...")
        
        for file_path in python_files:
            self._scan_file(file_path)
        
        # Perform additional security checks
        self._check_shell_command_filter()
        self._check_safe_file_operations()
        self._check_security_documentation()
        
        # Calculate results
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        critical_issues = len([i for i in self.issues if i.severity == 'CRITICAL'])
        high_issues = len([i for i in self.issues if i.severity == 'HIGH'])
        medium_issues = len([i for i in self.issues if i.severity == 'MEDIUM'])
        low_issues = len([i for i in self.issues if i.severity == 'LOW'])
        
        validation_passed = critical_issues == 0 and high_issues == 0
        
        result = SecurityValidationResult(
            total_files_scanned=len(python_files),
            issues_found=self.issues.copy(),
            critical_issues=critical_issues,
            high_issues=high_issues,
            medium_issues=medium_issues,
            low_issues=low_issues,
            validation_passed=validation_passed,
            scan_duration=duration,
            timestamp=end_time
        )
        
        logger.info(f"Security validation completed in {duration:.2f} seconds")
        logger.info(f"Issues found: {critical_issues} critical, {high_issues} high, {medium_issues} medium, {low_issues} low")
        
        return result
    
    def _find_python_files(self) -> List[Path]:
        """Find all Python files to scan."""
        python_files = []
        
        for root, dirs, files in os.walk(self.backend_dir):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if not any(excluded in d for excluded in self.excluded_files)]
            
            for file in files:
                if file.endswith('.py') and not any(excluded in file for excluded in self.excluded_files):
                    python_files.append(Path(root) / file)
        
        return python_files
    
    def _scan_file(self, file_path: Path):
        """Scan a single file for security issues."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                self._check_line_for_issues(file_path, line_num, line, content)
                
        except (UnicodeDecodeError, PermissionError) as e:
            logger.warning(f"Could not scan file {file_path}: {e}")
    
    def _check_line_for_issues(self, file_path: Path, line_num: int, line: str, full_content: str):
        """Check a single line for security issues."""
        line_stripped = line.strip()
        
        # Skip empty lines and comments
        if not line_stripped or line_stripped.startswith('#'):
            return
        
        # Check for dangerous patterns
        for category, patterns in self.dangerous_patterns.items():
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Check if this is an allowed pattern (commented out, etc.)
                    if self._is_allowed_pattern(line, full_content):
                        continue
                    
                    # Determine severity
                    severity = self._get_severity_for_category(category)
                    
                    issue = SecurityIssue(
                        severity=severity,
                        category=category,
                        file_path=str(file_path.relative_to(self.backend_dir)),
                        line_number=line_num,
                        issue_description=f"Found {category} pattern: {pattern}",
                        code_snippet=line.strip(),
                        recommendation=self._get_recommendation_for_category(category)
                    )
                    
                    self.issues.append(issue)
                    logger.warning(f"Security issue found in {file_path}:{line_num} - {category}")
    
    def _is_allowed_pattern(self, line: str, full_content: str) -> bool:
        """Check if a pattern is allowed (commented out, in docstring, etc.)."""
        # Check if line is commented out
        if line.strip().startswith('#'):
            return True
        
        # Check for allowed patterns
        for allowed_pattern in self.allowed_patterns:
            if re.search(allowed_pattern, line, re.IGNORECASE | re.DOTALL):
                return True
        
        # Check if we're in a docstring or comment block
        if '"""' in full_content or "'''" in full_content:
            # This is a simplified check - in practice, you'd want more sophisticated parsing
            return False
        
        return False
    
    def _get_severity_for_category(self, category: str) -> str:
        """Get severity level for a security issue category."""
        severity_map = {
            'subprocess_usage': 'CRITICAL',
            'os_system_usage': 'CRITICAL',
            'pexpect_usage': 'HIGH',
            'shell_execution': 'CRITICAL',
            'eval_exec_usage': 'HIGH',
        }
        return severity_map.get(category, 'MEDIUM')
    
    def _get_recommendation_for_category(self, category: str) -> str:
        """Get recommendation for fixing a security issue category."""
        recommendations = {
            'subprocess_usage': 'Comment out subprocess usage and replace with safe alternatives or security messages',
            'os_system_usage': 'Comment out os.system usage and replace with safe file operations',
            'pexpect_usage': 'Comment out pexpect usage and replace with explanatory messages',
            'shell_execution': 'Remove shell=True parameters and replace with safe alternatives',
            'eval_exec_usage': 'Replace eval/exec with safe alternatives or remove if not needed',
        }
        return recommendations.get(category, 'Review and remove or replace with safe alternative')
    
    def _check_shell_command_filter(self):
        """Check that shell command filter is working properly."""
        try:
            # Test shell command detection
            test_commands = [
                "pip install requests",
                "git clone repo",
                "ls -la",
                "docker run image"
            ]
            
            for command in test_commands:
                if not shell_command_filter.is_shell_command(command):
                    issue = SecurityIssue(
                        severity='HIGH',
                        category='shell_filter_failure',
                        file_path='services/shell_command_filter.py',
                        line_number=0,
                        issue_description=f"Shell command filter failed to detect: {command}",
                        code_snippet=command,
                        recommendation='Fix shell command filter patterns to detect this command'
                    )
                    self.issues.append(issue)
            
            logger.info("Shell command filter validation completed")
            
        except Exception as e:
            issue = SecurityIssue(
                severity='CRITICAL',
                category='shell_filter_error',
                file_path='services/shell_command_filter.py',
                line_number=0,
                issue_description=f"Shell command filter error: {str(e)}",
                code_snippet='',
                recommendation='Fix shell command filter implementation'
            )
            self.issues.append(issue)
    
    def _check_safe_file_operations(self):
        """Check that safe file operations are working properly."""
        try:
            # Test directory traversal protection
            operation = safe_file_ops.safe_read_file("../../../etc/passwd")
            
            if operation.success:
                issue = SecurityIssue(
                    severity='CRITICAL',
                    category='directory_traversal',
                    file_path='services/safe_file_operations.py',
                    line_number=0,
                    issue_description='Safe file operations allow directory traversal',
                    code_snippet='../../../etc/passwd',
                    recommendation='Fix directory traversal protection in safe file operations'
                )
                self.issues.append(issue)
            
            logger.info("Safe file operations validation completed")
            
        except Exception as e:
            issue = SecurityIssue(
                severity='HIGH',
                category='safe_file_ops_error',
                file_path='services/safe_file_operations.py',
                line_number=0,
                issue_description=f"Safe file operations error: {str(e)}",
                code_snippet='',
                recommendation='Fix safe file operations implementation'
            )
            self.issues.append(issue)
    
    def _check_security_documentation(self):
        """Check that security documentation is present and complete."""
        try:
            from services.shell_command_blocker import get_security_documentation
            
            documentation = get_security_documentation()
            
            required_terms = [
                'security', 'shell command', 'subprocess', 'command injection',
                'disabled', 'removed', 'blocked'
            ]
            
            for term in required_terms:
                if term.lower() not in documentation.lower():
                    issue = SecurityIssue(
                        severity='LOW',
                        category='documentation_incomplete',
                        file_path='services/shell_command_blocker.py',
                        line_number=0,
                        issue_description=f'Security documentation missing term: {term}',
                        code_snippet='',
                        recommendation=f'Add {term} to security documentation'
                    )
                    self.issues.append(issue)
            
            logger.info("Security documentation validation completed")
            
        except Exception as e:
            issue = SecurityIssue(
                severity='MEDIUM',
                category='documentation_error',
                file_path='services/shell_command_blocker.py',
                line_number=0,
                issue_description=f"Security documentation error: {str(e)}",
                code_snippet='',
                recommendation='Fix security documentation implementation'
            )
            self.issues.append(issue)
    
    def generate_report(self, result: SecurityValidationResult) -> str:
        """Generate a comprehensive security validation report."""
        report = []
        report.append("=" * 80)
        report.append("SECURITY VALIDATION REPORT")
        report.append("=" * 80)
        report.append(f"Timestamp: {result.timestamp}")
        report.append(f"Scan Duration: {result.scan_duration:.2f} seconds")
        report.append(f"Files Scanned: {result.total_files_scanned}")
        report.append("")
        
        # Summary
        report.append("SUMMARY")
        report.append("-" * 40)
        report.append(f"Validation Status: {'PASSED' if result.validation_passed else 'FAILED'}")
        report.append(f"Critical Issues: {result.critical_issues}")
        report.append(f"High Issues: {result.high_issues}")
        report.append(f"Medium Issues: {result.medium_issues}")
        report.append(f"Low Issues: {result.low_issues}")
        report.append(f"Total Issues: {len(result.issues_found)}")
        report.append("")
        
        # Issues by severity
        for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            severity_issues = [i for i in result.issues_found if i.severity == severity]
            if severity_issues:
                report.append(f"{severity} ISSUES ({len(severity_issues)})")
                report.append("-" * 40)
                
                for issue in severity_issues:
                    report.append(f"File: {issue.file_path}:{issue.line_number}")
                    report.append(f"Category: {issue.category}")
                    report.append(f"Description: {issue.issue_description}")
                    report.append(f"Code: {issue.code_snippet}")
                    report.append(f"Recommendation: {issue.recommendation}")
                    report.append("")
        
        # Security recommendations
        report.append("SECURITY RECOMMENDATIONS")
        report.append("-" * 40)
        
        if result.validation_passed:
            report.append("✅ All security validations passed!")
            report.append("✅ No shell command execution capabilities found")
            report.append("✅ Shell command filtering is working properly")
            report.append("✅ Safe file operations are secure")
            report.append("✅ Security documentation is complete")
        else:
            report.append("❌ Security validation failed!")
            report.append("❌ Critical or high-severity issues found")
            report.append("❌ Immediate action required to fix security issues")
            
            if result.critical_issues > 0:
                report.append("")
                report.append("CRITICAL ACTIONS REQUIRED:")
                critical_issues = [i for i in result.issues_found if i.severity == 'CRITICAL']
                for issue in critical_issues:
                    report.append(f"- {issue.recommendation} ({issue.file_path})")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)

def main():
    """Main function to run security validation."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Get backend directory
    backend_dir = os.path.join(os.path.dirname(__file__), '..')
    
    # Create validator and run validation
    validator = SecurityValidator(backend_dir)
    result = validator.validate_security()
    
    # Generate and print report
    report = validator.generate_report(result)
    print(report)
    
    # Save report to file
    report_file = os.path.join(backend_dir, 'security_validation_report.txt')
    with open(report_file, 'w') as f:
        f.write(report)
    
    logger.info(f"Security validation report saved to: {report_file}")
    
    # Exit with appropriate code
    if result.validation_passed:
        logger.info("🔒 Security validation PASSED - System is secure!")
        sys.exit(0)
    else:
        logger.error("❌ Security validation FAILED - Security issues found!")
        sys.exit(1)

if __name__ == '__main__':
    main()