# api/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from .config import settings
from .routes import chat, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print(f"  🚀 {settings.API_TITLE} v{settings.API_VERSION}")
    print(f"  🌍 Environment: {settings.APP_ENV}")
    print("=" * 50)

    from .dependencies import (
        get_embedding_model,
        get_collection,
        get_groq_client,
        get_conv_store,
        reset_collection,
    )

    # ── Step 1: Production mein ChromaDB rebuild check ──
    # Local dev mein skip (already built)
    if settings.APP_ENV == "production":
        print("🔍 Production mode — checking ChromaDB...")
        try:
            from scripts.build_on_startup import run as rebuild_check
            await asyncio.to_thread(rebuild_check)
        except Exception as e:
            print(f"⚠️  Startup rebuild error: {e}")
            print("   API will use fallback responses only")
        
        # Rebuild ke baad collection reset karo
        # Taaki naya data load ho
        reset_collection()

    # ── Step 2: Embedding Model ──────────────────────────
    try:
        get_embedding_model()
    except Exception as e:
        print(f"⚠️  Embedding model error: {e}")

    # ── Step 3: Vector DB (ChromaDB) ──���──────────────────
    try:
        get_collection()
    except Exception as e:
        print(f"⚠️  Vector DB: {e}")
        if settings.APP_ENV != "production":
            print("   Run: python -m scripts.build_vector_db")

    # ── Step 4: Groq LLM ─────────────────────────────────
    groq = get_groq_client()
    if not groq.is_configured():
        print("⚠️  Groq not configured!")
        print("   Get free key: console.groq.com")
        print("   Add GROQ_API_KEY to .env / Render environment")
        print("   (Smart fallback responses will be used)")

    # ── Step 5: Conversation Storage ─────────────────────
    # Dev = SQLite local
    # Production = Turso cloud (free)
    try:
        store = get_conv_store()
        stats = store.get_stats()
        print(f"✅ Storage: {settings.CONV_STORAGE.upper()}")
        print(f"   Conversations: {stats.get('total', 0)}")
    except Exception as e:
        print(f"⚠️  Conversation store error: {e}")

    # ── Ready ─────────────────────────────────────────────
    print("=" * 50)
    print("  ✅ API Ready!")
    if settings.APP_ENV != "production":
        print(f"  📖 Docs: http://localhost:{settings.API_PORT}/docs")
    print("=" * 50)

    yield

    # ── Shutdown ──────────────────────────────────────────
    print("👋 Shutting down...")


# ── App Instance ──────────────────────────────────────────
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    lifespan=lifespan,
    # Production mein docs disable karo (optional security)
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url=None,
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Vercel preview URLs automatically allow
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────
app.include_router(chat.router)
app.include_router(admin.router)


# ── Root ──────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "name": settings.API_TITLE,
        "version": settings.API_VERSION,
        "status": "running",
        # Production mein docs link nahi
        **({"docs": "/docs"} if settings.APP_ENV != "production" else {}),
    }


if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=port,
    )