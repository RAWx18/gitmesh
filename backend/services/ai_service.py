"""
AI Service for GitMesh

Simple AI service that integrates with the configured AI provider.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import httpx
from backend.config.unified_config import get_config

logger = logging.getLogger(__name__)


class AIService:
    """Simple AI service for chat functionality."""
    
    def __init__(self):
        self.config = get_config()
        self.client = httpx.AsyncClient(timeout=self.config.ai.timeout)
    
    async def generate_response(self, prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate AI response for the given prompt.
        
        Args:
            prompt: The user's message/prompt
            model: Optional model override
            
        Returns:
            Dict containing the AI response
        """
        try:
            provider = self.config.ai.provider.lower()
            api_key = self.config.get_ai_api_key()
            
            if not api_key:
                raise ValueError(f"No API key configured for provider: {provider}")
            
            if provider == "gemini":
                return await self._call_gemini(prompt, model or self.config.ai.default_model, api_key)
            else:
                raise ValueError(f"Unsupported AI provider: {provider}")
                
        except Exception as e:
            logger.error(f"AI service error: {e}")
            return {
                "content": f"I apologize, but I'm having trouble processing your request right now. Error: {str(e)}",
                "error": str(e)
            }
    
    async def _call_gemini(self, prompt: str, model: str, api_key: str) -> Dict[str, Any]:
        """Call Google Gemini API."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": api_key
            }
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": self.config.ai.temperature,
                    "maxOutputTokens": self.config.ai.max_tokens
                }
            }
            
            response = await self.client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            if "candidates" in data and len(data["candidates"]) > 0:
                content = data["candidates"][0]["content"]["parts"][0]["text"]
                return {
                    "content": content,
                    "model": model,
                    "provider": "gemini"
                }
            else:
                return {
                    "content": "I couldn't generate a response. Please try again.",
                    "error": "No candidates in response"
                }
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Gemini API HTTP error: {e}")
            return {
                "content": "I'm having trouble connecting to the AI service. Please try again later.",
                "error": f"HTTP {e.response.status_code}"
            }
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return {
                "content": "I encountered an error while processing your request.",
                "error": str(e)
            }
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# Global AI service instance
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get the global AI service instance."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service


async def close_ai_service():
    """Close the global AI service."""
    global _ai_service
    if _ai_service:
        await _ai_service.close()
        _ai_service = None