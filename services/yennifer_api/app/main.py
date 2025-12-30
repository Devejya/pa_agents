"""
Yennifer API Service - FastAPI Application

Web API for the Yennifer AI executive assistant.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import auth, chat, workspace, jobs, contacts
from .core.config import get_settings
from .core.scheduler import start_scheduler, stop_scheduler
from .db.connection import init_db, close_db
from .jobs import register_all_jobs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Yennifer API Service...")
    settings = get_settings()
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"OpenAI Model: {settings.openai_model}")
    
    # Initialize database connection pool
    logger.info("Initializing database connection...")
    try:
        await init_db()
        logger.info("Database connection established")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.warning("Continuing without database - token storage will be unavailable")
    
    # Start background scheduler
    logger.info("Starting background job scheduler...")
    register_all_jobs()
    start_scheduler()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Yennifer API Service...")
    
    # Stop background scheduler
    logger.info("Stopping background job scheduler...")
    stop_scheduler()
    
    # Close database connection pool
    logger.info("Closing database connection...")
    await close_db()


# Create FastAPI app
settings = get_settings()

app = FastAPI(
    title="Yennifer API",
    description="API for Yennifer AI Executive Assistant",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(workspace.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(contacts.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "yennifer-api"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "yennifer-api",
        "version": "1.0.0",
        "docs": "/docs",
        "assistant": "Yennifer - Your AI Executive Assistant",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
    )
