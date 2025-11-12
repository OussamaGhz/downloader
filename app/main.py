from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from .api.routes_sources import router as sources_router
from .api.routes_sessions import router as sessions_router
from .api.routes_flows import router as flows_router
from .core.database import engine, Base

# Import models to ensure tables are created
from .models.session import TelegramSession
from .models.temp_session import TempSession
from .models.source import Source
from .models.scrape import ScrapeRun, ScrapedFile, ScrapeLog
from .services.cleanup import cleanup_expired_temp_sessions
from .services.prefect_client import prefect_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager to handle startup and shutdown events.
    Creates database tables on startup and starts cleanup task.
    """
    # Startup: Create database tables
    Base.metadata.create_all(bind=engine)

    # Activate all concurrency limits on startup
    # This ensures any limits that were manually deactivated are re-enabled
    try:
        print("Activating concurrency limits...")
        prefect_client.activate_all_concurrency_limits()
    except Exception as e:
        print(f"Warning: Failed to activate concurrency limits on startup: {e}")

    # Start background cleanup task for expired temporary sessions
    cleanup_task = asyncio.create_task(cleanup_expired_temp_sessions())

    yield

    # Shutdown: Cancel cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Telegram Scraper API",
    version="2.0.0",
    description="API for managing Telegram scraping sources with session management",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sessions_router)
app.include_router(sources_router)
app.include_router(flows_router)


@app.get("/")
def read_root():
    """Root endpoint with API information."""
    return {
        "message": "Welcome to the Telegram Scraper API v2.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "sessions": "/sessions",
            "sources": "/sources",
            "flows": "/flows",
        },
    }


@app.get("/health")
def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "version": "2.0.0"}
