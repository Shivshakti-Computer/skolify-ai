# api/config.py

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
    API_PORT: int = 8000

    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "https://skolify.in",
        "https://www.skolify.in",
    ]

    # ✅ Sabse chhota model - sirf 30MB RAM
    EMBEDDING_MODEL: str = "paraphrase-MiniLM-L3-v2"
    VECTOR_COLLECTION_NAME: str = "skolify_public_kb"
    TOP_K_RESULTS: int = 5
    MIN_SIMILARITY_SCORE: float = 0.20

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    MAX_TOKENS: int = 500
    TEMPERATURE: float = 0.65

    MAX_HISTORY_PAIRS: int = 6
    CONVERSATION_EXPIRY_HOURS: int = 24

    CONV_STORAGE: str = "sqlite"
    TURSO_DATABASE_URL: str = ""
    TURSO_AUTH_TOKEN: str = ""

    ADMIN_API_KEY: str = "change-this-in-production"
    APP_ENV: str = "development"
    ENABLE_PORTAL_MODE: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()