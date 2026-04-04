# api/config.py

from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Project paths
    BASE_DIR: Path = Path(__file__).parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    CHROMA_DB_PATH: Path = DATA_DIR / "chroma_db"
    
    # API settings
    API_TITLE: str = "Skolify AI API"
    API_VERSION: str = "1.0.0"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # CORS settings
    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:3001",
        "https://skolify.in",
        "https://www.skolify.in"
    ]
    
    # AI settings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    VECTOR_COLLECTION_NAME: str = "skolify_public_kb"
    TOP_K_RESULTS: int = 5
    MIN_SIMILARITY_SCORE: float = 0.3
    
    # Admin settings
    ADMIN_API_KEY: str = "skolify-ai-admin-2024-secret-key"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()