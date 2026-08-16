from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Oracle Database
    oracle_dsn: str = "localhost:1525/FREEPDB1"
    oracle_user: str = "f1app"
    oracle_password: str = "f1app"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:35b-a3b"

    # AI pipeline
    agentic_chat: bool = Field(
        default=True,
        description="Use the tool-calling agentic pipeline first (falls back to classic RAG)",
    )

    # External APIs
    openf1_base_url: str = "https://api.openf1.org/v1"
    ergast_base_url: str = "https://ergast.com/api/f1"

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
