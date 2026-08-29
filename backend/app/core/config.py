from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "my-web-backend"
    DEBUG: bool = False

    DATABASE_URL: str = Field(min_length=1)
    JWT_SECRET_KEY: str = Field(min_length=1)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    CORS_ORIGINS: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    # LLM (OpenAI-compatible provider)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""
    LLM_TIMEOUT: float = 30.0

    # Embeddings (OpenAI-compatible provider)
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_MODEL: str = ""
    EMBEDDING_TIMEOUT: float = 30.0

    RAG_UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    RAG_MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 150
    RAG_MAX_CONTEXT_CHARS: int = 12000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
