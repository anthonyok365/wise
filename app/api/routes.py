"""FastAPI routes for the Hiring Signal Detection API."""
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models import Job, Company, JobStatus, JobType, SiteConfig
from app.api.schemas import (
    JobSummary,
    JobDetail,
    JobCreate,
    JobUpdate,
    JobFilter,
    CompanySummary,
    CompanyDetail,
    CompanyCreate,
    CompanyUpdate,
    CompanyWithJobs,
    SiteConfigCreate,
    SiteConfigUpdate,
    SiteConfigResponse,
    HiringStats,
    PaginatedResponse,
)

router = APIRouter()


# ===== Health Check =====
@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ===== Jobs Endpoints =====

@router.get("/jobs", response_model=PaginatedResponse)
async def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    company_id: Optional[int] = None,
    status: Optional[JobStatus] = None,
    job_type: Optional[JobType] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List all jobs with optional filtering and pagination.
    
    - **company_id**: Filter by company
    - **status**: Filter by job status (open/closed/unknown)
    - **job_type**: Filter by job type (remote/hybrid/onsite)
    - **search**: Search in job title
    """
    query = select(Job).options(selectinload(Job.company))
    
    # Apply filters
    if company_id:
        query = query.where(Job.company_id == company_id)
    if status:
        query = query.where(Job.status == status)
    if job_type:
        query = query.where(Job.job_type == job_type)
    if search:
        query = query.where(Job.job_title.ilike(f"%{search}%"))
    
    # Count total
    count_query = select(func.count(Job.id))
    if company_id:
        count_query = count_query.where(Job.company_id == company_id)
    if status:
        count_query = count_query.where(Job.status == status)
    if job_type:
        count_query = count_query.where(Job.job_type == job_type)
    if search:
        count_query = count_query.where(Job.job_title.ilike(f"%{search}%"))
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Job.created_at.desc())
    
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size
    
    return PaginatedResponse(
        items=[JobSummary.model_validate(job) for job in jobs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed information about a specific job."""
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.company))
        .where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobDetail.model_validate(job)


