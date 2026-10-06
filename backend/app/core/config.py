"""
Application settings, loaded from environment variables and .env file.

Pydantic Settings reads env vars, validates types at startup, and fails fast
if something is misconfigured.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",          # reads backend/.env when running from backend/
        env_file_encoding="utf-8",
        extra="ignore",           # ignore unrelated env vars
        case_sensitive=False,     # POSTGRES_USER == postgres_user
    )

    # --- App ---
    app_name: str = "AgriTech API"
    app_env: str = "dev"
    debug: bool = True

    # --- Postgres ---
    postgres_user: str = "agritech"
    postgres_password: str = "devpassword"
    postgres_db: str = "agritech"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        """Build the SQLAlchemy connection URL from the individual parts."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Auth ---
    jwt_secret: str = "insecure-dev-secret-change-me"
    jwt_access_ttl_min: int = 30

    # --- MQTT ---
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    # --- AI Models ---
    # llama.cpp server (vision — Gemma 3, Qwen3-VL)
    llama_server_url: str = "http://127.0.0.1:8081/v1"
    llama_server_api_key: str = "not-needed"
    vision_model_name: str = "gemma-3-4b"

    # Ollama (text reasoning — Qwen2.5 for both decision agent and chat)
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_api_key: str = "ollama"

# Single shared instance. Import this everywhere.
settings = Settings()