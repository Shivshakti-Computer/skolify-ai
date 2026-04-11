# api/config.py

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):

    BASE_DIR: Path = Path(__file__).parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    CHROMA_DB_PATH: Path = BASE_DIR / "data" / "chroma_db"
    CONVERSATIONS_DB: Path = BASE_DIR / "data" / "conversations.db"

    API_TITLE: str = "Skolify AI"
    API_VERSION: str = "3.0.0"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 7860

    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "https://skolify.in",
        "https://www.skolify.in",
        "https://*.vercel.app",
        "https://*.hf.space",
        "https://huggingface.co",
    ]

    NEXTJS_URL: str = os.environ.get("NEXTJS_URL", "http://localhost:3000")

    EMBEDDING_MODEL: str = "paraphrase-MiniLM-L3-v2"
    VECTOR_COLLECTION_NAME: str = "skolify_public_kb"
    TOP_K_RESULTS: int = 5
    MIN_SIMILARITY_SCORE: float = 0.05

    # ══════════════════════════════════════════════════════
    # 🚀 OPTIMIZED LLM STRATEGY (2026)
    # ══════════════════════════════════════════════════════
    
    # ── GROQ (Primary - Multiple Models by Use Case) ─────
    GROQ_API_KEY: str = ""
    
    # Public Chat - Fastest + Highest Daily Limit
    GROQ_PUBLIC_MODEL: str = "llama-3.1-8b-instant"
    # RPM: 30, RPD: 14,400, TPM: 6K, TPD: 500K
    
    # Portal Chat - Better Quality
    GROQ_PORTAL_MODEL: str = "llama-3.3-70b-versatile"
    # RPM: 30, RPD: 1,000, TPM: 12K, TPD: 100K
    
    # Admin Commands - Unlimited Tokens
    GROQ_ADMIN_MODEL: str = "groq/compound"
    # RPM: 30, RPD: 250, TPM: 70K, TPD: UNLIMITED
    
    # Fallback - High Quality
    GROQ_FALLBACK_MODEL: str = "llama-3.3-70b-versatile"
    
    # ── GEMINI (Secondary - When Groq Exhausted) ──────────
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash-exp"
    # Free experimental, but has daily limits
    
    # ── OPENROUTER (Tertiary) ─────────────────────────────
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "google/gemini-2.0-flash-exp:free"
    
    # ── DEEPSEEK (Quality Fallback - Paid but Cheap) ──────
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    # $0.14 per 1M tokens
    
    # ── HUGGINGFACE (Last Resort - Slow but Free) ─────────
    HF_API_KEY: str = ""
    HF_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
    
    # ── PROVIDER PRIORITY BY USE CASE ─────────────────────
    # Public website chat (high volume, simple queries)
    PUBLIC_LLM_PROVIDER_ORDER: str = "groq_public,gemini,openrouter"
    
    # Portal chat (authenticated users, complex queries)
    PORTAL_LLM_PROVIDER_ORDER: str = "groq_portal,groq_admin,gemini,deepseek"
    
    # Admin commands (very long prompts, tool calls)
    ADMIN_LLM_PROVIDER_ORDER: str = "groq_admin,groq_portal,deepseek"
    
    # ── RESPONSE CACHING ──────────────────────────────────
    ENABLE_RESPONSE_CACHE: bool = True
    
    # Public chat - longer cache (queries repeat often)
    PUBLIC_CACHE_TTL_SECONDS: int = 3600  # 1 hour
    
    # Portal chat - shorter cache (data changes)
    PORTAL_CACHE_TTL_SECONDS: int = 300   # 5 minutes
    
    # Tool responses - very short cache
    TOOL_CACHE_TTL_SECONDS: int = 120     # 2 minutes
    
    # ── RATE LIMITING ─────────────────────────────────────
    GROQ_MAX_RETRIES: int = 1
    FALLBACK_DELAY_MS: int = 100
    
    # Track Groq rate limits
    GROQ_TRACK_RATE_LIMITS: bool = True
    GROQ_RPM_LIMIT: int = 30
    GROQ_RPM_WARNING_THRESHOLD: float = 0.8  # Switch at 80%

    MAX_TOKENS: int = 500
    TEMPERATURE: float = 0.65

    MAX_HISTORY_PAIRS: int = 6
    CONVERSATION_EXPIRY_HOURS: int = 24
    
    PORTAL_MAX_HISTORY_PAIRS: int = 8
    PORTAL_CONVERSATION_EXPIRY_HOURS: int = 72

    CONV_STORAGE: str = "sqlite"
    TURSO_DATABASE_URL: str = ""
    TURSO_AUTH_TOKEN: str = ""

    ADMIN_API_KEY: str = "change-this-in-production"
    APP_ENV: str = os.environ.get("APP_ENV", "production")
    ENABLE_PORTAL_MODE: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()