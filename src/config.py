"""Configuration management."""

from typing import Optional
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = ""
    serper_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    zai_api_key: Optional[str] = None
    pollinations_referrer: str = "vektorflow-ai"
    gcp_project_id: Optional[str] = None
    gcp_dataset_id: str = "vektorflow_shop"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    jwt_secret: str = "vektorflow_jwt_secret_change_me"
    security_salt: str = "vektorflow_salt_2026"
    jwt_expiry_minutes: int = 1440
    encryption_key: Optional[str] = None
    shopify_store_url: Optional[str] = None
    shopify_access_token: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()