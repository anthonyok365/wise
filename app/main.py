"""Main FastAPI application for Hiring Signal Detection System."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.db.database import init_db, close_db
from app.api.routes import router
from app.tasks.runner import start_scheduler, stop_scheduler, get_job_status, trigger_scraper, trigger_validator, trigger_signals

# Initialize logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup
    logger.info("Starting Hiring Signal Detection System...")
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Start background scheduler
        await start_scheduler()
        logger.info("Background scheduler started")
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        # Continue anyway - allow app to start
    
    yield
    
    # Shutdown
    logger.info("Shutting down Hiring Signal Detection System...")
    
    try:
        # Stop scheduler
        await stop_scheduler()
        
        # Close database connections
        await close_db()
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title="Hiring Signal Detection API",
        description="""
        ## Hiring Signal Detection System
        
        A comprehensive system for tracking company career pages, extracting job listings,
        and computing hiring activity scores.
        
        ### Features
        
        * **Job Tracking**: Scrape and monitor job listings from company career pages
        * **AI Classification**: Classify jobs as open or closed using AI
        * **Hiring Signals**: Compute hiring activity scores for companies
        * **Background Tasks**: Automatic periodic scraping and validation
        
        ### Architecture
        
        * Scrapes career pages using Playwright (handles JavaScript rendering)
        * Stores jobs in PostgreSQL
        * Uses AI (Ollama/HuggingFace) for classification with keyword fallback
        * Background scheduler for continuous monitoring
        """,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    app.include_router(router, prefix="/api/v1")
    
    # Job management endpoints
    @app.get("/api/v1/jobs/trigger", tags=["Jobs"])
    async def trigger_scrape(background_tasks: BackgroundTasks):
        """Manually trigger the scraper job."""
        result = await trigger_scraper()
        return result
    
    @app.post("/api/v1/jobs/validate", tags=["Jobs"])
    async def validate_jobs(batch_size: int = 100):
        """Manually trigger the job validator."""
        result = await trigger_validator(batch_size=batch_size)
        return result
    
    @app.get("/api/v1/scheduler/status", tags=["Scheduler"])
    async def scheduler_status():
        """Get status of scheduled background jobs."""
        return get_job_status()
    
    @app.post("/api/v1/scheduler/trigger/{job_id}", tags=["Scheduler"])
    async def trigger_scheduled_job(job_id: str):
        """Manually trigger a specific scheduled job."""
        from app.tasks.runner import trigger_job
        return await trigger_job(job_id)
    
    @app.post("/api/v1/signals/recalculate", tags=["Signals"])
    async def recalculate_signals():
        """Manually trigger hiring signal recalculation."""
        result = await trigger_signals()
        return result
    
    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
