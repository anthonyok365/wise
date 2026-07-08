"""Unit tests for database models."""
import pytest
from datetime import datetime

from sqlalchemy import select

from app.db.models import Company, Job, JobStatus, JobType, SiteConfig


class TestCompanyModel:
    """Tests for Company model."""
    
    @pytest.mark.asyncio
    async def test_create_company(self, db_session):
        """Test creating a company."""
        company = Company(
            company_name="Acme Corp",
            career_page_url="https://acme.com/jobs",
            industry="Technology",
        )
        db_session.add(company)
        await db_session.commit()
        
        assert company.id is not None
        assert company.company_name == "Acme Corp"
        assert company.career_page_url == "https://acme.com/jobs"
        assert company.industry == "Technology"
        assert company.hiring_score == 0
        assert company.current_job_count == 0
        assert company.last_checked is None
    
    @pytest.mark.asyncio
    async def test_company_relationships(self, db_session, sample_company, sample_job):
        """Test company-job relationships."""
        # Use selectinload to eagerly load jobs
        from sqlalchemy.orm import selectinload
        result = await db_session.execute(
            select(Company).options(selectinload(Company.jobs)).where(Company.id == sample_company.id)
        )
        company = result.scalar_one()
        
        # Check jobs exist
        assert len(company.jobs) >= 1
        job_titles = [j.job_title for j in company.jobs]
        assert "Software Engineer" in job_titles
    
    @pytest.mark.asyncio
    async def test_company_defaults(self, db_session):
        """Test company default values."""
        company = Company(
            company_name="Test",
            career_page_url="https://test.com",
        )
        db_session.add(company)
        await db_session.commit()
        
        assert company.hiring_score == 0
        assert company.last_job_count == 0
        assert company.current_job_count == 0
        assert company.created_at is not None


class TestJobModel:
    """Tests for Job model."""
    
    @pytest.mark.asyncio
    async def test_create_job(self, db_session, sample_company):
        """Test creating a job."""
        job = Job(
            company_id=sample_company.id,
            job_title="Senior Developer",
            job_url="https://example.com/jobs/senior-dev",
            location="Remote",
            status=JobStatus.OPEN,
        )
        db_session.add(job)
        await db_session.commit()
        
        assert job.id is not None
        assert job.job_title == "Senior Developer"
        assert job.location == "Remote"
        assert job.status == JobStatus.OPEN
        assert job.job_type == JobType.UNKNOWN
    
    @pytest.mark.asyncio
    async def test_job_status_enum(self, db_session, sample_company):
        """Test job status enumeration."""
        for status in JobStatus:
            job = Job(
                company_id=sample_company.id,
                job_title=f"Test {status.value}",
                job_url=f"https://example.com/jobs/{status.value}",
                status=status,
            )
            db_session.add(job)
        
        await db_session.commit()
        
        result = await db_session.execute(select(Job))
        jobs = result.scalars().all()
        
        assert len(jobs) == 3
        statuses = {job.status for job in jobs}
        assert statuses == {JobStatus.OPEN, JobStatus.CLOSED, JobStatus.UNKNOWN}
    
    @pytest.mark.asyncio
    async def test_job_unique_constraint(self, db_session, sample_company, sample_job):
        """Test job URL unique constraint."""
        duplicate_job = Job(
            company_id=sample_company.id,
            job_title="Another Job",
            job_url=sample_job.job_url,  # Same URL
            status=JobStatus.OPEN,
        )
        db_session.add(duplicate_job)
        
        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()


class TestSiteConfigModel:
    """Tests for SiteConfig model."""
    
    @pytest.mark.asyncio
    async def test_create_site_config(self, db_session, sample_company):
        """Test creating site configuration."""
        config = SiteConfig(
            company_id=sample_company.id,
            job_listing_selector="div.job-listing",
            job_title_selector="h3.job-title",
            pagination_type="load_more",
            next_page_selector="button.load-more",
        )
        db_session.add(config)
        await db_session.commit()
        
        assert config.id is not None
        assert config.job_listing_selector == "div.job-listing"
        assert config.pagination_type == "load_more"
        assert config.is_active is True
