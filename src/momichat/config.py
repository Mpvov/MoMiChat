import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "MoMiChat"
    VERSION: str = "0.1.0"
    DEBUG: bool = True
    
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    DATABASE_URL: str
    REDIS_URL: str
    
    DEFAULT_LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    HF_TOKEN: str = ""
    
    PAYOS_CLIENT_ID: str = ""
    PAYOS_API_KEY: str = ""
    PAYOS_CHECKSUM_KEY: str = ""
    
    TELEGRAM_BOT_TOKEN: str = ""
    OWNER_CHAT_ID: str = ""
    FASTAPI_INTERNAL_URL: str = ""
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


