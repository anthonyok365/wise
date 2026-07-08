"""Hiring Signal Engine - calculates hiring activity scores for companies."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Company, Job, JobStatus, JobHistory

logger = get_logger(__name__)


@dataclass
class HiringSignalResult:
    """Result of hiring signal calculation."""
    company_id: int
    company_name: str
    previous_score: int
    new_score: int
    score_change: int
    total_jobs: int
    open_jobs: int
    closed_jobs: int
    new_jobs: int
    closed_jobs_delta: int
    job_updates: int


class HiringSignalEngine:
    """Engine for calculating hiring signals based on job activity."""
    
    # Scoring weights
    SCORE_NEW_JOB = 5
    SCORE_MANY_NEW_JOBS_BONUS = 10  # +10 if more than 3 new jobs
    SCORE_JOB_UPDATE = 3
    SCORE_JOB_CLOSED = -5
    SCORE_NEW_JOB_THRESHOLD = 3  # Number of new jobs for bonus
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def calculate_company_signal(self, company_id: int) -> Optional[HiringSignalResult]:
        """
        Calculate and update the hiring signal score for a company.
        
        Looks at job changes since last calculation and computes score.
        """
        # Get company
        result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()
        
        if not company:
            logger.warning(f"Company {company_id} not found")
            return None
        
        previous_score = company.hiring_score
        previous_job_count = company.last_job_count
        
        # Get current job statistics
        job_stats = await self._get_job_statistics(company_id)
        
        # Calculate new jobs since last check
        new_jobs = max(0, job_stats["total"] - previous_job_count)
        
        # Calculate closed jobs delta
        # Jobs that have been closed since last check = (current total - current open) - delta from history
        # Actually, we track closed jobs from history table
        closed_delta = await self._count_closed_since_last_check(company_id)
        
        # Calculate score changes
        score_change = 0
        
        # New jobs
        if new_jobs > 0:
            score_change += new_jobs * self.SCORE_NEW_JOB
            
            # Bonus for many new jobs
            if new_jobs >= self.SCORE_NEW_JOB_THRESHOLD:
                score_change += self.SCORE_MANY_NEW_JOBS_BONUS
        
        # Closed jobs penalty
        if closed_delta > 0:
            score_change += closed_delta * self.SCORE_JOB_CLOSED
        
        # Check for job updates (status changes in history)
        job_updates = await self._count_recent_updates(company_id)
        score_change += job_updates * self.SCORE_JOB_UPDATE
        
        # Calculate new score (ensure non-negative)
        new_score = max(0, previous_score + score_change)
        
        # Update company record
        company.current_job_count = job_stats["total"]
        company.last_job_count = previous_job_count  # Keep track of previous
        company.hiring_score = new_score
        company.last_checked = datetime.utcnow()
        
        await self.db.commit()
        
        logger.info(
            f"Updated hiring signal for {company.company_name}: "
            f"{previous_score} -> {new_score} (change: {score_change:+d})"
        )
        
        return HiringSignalResult(
            company_id=company_id,
            company_name=company.company_name,
            previous_score=previous_score,
            new_score=new_score,
            score_change=score_change,
            total_jobs=job_stats["total"],
            open_jobs=job_stats["open"],
            closed_jobs=job_stats["closed"],
            new_jobs=new_jobs,
            closed_jobs_delta=closed_delta,
            job_updates=job_updates,
        )
    
    async def calculate_all_signals(self) -> List[HiringSignalResult]:
        """Calculate hiring signals for all companies."""
        result = await self.db.execute(select(Company))
        companies = result.scalars().all()
        
        results = []
        for company in companies:
            signal_result = await self.calculate_company_signal(company.id)
            if signal_result:
                results.append(signal_result)
        
        return results
    
    async def _get_job_statistics(self, company_id: int) -> dict:
        """Get job statistics for a company."""
        # Total jobs
        total_result = await self.db.execute(
            select(func.count(Job.id)).where(Job.company_id == company_id)
        )
        total = total_result.scalar() or 0
        
        # Open jobs
        open_result = await self.db.execute(
            select(func.count(Job.id)).where(
                Job.company_id == company_id,
                Job.status == JobStatus.OPEN
            )
        )
        open_jobs = open_result.scalar() or 0
        
        # Closed jobs
        closed_result = await self.db.execute(
            select(func.count(Job.id)).where(
                Job.company_id == company_id,
                Job.status == JobStatus.CLOSED
            )
        )
        closed_jobs = closed_result.scalar() or 0
        
        return {
            "total": total,
            "open": open_jobs,
            "closed": closed_jobs,
        }
    
    async def _count_recent_updates(self, company_id: int, hours: int = 24) -> int:
        """Count job status updates in the last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        # Get jobs for this company
        jobs_result = await self.db.execute(
            select(Job.id).where(Job.company_id == company_id)
        )
        job_ids = [row[0] for row in jobs_result.fetchall()]
        
        if not job_ids:
            return 0
        
        # Count history entries for these jobs since cutoff
        count_result = await self.db.execute(
            select(func.count(JobHistory.id)).where(
                JobHistory.job_id.in_(job_ids),
                JobHistory.changed_at >= cutoff,
                JobHistory.old_status != JobHistory.new_status,
            )
        )
        
        return count_result.scalar() or 0
    
    async def _count_closed_since_last_check(self, company_id: int, hours: int = 48) -> int:
        """Count jobs that have been closed since last check."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        # Get jobs for this company that are closed
        jobs_result = await self.db.execute(
            select(Job.id).where(
                Job.company_id == company_id,
                Job.status == JobStatus.CLOSED
            )
        )
        job_ids = [row[0] for row in jobs_result.fetchall()]
        
        if not job_ids:
            return 0
        
        # Count history entries showing transitions to CLOSED status
        count_result = await self.db.execute(
            select(func.count(JobHistory.id)).where(
                JobHistory.job_id.in_(job_ids),
                JobHistory.changed_at >= cutoff,
                JobHistory.new_status == JobStatus.CLOSED,
            )
        )
        
        return count_result.scalar() or 0
    
    async def get_top_hiring_companies(
        self, 
        limit: int = 10,
        min_score: int = 0,
    ) -> List[Company]:
        """Get top companies by hiring score."""
        result = await self.db.execute(
            select(Company)
            .where(Company.hiring_score >= min_score)
            .order_by(Company.hiring_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class JobActivityTracker:
    """Tracks job status changes and records history."""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def record_status_change(
        self,
        job_id: int,
        old_status: Optional[JobStatus],
        new_status: JobStatus,
        reason: Optional[str] = None,
    ) -> JobHistory:
        """Record a job status change in history."""
        history = JobHistory(
            job_id=job_id,
            old_status=old_status,
            new_status=new_status,
            change_reason=reason,
        )
        
        self.db.add(history)
        await self.db.flush()
        
        return history
    
    async def update_job_status(
        self,
        job_id: int,
        new_status: JobStatus,
        reason: Optional[str] = None,
    ) -> Optional[Job]:
        """Update job status and record history."""
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return None
        
        old_status = job.status
        
        # Only record if status actually changed
        if old_status != new_status:
            await self.record_status_change(
                job_id=job_id,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
            )
            
            job.status = new_status
            await self.db.commit()
        
        return job
