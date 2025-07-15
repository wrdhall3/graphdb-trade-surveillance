import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time
from datetime import datetime

# Import your route modules
from .routes import auth, dashboard, patterns, agents, nlp
from pattern_detection.adaptive_detectors import adaptive_detector
from agents.surveillance_agent import surveillance_agent

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    # Startup
    logger.info("🚀 Starting GraphDB Trade Surveillance Backend...")
    start_time = time.time()
    
    try:
        # Initialize pattern detection
        logger.info("📊 Initializing pattern detection system...")
        adaptive_detector._initialize_schema()
        logger.info("✅ Pattern detection system initialized")
        
        # Initialize surveillance agent
        logger.info("🤖 Initializing surveillance agent...")
        surveillance_agent.initialize()
        logger.info("✅ Surveillance agent initialized")
        
        startup_time = time.time() - start_time
        logger.info(f"✅ Backend startup completed in {startup_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"❌ Backend startup failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down GraphDB Trade Surveillance Backend...")

# Create FastAPI app with lifespan
app = FastAPI(
    title="GraphDB Trade Surveillance API",
    description="API for detecting suspicious trading patterns using GraphDB and AI",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "message": "GraphDB Trade Surveillance API is running"
    }

# Add startup completion endpoint
@app.get("/ready")
async def ready_check():
    """Ready check endpoint - indicates backend is fully initialized"""
    return {
        "status": "ready",
        "timestamp": datetime.now().isoformat(),
        "message": "Backend is ready to serve requests"
    }

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(patterns.router, prefix="/api/patterns", tags=["patterns"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(nlp.router, prefix="/api/nlp", tags=["nlp"])

@app.get("/")
async def root():
    return {"message": "GraphDB Trade Surveillance API", "status": "running"}

if __name__ == "__main__":
    logger.info("Starting development server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")