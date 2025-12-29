"""
User Network Service - FastAPI Application

A microservice for managing user relationship graphs.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import persons, queries, relationships, sync
from .core.config import get_settings
from .db.connection import close_db, init_db

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
    logger.info("Starting User Network Service...")
    settings = get_settings()
    logger.info(f"Environment: {settings.environment}")
    
    try:
        await init_db()
        logger.info("Database connection established")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down User Network Service...")
    await close_db()
    logger.info("Database connection closed")


# Create FastAPI app
settings = get_settings()

app = FastAPI(
    title="User Network Service",
    description="API for managing user relationship graphs",
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
app.include_router(persons.router, prefix="/api/v1")
app.include_router(relationships.router, prefix="/api/v1")
app.include_router(queries.router, prefix="/api/v1")
app.include_router(sync.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "user-network"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "user-network",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
    )

