"""
utils/config.py
---------------
Centralised settings loaded from environment variables / .env file.
All other modules import from here — never import os.environ directly.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    gemini_api_key: str
    judge_model: str = "gemini-2.5-flash"
    twin_model: str = "gemini-2.5-flash"
    challenger_model: str = "gemini-2.5-flash"

    # ChromaDB
    chroma_persist_dir: str = "./chroma_store"
    chroma_collection_name: str = "debate_twin_personas"

    # Debate
    max_debate_rounds: int = 3

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # API
    cors_origins: str = "http://localhost:3000"

    # Logging
    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
