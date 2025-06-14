"""
Company Information API - Main Application

This is the main FastAPI application entry point that:
1. Configures the FastAPI app with CORS middleware
2. Registers domain-specific routers
3. Serves static files and infrastructure endpoints
4. Handles WebSocket connections for real-time updates

Domain routers are organized by business functionality:
- /api/descriptions/* - Company description generation
- /api/criteria/* - Company criteria analysis  
- /api/integrations/clay/* - Clay integration services
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import uvicorn

# Import domain routers
from .api.descriptions import router as descriptions_router
from .api.criteria import router as criteria_router
from .api.integrations.clay.routes import router as clay_router

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Company Information API",
    description="API for finding company information and generating descriptions.",
    version="1.0.0"
)

# --- CORS Middleware Configuration ---
origins = [
    "http://localhost",         # Base origin
    "http://localhost:8001",    # Default port for python -m http.server
    "http://127.0.0.1",
    "http://127.0.0.1:8001",
    # Add other origins if needed (e.g., http://localhost:3000 for React dev server)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register Domain Routers ---
app.include_router(descriptions_router, prefix="/api")  # /api/descriptions/*
app.include_router(criteria_router, prefix="/api")      # /api/criteria/*
app.include_router(clay_router, prefix="/api")          # /api/integrations/clay/*

# --- Static Files ---
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# --- WebSocket Support ---
# Store active WebSocket connections for real-time updates
active_connections: list[WebSocket] = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates during processing"""
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)

async def broadcast_update(data: dict):
    """Broadcast update to all connected WebSocket clients"""
    for connection in active_connections:
        try:
            await connection.send_json(data)
        except:
            # Remove dead connections
            if connection in active_connections:
                active_connections.remove(connection)

# --- Infrastructure Endpoints ---

@app.get("/")
async def read_root():
    """Serve the main application page"""
    return FileResponse("frontend/index.html")

@app.get("/style.css")
async def read_css():
    """Serve the main CSS file"""
    return FileResponse("frontend/style.css")

# --- Application Lifecycle ---

@app.on_event("shutdown")
async def app_shutdown():
    """Handle graceful application shutdown"""
    logger.info("Application shutdown initiated.")
    # Close any remaining WebSocket connections
    for connection in active_connections:
        try:
            await connection.close()
        except:
            pass
    active_connections.clear()
    logger.info("Shutdown completed.")

# --- Development Server ---

if __name__ == "__main__":
    # This is for local development testing
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True) 