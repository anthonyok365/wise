"""Unit tests for Hiring Signal Engine."""
import pytest
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db.models import Company, Job, JobStatus, JobHistory
from app.services.hiring_signal_engine import HiringSignalEngine, JobActivityTracker


class TestHiringSignalEngine:
    """Tests for HiringSignalEngine."""
    
    @pytest.fixture
    def engine(self, db_session):
        """Create engine instance."""
        return HiringSignalEngine(db_session)
    
    @pytest.mark.asyncio
    async def test_initial_score(self, db_session, engine, sample_company):
        """Test initial hiring score is zero."""
        result = await engine.calculate_company_signal(sample_company.id)
        
        assert result is not None
        assert result.new_score == 0
        assert result.previous_score == 0
    
    @pytest.mark.asyncio
    async def test_new_job_increases_score(self, db_session, engine, sample_company):
        """Test that new jobs increase the score."""
        # Add first job (new)
        job1 = Job(
            company_id=sample_company.id,
            job_title="New Job 1",
            job_url="https://example.com/job1",
            status=JobStatus.OPEN,
        )
        db_session.add(job1)
        await db_session.commit()
        
        result = await engine.calculate_company_signal(sample_company.id)
        
        # +5 for first new job
        assert result.new_jobs == 1
        assert result.score_change == 5
        assert result.new_score == 5
    
    @pytest.mark.asyncio
    async def test_many_new_jobs_bonus(self, db_session, engine, sample_company):
        """Test bonus for many new jobs."""
        # Add multiple new jobs
        for i in range(5):
            job = Job(
                company_id=sample_company.id,
                job_title=f"New Job {i}",
                job_url=f"https://example.com/job{i}",
                status=JobStatus.OPEN,
            )
            db_session.add(job)
        await db_session.commit()
        
        result = await engine.calculate_company_signal(sample_company.id)
        
        # 5 * 5 = 25 for jobs, +10 bonus for >3 jobs
        assert result.new_jobs == 5
        assert result.score_change == 35
    
    @pytest.mark.asyncio
    async def test_closed_job_penalty(self, db_session, engine, sample_company):
        """Test that closed jobs decrease score when recorded in history."""
        # Add open job first
        job = Job(
            company_id=sample_company.id,
            job_title="Job",
            job_url="https://example.com/job",
            status=JobStatus.OPEN,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)
        
        # Set previous job count
        sample_company.last_job_count = 1
        await db_session.commit()
        
        # Update job status and record history
        tracker = JobActivityTracker(db_session)
        await tracker.update_job_status(
            job_id=job.id,
            new_status=JobStatus.CLOSED,
            reason="Test",
        )
        await db_session.commit()
        
        result = await engine.calculate_company_signal(sample_company.id)
        
        # Closed job penalty (from history) minus job update bonus
        # -5 (closed) + 3 (update) = -2
        assert result.closed_jobs_delta == 1
        assert result.job_updates == 1
        assert result.score_change == -2
    
    @pytest.mark.asyncio
    async def test_score_never_negative(self, db_session, engine, sample_company):
        """Test that score never goes negative."""
        # Set initial score
        sample_company.hiring_score = 3
        
        # Close jobs
        for i in range(2):
            job = Job(
                company_id=sample_company.id,
                job_title=f"Job {i}",
                job_url=f"https://example.com/job{i}",
                status=JobStatus.CLOSED,
            )
            db_session.add(job)
        await db_session.commit()
        
        sample_company.last_job_count = 2
        await db_session.commit()
        
        result = await engine.calculate_company_signal(sample_company.id)
        
        assert result.new_score >= 0
    
    @pytest.mark.asyncio
    async def test_job_statistics(self, db_session, engine, sample_company):
        """Test job statistics calculation."""
        # Add various jobs
        jobs = [
            Job(company_id=sample_company.id, job_title=f"Job {i}", job_url=f"https://example.com/{i}", status=JobStatus.OPEN)
            for i in range(5)
        ]
        jobs.append(Job(company_id=sample_company.id, job_title="Closed", job_url="https://example.com/closed", status=JobStatus.CLOSED))
        
        for job in jobs:
            db_session.add(job)
        await db_session.commit()
        
        stats = await engine._get_job_statistics(sample_company.id)
        
        assert stats["total"] == 6
        assert stats["open"] == 5
        assert stats["closed"] == 1
    
    @pytest.mark.asyncio
    async def test_top_hiring_companies(self, db_session, engine):
        """Test getting top hiring companies."""
        # Create multiple companies with different scores
        for i in range(5):
            company = Company(
                company_name=f"Company {i}",
                career_page_url=f"https://example{i}.com/careers",
                hiring_score=(5 - i) * 10,  # Descending scores
            )
            db_session.add(company)
        await db_session.commit()
        
        top_companies = await engine.get_top_hiring_companies(limit=3)
        
        assert len(top_companies) == 3
        assert top_companies[0].hiring_score >= top_companies[1].hiring_score
        assert top_companies[1].hiring_score >= top_companies[2].hiring_score


class TestJobActivityTracker:
    """Tests for JobActivityTracker."""
    
    @pytest.fixture
    def tracker(self, db_session):
        """Create tracker instance."""
        return JobActivityTracker(db_session)
    
    @pytest.mark.asyncio
    async def test_record_status_change(self, tracker, sample_job):
        """Test recording job status changes."""
        history = await tracker.record_status_change(
            job_id=sample_job.id,
            old_status=JobStatus.OPEN,
            new_status=JobStatus.CLOSED,
            reason="AI classified as closed",
        )
        
        assert history.id is not None
        assert history.old_status == JobStatus.OPEN
        assert history.new_status == JobStatus.CLOSED
        assert history.change_reason == "AI classified as closed"
    
    @pytest.mark.asyncio
    async def test_update_job_status(self, tracker, sample_job):
        """Test updating job status."""
        updated_job = await tracker.update_job_status(
            job_id=sample_job.id,
            new_status=JobStatus.CLOSED,
            reason="Test update",
        )
        
        assert updated_job.status == JobStatus.CLOSED
        
        # Verify history was created
        history_result = await tracker.db.execute(
            select(JobHistory).where(JobHistory.job_id == sample_job.id)
        )
        history = history_result.scalar_one()
        
        assert history.old_status == JobStatus.OPEN
        assert history.new_status == JobStatus.CLOSED
    
    @pytest.mark.asyncio
    async def test_update_same_status_no_history(self, tracker, sample_job):
        """Test that updating to same status doesn't create history."""
        # Update to same status
        await tracker.update_job_status(
            job_id=sample_job.id,
            new_status=JobStatus.OPEN,  # Same as current
            reason="No change",
        )
        
        # Should not create history
        history_result = await tracker.db.execute(
            select(JobHistory).where(JobHistory.job_id == sample_job.id)
        )
        history = history_result.scalar_one_or_none()
        
        assert history is None
