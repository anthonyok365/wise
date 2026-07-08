"""AI-based job status classification service."""
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class JobStatusResult(str, Enum):
    """Result of job status classification."""
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    """Result of AI classification with confidence."""
    status: JobStatusResult
    confidence: float
    method: str  # "ai_ollama", "ai_huggingface", "keyword_fallback"
    reason: Optional[str] = None


class AIJobClassifier:
    """AI-based job status classifier with multiple providers."""
    
    # Keywords indicating a job is closed
    CLOSED_INDICATORS = [
        "no longer accepting applications",
        "position filled",
        "job expired",
        "this role is no longer available",
        "application closed",
        "we've filled this position",
        "this position has been closed",
        "job posting expired",
        "no longer available",
        "applications are closed",
        "hiring has been completed",
        "role has been filled",
        "job is closed",
        "position is no longer open",
        "this job has been filled",
        "unfortunately this role is no longer",
    ]
    
    # Keywords indicating a job is still open
    OPEN_INDICATORS = [
        "apply now",
        "submit your application",
        "join our team",
        "we're hiring",
        "open positions",
        "apply today",
        "apply before",
        "accepting applications",
        "now hiring",
        "apply online",
    ]
    
    def __init__(self):
        self.settings = get_settings()
        self._http_client: Optional[httpx.AsyncClient] = None
    
    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.settings.ai.request_timeout)
        return self._http_client
    
    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def classify_job_status(self, text: str) -> ClassificationResult:
        """
        Classify job status from page text.
        
        Tries providers in order:
        1. Ollama (if configured)
        2. HuggingFace (if configured)
        3. Keyword fallback (always available)
        """
        if not text or len(text.strip()) < 50:
            logger.debug("Text too short for classification")
            return ClassificationResult(
                status=JobStatusResult.UNKNOWN,
                confidence=0.0,
                method="insufficient_content",
            )
        
        # First try keyword-based detection as quick check
        keyword_result = self._keyword_fallback(text)
        if keyword_result.confidence > 0.8:
            logger.debug("Quick keyword check determined status")
            return keyword_result
        
        # Try Ollama
        if self.settings.ai.use_ollama:
            try:
                result = await self._classify_with_ollama(text)
                if result:
                    logger.info(f"Ollama classification: {result.status.value} (confidence: {result.confidence})")
                    return result
            except Exception as e:
                logger.warning(f"Ollama classification failed: {e}")
        
        # Try HuggingFace
        if self.settings.ai.huggingface_token:
            try:
                result = await self._classify_with_huggingface(text)
                if result:
                    logger.info(f"HuggingFace classification: {result.status.value} (confidence: {result.confidence})")
                    return result
            except Exception as e:
                logger.warning(f"HuggingFace classification failed: {e}")
        
        # Fall back to keywords
        logger.info("Using keyword fallback classification")
        return self._keyword_fallback(text)
    
    async def _classify_with_ollama(self, text: str) -> Optional[ClassificationResult]:
        """Classify using Ollama local model."""
        prompt = self._build_prompt(text)
        
        try:
            response = await self.http_client.post(
                f"{self.settings.ai.ollama_url}/api/generate",
                json={
                    "model": self.settings.ai.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 50,
                    },
                },
                timeout=60.0,
            )
            
            if response.status_code == 200:
                data = response.json()
                response_text = data.get("response", "").strip().lower()
                
                return self._parse_ai_response(response_text, "ai_ollama")
            
        except httpx.RequestError as e:
            logger.error(f"Ollama request error: {e}")
        
        return None
    
    async def _classify_with_huggingface(self, text: str) -> Optional[ClassificationResult]:
        """Classify using HuggingFace Inference API."""
        prompt = self._build_prompt(text)
        
        try:
            headers = {
                "Authorization": f"Bearer {self.settings.ai.huggingface_token}",
            }
            
            response = await self.http_client.post(
                "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2",
                headers=headers,
                json={
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": 50,
                        "temperature": 0.1,
                    },
                },
                timeout=self.settings.ai.request_timeout,
            )
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and data:
                    response_text = data[0].get("generated_text", "").strip().lower()
                else:
                    response_text = data.get("generated_text", "").strip().lower()
                
                return self._parse_ai_response(response_text, "ai_huggingface")
            
        except httpx.RequestError as e:
            logger.error(f"HuggingFace request error: {e}")
        
        return None
    
    def _build_prompt(self, text: str) -> str:
        """Build prompt for job status classification."""
        # Truncate text to first 2000 characters for efficiency
        truncated_text = text[:2000]
        
        return f"""Analyze the following job posting text and determine if it is still open or closed.

Rules:
- If the job is closed, expired, filled, or no longer accepting applications, respond with exactly: "closed"
- If the job is still open and accepting applications, respond with exactly: "open"
- Do not include any other text, explanation, or punctuation.

Job posting text:
---
{truncated_text}
---

Status:"""
    
    def _parse_ai_response(self, response: str, method: str) -> ClassificationResult:
        """Parse AI response to extract status."""
        response = response.strip().lower()
        
        # Look for "open" or "closed" in response
        if "closed" in response and "open" not in response:
            # Make sure it's not "not closed" or similar
            if "not closed" not in response and "isn't closed" not in response:
                return ClassificationResult(
                    status=JobStatusResult.CLOSED,
                    confidence=0.85,
                    method=method,
                )
        
        if "open" in response:
            return ClassificationResult(
                status=JobStatusResult.OPEN,
                confidence=0.85,
                method=method,
            )
        
        # Could not parse
        return ClassificationResult(
            status=JobStatusResult.UNKNOWN,
            confidence=0.0,
            method="parse_failed",
        )
    
    def _keyword_fallback(self, text: str) -> ClassificationResult:
        """Fallback to keyword-based classification."""
        text_lower = text.lower()
        
        # First check for explicit "closed" patterns (highest priority)
        explicit_closed_patterns = [
            r'no longer (accepting|open|available)',
            r'position\s+filled',
            r'job\s+expired',
            r'(is|has been|has)\s+(closed|filled)',
            r'role\s+(is\s+)?(no longer|not)\s+available',
            r'application\s+closed',
            r"we've\s+filled",
            r"we have\s+filled",
            r"hiring\s+(has\s+been\s+)?completed",
        ]
        
        import re
        explicit_closed_count = 0
        for pattern in explicit_closed_patterns:
            if re.search(pattern, text_lower):
                explicit_closed_count += 1
        
        if explicit_closed_count > 0:
            confidence = min(0.5 + explicit_closed_count * 0.2, 0.95)
            return ClassificationResult(
                status=JobStatusResult.CLOSED,
                confidence=confidence,
                method="keyword_fallback",
                reason=f"Found {explicit_closed_count} explicit closed indicators",
            )
        
        # Then check standard closed indicators
        closed_count = 0
        for indicator in self.CLOSED_INDICATORS:
            if indicator in text_lower:
                closed_count += 1
        
        # Check open indicators
        open_count = 0
        for indicator in self.OPEN_INDICATORS:
            if indicator in text_lower:
                open_count += 1
        
        # Determine status based on keyword counts
        if closed_count > open_count:
            confidence = min(0.5 + (closed_count - open_count) * 0.1, 0.9)
            return ClassificationResult(
                status=JobStatusResult.CLOSED,
                confidence=confidence,
                method="keyword_fallback",
                reason=f"Found {closed_count} closed indicators",
            )
        
        if open_count > closed_count:
            confidence = min(0.5 + (open_count - closed_count) * 0.1, 0.9)
            return ClassificationResult(
                status=JobStatusResult.OPEN,
                confidence=confidence,
                method="keyword_fallback",
                reason=f"Found {open_count} open indicators",
            )
        
        # Ambiguous - default to unknown
        return ClassificationResult(
            status=JobStatusResult.UNKNOWN,
            confidence=0.3,
            method="keyword_fallback",
            reason="No clear indicators found",
        )


# Global classifier instance
_classifier: Optional[AIJobClassifier] = None


def get_classifier() -> AIJobClassifier:
    """Get or create the global classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = AIJobClassifier()
    return _classifier


async def classify_job_status(text: str) -> ClassificationResult:
    """Convenience function to classify job status."""
    classifier = get_classifier()
    return await classifier.classify_job_status(text)
