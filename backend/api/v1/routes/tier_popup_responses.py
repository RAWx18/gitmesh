"""
Standardized popup responses for tier-based access control.

This module provides consistent popup messages and responses for different
tier-related scenarios to ensure a good user experience.
"""

from typing import Dict, Any, Optional
from enum import Enum


class PopupType(Enum):
    """Types of tier-related popups."""
    REPOSITORY_TOO_LARGE = "repository_too_large"
    MONTHLY_LIMIT_EXCEEDED = "monthly_limit_exceeded"
    HOURLY_LIMIT_EXCEEDED = "hourly_limit_exceeded"
    MODEL_NOT_AVAILABLE = "model_not_available"
    CONTEXT_FILES_LIMIT = "context_files_limit"
    SESSION_LIMIT_EXCEEDED = "session_limit_exceeded"
    REPOSITORY_NOT_ANALYZED = "repository_not_analyzed"
    UPGRADE_REQUIRED = "upgrade_required"


class TierPopupGenerator:
    """Generator for tier-related popup messages and responses."""
    
    @staticmethod
    def repository_too_large_popup(
        current_tier: str,
        repository_tokens: int,
        tier_limit: int,
        repository_url: str
    ) -> Dict[str, Any]:
        """Generate popup for repository too large error."""
        
        # Determine upgrade path
        if current_tier == "personal":
            upgrade_tier = "Pro"
            upgrade_limit = "10M tokens"
        elif current_tier == "pro":
            upgrade_tier = "Enterprise"
            upgrade_limit = "custom limits"
        else:
            upgrade_tier = "Enterprise"
            upgrade_limit = "custom limits"
        
        return {
            "type": PopupType.REPOSITORY_TOO_LARGE.value,
            "title": "Repository Too Large",
            "message": (
                f"This repository ({repository_tokens:,} tokens) exceeds your "
                f"{current_tier.title()} plan limit of {tier_limit:,} tokens."
            ),
            "details": {
                "repository_url": repository_url,
                "repository_tokens": repository_tokens,
                "tier_limit": tier_limit,
                "current_tier": current_tier
            },
            "actions": [
                {
                    "type": "primary",
                    "label": f"Upgrade to {upgrade_tier}",
                    "action": "upgrade_tier",
                    "data": {"target_tier": upgrade_tier.lower()}
                },
                {
                    "type": "secondary",
                    "label": "Choose Different Repository",
                    "action": "select_repository"
                },
                {
                    "type": "tertiary",
                    "label": "Learn More",
                    "action": "learn_more",
                    "data": {"topic": "repository_limits"}
                }
            ],
            "upgrade_info": {
                "current_plan": current_tier.title(),
                "recommended_plan": upgrade_tier,
                "new_limit": upgrade_limit,
                "benefits": [
                    f"Access repositories up to {upgrade_limit}",
                    "More AI requests per month",
                    "Advanced AI models",
                    "Extended session duration"
                ]
            }
        }
    
    @staticmethod
    def monthly_limit_exceeded_popup(
        current_tier: str,
        requests_used: int,
        monthly_limit: int,
        reset_date: str
    ) -> Dict[str, Any]:
        """Generate popup for monthly request limit exceeded."""
        
        return {
            "type": PopupType.MONTHLY_LIMIT_EXCEEDED.value,
            "title": "Monthly AI Request Limit Reached",
            "message": (
                f"You've used all {monthly_limit:,} AI requests for your "
                f"{current_tier.title()} plan this month."
            ),
            "details": {
                "requests_used": requests_used,
                "monthly_limit": monthly_limit,
                "current_tier": current_tier,
                "reset_date": reset_date
            },
            "actions": [
                {
                    "type": "primary",
                    "label": "Upgrade Plan",
                    "action": "upgrade_tier"
                },
                {
                    "type": "secondary",
                    "label": "Wait for Reset",
                    "action": "close"
                },
                {
                    "type": "tertiary",
                    "label": "View Usage Details",
                    "action": "view_usage"
                }
            ],
            "usage_info": {
                "requests_used": requests_used,
                "monthly_limit": monthly_limit,
                "reset_date": reset_date,
                "percentage_used": round((requests_used / monthly_limit) * 100, 1) if monthly_limit > 0 else 100
            }
        }
    
    @staticmethod
    def repository_not_analyzed_popup(repository_url: str) -> Dict[str, Any]:
        """Generate popup for repository not analyzed by gitingest."""
        
        return {
            "type": PopupType.REPOSITORY_NOT_ANALYZED.value,
            "title": "Repository Analysis Required",
            "message": (
                "This repository hasn't been analyzed yet. Please run gitingest "
                "analysis before starting a chat session."
            ),
            "details": {
                "repository_url": repository_url,
                "reason": "no_gitingest_data"
            },
            "actions": [
                {
                    "type": "primary",
                    "label": "Analyze Repository",
                    "action": "analyze_repository",
                    "data": {"repository_url": repository_url}
                },
                {
                    "type": "secondary",
                    "label": "Choose Different Repository",
                    "action": "select_repository"
                }
            ],
            "help_info": {
                "title": "Why is analysis needed?",
                "description": (
                    "We analyze repositories to understand their size and structure, "
                    "ensuring they fit within your plan's limits and providing better "
                    "AI assistance."
                ),
                "steps": [
                    "Repository content is processed by gitingest",
                    "Token count and structure are calculated",
                    "Analysis is cached for future use",
                    "Chat sessions can then access the repository"
                ]
            }
        }
    
    @staticmethod
    def model_not_available_popup(
        requested_model: str,
        current_tier: str,
        available_models: list
    ) -> Dict[str, Any]:
        """Generate popup for model not available in current tier."""
        
        return {
            "type": PopupType.MODEL_NOT_AVAILABLE.value,
            "title": "AI Model Not Available",
            "message": (
                f"The {requested_model} model is not available in your "
                f"{current_tier.title()} plan."
            ),
            "details": {
                "requested_model": requested_model,
                "current_tier": current_tier,
                "available_models": available_models
            },
            "actions": [
                {
                    "type": "primary",
                    "label": "Upgrade Plan",
                    "action": "upgrade_tier"
                },
                {
                    "type": "secondary",
                    "label": "Use Available Model",
                    "action": "select_model",
                    "data": {"models": available_models}
                }
            ],
            "model_info": {
                "available_in_current_tier": available_models,
                "upgrade_benefits": [
                    "Access to advanced AI models",
                    "Better code understanding",
                    "More accurate responses",
                    "Enhanced capabilities"
                ]
            }
        }
    
    @staticmethod
    def generate_popup_response(
        popup_type: PopupType,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate appropriate popup response based on type and parameters."""
        
        if popup_type == PopupType.REPOSITORY_TOO_LARGE:
            return TierPopupGenerator.repository_too_large_popup(
                current_tier=kwargs.get("current_tier"),
                repository_tokens=kwargs.get("repository_tokens"),
                tier_limit=kwargs.get("tier_limit"),
                repository_url=kwargs.get("repository_url")
            )
        
        elif popup_type == PopupType.MONTHLY_LIMIT_EXCEEDED:
            return TierPopupGenerator.monthly_limit_exceeded_popup(
                current_tier=kwargs.get("current_tier"),
                requests_used=kwargs.get("requests_used"),
                monthly_limit=kwargs.get("monthly_limit"),
                reset_date=kwargs.get("reset_date", "next month")
            )
        
        elif popup_type == PopupType.REPOSITORY_NOT_ANALYZED:
            return TierPopupGenerator.repository_not_analyzed_popup(
                repository_url=kwargs.get("repository_url")
            )
        
        elif popup_type == PopupType.MODEL_NOT_AVAILABLE:
            return TierPopupGenerator.model_not_available_popup(
                requested_model=kwargs.get("requested_model"),
                current_tier=kwargs.get("current_tier"),
                available_models=kwargs.get("available_models", [])
            )
        
        else:
            # Generic popup for unhandled cases
            return {
                "type": "generic_error",
                "title": "Access Restricted",
                "message": kwargs.get("message", "This action is not available in your current plan."),
                "actions": [
                    {
                        "type": "primary",
                        "label": "Upgrade Plan",
                        "action": "upgrade_tier"
                    },
                    {
                        "type": "secondary",
                        "label": "Close",
                        "action": "close"
                    }
                ]
            }


def create_tier_popup_response(
    validation_result,
    repository_url: Optional[str] = None,
    repository_tokens: Optional[int] = None,
    **additional_data
) -> Dict[str, Any]:
    """
    Create a standardized popup response from a validation result.
    
    Args:
        validation_result: AccessValidationResult from tier validation
        repository_url: Repository URL (if applicable)
        repository_tokens: Repository token count (if applicable)
        **additional_data: Additional data for popup generation
    
    Returns:
        Standardized popup response dictionary
    """
    
    if not validation_result.allowed:
        # Determine popup type based on validation message
        message = validation_result.message.lower()
        
        if "repository size" in message and "exceeds" in message:
            return TierPopupGenerator.generate_popup_response(
                PopupType.REPOSITORY_TOO_LARGE,
                current_tier=validation_result.tier,
                repository_tokens=repository_tokens,
                tier_limit=validation_result.limits.max_repository_tokens if validation_result.limits else 0,
                repository_url=repository_url
            )
        
        elif "monthly" in message and "limit" in message:
            return TierPopupGenerator.generate_popup_response(
                PopupType.MONTHLY_LIMIT_EXCEEDED,
                current_tier=validation_result.tier,
                requests_used=validation_result.usage.get("used", 0) if validation_result.usage else 0,
                monthly_limit=validation_result.limits.max_requests_per_month if validation_result.limits else 0,
                **additional_data
            )
        
        elif "analysis not available" in message or "not been processed" in message:
            return TierPopupGenerator.generate_popup_response(
                PopupType.REPOSITORY_NOT_ANALYZED,
                repository_url=repository_url
            )
        
        else:
            # Generic error popup
            return {
                "type": "access_denied",
                "title": "Access Restricted",
                "message": validation_result.message,
                "tier": validation_result.tier,
                "actions": [
                    {
                        "type": "primary",
                        "label": "Upgrade Plan",
                        "action": "upgrade_tier"
                    },
                    {
                        "type": "secondary",
                        "label": "Close",
                        "action": "close"
                    }
                ]
            }
    
    # If validation passed, return success response
    return {
        "type": "success",
        "title": "Access Granted",
        "message": validation_result.message,
        "tier": validation_result.tier
    }