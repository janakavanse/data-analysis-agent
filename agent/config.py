from functools import lru_cache
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")
    llm_provider: str = "google_genai"
    llm_model: str = "gemini-2.5-flash"
    llm_api_key: SecretStr = SecretStr("")
    database_url: str = "sqlite+aiosqlite:///./agent.db"
    port: int = 8001
    max_iterations: int = 10
    price_in: float = 0.075    # USD per 1M input tokens (gemini-2.5-flash)
    price_out: float = 0.30    # USD per 1M output tokens (gemini-2.5-flash)

    @field_validator("llm_provider", "llm_model", "database_url", mode="before")
    @classmethod
    def _strip_inline_comment(cls, v):
        if isinstance(v, str):
            return v.split(" #", 1)[0].strip()
        return v

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def _clean_secret(cls, v):
        return v.split(" #", 1)[0].strip() if isinstance(v, str) else v


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_required_config() -> None:
    """Fail LOUD at boot if required config is missing."""
    s = get_settings()
    missing = []
    if not s.llm_api_key.get_secret_value():
        missing.append("APP_LLM_API_KEY")
    if not s.llm_model:
        missing.append("APP_LLM_MODEL")
    if missing:
        raise RuntimeError(f"missing required config: {', '.join(missing)} — set them in .env (see README).")
