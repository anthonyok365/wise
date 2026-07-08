"""Browser management for Playwright scraper."""
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from fake_useragent import UserAgent

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Global browser instance
_browser: Optional[Browser] = None
_playwright: Optional[Playwright] = None


class BrowserManager:
    """Manages Playwright browser instances with pooling support."""
    
    def __init__(self):
        self.settings = get_settings()
        self.ua = UserAgent()
    
    async def initialize(self) -> None:
        """Initialize Playwright and browser."""
        global _browser, _playwright
        if _playwright is None:
            _playwright = await async_playwright().start()
            logger.info("Playwright started")
        
        if _browser is None:
            _browser = await _playwright.chromium.launch(
                headless=self.settings.scraper.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                ]
            )
            logger.info("Browser launched")
    
    async def close(self) -> None:
        """Close browser and Playwright."""
        global _browser, _playwright
        if _browser is not None:
            await _browser.close()
            _browser = None
            logger.info("Browser closed")
        
        if _playwright is not None:
            await _playwright.stop()
            _playwright = None
            logger.info("Playwright stopped")
    
    def get_user_agent(self) -> str:
        """Get a random user agent string."""
        if self.settings.scraper.user_agent_rotation:
            return self.ua.random
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    async def create_context(self) -> BrowserContext:
        """Create a new browser context with randomized settings."""
        if _browser is None:
            await self.initialize()
        
        context = await _browser.new_context(
            user_agent=self.get_user_agent(),
            viewport={
                'width': self.settings.scraper.viewport_width,
                'height': self.settings.scraper.viewport_height,
            },
            locale='en-US',
            timezone_id='America/New_York',
            ignore_https_errors=True,
        )
        
        # Add extra headers
        await context.set_extra_http_headers({
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })
        
        return context
    
    @asynccontextmanager
    async def get_page(self):
        """Context manager for getting a page."""
        context = await self.create_context()
        page = await context.new_page()
        try:
            yield page
        finally:
            await page.close()
            await context.close()


async def get_browser() -> Browser:
    """Get or create the browser instance."""
    global _browser
    if _browser is None:
        manager = BrowserManager()
        await manager.initialize()
    return _browser


async def close_browser() -> None:
    """Close the browser."""
    manager = BrowserManager()
    await manager.close()
