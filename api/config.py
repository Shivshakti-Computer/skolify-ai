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
    API_VERSION: str = "2.0.0"
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
    # 🎯 LLM PROVIDERS (2025 Best Free Options)
    # ══════════════════════════════════════════════════════
    
    # 1️⃣ Groq (Fastest, good free tier)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    # Free: 30 RPM, 14,400 RPD
    
    # 2️⃣ Gemini 2.0 (Latest, very capable)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash-exp"
    # Free experimental: Unlimited till Feb 2025
    # Fallback: "gemini-1.5-flash" (15 RPM, 1500 RPD)
    
    # 3️⃣ OpenRouter (100+ models, one API)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "google/gemini-2.0-flash-exp:free"
    # Many free models available
    
    # 4️⃣ DeepSeek (Best value, very cheap)
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    # $0.14 per 1M tokens (99% cheaper than GPT-4)
    
    # 5️⃣ Hugging Face (Unlimited free)
    HF_API_KEY: str = ""
    HF_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
    # Unlimited requests, slower cold start
    
    # Provider order (comma-separated)
    LLM_PROVIDER_ORDER: str = "groq,gemini,openrouter,deepseek,huggingface"

    # ── Rate Limiting & Caching ───────────────────────────
    ENABLE_RESPONSE_CACHE: bool = True
    CACHE_TTL_SECONDS: int = 300
    GROQ_MAX_RETRIES: int = 1
    FALLBACK_DELAY_MS: int = 100

    MAX_TOKENS: int = 500
    TEMPERATURE: float = 0.65

    MAX_HISTORY_PAIRS: int = 6
    CONVERSATION_EXPIRY_HOURS: int = 24

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