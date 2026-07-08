"""Background tasks for periodic job scraping and validation."""
import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.database import get_db_context
from app.db.models import Company, Job, JobStatus, SiteConfig
from app.scraper.scraper import CareerPageScraper, JobPageScraper
from app.scraper.parser import SelectorConfig, JobListingParser
from app.services.ai_classifier import classify_job_status, JobStatusResult
from app.services.hiring_signal_engine import HiringSignalEngine, JobActivityTracker

logger = get_logger(__name__)


class ScraperTask:
    """Background task for scraping career pages."""
    
    def __init__(self):
        self.settings = get_settings()
        self.scraper = CareerPageScraper()
    
    async def run(self) -> dict:
        """Run the scraper task for all companies."""
        logger.info("Starting scraper task...")
        start_time = datetime.utcnow()
        
        total_jobs_found = 0
        companies_processed = 0
        errors = []
        
        async with get_db_context() as db:
            # Get all companies
            result = await db.execute(select(Company))
            companies = result.scalars().all()
            
            for company in companies:
                try:
                    jobs_found = await self._scrape_company(company, db)
                    total_jobs_found += jobs_found
                    companies_processed += 1
                    
                    # Rate limiting between companies
                    await asyncio.sleep(self.settings.scraper.delay_between_requests)
                    
                except Exception as e:
                    logger.error(f"Error scraping {company.company_name}: {e}")
                    errors.append({"company": company.company_name, "error": str(e)})
            
            # Update last_checked for all companies
            for company in companies:
                company.last_checked = datetime.utcnow()
            
            await db.commit()
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(
            f"Scraper task completed: {companies_processed} companies, "
            f"{total_jobs_found} jobs found in {elapsed:.2f}s"
        )
        
        return {
            "companies_processed": companies_processed,
            "total_jobs_found": total_jobs_found,
            "elapsed_seconds": elapsed,
            "errors": errors,
        }
    
    async def _scrape_company(self, company: Company, db: AsyncSession) -> int:
        """Scrape jobs from a single company."""
        logger.info(f"Scraping {company.company_name}...")
        
        # Get site configuration if exists
        config_result = await db.execute(
            select(SiteConfig).where(
                SiteConfig.company_id == company.id,
                SiteConfig.is_active == True
            )
        )
        site_config = config_result.scalar_one_or_none()
        
        # Build selector config
        selector_config = None
        if site_config:
            selector_config = SelectorConfig(
                job_listing=site_config.job_listing_selector or "",
                job_title=site_config.job_title_selector or "",
                job_url=site_config.job_url_selector or "",
                job_location=site_config.job_location_selector or "",
                job_date=site_config.job_date_selector or "",
            )
        
        # Scrape jobs
        jobs = await self.scraper.scrape_career_page(
            url=company.career_page_url,
            selector_config=selector_config,
            max_pages=3,
        )
        
        jobs_added = 0
        
        for parsed_job in jobs:
            # Check if job already exists
            existing_result = await db.execute(
                select(Job).where(Job.job_url == parsed_job.job_url)
            )
            existing_job = existing_result.scalar_one_or_none()
            
            if not existing_job:
                # Create new job
                job = Job(
                    company_id=company.id,
                    job_title=parsed_job.job_title,
                    job_url=parsed_job.job_url,
                    location=parsed_job.location,
                    date_posted=parsed_job.date_posted,
                    description_preview=parsed_job.description_preview,
                    status=JobStatus.UNKNOWN,
                )
                db.add(job)
                jobs_added += 1
                logger.debug(f"Added new job: {parsed_job.job_title}")
            else:
                # Update existing job if needed
                if parsed_job.job_title != existing_job.job_title:
                    existing_job.job_title = parsed_job.job_title
                if parsed_job.location and not existing_job.location:
                    existing_job.location = parsed_job.location
        
        # Update company job count
        count_result = await db.execute(
            select(Job).where(Job.company_id == company.id)
        )
        company.current_job_count = len(count_result.scalars().all())
        
        await db.commit()
        
        logger.info(f"Scraped {jobs_added} new jobs from {company.company_name}")
        
        return jobs_added
    
    async def cleanup(self):
        """Cleanup resources."""
        await self.scraper.close()


