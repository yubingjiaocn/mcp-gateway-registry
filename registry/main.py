#!/usr/bin/env python3
"""
MCP Gateway Registry - Modern FastAPI Application

A clean, domain-driven FastAPI app for managing MCP (Model Context Protocol) servers.
This main.py file serves as the application coordinator, importing and registering 
domain routers while handling core app configuration.
"""

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Dict, Any
from pathlib import Path

from fastapi import FastAPI, Cookie, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Import domain routers
from registry.auth.routes import router as auth_router
from registry.api.server_routes import router as servers_router
from registry.api.wellknown_routes import router as wellknown_router
from registry.api.registry_routes import router as registry_router
from registry.health.routes import router as health_router

# Import auth dependencies
from registry.auth.dependencies import enhanced_auth

# Import services for initialization
from registry.services.server_service import server_service
from registry.search.service import faiss_service
from registry.health.service import health_service
from registry.core.nginx_service import nginx_service

# Import core configuration
from registry.core.config import settings

# Configure logging with file and console handlers
def setup_logging():
    """Configure logging to write to both file and console."""
    # Ensure log directory exists
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Define log file path
    log_file = log_dir / "registry.log"
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s'
    )
    
    console_formatter = logging.Formatter(
        '%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s'
    )
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    
    # Add handlers to root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return log_file

# Setup logging
log_file_path = setup_logging()
logger = logging.getLogger(__name__)
logger.info(f"Logging configured. Writing to file: {log_file_path}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle management."""
    logger.info("🚀 Starting MCP Gateway Registry...")
    
    try:
        # Initialize services in order
        logger.info("📚 Loading server definitions and state...")
        server_service.load_servers_and_state()
        
        logger.info("🔍 Initializing FAISS search service...")
        await faiss_service.initialize()
        
        logger.info("📊 Updating FAISS index with all registered services...")
        all_servers = server_service.get_all_servers()
        for service_path, server_info in all_servers.items():
            is_enabled = server_service.is_service_enabled(service_path)
            try:
                await faiss_service.add_or_update_service(service_path, server_info, is_enabled)
                logger.debug(f"Updated FAISS index for service: {service_path}")
            except Exception as e:
                logger.error(f"Failed to update FAISS index for service {service_path}: {e}", exc_info=True)
        
        logger.info(f"✅ FAISS index updated with {len(all_servers)} services")
        
        logger.info("🏥 Initializing health monitoring service...")
        await health_service.initialize()
        
        logger.info("🌐 Generating initial Nginx configuration...")
        enabled_servers = {
            path: server_service.get_server_info(path) 
            for path in server_service.get_enabled_services()
        }
        await nginx_service.generate_config_async(enabled_servers)
        
        logger.info("✅ All services initialized successfully!")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}", exc_info=True)
        raise
    
    # Application is ready
    yield
    
    # Shutdown tasks
    logger.info("🔄 Shutting down MCP Gateway Registry...")
    try:
        # Shutdown services gracefully
        await health_service.shutdown()
        logger.info("✅ Shutdown completed successfully!")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}", exc_info=True)


# Create FastAPI application
app = FastAPI(
    title="MCP Gateway Registry",
    description="A registry and management system for Model Context Protocol (MCP) servers",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for React development and Docker deployment
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost(:[0-9]+)?|.*\.compute.*\.amazonaws\.com(:[0-9]+)?)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register API routers with /api prefix
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(servers_router, prefix="/api", tags=["Server Management"])
app.include_router(health_router, prefix="/api/health", tags=["Health Monitoring"])

# Register Anthropic MCP Registry API (public API)
app.include_router(registry_router, tags=["Anthropic Registry API"])

# Register well-known discovery router
app.include_router(wellknown_router, prefix="/.well-known", tags=["Discovery"])

# Add user info endpoint for React auth context
@app.get("/api/auth/me")
async def get_current_user(user_context: Dict[str, Any] = Depends(enhanced_auth)):
    """Get current user information for React auth context"""
    # Return user info with scopes for token generation
    return {
        "username": user_context["username"],
        "auth_method": user_context.get("auth_method", "basic"),
        "provider": user_context.get("provider"),
        "scopes": user_context.get("scopes", []),
        "groups": user_context.get("groups", []),
        "can_modify_servers": user_context.get("can_modify_servers", False),
        "is_admin": user_context.get("is_admin", False)
    }

# Basic health check endpoint
@app.get("/health")
async def health_check():
    """Simple health check for load balancers and monitoring."""
    return {"status": "healthy", "service": "mcp-gateway-registry"}

# Serve React static files
FRONTEND_BUILD_PATH = Path(__file__).parent.parent / "frontend" / "build"

if FRONTEND_BUILD_PATH.exists():
    # Serve static assets
    app.mount("/static", StaticFiles(directory=FRONTEND_BUILD_PATH / "static"), name="static")
    
    # Serve React app for all other routes (SPA)
    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        """Serve React app for all non-API routes"""
        # Import here to avoid circular dependency
        from registry.constants import REGISTRY_CONSTANTS

        # Don't serve React for API routes, Anthropic registry API, health checks, and well-known discovery endpoints
        anthropic_api_prefix = f"{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/"
        if full_path.startswith("api/") or full_path.startswith(anthropic_api_prefix) or full_path.startswith("health") or full_path.startswith(".well-known/"):
            raise HTTPException(status_code=404)

        return FileResponse(FRONTEND_BUILD_PATH / "index.html")
else:
    logger.warning("React build directory not found. Serve React app separately during development.")
    
    # Serve legacy templates and static files during development
    from fastapi.templating import Jinja2Templates
    app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
    templates = Jinja2Templates(directory=settings.templates_dir)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "registry.main:app", 
        host="0.0.0.0", 
        port=7860, 
        reload=True,
        log_level="info"
    ) 