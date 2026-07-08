"""SQLAlchemy async models for the Hiring Signal Detection System."""
import enum
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Text, DateTime, ForeignKey, 
    Enum as SQLEnum, Index, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class JobStatus(str, enum.Enum):
    """Job status enumeration."""
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class JobType(str, enum.Enum):
    """Job type classification."""
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class Company(Base):
    """Company model for tracking hiring activity."""
    
    __tablename__ = "companies"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    career_page_url: Mapped[str] = mapped_column(Text, nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Hiring metrics
    last_job_count: Mapped[int] = mapped_column(Integer, default=0)
    current_job_count: Mapped[int] = mapped_column(Integer, default=0)
    hiring_score: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    last_checked: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True,
        onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    jobs: Mapped[List["Job"]] = relationship(
        "Job", 
        back_populates="company",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index("ix_companies_career_url", "career_page_url"),
        Index("ix_companies_hiring_score", "hiring_score"),
    )
    
    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.company_name}', score={self.hiring_score})>"


class Job(Base):
    """Job listing model for tracking individual positions."""
    
    __tablename__ = "jobs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Job details
    job_title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    job_url: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    job_type: Mapped[JobType] = mapped_column(
        SQLEnum(JobType), 
        default=JobType.UNKNOWN
    )
    description_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Status tracking
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus), 
        default=JobStatus.UNKNOWN,
        index=True
    )
    
    # Dates
    date_posted: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    last_checked: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="jobs")
    
    __table_args__ = (
        UniqueConstraint("company_id", "job_url", name="uq_company_job_url"),
        Index("ix_jobs_status_date", "status", "created_at"),
        Index("ix_jobs_company_status", "company_id", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title='{self.job_title}', status='{self.status.value}')>"


class JobHistory(Base):
    """Job history model for tracking status changes."""
    
    __tablename__ = "job_history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Status change details
    old_status: Mapped[Optional[JobStatus]] = mapped_column(
        SQLEnum(JobStatus),
        nullable=True
    )
    new_status: Mapped[JobStatus] = mapped_column(SQLEnum(JobStatus), nullable=False)
    change_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamp
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    
    __table_args__ = (
        Index("ix_job_history_job_time", "job_id", "changed_at"),
    )
    
    def __repr__(self) -> str:
        return f"<JobHistory(job_id={self.job_id}, {self.old_status}->{self.new_status})>"


class SiteConfig(Base):
    """Site-specific configuration for scraping."""
    
    __tablename__ = "site_configs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # CSS selectors for job listing containers
    job_listing_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_title_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_url_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_location_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_date_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Pagination configuration
    pagination_type: Mapped[str] = mapped_column(
        String(50), 
        default="none"  # none, load_more, pagination, infinite_scroll
    )
    next_page_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Additional JavaScript to execute
    wait_for_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    load_more_button_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Active status
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    def __repr__(self) -> str:
        return f"<SiteConfig(company_id={self.company_id}, pagination='{self.pagination_type}')>"