class JobValidatorTask:
    """Background task for validating job status."""
    
    def __init__(self):
        self.settings = get_settings()
        self.scraper = JobPageScraper()
        self.ai_classifier = None
    
    async def run(self, batch_size: int = 50) -> dict:
        """Run the validator task for jobs."""
        logger.info("Starting job validator task...")
        start_time = datetime.utcnow()
        
        validated_count = 0
        closed_count = 0
        errors = []
        
        async with get_db_context() as db:
            # Get jobs that need validation (unknown or old open status)
            query = (
                select(Job)
                .where(
                    (Job.status == JobStatus.UNKNOWN) |
                    (
                        (Job.status == JobStatus.OPEN) &
                        (Job.last_checked == None)
                    )
                )
                .limit(batch_size)
            )
            result = await db.execute(query)
            jobs = result.scalars().all()
            
            for job in jobs:
                try:
                    status_result = await self._validate_job(job, db)
                    if status_result:
                        validated_count += 1
                        if status_result == JobStatusResult.CLOSED:
                            closed_count += 1
                    
                    # Rate limiting
                    await asyncio.sleep(1.0)
                    
                except Exception as e:
                    logger.error(f"Error validating job {job.id}: {e}")
                    errors.append({"job_id": job.id, "error": str(e)})
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(
            f"Validator task completed: {validated_count} validated, "
            f"{closed_count} marked closed in {elapsed:.2f}s"
        )
        
        return {
            "validated_count": validated_count,
            "closed_count": closed_count,
            "elapsed_seconds": elapsed,
            "errors": errors,
        }
    
    async def _validate_job(self, job: Job, db: AsyncSession) -> Optional[JobStatusResult]:
        """Validate a single job's status."""
        # Get page content
        page_text = await self.scraper.get_job_page_text(job.job_url)
        
        if not page_text:
            # Job page couldn't be fetched - might be closed
            logger.debug(f"Could not fetch job page for {job.id}")
            return None
        
        # Classify using AI or keywords
        result = await classify_job_status(page_text)
        
        # Map to JobStatus
        if result.status == JobStatusResult.CLOSED:
            new_status = JobStatus.CLOSED
        elif result.status == JobStatusResult.OPEN:
            new_status = JobStatus.OPEN
        else:
            new_status = JobStatus.UNKNOWN
        
        # Update job if status changed
        if job.status != new_status:
            tracker = JobActivityTracker(db)
            await tracker.update_job_status(
                job_id=job.id,
                new_status=new_status,
                reason=f"{result.method}: {result.reason or 'AI classification'}"
            )
            logger.info(f"Job {job.id} status changed: {job.status} -> {new_status}")
        
        # Update last_checked
        job.last_checked = datetime.utcnow()
        await db.commit()
        
        return result.status
    
    async def cleanup(self):
        """Cleanup resources."""
        await self.scraper.close()


class HiringSignalTask:
    """Background task for updating hiring signals."""
    
    def __init__(self):
        self.settings = get_settings()
    
    async def run(self) -> dict:
        """Run the hiring signal calculation."""
        logger.info("Starting hiring signal task...")
        start_time = datetime.utcnow()
        
        results = []
        
        async with get_db_context() as db:
            engine = HiringSignalEngine(db)
            signals = await engine.calculate_all_signals()
            
            for signal in signals:
                results.append({
                    "company_id": signal.company_id,
                    "company_name": signal.company_name,
                    "previous_score": signal.previous_score,
                    "new_score": signal.new_score,
                    "score_change": signal.score_change,
                })
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(
            f"Hiring signal task completed: {len(results)} companies "
            f"updated in {elapsed:.2f}s"
        )
        
        return {
            "companies_updated": len(results),
            "results": results,
            "elapsed_seconds": elapsed,
        }


# Task runner functions
async def run_scraper_task():
    """Run the scraper task."""
    task = ScraperTask()
    try:
        result = await task.run()
        return result
    finally:
        await task.cleanup()


async def run_validator_task(batch_size: int = 50):
    """Run the validator task."""
    task = JobValidatorTask()
    try:
        result = await task.run(batch_size=batch_size)
        return result
    finally:
        await task.cleanup()


async def run_signal_task():
    """Run the hiring signal task."""
    task = HiringSignalTask()
    return await task.run()
