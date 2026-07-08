"""Pytest configuration and fixtures."""
import asyncio
import pytest
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Company, Job, JobStatus


# Test database URL (SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with session_factory() as session:
        yield session


@pytest.fixture(scope="function")
async def sample_company(db_session: AsyncSession) -> Company:
    """Create a sample company for testing."""
    company = Company(
        company_name="Test Company",
        career_page_url="https://example.com/careers",
        industry="Technology",
    )
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    return company


@pytest.fixture(scope="function")
async def sample_job(db_session: AsyncSession, sample_company: Company) -> Job:
    """Create a sample job for testing."""
    job = Job(
        company_id=sample_company.id,
        job_title="Software Engineer",
        job_url="https://example.com/careers/software-engineer",
        location="San Francisco, CA",
        status=JobStatus.OPEN,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job
