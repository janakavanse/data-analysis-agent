from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")
    llm_provider: str = "google_genai"
    llm_model: str = "gemini-2.5-pro"
    llm_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./agent.db"
    port: int = 8001
    max_iterations: int = 10
    # Gemini 2.5 Pro pricing per 1M tokens (verify at ai.google.dev)
    cost_per_1m_input: float = 1.25
    cost_per_1m_output: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
