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

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    groq_audio_model: str = "whisper-large-v3-turbo"

    max_words: int = 0
    request_timeout: float = 120.0
    rate_limit_per_minute: int = 20
    cache_size: int = 48
    chunk_words: int = 1400

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key and self.groq_api_key.strip())

    @property
    def llm_configured(self) -> bool:
        return self.groq_configured

    @property
    def active_model(self) -> str:
        return self.groq_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
