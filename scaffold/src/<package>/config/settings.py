from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",   # replace APP_ with your agent's prefix
        env_file=".env",
        case_sensitive=False,
        extra="ignore",      # .env may contain vars we don't own — see code-style.md
    )

    database_url: str = Field(...)
    anthropic_api_key: str = Field(default="")
    llm_model: str = Field(default="claude-sonnet-4-6")  # source of truth: tech-stack.md § Models
    log_level: str = Field(default="INFO")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
