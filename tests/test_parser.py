"""Unit tests for job listing parser."""
import pytest
from datetime import datetime

from app.scraper.parser import JobListingParser, ParsedJob, SelectorConfig


class TestJobListingParser:
    """Tests for JobListingParser."""
    
    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return JobListingParser()
    
    def test_clean_text(self, parser):
        """Test text cleaning."""
        dirty = "  Hello   \n\n  World  \t  "
        clean = parser._clean_text(dirty)
        
        assert clean == "Hello World"
    
    def test_clean_text_empty(self, parser):
        """Test cleaning empty text."""
        assert parser._clean_text("") == ""
        assert parser._clean_text(None) == ""
    
    def test_parse_date_text_days_ago(self, parser):
        """Test parsing 'X days ago' dates."""
        result = parser._parse_date_text("Posted 3 days ago")
        
        assert result is not None
        assert (datetime.now() - result).days == 3
    
    def test_parse_date_text_hours_ago(self, parser):
        """Test parsing 'X hours ago' dates."""
        result = parser._parse_date_text("5 hours ago")
        
        assert result is not None
        assert (datetime.now() - result).total_seconds() < 6 * 3600
    
    def test_parse_date_text_weeks_ago(self, parser):
        """Test parsing 'X weeks ago' dates."""
        result = parser._parse_date_text("2 weeks ago")
        
        assert result is not None
        assert (datetime.now() - result).days >= 13
    
    def test_parse_date_text_invalid(self, parser):
        """Test parsing invalid date text."""
        result = parser._parse_date_text("sometime")
        
        assert result is None
    
    def test_check_closed_keywords_found(self, parser):
        """Test detecting closed keywords."""
        text = "This position is no longer accepting applications"
        
        assert parser.check_closed_keywords(text) is True
    
    def test_check_closed_keywords_not_found(self, parser):
        """Test when closed keywords not found."""
        text = "We are hiring! Apply now"
        
        assert parser.check_closed_keywords(text) is False
    
    def test_check_closed_keywords_empty(self, parser):
        """Test with empty text."""
        assert parser.check_closed_keywords("") is False
        assert parser.check_closed_keywords(None) is False
    
    def test_selector_config_defaults(self):
        """Test default selector configuration."""
        config = SelectorConfig(job_listing="div.jobs")
        
        assert config.job_listing == "div.jobs"
        assert config.job_title is not None
        assert config.job_url is not None
    
    def test_parsed_job_dataclass(self):
        """Test ParsedJob dataclass."""
        job = ParsedJob(
            job_title="Software Engineer",
            job_url="https://example.com/job",
            location="Remote",
        )
        
        assert job.job_title == "Software Engineer"
        assert job.location == "Remote"
        assert job.date_posted is None
        assert job.raw_data is None


class TestClosedIndicators:
    """Tests for closed job indicator patterns."""
    
    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return JobListingParser()
    
    @pytest.mark.parametrize("text,expected", [
        ("This job is no longer accepting applications", True),
        ("Position filled", True),
        ("Job expired", True),
        ("This role is no longer available", True),
        ("Application closed", True),
        ("We've filled this position", True),
        ("We are hiring", False),
        ("Apply now", False),
        ("Join our team", False),
    ])
    def test_closed_indicator_patterns(self, parser, text, expected):
        """Test various closed indicator patterns."""
        result = parser.check_closed_keywords(text)
        assert result == expected
