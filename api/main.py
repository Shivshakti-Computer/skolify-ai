# api/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import os
from .config import settings
from .routes import chat, admin, portal_chat

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 60)
    print(f"  🚀 {settings.API_TITLE} v{settings.API_VERSION}")
    print(f"  🌍 Environment: {settings.APP_ENV}")
    print(f"  🔌 PORT: {os.environ.get('PORT', 7860)}")
    print(f"  🌐 Next.js: {settings.NEXTJS_URL}")
    print("=" * 60)

    from .dependencies import (
        get_embedding_model,
        get_collection,
        get_llm_manager,      # ✅ Changed from get_groq_client
        get_conv_store,
        reset_collection,
    )

    # ── ChromaDB Rebuild (Production only) ────────────────
    if settings.APP_ENV == "production":
        print("🔍 Checking ChromaDB...")
        try:
            from scripts.build_on_startup import run as rebuild_check
            await asyncio.to_thread(rebuild_check)
            reset_collection()
        except Exception as e:
            # ⚠️ Non-blocking - fallback responses will work
            print(f"⚠️  ChromaDB rebuild skipped: {e}")

    # ── Embedding Model ────────────────────────────────────
    try:
        get_embedding_model()
    except Exception as e:
        print(f"⚠️  Embedding model: {e}")

    # ── Vector DB ──────────────────────────────────────────
    try:
        col = get_collection()
        if col:
            print(f"✅ Vector DB: {col.count()} documents")
        else:
            print("⚠️  Vector DB: unavailable (will use fallbacks)")
    except Exception as e:
        print(f"⚠️  Vector DB: {e}")

    # ── LLM Providers (2025 Multi-Provider) ───────────────
    try:
        llm = get_llm_manager()
        
        configured = [
            name for name in llm.provider_order 
            if llm.providers[name].is_configured()
        ]
        
        if configured:
            print(f"✅ LLM Providers: {', '.join(configured)}")
        else:
            print("⚠️  No LLM configured - template fallbacks only")
            
    except Exception as e:
        print(f"⚠️  LLM Manager: {e}")

    # ── Conversation Storage ───────────────────────────────
    try:
        store = get_conv_store()
        stats = store.get_stats()
        storage_type = stats.get('storage', settings.CONV_STORAGE)
        
        print(f"✅ Storage: {storage_type.upper()}")
        print(f"   Total conversations: {stats.get('total', 0)}")
        print(f"   Active (last hour): {stats.get('active_last_hour', 0)}")
        
    except Exception as e:
        print(f"⚠️  Conversation store: {e}")

    print("=" * 60)
    print("  ✅ API Ready!")
    print("=" * 60)

    yield

    print("\n👋 Shutting down gracefully...")


# ════════════════════════════════════════════════
# APP INITIALIZATION
# ════════════════════════════════════════════════

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
)

# ════════════════════════════════════════════════
# CORS MIDDLEWARE
# ════════════════════════════════════════════════

# ✅ UPDATED: Explicit skolify.in domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://skolify.in",           # ✅ Your production domain
        "https://www.skolify.in",       # ✅ WWW variant
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",  # Vercel previews
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════

app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(portal_chat.router)


# ════════════════════════════════════════════════
# ROOT ENDPOINT
# ════════════════════════════════════════════════

@app.get("/")
async def root():
    """API root - health check"""
    return {
        "name": settings.API_TITLE,
        "version": settings.API_VERSION,
        "status": "running",
        "environment": settings.APP_ENV,
        "docs": "/docs" if settings.APP_ENV != "production" else "disabled",
    }


@app.get("/ping")
async def ping():
    """Simple ping endpoint for monitoring"""
    return {"status": "ok", "timestamp": __import__("datetime").datetime.now().isoformat()}


# ════════════════════════════════════════════════
# MAIN (for local development)
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    
    # ✅ HuggingFace/Render auto-set PORT env
    port = int(os.environ.get("PORT", 7860))
    
    print(f"\n🚀 Starting {settings.API_TITLE} on port {port}...")
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.APP_ENV != "production",
        log_level="info",
    )