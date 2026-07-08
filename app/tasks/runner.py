"""Background job scheduler using APScheduler."""
import asyncio
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.base import JobLookupError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.tasks.scheduler import (
    run_scraper_task,
    run_validator_task,
    run_signal_task,
)

logger = get_logger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,  # Combine multiple pending executions
                "max_instances": 1,  # Only one instance of each job at a time
                "misfire_grace_time": 3600,  # 1 hour grace time for missed jobs
            },
        )
    return _scheduler


async def start_scheduler() -> None:
    """Start the background job scheduler."""
    settings = get_settings()
    
    if not settings.scheduler.enabled:
        logger.info("Scheduler is disabled in configuration")
        return
    
    scheduler = get_scheduler()
    
    if scheduler.running:
        logger.info("Scheduler already running")
        return
    
    # Add jobs
    _add_scheduled_jobs(scheduler, settings)
    
    # Start scheduler
    scheduler.start()
    logger.info(
        f"Background scheduler started - "
        f"Scraper: every {settings.scheduler.scraper_interval_hours}h, "
        f"Validator: every {settings.scheduler.validator_interval_hours}h, "
        f"Signals: every {settings.scheduler.scoring_interval_hours}h"
    )


async def stop_scheduler() -> None:
    """Stop the background job scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
    _scheduler = None


def _add_scheduled_jobs(scheduler: AsyncIOScheduler, settings) -> None:
    """Add all scheduled jobs to the scheduler."""
    
    # Scraper job - runs every X hours
    scheduler.add_job(
        run_scraper_task,
        trigger=IntervalTrigger(hours=settings.scheduler.scraper_interval_hours),
        id="career_page_scraper",
        name="Career Page Scraper",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    
    # Validator job - runs every X hours
    scheduler.add_job(
        run_validator_task,
        trigger=IntervalTrigger(hours=settings.scheduler.validator_interval_hours),
        id="job_validator",
        name="Job Validator",
        replace_existing=True,
        misfire_grace_time=3600,
        kwargs={"batch_size": 100},
    )
    
    # Hiring signal calculation - runs every hour
    scheduler.add_job(
        run_signal_task,
        trigger=IntervalTrigger(hours=settings.scheduler.scoring_interval_hours),
        id="hiring_signal_calculator",
        name="Hiring Signal Calculator",
        replace_existing=True,
        misfire_grace_time=1800,
    )


async def trigger_job(job_id: str) -> dict:
    """Manually trigger a specific job."""
    scheduler = get_scheduler()
    
    try:
        job = scheduler.get_job(job_id)
        if job:
            # Get the job function
            job_func = None
            if job_id == "career_page_scraper":
                job_func = run_scraper_task
            elif job_id == "job_validator":
                job_func = run_validator_task
            elif job_id == "hiring_signal_calculator":
                job_func = run_signal_task
            
            if job_func:
                logger.info(f"Manually triggering job: {job_id}")
                result = await job_func()
                return {"status": "completed", "job_id": job_id, "result": result}
        else:
            return {"status": "error", "message": f"Job not found: {job_id}"}
    except Exception as e:
        logger.error(f"Error triggering job {job_id}: {e}")
        return {"status": "error", "job_id": job_id, "error": str(e)}
    
    return {"status": "unknown", "job_id": job_id}


def get_job_status() -> list:
    """Get status of all scheduled jobs."""
    scheduler = get_scheduler()
    jobs = scheduler.get_jobs()
    
    job_list = []
    for job in jobs:
        job_list.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "pending": job.pending,
        })
    
    return job_list


# API endpoints for job management
async def trigger_scraper() -> dict:
    """Manually trigger the scraper job."""
    return await trigger_job("career_page_scraper")


async def trigger_validator(batch_size: int = 100) -> dict:
    """Manually trigger the validator job."""
    try:
        logger.info(f"Manually triggering job validator with batch_size={batch_size}")
        result = await run_validator_task(batch_size=batch_size)
        return {"status": "completed", "result": result}
    except Exception as e:
        logger.error(f"Error triggering validator: {e}")
        return {"status": "error", "error": str(e)}


async def trigger_signals() -> dict:
    """Manually trigger the signal calculation job."""
    return await trigger_job("hiring_signal_calculator")
