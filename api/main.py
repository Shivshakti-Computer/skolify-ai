# api/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config import settings
from .routes import chat, admin

# ══════════════════════════════════════════════════════════
# Lifespan event handler (replaces deprecated on_event)
# ══════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("=" * 50)
    print(f"🚀 {settings.API_TITLE} v{settings.API_VERSION}")
    print("=" * 50)
    
    from .dependencies import get_embedding_model, get_collection
    
    try:
        get_embedding_model()
        get_collection()
        print("✅ All systems ready")
    except Exception as e:
        print(f"⚠️  Warning: {e}")
        print("Run build_vector_db.py first if this is a fresh setup")
    
    print("=" * 50)
    
    yield
    
    # Shutdown
    print("\n👋 Shutting down...")

# ══════════════════════════════════════════════════════════
# Create app
# ══════════════════════════════════════════════════════════

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="AI-powered chat API for Skolify website",
    lifespan=lifespan
)

# ══════════════════════════════════════════════════════════
# CORS middleware
# ══════════════════════════════════════════════════════════

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════
# Include routers
# ══════════════════════════════════════════════════════════

app.include_router(chat.router)
app.include_router(admin.router)

# ══════════════════════════════════════════════════════════
# Root endpoint
# ══════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "message": "Skolify AI API",
        "version": settings.API_VERSION,
        "status": "running",
        "docs": "/docs"
    }

# ══════════════════════════════════════════════════════════
# Run with uvicorn
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True
    )