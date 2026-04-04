# api/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
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
    )

    try:
        get_embedding_model()
    except Exception as e:
        print(f"⚠️  Embedding: {e}")

    try:
        get_collection()
    except Exception as e:
        print(f"⚠️  Vector DB: {e}")
        print("   Run: python -m scripts.build_vector_db")

    groq = get_groq_client()
    if not groq.is_configured():
        print("⚠️  Groq not configured!")
        print("   1. Get free key: console.groq.com")
        print("   2. Add GROQ_API_KEY to .env")
        print("   (Fallback responses will be used)")

    get_conv_store()

    print("=" * 50)
    print("  ✅ API Ready!")
    print(f"  📖 Docs: http://localhost:{settings.API_PORT}/docs")
    print("=" * 50)

    yield

    print("👋 Shutting down...")


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    lifespan=lifespan,
)

# CORS — allows Vercel + localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {
        "name": settings.API_TITLE,
        "version": settings.API_VERSION,
        "status": "running",
        "docs": "/docs",
    }