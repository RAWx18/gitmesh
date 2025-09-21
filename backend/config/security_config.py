"""
Security Configuration for Cosmos Web Chat Integration

Centralized security configuration including rate limits, validation rules,
CORS settings, and security policies.
"""

from typing import Dict, List, Any
from dataclasses import dataclass
from enum import Enum

from utils.rate_limiting import RateLimitType, RateLimitRule
from utils.security_validation import ValidationLevel
from config.settings import get_settings

settings = get_settings()


class SecurityLevel(str, Enum):
    """Security enforcement levels."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class SecurityConfig:
    """Main security configuration."""
    
    # Security level
    security_level: SecurityLevel
    
    # Validation settings
    validation_level: ValidationLevel
    input_sanitization_enabled: bool
    output_sanitization_enabled: bool
    
    # Rate limiting settings
    rate_limiting_enabled: bool
    abuse_detection_enabled: bool
    auto_blocking_enabled: bool
    
    # CORS settings
    cors_enabled: bool
    allowed_origins: List[str]
    allow_credentials: bool
    
    # Security headers
    security_headers_enabled: bool
    hsts_enabled: bool
    csp_enabled: bool
    
    # Audit logging
    audit_logging_enabled: bool
    audit_retention_days: int
    
    # File upload restrictions
    max_file_size_mb: int
    allowed_file_types: List[str]
    
    # Request size limits
    max_request_size_mb: int
    max_json_payload_mb: int
    
    # Session security
    session_timeout_minutes: int
    secure_cookies: bool
    
    @classmethod
    def get_config(cls) -> 'SecurityConfig':
        """Get security configuration based on environment."""
        env = settings.environment.lower()
        
        if env == "production":
            return cls._get_production_config()
        elif env == "staging":
            return cls._get_staging_config()
        else:
            return cls._get_development_config()
    
    @classmethod
    def _get_production_config(cls) -> 'SecurityConfig':
        """Production security configuration (strictest)."""
        return cls(
            security_level=SecurityLevel.PRODUCTION,
            validation_level=ValidationLevel.STRICT,
            input_sanitization_enabled=True,
            output_sanitization_enabled=True,
            rate_limiting_enabled=True,
            abuse_detection_enabled=True,
            auto_blocking_enabled=True,
            cors_enabled=True,
            allowed_origins=cls._get_production_origins(),
            allow_credentials=True,
            security_headers_enabled=True,
            hsts_enabled=True,
            csp_enabled=True,
            audit_logging_enabled=True,
            audit_retention_days=365,
            max_file_size_mb=10,
            allowed_file_types=['.py', '.js', '.ts', '.json', '.md', '.txt', '.yml', '.yaml'],
            max_request_size_mb=10,
            max_json_payload_mb=5,
            session_timeout_minutes=60,
            secure_cookies=True
        )
    
    @classmethod
    def _get_staging_config(cls) -> 'SecurityConfig':
        """Staging security configuration (moderate)."""
        return cls(
            security_level=SecurityLevel.STAGING,
            validation_level=ValidationLevel.MODERATE,
            input_sanitization_enabled=True,
            output_sanitization_enabled=True,
            rate_limiting_enabled=True,
            abuse_detection_enabled=True,
            auto_blocking_enabled=False,  # Manual review in staging
            cors_enabled=True,
            allowed_origins=cls._get_staging_origins(),
            allow_credentials=True,
            security_headers_enabled=True,
            hsts_enabled=False,  # No HTTPS in staging
            csp_enabled=True,
            audit_logging_enabled=True,
            audit_retention_days=90,
            max_file_size_mb=20,
            allowed_file_types=['.py', '.js', '.ts', '.json', '.md', '.txt', '.yml', '.yaml', '.log'],
            max_request_size_mb=20,
            max_json_payload_mb=10,
            session_timeout_minutes=120,
            secure_cookies=False
        )
    
    @classmethod
    def _get_development_config(cls) -> 'SecurityConfig':
        """Development security configuration (lenient)."""
        return cls(
            security_level=SecurityLevel.DEVELOPMENT,
            validation_level=ValidationLevel.LENIENT,
            input_sanitization_enabled=True,
            output_sanitization_enabled=False,  # Easier debugging
            rate_limiting_enabled=True,
            abuse_detection_enabled=False,  # Avoid blocking during development
            auto_blocking_enabled=False,
            cors_enabled=True,
            allowed_origins=["*"],  # Allow all origins in development
            allow_credentials=True,
            security_headers_enabled=True,
            hsts_enabled=False,  # No HTTPS in development
            csp_enabled=False,  # Relaxed CSP for development
            audit_logging_enabled=True,
            audit_retention_days=30,
            max_file_size_mb=50,
            allowed_file_types=['.py', '.js', '.ts', '.json', '.md', '.txt', '.yml', '.yaml', '.log', '.csv'],
            max_request_size_mb=50,
            max_json_payload_mb=25,
            session_timeout_minutes=480,  # 8 hours for development
            secure_cookies=False
        )
    
    @classmethod
    def _get_production_origins(cls) -> List[str]:
        """Get allowed origins for production."""
        # These should be configured via environment variables
        origins = []
        
        # Add from settings
        if hasattr(settings, 'cors_origins'):
            origins.extend(settings.cors_origins)
        
        # Remove wildcard in production
        origins = [origin for origin in origins if origin != "*"]
        
        # Default production origins if none configured
        if not origins:
            origins = [
                "https://yourdomain.com",
                "https://www.yourdomain.com",
                "https://app.yourdomain.com"
            ]
        
        return origins
    
    @classmethod
    def _get_staging_origins(cls) -> List[str]:
        """Get allowed origins for staging."""
        return [
            "https://staging.yourdomain.com",
            "https://staging-app.yourdomain.com",
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3002"
        ]


class RateLimitConfig:
    """Rate limiting configuration."""
    
    @staticmethod
    def get_rate_limit_rules() -> Dict[RateLimitType, RateLimitRule]:
        """Get rate limit rules based on environment."""
        security_config = SecurityConfig.get_config()
        
        if security_config.security_level == SecurityLevel.PRODUCTION:
            return RateLimitConfig._get_production_rules()
        elif security_config.security_level == SecurityLevel.STAGING:
            return RateLimitConfig._get_staging_rules()
        else:
            return RateLimitConfig._get_development_rules()
    
    @staticmethod
    def _get_production_rules() -> Dict[RateLimitType, RateLimitRule]:
        """Production rate limit rules (strict)."""
        return {
            RateLimitType.REQUESTS_PER_MINUTE: RateLimitRule(
                limit_type=RateLimitType.REQUESTS_PER_MINUTE,
                max_requests=60,
                window_seconds=60,
                burst_allowance=10,
                tier_multipliers={"free": 1.0, "pro": 3.0, "enterprise": 10.0}
            ),
            RateLimitType.REQUESTS_PER_HOUR: RateLimitRule(
                limit_type=RateLimitType.REQUESTS_PER_HOUR,
                max_requests=1000,
                window_seconds=3600,
                burst_allowance=50,
                tier_multipliers={"free": 1.0, "pro": 3.0, "enterprise": 10.0}
            ),
            RateLimitType.REQUESTS_PER_DAY: RateLimitRule(
                limit_type=RateLimitType.REQUESTS_PER_DAY,
                max_requests=10000,
                window_seconds=86400,
                burst_allowance=100,
                tier_multipliers={"free": 1.0, "pro": 5.0, "enterprise": 20.0}
            ),
            RateLimitType.MESSAGES_PER_MINUTE: RateLimitRule(
                limit_type=RateLimitType.MESSAGES_PER_MINUTE,
                max_requests=10,
                window_seconds=60,
                burst_allowance=2,
                tier_multipliers={"free": 1.0, "pro": 2.0, "enterprise": 5.0}
            ),
            RateLimitType.MESSAGES_PER_HOUR: RateLimitRule(
                limit_type=RateLimitType.MESSAGES_PER_HOUR,
                max_requests=100,
                window_seconds=3600,
                burst_allowance=10,
                tier_multipliers={"free": 1.0, "pro": 3.0, "enterprise": 10.0}
            ),
            RateLimitType.CONTEXT_FILES_PER_HOUR: RateLimitRule(
                limit_type=RateLimitType.CONTEXT_FILES_PER_HOUR,
                max_requests=500,
                window_seconds=3600,
                burst_allowance=20,
                tier_multipliers={"free": 1.0, "pro": 2.0, "enterprise": 5.0}
            ),
            RateLimitType.REPOSITORY_FETCHES_PER_DAY: RateLimitRule(
                limit_type=RateLimitType.REPOSITORY_FETCHES_PER_DAY,
                max_requests=50,
                window_seconds=86400,
                burst_allowance=5,
                tier_multipliers={"free": 1.0, "pro": 3.0, "enterprise": 10.0}
            ),
            RateLimitType.MODEL_SWITCHES_PER_HOUR: RateLimitRule(
                limit_type=RateLimitType.MODEL_SWITCHES_PER_HOUR,
                max_requests=20,
                window_seconds=3600,
                burst_allowance=5,
                tier_multipliers={"free": 1.0, "pro": 2.0, "enterprise": 5.0}
            )
        }
    
    @staticmethod
    def _get_staging_rules() -> Dict[RateLimitType, RateLimitRule]:
        """Staging rate limit rules (moderate)."""
        production_rules = RateLimitConfig._get_production_rules()
        
        # Increase limits by 50% for staging
        for rule in production_rules.values():
            rule.max_requests = int(rule.max_requests * 1.5)
            rule.burst_allowance = int(rule.burst_allowance * 1.5)
        
        return production_rules
    
    @staticmethod
    def _get_development_rules() -> Dict[RateLimitType, RateLimitRule]:
        """Development rate limit rules (lenient)."""
        production_rules = RateLimitConfig._get_production_rules()
        
        # Increase limits by 10x for development
        for rule in production_rules.values():
            rule.max_requests = rule.max_requests * 10
            rule.burst_allowance = rule.burst_allowance * 10
        
        return production_rules


class ValidationConfig:
    """Input validation configuration."""
    
    @staticmethod
    def get_validation_rules() -> Dict[str, Any]:
        """Get validation rules based on environment."""
        security_config = SecurityConfig.get_config()
        
        base_rules = {
            "max_message_length": 10000,
            "max_title_length": 200,
            "max_description_length": 1000,
            "max_url_length": 2048,
            "max_filename_length": 255,
            "max_file_path_length": 500,
            "max_context_files": 100,
            "allowed_file_extensions": security_config.allowed_file_types,
            "max_json_depth": 10,
            "max_array_length": 1000
        }
        
        if security_config.security_level == SecurityLevel.PRODUCTION:
            # Stricter limits for production
            base_rules.update({
                "max_message_length": 5000,
                "max_context_files": 50,
                "max_json_depth": 5,
                "max_array_length": 500
            })
        elif security_config.security_level == SecurityLevel.DEVELOPMENT:
            # More lenient limits for development
            base_rules.update({
                "max_message_length": 50000,
                "max_context_files": 500,
                "max_json_depth": 20,
                "max_array_length": 5000
            })
        
        return base_rules


class AuditConfig:
    """Audit logging configuration."""
    
    @staticmethod
    def get_audit_config() -> Dict[str, Any]:
        """Get audit configuration based on environment."""
        security_config = SecurityConfig.get_config()
        
        return {
            "enabled": security_config.audit_logging_enabled,
            "retention_days": security_config.audit_retention_days,
            "log_level": "INFO" if security_config.security_level == SecurityLevel.PRODUCTION else "DEBUG",
            "include_request_body": security_config.security_level != SecurityLevel.PRODUCTION,
            "include_response_body": False,  # Never log response bodies for security
            "sensitive_fields": [
                "password", "token", "key", "secret", "credential",
                "access_token", "refresh_token", "api_key", "private_key"
            ],
            "alert_events": [
                "login_failure", "access_denied", "abuse_detected",
                "security_violation", "suspicious_activity", "permission_escalation"
            ],
            "high_priority_events": [
                "system_error", "configuration_change", "user_deleted", "tier_changed"
            ]
        }


# Global security configuration instance
security_config = SecurityConfig.get_config()
rate_limit_config = RateLimitConfig.get_rate_limit_rules()
validation_config = ValidationConfig.get_validation_rules()
audit_config = AuditConfig.get_audit_config()