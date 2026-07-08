"""Main Playwright scraper for career pages."""
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.scraper.browser import BrowserManager
from app.scraper.parser import JobListingParser, ParsedJob, SelectorConfig

logger = get_logger(__name__)


class ScrapingError(Exception):
    """Custom exception for scraping errors."""
    pass


class CareerPageScraper:
    """Async Playwright scraper for career pages."""
    
    def __init__(
        self, 
        browser_manager: Optional[BrowserManager] = None,
        parser: Optional[JobListingParser] = None,
    ):
        self.settings = get_settings()
        self.browser_manager = browser_manager or BrowserManager()
        self.parser = parser or JobListingParser()
        self.session_cache: Dict[str, Dict[str, Any]] = {}
    
    async def initialize(self) -> None:
        """Initialize browser if not already initialized."""
        await self.browser_manager.initialize()
    
    async def close(self) -> None:
        """Close browser resources."""
        await self.browser_manager.close()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((PlaywrightTimeout, ScrapingError)),
    )
    async def scrape_career_page(
        self,
        url: str,
        selector_config: Optional[SelectorConfig] = None,
        max_pages: int = 5,
        scroll_pause: float = 2.0,
    ) -> List[ParsedJob]:
        """
        Scrape job listings from a career page.
        
        Args:
            url: The career page URL to scrape
            selector_config: Optional custom selector configuration
            max_pages: Maximum number of pagination pages to scrape
            scroll_pause: Seconds to wait between scroll actions
            
        Returns:
            List of parsed job listings
        """
        parser = JobListingParser(selector_config) if selector_config else self.parser
        
        try:
            await self.initialize()
        except Exception:
            pass
        
        all_jobs = []
        seen_urls = set()
        
        async with self.browser_manager.get_page() as page:
            try:
                # Set up page event handlers
                await self._setup_page_handlers(page)
                
                # Navigate to the page
                logger.info(f"Navigating to {url}")
                await page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=self.settings.scraper.navigation_timeout,
                )
                
                # Wait for dynamic content
                await asyncio.sleep(scroll_pause)
                
                # Initial scrape
                jobs = await parser.parse_listings(page, url)
                logger.info(f"Found {len(jobs)} jobs on first page")
                
                for job in jobs:
                    if job.job_url not in seen_urls:
                        seen_urls.add(job.job_url)
                        all_jobs.append(job)
                
                # Handle pagination
                if max_pages > 1:
                    for page_num in range(2, max_pages + 1):
                        # Try to find and click next page
                        has_next = await self._go_to_next_page(page, page_num, scroll_pause)
                        if not has_next:
                            break
                        
                        # Scrape this page
                        jobs = await parser.parse_listings(page, url)
                        logger.info(f"Found {len(jobs)} jobs on page {page_num}")
                        
                        for job in jobs:
                            if job.job_url not in seen_urls:
                                seen_urls.add(job.job_url)
                                all_jobs.append(job)
                
                # Deduplicate
                unique_jobs = self._deduplicate_jobs(all_jobs)
                logger.info(f"Total unique jobs: {len(unique_jobs)}")
                
                return unique_jobs
                
            except PlaywrightTimeout:
                logger.error(f"Timeout while scraping {url}")
                raise ScrapingError(f"Timeout scraping {url}")
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                raise ScrapingError(f"Error scraping {url}: {str(e)}")
        
        return all_jobs
    
    async def _setup_page_handlers(self, page: Page) -> None:
        """Set up page event handlers for logging."""
        page.on("console", lambda msg: logger.debug(f"Console {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: logger.error(f"Page error: {err}"))
    
    async def _go_to_next_page(
        self, 
        page: Page, 
        page_num: int,
        scroll_pause: float,
    ) -> bool:
        """Attempt to navigate to the next page."""
        try:
            # Strategy 1: Find and click "Next" button
            next_selectors = [
                "a[rel='next']",
                "a[data-testid*='next']",
                "button[data-testid*='next']",
                "a[class*='next']",
                "button[class*='next']",
                "a:has-text('Next')",
                "a:has-text('next')",
                "button:has-text('Next')",
                "[aria-label*='Next']",
                "[aria-label*='next page']",
            ]
            
            for selector in next_selectors:
                try:
                    next_btn = await page.query_selector(selector)
                    if next_btn:
                        is_disabled = await next_btn.get_attribute("disabled")
                        aria_disabled = await next_btn.get_attribute("aria-disabled")
                        
                        if is_disabled == "true" or aria_disabled == "true":
                            return False
                        
                        await next_btn.click()
                        await page.wait_for_load_state("networkidle", timeout=10000)
                        await asyncio.sleep(scroll_pause)
                        return True
                except Exception:
                    continue
            
            # Strategy 2: Look for pagination with specific page number
            page_link = await page.query_selector(f"a:has-text('{page_num}')")
            if page_link:
                await page_link.click()
                await page.wait_for_load_state("networkidle", timeout=10000)
                await asyncio.sleep(scroll_pause)
                return True
            
            # Strategy 3: Infinite scroll check
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(scroll_pause)
            
            # Check if new content loaded
            current_height = await page.evaluate("document.body.scrollHeight")
            return False
            
        except Exception as e:
            logger.debug(f"Failed to navigate to next page: {e}")
            return False
    
    def _deduplicate_jobs(self, jobs: List[ParsedJob]) -> List[ParsedJob]:
        """Remove duplicate jobs based on URL."""
        seen = set()
        unique_jobs = []
        
        for job in jobs:
            if job.job_url and job.job_url not in seen:
                seen.add(job.job_url)
                unique_jobs.append(job)
        
        return unique_jobs
    
    async def scrape_and_save_jobs(
        self,
        url: str,
        company_id: int,
        db_session,
        selector_config: Optional[SelectorConfig] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scrape jobs and prepare them for database storage.
        
        Returns list of job dictionaries ready for insertion.
        """
        jobs = await self.scrape_career_page(url, selector_config)
        
        job_dicts = []
        for job in jobs:
            job_dicts.append({
                "company_id": company_id,
                "job_title": job.job_title,
                "job_url": job.job_url,
                "location": job.location,
                "date_posted": job.date_posted,
                "description_preview": job.description_preview,
            })
        
        return job_dicts


class JobPageScraper:
    """Scraper for individual job detail pages."""
    
    def __init__(self, browser_manager: Optional[BrowserManager] = None):
        self.settings = get_settings()
        self.browser_manager = browser_manager or BrowserManager()
    
    async def get_job_page_text(self, url: str) -> str:
        """
        Get the full text content of a job page for AI classification.
        
        Returns:
            Extracted text content from the job page
        """
        try:
            await self.browser_manager.initialize()
        except Exception:
            pass
        
        async with self.browser_manager.get_page() as page:
            try:
                logger.info(f"Fetching job page: {url}")
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.settings.scraper.timeout,
                )
                
                # Wait a bit for dynamic content
                await asyncio.sleep(1.5)
                
                # Extract main content
                content = await page.evaluate("""() => {
                    // Remove script and style elements
                    const elements = document.querySelectorAll('script, style, nav, footer, header, aside');
                    elements.forEach(el => el.remove());
                    
                    // Get main content area if available
                    const main = document.querySelector('main, [role="main"], .job-content, .job-description, article');
                    if (main) {
                        return main.innerText;
                    }
                    
                    // Fall back to body
                    return document.body.innerText;
                }""")
                
                return content.strip()
                
            except Exception as e:
                logger.error(f"Error fetching job page {url}: {e}")
                return ""
    
    async def check_job_still_exists(self, url: str) -> bool:
        """
        Quick check if a job page still exists or returns 404.
        
        Returns:
            True if job page exists, False if not found
        """
        try:
            await self.browser_manager.initialize()
        except Exception:
            pass
        
        async with self.browser_manager.get_page() as page:
            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=10000,
                )
                
                # Check for 404 or similar
                if response and response.status in [404, 410, 403]:
                    return False
                
                # Check page content for "no longer available" messages
                page_text = await page.inner_text("body")
                
                closed_patterns = [
                    r'job no longer (exists|available)',
                    r'position (has been|is) (filled|closed)',
                    r'no longer accepting applications',
                    r'this role is (no longer|not) (available|accepting)',
                    r'we have filled this position',
                    r'404\s*page|page not found',
                ]
                
                import re
                for pattern in closed_patterns:
                    if re.search(pattern, page_text, re.IGNORECASE):
                        return False
                
                return True
                
            except Exception as e:
                logger.debug(f"Error checking job existence: {e}")
                return False
