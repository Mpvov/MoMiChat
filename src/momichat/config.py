import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "MoMiChat"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    DATABASE_URL: str
    REDIS_URL: str
    
    DEFAULT_LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEYS: str = ""  # Comma separated list of keys for fallback
    GEMINI_MODELS: str = "gemini-3.1-flash-lite-preview" # Comma separated models
    OPENAI_API_KEY: str = ""
    HF_TOKEN: str = ""
    
    OLLAMA_BASE_URL: str = ""
    OLLAMA_MODEL: str = "llama3"
    
    @property
    def gemini_keys_list(self) -> list[str]:
        """Parsed list of Gemini keys from comma-separated string."""
        if not self.GEMINI_API_KEYS:
            return []
        return [k.strip() for k in self.GEMINI_API_KEYS.split(",") if k.strip()]

    @property
    def gemini_models_list(self) -> list[str]:
        """Parsed list of Gemini models from comma-separated string."""
        if not self.GEMINI_MODELS:
            return ["gemini-3.1-flash-lite-preview"]
        return [m.strip() for m in self.GEMINI_MODELS.split(",") if m.strip()]

    PAYOS_CLIENT_ID: str = ""
    PAYOS_API_KEY: str = ""
    PAYOS_CHECKSUM_KEY: str = ""
    
    TELEGRAM_BOT_TOKEN: str = ""
    OWNER_CHAT_ID: str = ""
    FASTAPI_INTERNAL_URL: str = ""
    APP_BASE_URL: str = "http://localhost:8080"  # ngrok/domain URL for PayOS callbacks
    SECRET_KEY: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()

if settings.HF_TOKEN:
    os.environ["HF_TOKEN"] = settings.HF_TOKEN

if settings.TELEGRAM_BOT_TOKEN:
    os.environ["TELEGRAM_BOT_TOKEN"] = settings.TELEGRAM_BOT_TOKEN

if settings.OWNER_CHAT_ID:
    os.environ["OWNER_CHAT_ID"] = settings.OWNER_CHAT_ID

if settings.FASTAPI_INTERNAL_URL:
    os.environ["FASTAPI_INTERNAL_URL"] = settings.FASTAPI_INTERNAL_URL


