"""
Application settings for Safebot.

Reads all configuration from environment variables or a .env file
via pydantic-settings. A single module-level `settings` singleton
is created so every module imports the same object.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: str

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 15
    refresh_token_ttl_days: int = 7
    refresh_token_length: int = 48

    # Algorand
    algorand_app_id: int = 0
    algorand_mnemonic: str = ""
    algorand_network: str = "testnet"
    algorand_node_url: str = "https://testnet-api.4160.nodely.dev"
    algorand_api_token: str = ""

    # Sentry
    sentry_dsn: str = ""

    # App
    environment: str = "development"
    debug: bool = False
    rate_limit_per_minute: int = 60
    perf_trace_enabled: bool = False
    perf_trace_sample_rate: float = 0.1
    api_key_verify_cache_ttl_seconds: int = 60
    api_key_verify_cache_max_entries: int = 10000

    # Password reset
    password_reset_token_ttl_seconds: int = 900  # 15 minutes
    frontend_url: str = "http://localhost:5173"

    # CORS — comma-separated origins or JSON array string
    # Example: CORS_ORIGINS='["https://app.example.com"]'
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()
