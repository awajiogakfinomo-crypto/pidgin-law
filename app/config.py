from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Pidgin Law"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-4.5"

    max_words: int = 0
    request_timeout: float = 120.0
    rate_limit_per_minute: int = 20
    cache_size: int = 48
    chunk_words: int = 1400

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.strip())

    @property
    def llm_configured(self) -> bool:
        return self.gemini_configured or bool(self.xai_api_key and self.xai_api_key.strip())

    @property
    def active_model(self) -> str:
        return self.gemini_model if self.gemini_configured else self.xai_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
