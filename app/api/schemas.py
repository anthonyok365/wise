"""Pydantic schemas for API request/response validation."""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict

from app.db.models import JobStatus, JobType


# ===== Company Schemas =====

class CompanyBase(BaseModel):
    """Base schema for company data."""
    company_name: str = Field(..., min_length=1, max_length=255)
    career_page_url: str = Field(..., min_length=1)
    logo_url: Optional[str] = None
    industry: Optional[str] = Field(None, max_length=100)


class CompanyCreate(CompanyBase):
    """Schema for creating a company."""
    pass


class CompanyUpdate(BaseModel):
    """Schema for updating a company."""
    company_name: Optional[str] = Field(None, min_length=1, max_length=255)
    career_page_url: Optional[str] = Field(None, min_length=1)
    logo_url: Optional[str] = None
    industry: Optional[str] = Field(None, max_length=100)


class CompanySummary(BaseModel):
    """Schema for company summary in listings."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    company_name: str
    career_page_url: str
    logo_url: Optional[str] = None
    industry: Optional[str] = None
    current_job_count: int
    hiring_score: int
    last_checked: Optional[datetime] = None


class CompanyDetail(CompanySummary):
    """Schema for detailed company information."""
    model_config = ConfigDict(from_attributes=True)
    
    last_job_count: int
    created_at: datetime
    updated_at: datetime


class CompanyWithJobs(CompanyDetail):
    """Schema for company with its jobs."""
    jobs: List["JobSummary"] = []


# ===== Job Schemas =====

class JobBase(BaseModel):
    """Base schema for job data."""
    job_title: str = Field(..., min_length=1, max_length=500)
    job_url: str = Field(..., min_length=1)
    location: Optional[str] = Field(None, max_length=255)
    job_type: JobType = JobType.UNKNOWN
    description_preview: Optional[str] = None
    date_posted: Optional[datetime] = None


class JobCreate(JobBase):
    """Schema for creating a job."""
    company_id: int


class JobUpdate(BaseModel):
    """Schema for updating a job."""
    job_title: Optional[str] = Field(None, min_length=1, max_length=500)
    location: Optional[str] = Field(None, max_length=255)
    job_type: Optional[JobType] = None
    description_preview: Optional[str] = None
    status: Optional[JobStatus] = None


class JobSummary(BaseModel):
    """Schema for job summary in listings."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    company_id: int
    job_title: str
    job_url: str
    location: Optional[str] = None
    job_type: JobType
    status: JobStatus
    date_posted: Optional[datetime] = None
    last_checked: Optional[datetime] = None


class JobDetail(JobSummary):
    """Schema for detailed job information."""
    model_config = ConfigDict(from_attributes=True)
    
    description_preview: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    company: Optional[CompanySummary] = None


class JobWithCompany(JobSummary):
    """Schema for job with company information."""
    model_config = ConfigDict(from_attributes=True)
    
    company: CompanySummary


# ===== Site Config Schemas =====

class SiteConfigBase(BaseModel):
    """Base schema for site configuration."""
    job_listing_selector: Optional[str] = None
    job_title_selector: Optional[str] = None
    job_url_selector: Optional[str] = None
    job_location_selector: Optional[str] = None
    job_date_selector: Optional[str] = None
    pagination_type: str = "none"
    next_page_selector: Optional[str] = None
    wait_for_selector: Optional[str] = None
    load_more_button_selector: Optional[str] = None


class SiteConfigCreate(SiteConfigBase):
    """Schema for creating site configuration."""
    company_id: int


class SiteConfigUpdate(BaseModel):
    """Schema for updating site configuration."""
    job_listing_selector: Optional[str] = None
    job_title_selector: Optional[str] = None
    job_url_selector: Optional[str] = None
    job_location_selector: Optional[str] = None
    job_date_selector: Optional[str] = None
    pagination_type: Optional[str] = None
    next_page_selector: Optional[str] = None
    wait_for_selector: Optional[str] = None
    load_more_button_selector: Optional[str] = None
    is_active: Optional[bool] = None


class SiteConfigResponse(SiteConfigBase):
    """Schema for site configuration response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    company_id: int
    is_active: bool


# ===== Pagination Schemas =====

class PaginatedResponse(BaseModel):
    """Generic paginated response schema."""
    items: List
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ===== Filter Schemas =====

class JobFilter(BaseModel):
    """Filters for job queries."""
    company_id: Optional[int] = None
    status: Optional[JobStatus] = None
    job_type: Optional[JobType] = None
    search: Optional[str] = Field(None, max_length=255)


class CompanyFilter(BaseModel):
    """Filters for company queries."""
    industry: Optional[str] = None
    min_score: Optional[int] = None
    search: Optional[str] = Field(None, max_length=255)


# ===== Stats Schemas =====

class HiringStats(BaseModel):
    """Overall hiring statistics."""
    total_companies: int
    total_jobs: int
    open_jobs: int
    closed_jobs: int
    unknown_jobs: int
    top_hiring_companies: List[CompanySummary]


class JobStatusUpdate(BaseModel):
    """Schema for updating job status via AI."""
    job_id: int
    status: JobStatus
    confidence: Optional[float] = None
    reason: Optional[str] = None


# Update forward references
CompanyWithJobs.model_rebuild()
