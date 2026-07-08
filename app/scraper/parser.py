"""Flexible job listing parser with multiple parsing strategies."""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Callable
from urllib.parse import urljoin

from playwright.async_api import Page, ElementHandle

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedJob:
    """Represents a parsed job listing."""
    job_title: str
    job_url: str
    location: Optional[str] = None
    date_posted: Optional[datetime] = None
    description_preview: Optional[str] = None
    raw_data: Optional[dict] = None


@dataclass
class SelectorConfig:
    """Configuration for CSS selectors."""
    job_listing: str
    job_title: str = "[data-testid='job-title'], h2, h3, a.job-link"
    job_url: str = "a[href*='job'], a[href*='career'], a"
    job_location: str = "[class*='location'], [class*='city'], [class*='remote']"
    job_date: str = "[class*='date'], [class*='posted'], time"
    description: str = "[class*='description'], [class*='summary'], p"


class JobListingParser:
    """Flexible parser for job listings with multiple strategies."""
    
    # Common patterns for closed/expired jobs
    CLOSED_PATTERNS = [
        r'no longer accepting applications',
        r'position filled',
        r'job expired',
        r'this role is no longer available',
        r'application closed',
        r'we\'ve filled this position',
        r'this position has been closed',
        r'job posting expired',
        r'n\.o\. longer available',
    ]
    
    def __init__(self, selector_config: Optional[SelectorConfig] = None):
        self.config = selector_config or self._get_default_config()
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.CLOSED_PATTERNS
        ]
    
    def _get_default_config(self) -> SelectorConfig:
        """Get default selector configuration."""
        return SelectorConfig(
            job_listing=self._detect_job_listing_selector(),
        )
    
    def _detect_job_listing_selector(self) -> str:
        """Common selectors for job listing containers."""
        return (
            "[data-job-id], "           # Common data attribute
            "[class*='job-card'], "      # Job card class
            "[class*='job-listing'], "   # Job listing class
            "[class*='job posting'], "   # Job posting class
            "article.job, "              # Article element
            "div[data-id*='job'], "       # Data ID with job
            "li.job-item, "              # List item job
            ".job, "                     # Generic job class
            "a[href*='/jobs/']"          # Links with /jobs/ path
        )
    
    async def parse_listings(self, page: Page, base_url: str) -> List[ParsedJob]:
        """Parse all job listings from the page."""
        jobs = []
        
        # Try different strategies to find job listings
        listing_elements = await self._find_listing_elements(page)
        
        if not listing_elements:
            logger.warning(f"No job listings found on {base_url}")
            return jobs
        
        logger.info(f"Found {len(listing_elements)} potential job listings")
        
        for element in listing_elements:
            try:
                job = await self._parse_single_listing(element, base_url)
                if job and job.job_title and job.job_url:
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"Failed to parse listing element: {e}")
                continue
        
        return jobs
    
    async def _find_listing_elements(self, page: Page) -> List[ElementHandle]:
        """Find job listing elements using multiple strategies."""
        # Strategy 1: Try common job listing selectors
        selectors = self.config.job_listing.split(", ")
        
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                if elements:
                    logger.info(f"Found {len(elements)} elements with selector: {selector}")
                    return elements
            except Exception:
                continue
        
        # Strategy 2: Find all links that look like job postings
        job_links = await page.query_selector_all(
            "a[href*='job'], a[href*='career'], a[href*='position']"
        )
        if job_links:
            # Wrap in a container-like structure
            return job_links
        
        # Strategy 3: Look for structured data (JSON-LD)
        structured_data = await page.evaluate("""() => {
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            const jobs = [];
            for (const script of scripts) {
                try {
                    const data = JSON.parse(script.textContent);
                    if (data['@type'] === 'JobPosting' || 
                        (Array.isArray(data) && data.some(d => d['@type'] === 'JobPosting'))) {
                        jobs.push(data);
                    }
                } catch (e) {}
            }
            return jobs;
        }""")
        
        if structured_data:
            logger.info("Found JSON-LD structured data")
            # Convert to ParsedJob objects
            return [self._parse_structured_job(sd) for sd in structured_data]
        
        return []
    
    def _parse_structured_job(self, data: dict) -> Optional[ParsedJob]:
        """Parse a job from JSON-LD structured data."""
        try:
            if isinstance(data, list):
                data = data[0] if data else {}
            
            date_posted = None
            if data.get("datePosted"):
                try:
                    date_posted = datetime.fromisoformat(
                        data["datePosted"].replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass
            
            return ParsedJob(
                job_title=data.get("title", ""),
                job_url=data.get("url", "") or data.get("identifier", {}).get("value", ""),
                location=data.get("jobLocation", {}).get("address", {}).get("addressLocality", ""),
                date_posted=date_posted,
                description_preview=data.get("description", "")[:500] if data.get("description") else None,
                raw_data=data,
            )
        except Exception as e:
            logger.error(f"Failed to parse structured job data: {e}")
            return None
    
    async def _parse_single_listing(
        self, 
        element: ElementHandle, 
        base_url: str
    ) -> Optional[ParsedJob]:
        """Parse a single job listing element."""
        # Try to extract job title
        job_title = await self._extract_text(element, self.config.job_title)
        if not job_title:
            job_title = await self._extract_text(element, "h1, h2, h3, h4")
        
        # Extract job URL
        job_url = await self._extract_href(element, self.config.job_url)
        if not job_url:
            job_url = await element.get_attribute("href")
        
        # Make URL absolute
        if job_url and not job_url.startswith(("http://", "https://")):
            job_url = urljoin(base_url, job_url)
        
        # Extract location
        location = await self._extract_text(element, self.config.job_location)
        
        # Extract date
        date_posted = await self._extract_date(element, self.config.job_date)
        
        # Extract description preview
        description_preview = await self._extract_text(element, self.config.description)
        
        if job_title:
            job_title = self._clean_text(job_title)
        
        return ParsedJob(
            job_title=job_title or "Unknown Position",
            job_url=job_url or "",
            location=location,
            date_posted=date_posted,
            description_preview=description_preview[:500] if description_preview else None,
        )
    
    async def _extract_text(self, element: ElementHandle, selector: str) -> Optional[str]:
        """Extract text content from an element or its children."""
        try:
            child = await element.query_selector(selector)
            if child:
                text = await child.text_content()
                return self._clean_text(text) if text else None
            
            # Try self
            text = await element.text_content()
            return self._clean_text(text) if text else None
        except Exception:
            return None
    
    async def _extract_href(self, element: ElementHandle, selector: str) -> Optional[str]:
        """Extract href from an anchor element."""
        try:
            # Try to find anchor within the element
            anchor = await element.query_selector("a")
            if anchor:
                href = await anchor.get_attribute("href")
                if href:
                    return href
            
            # Try self if it's an anchor
            if await element.evaluate("el => el.tagName === 'A'"):
                return await element.get_attribute("href")
            
            return None
        except Exception:
            return None
    
    async def _extract_date(self, element: ElementHandle, selector: str) -> Optional[datetime]:
        """Extract and parse date from element."""
        try:
            date_elem = await element.query_selector(selector)
            if date_elem:
                # Check for datetime attribute
                datetime_attr = await date_elem.get_attribute("datetime")
                if datetime_attr:
                    try:
                        return datetime.fromisoformat(datetime_attr.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                
                # Try to parse text content
                text = await date_elem.text_content()
                if text:
                    return self._parse_date_text(text)
            
            return None
        except Exception:
            return None
    
    def _parse_date_text(self, text: str) -> Optional[datetime]:
        """Parse date from text like '2 days ago', 'Posted Jan 15', etc."""
        text = text.strip().lower()
        
        # Try relative dates
        from datetime import timedelta
        
        now = datetime.now()
        relative_patterns = [
            (r'(\d+)\s*day[s]?\s*ago', lambda m: timedelta(days=int(m.group(1)))),
            (r'(\d+)\s*hour[s]?\s*ago', lambda m: timedelta(hours=int(m.group(1)))),
            (r'(\d+)\s*week[s]?\s*ago', lambda m: timedelta(weeks=int(m.group(1)))),
            (r'(\d+)\s*month[s]?\s*ago', lambda m: timedelta(days=int(m.group(1)) * 30)),
        ]
        
        for pattern, delta_func in relative_patterns:
            match = re.search(pattern, text)
            if match:
                delta = delta_func(match)
                return now - delta
        
        # Try to parse "Posted X" format
        posted_match = re.search(r'posted\s+(.+)', text)
        if posted_match:
            date_str = posted_match.group(1).strip()
            for fmt in ['%b %d', '%B %d', '%Y-%m-%d', '%m/%d/%Y']:
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    if parsed.year == 1900:
                        parsed = parsed.replace(year=now.year)
                    return parsed
                except ValueError:
                    continue
        
        return None
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content."""
        if not text:
            return ""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def check_closed_keywords(self, text: str) -> bool:
        """Check if text contains closed job keywords."""
        if not text:
            return False
        text = text.lower()
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True
        return False
