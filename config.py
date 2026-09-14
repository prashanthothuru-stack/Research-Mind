from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    app_name: str = "ResearchMind"
    secret_key: str = "dev-only-change-me"
    cors_origins: str = "http://localhost:5173"

    llm_provider: str = "auto"  # auto | groq | ollama | openai | none
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    embedding_dim: int = 384
    max_sources: int = 12
    max_fetch: int = 6

    sqlite_path: str = str(ROOT / "data" / "researchmind.db")


@lru_cache
def get_settings() -> Settings:
    return Settings()