@router.post("/jobs", response_model=JobSummary, status_code=201)
async def create_job(job_data: JobCreate, db: AsyncSession = Depends(get_db)):
    """Create a new job listing."""
    # Verify company exists
    company_result = await db.execute(
        select(Company).where(Company.id == job_data.company_id)
    )
    if not company_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Check for duplicate URL
    existing = await db.execute(
        select(Job).where(Job.job_url == job_data.job_url)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Job with this URL already exists")
    
    job = Job(
        company_id=job_data.company_id,
        job_title=job_data.job_title,
        job_url=job_data.job_url,
        location=job_data.location,
        job_type=job_data.job_type,
        description_preview=job_data.description_preview,
        date_posted=job_data.date_posted,
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    return JobSummary.model_validate(job)


@router.patch("/jobs/{job_id}", response_model=JobSummary)
async def update_job(
    job_id: int,
    job_data: JobUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing job listing."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Update only provided fields
    update_data = job_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(job, field, value)
    
    await db.commit()
    await db.refresh(job)
    
    return JobSummary.model_validate(job)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a job listing."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    await db.delete(job)
    await db.commit()


# ===== Companies Endpoints =====

@router.get("/companies", response_model=List[CompanySummary])
async def list_companies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    industry: Optional[str] = None,
    min_score: Optional[int] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List all companies with optional filtering.
    
    - **industry**: Filter by industry
    - **min_score**: Filter by minimum hiring score
    - **search**: Search in company name
    """
    query = select(Company)
    
    # Apply filters
    if industry:
        query = query.where(Company.industry == industry)
    if min_score is not None:
        query = query.where(Company.hiring_score >= min_score)
    if search:
        query = query.where(Company.company_name.ilike(f"%{search}%"))
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Company.hiring_score.desc())
    
    result = await db.execute(query)
    companies = result.scalars().all()
    
    return [CompanySummary.model_validate(c) for c in companies]


@router.get("/companies/{company_id}", response_model=CompanyDetail)
async def get_company(company_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed information about a specific company."""
    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    return CompanyDetail.model_validate(company)


@router.get("/companies/{company_id}/jobs", response_model=List[JobSummary])
async def get_company_jobs(
    company_id: int,
    status: Optional[JobStatus] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get all jobs for a specific company."""
    # Verify company exists
    company_result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    if not company_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Company not found")
    
    query = select(Job).where(Job.company_id == company_id)
    
    if status:
        query = query.where(Job.status == status)
    
    query = query.order_by(Job.created_at.desc())
    
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return [JobSummary.model_validate(j) for j in jobs]


@router.post("/companies", response_model=CompanySummary, status_code=201)
async def create_company(company_data: CompanyCreate, db: AsyncSession = Depends(get_db)):
    """Create a new company."""
    # Check for duplicate URL
    existing = await db.execute(
        select(Company).where(Company.career_page_url == company_data.career_page_url)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Company with this URL already exists")
    
    company = Company(
        company_name=company_data.company_name,
        career_page_url=company_data.career_page_url,
        logo_url=company_data.logo_url,
        industry=company_data.industry,
    )
    
    db.add(company)
    await db.commit()
    await db.refresh(company)
    
    return CompanySummary.model_validate(company)


@router.patch("/companies/{company_id}", response_model=CompanySummary)
async def update_company(
    company_id: int,
    company_data: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing company."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Update only provided fields
    update_data = company_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)
    
    await db.commit()
    await db.refresh(company)
    
    return CompanySummary.model_validate(company)


@router.delete("/companies/{company_id}", status_code=204)
async def delete_company(company_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a company and all its jobs."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    await db.delete(company)
    await db.commit()


# ===== Site Config Endpoints =====

@router.post("/companies/{company_id}/config", response_model=SiteConfigResponse, status_code=201)
async def create_site_config(
    company_id: int,
    config_data: SiteConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create site-specific scraping configuration for a company."""
    # Verify company exists
    company_result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    if not company_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Company not found")
    
    config = SiteConfig(
        company_id=company_id,
        job_listing_selector=config_data.job_listing_selector,
        job_title_selector=config_data.job_title_selector,
        job_url_selector=config_data.job_url_selector,
        job_location_selector=config_data.job_location_selector,
        job_date_selector=config_data.job_date_selector,
        pagination_type=config_data.pagination_type,
        next_page_selector=config_data.next_page_selector,
        wait_for_selector=config_data.wait_for_selector,
        load_more_button_selector=config_data.load_more_button_selector,
    )
    
    db.add(config)
    await db.commit()
    await db.refresh(config)
    
    return SiteConfigResponse.model_validate(config)


@router.get("/companies/{company_id}/config", response_model=SiteConfigResponse)
async def get_site_config(company_id: int, db: AsyncSession = Depends(get_db)):
    """Get site configuration for a company."""
    result = await db.execute(
        select(SiteConfig)
        .where(SiteConfig.company_id == company_id)
        .where(SiteConfig.is_active == True)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="No active site config found")
    
    return SiteConfigResponse.model_validate(config)


# ===== Statistics Endpoint =====

@router.get("/stats", response_model=HiringStats)
async def get_hiring_stats(db: AsyncSession = Depends(get_db)):
    """Get overall hiring statistics."""
    # Count companies
    companies_result = await db.execute(select(func.count(Company.id)))
    total_companies = companies_result.scalar() or 0
    
    # Count jobs by status
    total_result = await db.execute(select(func.count(Job.id)))
    total_jobs = total_result.scalar() or 0
    
    open_result = await db.execute(
        select(func.count(Job.id)).where(Job.status == JobStatus.OPEN)
    )
    open_jobs = open_result.scalar() or 0
    
    closed_result = await db.execute(
        select(func.count(Job.id)).where(Job.status == JobStatus.CLOSED)
    )
    closed_jobs = closed_result.scalar() or 0
    
    unknown_result = await db.execute(
        select(func.count(Job.id)).where(Job.status == JobStatus.UNKNOWN)
    )
    unknown_jobs = unknown_result.scalar() or 0
    
    # Get top hiring companies
    top_result = await db.execute(
        select(Company)
        .order_by(Company.hiring_score.desc())
        .limit(10)
    )
    top_companies = list(top_result.scalars().all())
    
    return HiringStats(
        total_companies=total_companies,
        total_jobs=total_jobs,
        open_jobs=open_jobs,
        closed_jobs=closed_jobs,
        unknown_jobs=unknown_jobs,
        top_hiring_companies=[CompanySummary.model_validate(c) for c in top_companies],
    )
