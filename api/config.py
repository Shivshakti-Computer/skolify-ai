# api/config.py

from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):

    # ─── Paths ───────────────────────────────────
    BASE_DIR: Path = Path(__file__).parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    CHROMA_DB_PATH: Path = BASE_DIR / "data" / "chroma_db"
    CONVERSATIONS_DB: Path = BASE_DIR / "data" / "conversations.db"

    # ─── API ─────────────────────────────────────
    API_TITLE: str = "Skolify AI"
    API_VERSION: str = "2.0.0"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # ─── CORS ─────────────────────────────────────
    # Vercel URLs + localhost
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "https://skolify.in",
        "https://www.skolify.in",
        # Vercel preview URLs ke liye
        "https://*.vercel.app",
    ]

    # ─── Vector DB ────────────────────────────────
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    VECTOR_COLLECTION_NAME: str = "skolify_public_kb"
    TOP_K_RESULTS: int = 5
    MIN_SIMILARITY_SCORE: float = 0.20

    # ─── Groq LLM (FREE - No data sharing) ───────
    # Sign up: console.groq.com (free)
    # Aapka data train nahi hota
    GROQ_API_KEY: str = ""
    # Best free models:
    # llama-3.3-70b-versatile - Best quality (free)
    # llama-3.1-8b-instant    - Fastest (free)  
    # mixtral-8x7b-32768      - Good (free)
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Generation
    MAX_TOKENS: int = 500
    TEMPERATURE: float = 0.65

    # ─── Conversation ─────────────────────────────
    MAX_HISTORY_PAIRS: int = 6
    CONVERSATION_EXPIRY_HOURS: int = 24

    # ─── Security ─────────────────────────────────
    ADMIN_API_KEY: str = "change-this-in-production"

    # ─── App ──────────────────────────────────────
    APP_ENV: str = "development"

    # Future: School Portal
    # Jab portal integration karoge tab ye use hoga
    ENABLE_PORTAL_MODE: bool = False
    PORTAL_SECRET_KEY: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()