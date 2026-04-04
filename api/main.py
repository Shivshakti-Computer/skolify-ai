# api/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import os
from .config import settings
from .routes import chat, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print(f"  🚀 {settings.API_TITLE} v{settings.API_VERSION}")
    print(f"  🌍 Environment: {settings.APP_ENV}")
    print(f"  🔌 PORT: {os.environ.get('PORT', 'not set')}")
    print("=" * 50)

    from .dependencies import (
        get_embedding_model,
        get_collection,
        get_groq_client,
        get_conv_store,
        reset_collection,
    )

    # ChromaDB rebuild - production only
    if settings.APP_ENV == "production":
        print("🔍 Checking ChromaDB...")
        try:
            from scripts.build_on_startup import run as rebuild_check
            await asyncio.to_thread(rebuild_check)
            reset_collection()
        except Exception as e:
            # ⚠️ Crash mat karo - fallback responses chalenge
            print(f"⚠️  ChromaDB rebuild skipped: {e}")

    # Embedding model
    try:
        get_embedding_model()
    except Exception as e:
        print(f"⚠️  Embedding model: {e}")

    # Vector DB
    try:
        get_collection()
    except Exception as e:
        print(f"⚠️  Vector DB: {e}")

    # Groq
    try:
        groq = get_groq_client()
        if not groq.is_configured():
            print("⚠️  Groq not configured - fallbacks will be used")
    except Exception as e:
        print(f"⚠️  Groq: {e}")

    # Conversation store
    try:
        store = get_conv_store()
        stats = store.get_stats()
        print(f"✅ Storage: {settings.CONV_STORAGE.upper()}")
        print(f"   Conversations: {stats.get('total', 0)}")
    except Exception as e:
        print(f"⚠️  Conv store: {e}")

    print("=" * 50)
    print("  ✅ API Ready!")
    print("=" * 50)

    yield

    print("👋 Shutting down...")


# App
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url=None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(chat.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {
        "name": settings.API_TITLE,
        "version": settings.API_VERSION,
        "status": "running",
    }


# ✅ Direct run ke liye
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    print(f"Starting on port: {port}")
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )