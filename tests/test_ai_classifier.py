"""Unit tests for AI job classifier."""
import pytest

from app.services.ai_classifier import (
    AIJobClassifier,
    JobStatusResult,
    ClassificationResult,
)


class TestKeywordFallback:
    """Tests for keyword-based fallback classification."""
    
    @pytest.fixture
    def classifier(self):
        """Create a classifier instance."""
        return AIJobClassifier()
    
    def test_closed_keywords_detected(self, classifier):
        """Test that closed keywords are detected."""
        text = "This position has been filled and we are no longer accepting applications."
        result = classifier._keyword_fallback(text)
        
        assert result.status == JobStatusResult.CLOSED
        assert result.method == "keyword_fallback"
    
    def test_open_keywords_detected(self, classifier):
        """Test that open keywords are detected."""
        text = "We are hiring! Apply now to join our team. We're accepting applications."
        result = classifier._keyword_fallback(text)
        
        assert result.status == JobStatusResult.OPEN
        assert result.method == "keyword_fallback"
        assert result.confidence > 0.5
    
    def test_mixed_keywords_uses_counts(self, classifier):
        """Test that keyword counts determine result."""
        # More open indicators
        text = """
        Apply now! Submit your application today.
        We are hiring and looking for talented people.
        Open positions available.
        """
        result = classifier._keyword_fallback(text)
        
        assert result.status == JobStatusResult.OPEN
    
    def test_insufficient_content(self, classifier):
        """Test handling of insufficient content."""
        text = "Job"
        result = classifier._keyword_fallback(text)
        
        # With short text, may not find enough keywords
        assert result.status in [JobStatusResult.OPEN, JobStatusResult.CLOSED, JobStatusResult.UNKNOWN]
    
    def test_closed_indicators(self, classifier):
        """Test all closed indicators are recognized."""
        closed_texts = [
            "This position is no longer accepting applications",
            "The position is filled and no longer available",
            "Job expired and removed from site",
            "This role is no longer available",
            "Application closed for this position",
            "We've filled this position",
            "This position has been closed",
            "Hiring has been completed for this role",
        ]
        
        for text in closed_texts:
            result = classifier._keyword_fallback(text)
            assert result.status == JobStatusResult.CLOSED, f"Failed for: {text}"
    
    def test_open_indicators(self, classifier):
        """Test all open indicators are recognized."""
        open_texts = [
            "Apply now",
            "Submit your application",
            "Join our team",
            "We're hiring",
            "Open positions",
            "Apply today",
        ]
        
        for text in open_texts:
            result = classifier._keyword_fallback(text)
            assert result.status == JobStatusResult.OPEN, f"Failed for: {text}"


class TestAIResponseParsing:
    """Tests for AI response parsing."""
    
    @pytest.fixture
    def classifier(self):
        """Create a classifier instance."""
        return AIJobClassifier()
    
    def test_parse_open_response(self, classifier):
        """Test parsing 'open' from AI response."""
        response = "open"
        result = classifier._parse_ai_response(response, "test")
        
        assert result.status == JobStatusResult.OPEN
        assert result.confidence == 0.85
    
    def test_parse_closed_response(self, classifier):
        """Test parsing 'closed' from AI response."""
        response = "closed"
        result = classifier._parse_ai_response(response, "test")
        
        assert result.status == JobStatusResult.CLOSED
        assert result.confidence == 0.85
    
    def test_parse_closed_in_context(self, classifier):
        """Test parsing when 'closed' appears in context."""
        response = "The job is not closed anymore, it's open now."
        result = classifier._parse_ai_response(response, "test")
        
        # Should be open since context indicates job opened
        assert result.status == JobStatusResult.OPEN
    
    def test_parse_unclear_response(self, classifier):
        """Test parsing unclear AI response."""
        response = "maybe, perhaps, uncertain"
        result = classifier._parse_ai_response(response, "test")
        
        assert result.status == JobStatusResult.UNKNOWN
        assert result.confidence == 0.0


class TestBuildPrompt:
    """Tests for prompt building."""
    
    @pytest.fixture
    def classifier(self):
        """Create a classifier instance."""
        return AIJobClassifier()
    
    def test_prompt_truncation(self, classifier):
        """Test that long text is truncated."""
        long_text = "Job description. " * 500  # Very long text
        prompt = classifier._build_prompt(long_text)
        
        # Text should be truncated to ~2000 chars
        assert len(prompt) < 5000
    
    def test_prompt_structure(self, classifier):
        """Test prompt has correct structure."""
        text = "Test job description"
        prompt = classifier._build_prompt(text)
        
        assert "Analyze the following job posting" in prompt
        assert text in prompt
        assert "Status:" in prompt
        assert "open" in prompt.lower()
        assert "closed" in prompt.lower()


@pytest.mark.asyncio
class TestClassifierIntegration:
    """Integration tests for the classifier."""
    
    @pytest.fixture
    def classifier(self):
        """Create a classifier instance."""
        return AIJobClassifier()
    
    async def test_classify_short_text(self, classifier):
        """Test classification with insufficient text."""
        result = await classifier.classify_job_status("Job")
        
        assert result.status == JobStatusResult.UNKNOWN
        assert result.confidence == 0.0
        assert result.method == "insufficient_content"
    
    async def test_classify_with_fallback(self, classifier):
        """Test classification uses fallback when AI unavailable."""
        # Disable AI by setting provider to something that won't work
        classifier.settings.ai.provider = "nonexistent"
        
        result = await classifier.classify_job_status(
            "This job is closed and no longer accepting applications. "
            "The position has been filled."
        )
        
        # Should fall back to keyword detection
        assert result.method == "keyword_fallback"
        assert result.status == JobStatusResult.CLOSED
