"""
Input and Confirmation Automation for Cosmos Integration
Provides automatic responses for confirmations and various input types
"""
import re
import os
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)

class InputType(Enum):
    """Types of input requests that Cosmos might generate"""
    CONFIRMATION = "confirmation"
    YES_NO = "yes_no"
    TOKEN_INPUT = "token_input"
    FILE_PATH = "file_path"
    NUMBER_SELECTION = "number_selection"
    TEXT_INPUT = "text_input"
    OPTIONAL_INPUT = "optional_input"
    DANGEROUS_CONFIRMATION = "dangerous_confirmation"

@dataclass
class InputRule:
    """Rule for handling specific input types"""
    pattern: str
    input_type: InputType
    default_response: str
    skip_if_optional: bool = False
    requires_context: bool = False
    description: str = ""

@dataclass
class AutomatedInput:
    """Result of automated input processing"""
    response: str
    input_type: InputType
    confidence: float
    skipped: bool = False
    reasoning: str = ""
    original_prompt: str = ""

class InputAutomation:
    """
    Handles automatic responses for confirmations and various input types.
    
    This class provides intelligent default responses for different types of
    input requests from Cosmos, including confirmations, token requests,
    and optional prompts.
    """
    
    def __init__(self, context: Dict[str, Any] = None):
        """
        Initialize the input automation handler.
        
        Args:
            context: Current context including user preferences, tokens, etc.
        """
        self.context = context or {}
        self.input_log = []  # Track all automated inputs for debugging
        self.input_rules = self._initialize_input_rules()
        
        logger.info("InputAutomation initialized")
    
    def _initialize_input_rules(self) -> List[InputRule]:
        """Initialize the input rules for different types of prompts"""
        return [
            # Confirmation rules (safe operations)
            InputRule(
                pattern=r"continue.*\?",
                input_type=InputType.CONFIRMATION,
                default_response="y",
                description="Continue operation confirmation"
            ),
            InputRule(
                pattern=r"proceed.*\?",
                input_type=InputType.CONFIRMATION,
                default_response="y",
                description="Proceed with operation confirmation"
            ),
            InputRule(
                pattern=r"are you sure.*\?",
                input_type=InputType.CONFIRMATION,
                default_response="y",
                description="General confirmation"
            ),
            InputRule(
                pattern=r"confirm.*\?",
                input_type=InputType.CONFIRMATION,
                default_response="y",
                description="Explicit confirmation request"
            ),
            
            # Dangerous confirmation rules (operations that might cause data loss)
            InputRule(
                pattern=r"delete.*\?",
                input_type=InputType.DANGEROUS_CONFIRMATION,
                default_response="n",
                description="Delete operation - default to no"
            ),
            InputRule(
                pattern=r"remove.*\?",
                input_type=InputType.DANGEROUS_CONFIRMATION,
                default_response="n",
                description="Remove operation - default to no"
            ),
            InputRule(
                pattern=r"overwrite.*\?",
                input_type=InputType.DANGEROUS_CONFIRMATION,
                default_response="n",
                description="Overwrite operation - default to no"
            ),
            InputRule(
                pattern=r"reset.*\?",
                input_type=InputType.DANGEROUS_CONFIRMATION,
                default_response="n",
                description="Reset operation - default to no"
            ),
            
            # Yes/No rules
            InputRule(
                pattern=r"\(y/n\)|\(yes/no\)",
                input_type=InputType.YES_NO,
                default_response="y",
                description="General yes/no prompt - default to yes"
            ),
            
            # Token input rules
            InputRule(
                pattern=r"github token",
                input_type=InputType.TOKEN_INPUT,
                default_response="",
                skip_if_optional=True,
                requires_context=True,
                description="GitHub token request"
            ),
            InputRule(
                pattern=r"api key",
                input_type=InputType.TOKEN_INPUT,
                default_response="",
                skip_if_optional=True,
                requires_context=True,
                description="API key request"
            ),
            InputRule(
                pattern=r"access token",
                input_type=InputType.TOKEN_INPUT,
                default_response="",
                skip_if_optional=True,
                requires_context=True,
                description="Access token request"
            ),
            
            # Number selection rules
            InputRule(
                pattern=r"select.*\(1-\d+\)",
                input_type=InputType.NUMBER_SELECTION,
                default_response="1",
                description="Number selection - default to first option"
            ),
            InputRule(
                pattern=r"choose.*\(1-\d+\)",
                input_type=InputType.NUMBER_SELECTION,
                default_response="1",
                description="Choice selection - default to first option"
            ),
            
            # File path rules
            InputRule(
                pattern=r"enter.*path",
                input_type=InputType.FILE_PATH,
                default_response=".",
                description="File path request - default to current directory"
            ),
            InputRule(
                pattern=r"file.*location",
                input_type=InputType.FILE_PATH,
                default_response=".",
                description="File location request - default to current directory"
            ),
            
            # Optional input rules
            InputRule(
                pattern=r"optional.*\(.*\)",
                input_type=InputType.OPTIONAL_INPUT,
                default_response="",
                skip_if_optional=True,
                description="Optional input - skip"
            ),
            InputRule(
                pattern=r"\(optional\)",
                input_type=InputType.OPTIONAL_INPUT,
                default_response="",
                skip_if_optional=True,
                description="Optional input marker - skip"
            )
        ]
    
    def handle_input_request(self, prompt: str, context: Dict[str, Any] = None) -> str:
        """
        Handle an input request and provide automatic response.
        
        Args:
            prompt: The input prompt from Cosmos
            context: Additional context for the input request
            
        Returns:
            Automatic response string
        """
        # Merge context
        merged_context = {**self.context, **(context or {})}
        
        # Process the input request
        automated_input = self._process_input_request(prompt, merged_context)
        
        # Log the automated input
        self._log_automated_input(automated_input)
        
        # Return response or empty string if skipped
        if automated_input.skipped:
            logger.info("Input request skipped",
                       prompt=prompt[:100],
                       reasoning=automated_input.reasoning)
            return ""
        
        logger.info("Automated input response generated",
                   prompt=prompt[:100],
                   response=automated_input.response,
                   input_type=automated_input.input_type.value,
                   confidence=automated_input.confidence)
        
        return automated_input.response
    
    def _process_input_request(self, prompt: str, context: Dict[str, Any]) -> AutomatedInput:
        """
        Process an input request and determine the appropriate response.
        
        Args:
            prompt: The input prompt
            context: Merged context for processing
            
        Returns:
            AutomatedInput object with response details
        """
        normalized_prompt = prompt.lower().strip()
        
        # Find matching rule
        best_match = None
        highest_confidence = 0.0
        
        for rule in self.input_rules:
            if re.search(rule.pattern, normalized_prompt, re.IGNORECASE):
                # Calculate confidence based on pattern specificity
                confidence = len(rule.pattern) / max(len(normalized_prompt), 1)
                confidence = min(confidence, 1.0)  # Cap at 1.0
                
                if confidence > highest_confidence:
                    highest_confidence = confidence
                    best_match = rule
        
        if not best_match:
            # No specific rule found - provide safe default
            return AutomatedInput(
                response="",
                input_type=InputType.TEXT_INPUT,
                confidence=0.1,
                reasoning="No specific rule matched - using empty response",
                original_prompt=prompt
            )
        
        # Apply rule logic
        return self._apply_input_rule(best_match, prompt, context, highest_confidence)
    
    def _apply_input_rule(self, rule: InputRule, prompt: str, context: Dict[str, Any], confidence: float) -> AutomatedInput:
        """
        Apply a specific input rule to generate response.
        
        Args:
            rule: The matched input rule
            prompt: Original prompt
            context: Current context
            confidence: Confidence score for the match
            
        Returns:
            AutomatedInput object with response
        """
        # Check if this is an optional input that should be skipped
        if rule.skip_if_optional and self._is_optional_prompt(prompt):
            return AutomatedInput(
                response="",
                input_type=rule.input_type,
                confidence=confidence,
                skipped=True,
                reasoning=f"Skipped optional input: {rule.description}",
                original_prompt=prompt
            )
        
        # Handle context-dependent rules
        if rule.requires_context:
            response = self._handle_context_dependent_input(rule, prompt, context)
        else:
            response = rule.default_response
        
        return AutomatedInput(
            response=response,
            input_type=rule.input_type,
            confidence=confidence,
            reasoning=rule.description,
            original_prompt=prompt
        )
    
    def _handle_context_dependent_input(self, rule: InputRule, prompt: str, context: Dict[str, Any]) -> str:
        """
        Handle input that depends on context (like tokens).
        
        Args:
            rule: The input rule
            prompt: Original prompt
            context: Current context
            
        Returns:
            Context-aware response
        """
        if rule.input_type == InputType.TOKEN_INPUT:
            return self._handle_token_input(prompt, context)
        
        # Default to rule's default response
        return rule.default_response
    
    def _handle_token_input(self, prompt: str, context: Dict[str, Any]) -> str:
        """
        Handle token input requests (GitHub tokens, API keys, etc.).
        
        Args:
            prompt: Token input prompt
            context: Current context
            
        Returns:
            Token value or empty string
        """
        normalized_prompt = prompt.lower()
        
        # GitHub token handling
        if "github" in normalized_prompt:
            # Check context for GitHub token
            github_token = context.get("github_token") or os.environ.get("GITHUB_TOKEN")
            if github_token:
                logger.info("Using GitHub token from context/environment")
                return github_token
            else:
                logger.info("No GitHub token available - skipping")
                return ""
        
        # API key handling
        if "api key" in normalized_prompt:
            # Check for various API key environment variables
            api_keys = [
                os.environ.get("OPENAI_API_KEY"),
                os.environ.get("ANTHROPIC_API_KEY"),
                os.environ.get("GOOGLE_API_KEY"),
                context.get("api_key")
            ]
            
            for key in api_keys:
                if key:
                    logger.info("Using API key from context/environment")
                    return key
            
            logger.info("No API key available - skipping")
            return ""
        
        # Default: skip token input
        logger.info("Unknown token type - skipping")
        return ""
    
    def _is_optional_prompt(self, prompt: str) -> bool:
        """
        Check if a prompt is optional based on various indicators.
        
        Args:
            prompt: The prompt to check
            
        Returns:
            True if the prompt appears to be optional
        """
        optional_indicators = [
            "(optional)",
            "optional:",
            "skip",
            "press enter to skip",
            "leave blank",
            "not required"
        ]
        
        normalized_prompt = prompt.lower()
        return any(indicator in normalized_prompt for indicator in optional_indicators)
    
    def handle_confirmation(self, question: str, context: Dict[str, Any] = None) -> bool:
        """
        Handle a confirmation question and return boolean response.
        
        Args:
            question: The confirmation question
            context: Additional context
            
        Returns:
            Boolean confirmation response
        """
        response = self.handle_input_request(question, context)
        
        # Convert response to boolean
        if response.lower() in ['y', 'yes', '1', 'true']:
            return True
        elif response.lower() in ['n', 'no', '0', 'false']:
            return False
        else:
            # Default to True for confirmations unless it's dangerous
            normalized_question = question.lower()
            dangerous_keywords = ['delete', 'remove', 'overwrite', 'reset', 'destroy']
            
            if any(keyword in normalized_question for keyword in dangerous_keywords):
                logger.info("Dangerous operation detected - defaulting to False")
                return False
            else:
                logger.info("Safe operation - defaulting to True")
                return True
    
    def _log_automated_input(self, automated_input: AutomatedInput):
        """
        Log the automated input for debugging and monitoring.
        
        Args:
            automated_input: The automated input to log
        """
        log_entry = {
            "timestamp": logger._context.get("timestamp"),
            "prompt": automated_input.original_prompt[:200],  # Truncate long prompts
            "response": automated_input.response,
            "input_type": automated_input.input_type.value,
            "confidence": automated_input.confidence,
            "skipped": automated_input.skipped,
            "reasoning": automated_input.reasoning
        }
        
        self.input_log.append(log_entry)
        
        # Keep only last 100 entries to prevent memory issues
        if len(self.input_log) > 100:
            self.input_log = self.input_log[-100:]
    
    def update_context(self, new_context: Dict[str, Any]):
        """
        Update the context for better input handling.
        
        Args:
            new_context: New context to merge
        """
        self.context.update(new_context)
        logger.info("Input automation context updated")
    
    def get_input_log(self) -> List[Dict[str, Any]]:
        """
        Get the log of automated inputs for debugging.
        
        Returns:
            List of logged inputs
        """
        return self.input_log.copy()
    
    def clear_input_log(self):
        """Clear the input log."""
        self.input_log.clear()
        logger.info("Input log cleared")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about automated inputs.
        
        Returns:
            Dictionary with input statistics
        """
        if not self.input_log:
            return {"total_inputs": 0}
        
        input_type_counts = {}
        skipped_count = 0
        total_confidence = 0.0
        
        for entry in self.input_log:
            input_type = entry["input_type"]
            input_type_counts[input_type] = input_type_counts.get(input_type, 0) + 1
            
            if entry["skipped"]:
                skipped_count += 1
            
            total_confidence += entry["confidence"]
        
        return {
            "total_inputs": len(self.input_log),
            "skipped_inputs": skipped_count,
            "average_confidence": total_confidence / len(self.input_log),
            "input_type_distribution": input_type_counts,
            "skip_rate": skipped_count / len(self.input_log),
            "most_common_input_type": max(input_type_counts.items(), key=lambda x: x[1])[0] if input_type_counts else None
        }