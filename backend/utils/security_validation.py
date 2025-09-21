"""
Security Validation and Input Sanitization Utilities

Provides comprehensive input validation, sanitization, and security checks
for all API endpoints in the Cosmos Web Chat Integration.
"""

import re
import html
import json
import logging
from typing import Any, Dict, List, Optional, Union, Tuple
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass
from enum import Enum
import bleach
from pydantic import BaseModel, validator, ValidationError as PydanticValidationError
from fastapi import HTTPException, status

from utils.error_handling import ValidationError, CosmosError, ErrorCategory, ErrorSeverity

logger = logging.getLogger(__name__)


class ValidationLevel(str, Enum):
    """Validation strictness levels."""
    STRICT = "strict"
    MODERATE = "moderate"
    LENIENT = "lenient"


@dataclass
class ValidationResult:
    """Result of input validation."""
    is_valid: bool
    sanitized_value: Any = None
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class SecurityValidator:
    """
    Comprehensive security validator for input sanitization and validation.
    
    Provides methods for validating and sanitizing various types of input
    to prevent security vulnerabilities like XSS, SQL injection, and more.
    """
    
    def __init__(self, validation_level: ValidationLevel = ValidationLevel.STRICT):
        """Initialize the security validator."""
        self.validation_level = validation_level
        
        # Configure bleach for HTML sanitization
        self.allowed_tags = [
            'p', 'br', 'strong', 'em', 'u', 'code', 'pre', 'blockquote',
            'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'
        ]
        self.allowed_attributes = {
            '*': ['class'],
            'code': ['class'],
            'pre': ['class']
        }
        
        # Regex patterns for validation
        self.patterns = {
            'email': re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
            'github_repo': re.compile(r'^https://github\.com/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+/?$'),
            'github_username': re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$'),
            'session_id': re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'),
            'model_name': re.compile(r'^[a-zA-Z0-9._-]+$'),
            'branch_name': re.compile(r'^[a-zA-Z0-9._/-]+$'),
            'file_path': re.compile(r'^[a-zA-Z0-9._/\-\s]+\.[a-zA-Z0-9]+$'),
            'safe_string': re.compile(r'^[a-zA-Z0-9\s._-]+$'),
            'alphanumeric': re.compile(r'^[a-zA-Z0-9]+$'),
            'sql_injection': re.compile(r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b|\'.*OR.*\'|\'.*=.*\'|\'--|admin\')', re.IGNORECASE),
            'xss_patterns': re.compile(r'(<script|javascript:|on\w+\s*=|<iframe|<object|<embed)', re.IGNORECASE)
        }
        
        # Maximum lengths for different input types
        self.max_lengths = {
            'message': 10000,
            'title': 200,
            'description': 1000,
            'url': 2048,
            'filename': 255,
            'username': 50,
            'email': 254,
            'session_title': 100,
            'model_name': 50,
            'branch_name': 100,
            'file_path': 500
        }
    
    def validate_string(
        self,
        value: str,
        field_name: str,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
        allow_empty: bool = False,
        sanitize_html: bool = True
    ) -> ValidationResult:
        """
        Validate and sanitize a string input.
        
        Args:
            value: String value to validate
            field_name: Name of the field for error messages
            max_length: Maximum allowed length
            pattern: Regex pattern name to validate against
            allow_empty: Whether empty strings are allowed
            sanitize_html: Whether to sanitize HTML content
            
        Returns:
            ValidationResult with validation status and sanitized value
        """
        errors = []
        warnings = []
        
        # Check if value is provided
        if not value or not value.strip():
            if not allow_empty:
                errors.append(f"{field_name} cannot be empty")
                return ValidationResult(is_valid=False, errors=errors)
            else:
                return ValidationResult(is_valid=True, sanitized_value="")
        
        # Convert to string if not already
        if not isinstance(value, str):
            value = str(value)
        
        # Check length
        if max_length is None:
            max_length = self.max_lengths.get(field_name.lower(), 1000)
        
        if len(value) > max_length:
            errors.append(f"{field_name} exceeds maximum length of {max_length} characters")
        
        # Check for potential security threats
        if self.patterns['sql_injection'].search(value):
            errors.append(f"{field_name} contains potentially dangerous SQL patterns")
        
        if self.patterns['xss_patterns'].search(value):
            if sanitize_html:
                warnings.append(f"{field_name} contained HTML/JavaScript that was sanitized")
            else:
                errors.append(f"{field_name} contains potentially dangerous HTML/JavaScript")
        
        # Validate against pattern if provided
        if pattern and pattern in self.patterns:
            if not self.patterns[pattern].match(value):
                errors.append(f"{field_name} format is invalid")
        
        # Sanitize the value
        sanitized_value = value
        
        if sanitize_html:
            # Remove HTML tags and decode entities
            sanitized_value = bleach.clean(
                sanitized_value,
                tags=self.allowed_tags if self.validation_level == ValidationLevel.LENIENT else [],
                attributes=self.allowed_attributes if self.validation_level == ValidationLevel.LENIENT else {},
                strip=True
            )
            sanitized_value = html.unescape(sanitized_value)
        
        # Additional sanitization
        sanitized_value = sanitized_value.strip()
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_value=sanitized_value,
            errors=errors,
            warnings=warnings
        )
    
    def validate_email(self, email: str) -> ValidationResult:
        """Validate email address."""
        return self.validate_string(
            email,
            "email",
            pattern="email",
            sanitize_html=False
        )
    
    def validate_github_repository_url(self, url: str) -> ValidationResult:
        """Validate GitHub repository URL."""
        result = self.validate_string(
            url,
            "repository_url",
            max_length=self.max_lengths['url'],
            sanitize_html=False
        )
        
        if not result.is_valid:
            return result
        
        # Additional GitHub-specific validation
        if not self.patterns['github_repo'].match(result.sanitized_value):
            result.errors.append("Invalid GitHub repository URL format")
            result.is_valid = False
        
        return result
    
    def validate_session_id(self, session_id: str) -> ValidationResult:
        """Validate session ID format."""
        return self.validate_string(
            session_id,
            "session_id",
            pattern="session_id",
            sanitize_html=False
        )
    
    def validate_model_name(self, model_name: str) -> ValidationResult:
        """Validate AI model name."""
        return self.validate_string(
            model_name,
            "model_name",
            pattern="model_name",
            sanitize_html=False
        )
    
    def validate_branch_name(self, branch_name: str) -> ValidationResult:
        """Validate Git branch name."""
        return self.validate_string(
            branch_name,
            "branch_name",
            pattern="branch_name",
            sanitize_html=False
        )
    
    def validate_file_path(self, file_path: str) -> ValidationResult:
        """Validate file path."""
        result = self.validate_string(
            file_path,
            "file_path",
            pattern="file_path",
            sanitize_html=False
        )
        
        if not result.is_valid:
            return result
        
        # Additional file path security checks
        sanitized_path = result.sanitized_value
        
        # Check for directory traversal attempts
        if '..' in sanitized_path or sanitized_path.startswith('/'):
            result.errors.append("File path contains invalid directory traversal patterns")
            result.is_valid = False
        
        # Check for hidden files (optional warning)
        if sanitized_path.startswith('.'):
            result.warnings.append("File path refers to a hidden file")
        
        return result
    
    def validate_json_payload(
        self,
        payload: Union[str, Dict[str, Any]],
        max_size: int = 1024 * 1024,  # 1MB default
        required_fields: Optional[List[str]] = None
    ) -> ValidationResult:
        """
        Validate JSON payload.
        
        Args:
            payload: JSON string or dictionary
            max_size: Maximum payload size in bytes
            required_fields: List of required field names
            
        Returns:
            ValidationResult with parsed and validated JSON
        """
        errors = []
        warnings = []
        
        # Convert string to dict if needed
        if isinstance(payload, str):
            # Check size
            if len(payload.encode('utf-8')) > max_size:
                errors.append(f"JSON payload exceeds maximum size of {max_size} bytes")
                return ValidationResult(is_valid=False, errors=errors)
            
            try:
                parsed_payload = json.loads(payload)
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON format: {str(e)}")
                return ValidationResult(is_valid=False, errors=errors)
        else:
            parsed_payload = payload
        
        # Validate required fields
        if required_fields:
            for field in required_fields:
                if field not in parsed_payload:
                    errors.append(f"Required field '{field}' is missing")
        
        # Recursively validate string values in the payload
        sanitized_payload = self._sanitize_json_values(parsed_payload)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_value=sanitized_payload,
            errors=errors,
            warnings=warnings
        )
    
    def _sanitize_json_values(self, obj: Any) -> Any:
        """Recursively sanitize string values in a JSON object."""
        if isinstance(obj, dict):
            return {key: self._sanitize_json_values(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_json_values(item) for item in obj]
        elif isinstance(obj, str):
            # Basic sanitization for JSON string values
            result = self.validate_string(
                obj,
                "json_value",
                max_length=10000,
                sanitize_html=True
            )
            return result.sanitized_value if result.is_valid else obj
        else:
            return obj
    
    def validate_request_size(
        self,
        content_length: Optional[int],
        max_size: int = 10 * 1024 * 1024  # 10MB default
    ) -> ValidationResult:
        """Validate request content size."""
        if content_length is None:
            return ValidationResult(is_valid=True)
        
        if content_length > max_size:
            return ValidationResult(
                is_valid=False,
                errors=[f"Request size {content_length} exceeds maximum allowed size of {max_size} bytes"]
            )
        
        return ValidationResult(is_valid=True)
    
    def validate_rate_limit_identifier(self, identifier: str) -> ValidationResult:
        """Validate rate limit identifier (usually user ID or IP)."""
        return self.validate_string(
            identifier,
            "rate_limit_identifier",
            pattern="safe_string",
            sanitize_html=False
        )


class ChatMessageValidator(BaseModel):
    """Pydantic model for chat message validation."""
    
    message: str
    session_id: str
    model: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    
    @validator('message')
    def validate_message_content(cls, v):
        """Validate message content."""
        validator = SecurityValidator()
        result = validator.validate_string(
            v,
            "message",
            max_length=10000,
            sanitize_html=True
        )
        
        if not result.is_valid:
            raise ValueError(f"Invalid message: {', '.join(result.errors)}")
        
        return result.sanitized_value
    
    @validator('session_id')
    def validate_session_id_format(cls, v):
        """Validate session ID format."""
        validator = SecurityValidator()
        result = validator.validate_session_id(v)
        
        if not result.is_valid:
            raise ValueError(f"Invalid session ID: {', '.join(result.errors)}")
        
        return result.sanitized_value
    
    @validator('model')
    def validate_model_name_format(cls, v):
        """Validate model name format."""
        if v is None:
            return v
        
        validator = SecurityValidator()
        result = validator.validate_model_name(v)
        
        if not result.is_valid:
            raise ValueError(f"Invalid model name: {', '.join(result.errors)}")
        
        return result.sanitized_value
    
    @validator('context')
    def validate_context_data(cls, v):
        """Validate context data."""
        if v is None:
            return v
        
        validator = SecurityValidator()
        result = validator.validate_json_payload(v, max_size=1024 * 1024)  # 1MB limit
        
        if not result.is_valid:
            raise ValueError(f"Invalid context data: {', '.join(result.errors)}")
        
        return result.sanitized_value


class SessionValidator(BaseModel):
    """Pydantic model for session validation."""
    
    title: Optional[str] = None
    repository_id: Optional[str] = None
    repository_url: Optional[str] = None
    branch: Optional[str] = "main"
    
    @validator('title')
    def validate_title_content(cls, v):
        """Validate session title."""
        if v is None:
            return v
        
        validator = SecurityValidator()
        result = validator.validate_string(
            v,
            "session_title",
            max_length=100,
            sanitize_html=True
        )
        
        if not result.is_valid:
            raise ValueError(f"Invalid title: {', '.join(result.errors)}")
        
        return result.sanitized_value
    
    @validator('repository_url')
    def validate_repository_url_format(cls, v):
        """Validate repository URL format."""
        if v is None:
            return v
        
        validator = SecurityValidator()
        result = validator.validate_github_repository_url(v)
        
        if not result.is_valid:
            raise ValueError(f"Invalid repository URL: {', '.join(result.errors)}")
        
        return result.sanitized_value
    
    @validator('branch')
    def validate_branch_name_format(cls, v):
        """Validate branch name format."""
        if v is None:
            return "main"
        
        validator = SecurityValidator()
        result = validator.validate_branch_name(v)
        
        if not result.is_valid:
            raise ValueError(f"Invalid branch name: {', '.join(result.errors)}")
        
        return result.sanitized_value


class ContextFileValidator(BaseModel):
    """Pydantic model for context file validation."""
    
    file_paths: List[str]
    repository_url: Optional[str] = None
    branch: Optional[str] = "main"
    
    @validator('file_paths')
    def validate_file_paths_list(cls, v):
        """Validate list of file paths."""
        if not v:
            raise ValueError("At least one file path is required")
        
        if len(v) > 100:  # Reasonable limit
            raise ValueError("Too many files specified (maximum 100)")
        
        validator = SecurityValidator()
        sanitized_paths = []
        
        for file_path in v:
            result = validator.validate_file_path(file_path)
            if not result.is_valid:
                raise ValueError(f"Invalid file path '{file_path}': {', '.join(result.errors)}")
            sanitized_paths.append(result.sanitized_value)
        
        return sanitized_paths
    
    @validator('repository_url')
    def validate_repository_url_format(cls, v):
        """Validate repository URL format."""
        if v is None:
            return v
        
        validator = SecurityValidator()
        result = validator.validate_github_repository_url(v)
        
        if not result.is_valid:
            raise ValueError(f"Invalid repository URL: {', '.join(result.errors)}")
        
        return result.sanitized_value


def validate_and_sanitize_input(
    data: Dict[str, Any],
    validator_class: type,
    field_name: str = "request"
) -> Any:
    """
    Validate and sanitize input data using a Pydantic validator.
    
    Args:
        data: Input data to validate
        validator_class: Pydantic validator class to use
        field_name: Field name for error messages
        
    Returns:
        Validated and sanitized data
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        validated_data = validator_class(**data)
        return validated_data.dict()
    except PydanticValidationError as e:
        errors = []
        for error in e.errors():
            field = '.'.join(str(loc) for loc in error['loc'])
            message = error['msg']
            errors.append(f"{field}: {message}")
        
        raise ValidationError(
            message=f"Invalid {field_name}: {'; '.join(errors)}",
            details={"validation_errors": errors, "field": field_name}
        )


def sanitize_output(data: Any) -> Any:
    """
    Sanitize output data to prevent information leakage.
    
    Args:
        data: Data to sanitize
        
    Returns:
        Sanitized data with sensitive information removed
    """
    if isinstance(data, dict):
        sanitized = {}
        sensitive_keys = {
            'password', 'token', 'key', 'secret', 'credential',
            'access_token', 'refresh_token', 'api_key', 'private_key'
        }
        
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_output(value)
        
        return sanitized
    elif isinstance(data, list):
        return [sanitize_output(item) for item in data]
    else:
        return data


# Global validator instance
security_validator = SecurityValidator()